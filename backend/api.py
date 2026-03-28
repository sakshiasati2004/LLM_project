import os
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel

from backend.db import (
    register_user,
    login_user,
    create_chat_session,
    get_chat_history,
    get_user_sessions,
    rename_session,
    delete_session,
    create_tables,
    verify_session_ownership   # ✅ added
)

from backend.auth import create_access_token, get_current_user
from backend.chat import chat, set_vectorstore

from backend.rag import (
    load_and_split,
    add_metadata,
    create_or_load_vectorstore,
    load_existing_vectorstore,
    get_all_documents
)

# ==================== INIT ====================

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


# ==================== ROOT ====================

@app.get("/")
def home():
    return {"message": "FastAPI running 🚀"}


# ==================== AUTH ====================

@app.post("/register")
def register(request: AuthRequest):
    try:
        success = register_user(request.username, request.password)

        if success:
            return {"message": "User registered ✅"}

        raise HTTPException(status_code=400, detail="User already exists ❌")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/login")
def login(request: AuthRequest):
    try:
        user = login_user(request.username, request.password)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials ❌")

        token = create_access_token({"user_id": request.username})

        return {
            "access_token": token,
            "token_type": "bearer"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CHAT SESSION ====================

@app.post("/create_chat")
def create_chat(user_id: str = Depends(get_current_user)):
    try:
        session_id = create_chat_session(user_id)
        return {"session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
def get_sessions(user_id: str = Depends(get_current_user)):
    try:
        sessions = get_user_sessions(user_id)
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/rename_session")
def rename_chat(req: RenameRequest, user_id: str = Depends(get_current_user)):
    try:
        if not verify_session_ownership(req.session_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized ❌")

        rename_session(req.session_id, req.title)
        return {"message": "Renamed ✅"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete_session/{session_id}")
def delete_chat(session_id: int, user_id: str = Depends(get_current_user)):
    try:
        if not verify_session_ownership(session_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized ❌")

        delete_session(session_id)
        return {"message": "Deleted ✅"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CHAT ====================

@app.post("/chat")
def chat_api(req: ChatRequest, user_id: str = Depends(get_current_user)):
    try:
        if not verify_session_ownership(req.session_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized ❌")

        vectorstore = load_existing_vectorstore(user_id)

        if vectorstore:
            set_vectorstore(vectorstore)

        response = chat(
            user_id,
            req.session_id,
            req.message,
            selected_doc=req.selected_doc
        )

        return {"response": response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HISTORY ====================

@app.get("/history/{session_id}")
def get_history(session_id: int, user_id: str = Depends(get_current_user)):
    try:
        if not verify_session_ownership(session_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized ❌")

        history = get_chat_history(user_id, session_id)
        return {"messages": history}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DOCUMENTS ====================

@app.get("/documents")
def get_documents(user_id: str = Depends(get_current_user)):
    try:
        vectorstore = load_existing_vectorstore(user_id)

        if not vectorstore:
            return {"documents": []}

        docs = get_all_documents(vectorstore, user_id)

        return {"documents": docs}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FILE UPLOAD ====================

@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    session_id: int = 1,
    user_id: str = Depends(get_current_user)
):
    try:
        if not verify_session_ownership(session_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized ❌")

        # ✅ Safe filename
        filename = f"{user_id}_{uuid.uuid4()}_{file.filename}"
        file_path = filename

        # ✅ Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ✅ Process document
        chunks = load_and_split(file_path)

        chunks = add_metadata(
            chunks,
            user_id,
            session_id,
            file.filename
        )

        vectorstore = create_or_load_vectorstore(chunks, user_id)

        set_vectorstore(vectorstore)

        return {"message": "File uploaded & processed ✅"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))