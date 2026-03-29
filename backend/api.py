import os
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from fastapi.responses import FileResponse

from backend.nl2sql import (
    load_file, load_postgres,
    generate_sql, execute_sql,
    get_table_info
)

from backend.db import (
    register_user, login_user,
    create_chat_session, get_chat_history,
    get_user_sessions, rename_session,
    delete_session, create_tables,
    verify_session_ownership
)

from backend.auth import create_access_token, get_current_user
from backend.chat import chat

from backend.rag import (
    load_and_split, add_metadata,
    create_or_load_vectorstore,
    load_existing_vectorstore,
    get_all_documents,
    get_session_documents
)

UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()
create_tables()


# ==================== MODELS ====================

class AuthRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    session_id: int
    message: str
    selected_doc: Optional[str] = "All Documents"

class RenameRequest(BaseModel):
    session_id: int
    title: str

class SQLQueryRequest(BaseModel):
    message: str

class PostgresRequest(BaseModel):
    connection_string: str


# ==================== ROOT ====================

@app.get("/")
def home():
    return {"message": "FastAPI running 🚀"}


# ==================== AUTH ====================

@app.post("/register")
def register(request: AuthRequest):
    success = register_user(request.username, request.password)
    if success:
        return {"message": "Registered successfully ✅"}
    raise HTTPException(status_code=400, detail="Username already exists ❌")


@app.post("/login")
def login(request: AuthRequest):
    result = login_user(request.username, request.password)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="User does not exist ❌")
    if result == "wrong_password":
        raise HTTPException(status_code=401, detail="Incorrect password ❌")
    token = create_access_token({"user_id": request.username})
    return {"access_token": token, "token_type": "bearer"}


# ==================== SESSIONS ====================

@app.post("/create_chat")
def create_chat_session_api(user_id: str = Depends(get_current_user)):
    session_id = create_chat_session(user_id)
    return {"session_id": session_id}


@app.get("/sessions")
def get_sessions(user_id: str = Depends(get_current_user)):
    return {"sessions": get_user_sessions(user_id)}


@app.put("/rename_session")
def rename_chat(req: RenameRequest, user_id: str = Depends(get_current_user)):
    if not verify_session_ownership(req.session_id, user_id):
        raise HTTPException(status_code=403, detail="Unauthorized ❌")
    rename_session(req.session_id, req.title, user_id)
    return {"message": "Renamed ✅"}


@app.delete("/delete_session/{session_id}")
def delete_chat(session_id: int, user_id: str = Depends(get_current_user)):
    if not verify_session_ownership(session_id, user_id):
        raise HTTPException(status_code=403, detail="Unauthorized ❌")
    delete_session(session_id)
    return {"message": "Deleted ✅"}


# ==================== CHAT ====================

@app.post("/chat")
def chat_api(req: ChatRequest, user_id: str = Depends(get_current_user)):
    if not verify_session_ownership(req.session_id, user_id):
        raise HTTPException(status_code=403, detail="Unauthorized ❌")

    vectorstore = load_existing_vectorstore(user_id)
    response, sources = chat(
        user_id, req.session_id,
        req.message, vectorstore,
        selected_doc=req.selected_doc
    )
    return {"response": response, "sources": sources}


# ==================== HISTORY ====================

@app.get("/history/{session_id}")
def get_history(session_id: int, user_id: str = Depends(get_current_user)):
    if not verify_session_ownership(session_id, user_id):
        raise HTTPException(status_code=403, detail="Unauthorized ❌")
    return {"messages": get_chat_history(user_id, session_id)}


# ==================== DOCUMENTS ====================

@app.get("/documents")
def get_documents(user_id: str = Depends(get_current_user)):
    vectorstore = load_existing_vectorstore(user_id)
    if not vectorstore:
        return {"documents": []}
    return {"documents": get_all_documents(vectorstore, user_id)}


@app.get("/documents/{session_id}")
def get_session_docs(session_id: int, user_id: str = Depends(get_current_user)):
    if not verify_session_ownership(session_id, user_id):
        raise HTTPException(status_code=403, detail="Unauthorized ❌")
    vectorstore = load_existing_vectorstore(user_id)
    if not vectorstore:
        return {"documents": []}
    return {"documents": get_session_documents(vectorstore, user_id, session_id)}


# ==================== RAG UPLOAD ====================

@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    session_id: int = Form(...),
    user_id: str = Depends(get_current_user)
):
    if not verify_session_ownership(session_id, user_id):
        raise HTTPException(status_code=403, detail="Unauthorized ❌")

    # ✅ ADDED: explicit file type validation with clear error message
    allowed_extensions = {"pdf", "txt", "doc", "docx", "msg", "chm"}
    file_ext = file.filename.rsplit(".", 1)[-1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{file_ext}. Allowed: pdf, txt, doc, docx, msg, chm"
        )

    filename = f"{user_id}_{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        chunks = load_and_split(file_path)
        chunks = add_metadata(chunks, user_id, session_id, file.filename)
        create_or_load_vectorstore(chunks, user_id)

        return {"message": f"{file.filename} uploaded & processed ✅"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ==================== NL2SQL ====================

@app.post("/upload_sql")
def upload_sql_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    filename = f"{user_id}_{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        table_name, columns = load_file(file_path, user_id)

        return {
            "message": "File uploaded ✅",
            "table_name": table_name,
            "columns": columns
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.post("/connect_postgres")
def connect_postgres(
    req: PostgresRequest,
    user_id: str = Depends(get_current_user)
):
    """Connect to PostgreSQL database"""
    try:
        table_name, columns = load_postgres(req.connection_string, user_id)
        return {
            "message": "PostgreSQL connected ✅",
            "table_name": table_name,
            "columns": columns
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/table_info")
def table_info(user_id: str = Depends(get_current_user)):
    """Get current table info"""
    info = get_table_info(user_id)
    if not info:
        return {"loaded": False}
    return {"loaded": True, **info}


@app.post("/query_sql")
def query_sql(
    req: SQLQueryRequest,
    user_id: str = Depends(get_current_user)
):
    try:
        sql_query = generate_sql(user_id, req.message)
        result = execute_sql(user_id, sql_query)
        return {"sql_query": sql_query, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download_sql")
def download_sql(
    file_path: str,
    user_id: str = Depends(get_current_user)
):
    if user_id not in file_path:
        raise HTTPException(status_code=403, detail="Unauthorized ❌")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found ❌")
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream"
    )