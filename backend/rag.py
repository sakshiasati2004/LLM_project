import os
from dotenv import load_dotenv
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    CSVLoader,
    UnstructuredWordDocumentLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

load_dotenv()

FAISS_BASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "faiss_indexes"
)
os.makedirs(FAISS_BASE_DIR, exist_ok=True)


# -------------------- DOCUMENT LOADERS --------------------

def load_msg_file(file_path):
    """Load .msg (Outlook email) files"""
    try:
        import extract_msg
        msg = extract_msg.Message(file_path)
        content = f"""
Subject: {msg.subject}
From: {msg.sender}
To: {msg.to}
Date: {msg.date}
Body:
{msg.body}
"""
        return [Document(page_content=content, metadata={"source": file_path})]
    except Exception as e:
        raise ValueError(f"Error loading .msg file: {str(e)}")


def load_chm_file(file_path):
    """Load .chm (Help) files"""
    try:
        import chm.chm as chmlib
        chm_file = chmlib.CHMFile()
        chm_file.LoadCHM(file_path)

        contents = []
        def get_files(chm, ui, ctx):
            path = ui.path.decode("utf-8") if isinstance(ui.path, bytes) else ui.path
            if path.endswith(".html") or path.endswith(".htm"):
                result, content = chm.RetrieveObject(ui)
                if result == 0 and content:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, "html.parser")
                    text = soup.get_text(separator="\n")
                    if text.strip():
                        contents.append(text)

        chm_file.EnumerateFiles(get_files, None)
        chm_file.CloseCHM()

        if not contents:
            raise ValueError("No readable content found in .chm file")

        full_text = "\n\n".join(contents)
        return [Document(page_content=full_text, metadata={"source": file_path})]
    except Exception as e:
        raise ValueError(f"Error loading .chm file: {str(e)}")


def load_document(file_path):
    """Load document based on file extension"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return PyPDFLoader(file_path).load()

    elif ext == ".txt":
        return TextLoader(file_path).load()

    elif ext == ".csv":
        return CSVLoader(file_path).load()

    elif ext in [".doc", ".docx"]:
        return UnstructuredWordDocumentLoader(file_path).load()

    elif ext == ".msg":
        return load_msg_file(file_path)

    elif ext == ".chm":
        return load_chm_file(file_path)

    else:
        raise ValueError(f"Unsupported file type: {ext}")


def load_and_split(file_path):
    documents = load_document(file_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )
    return splitter.split_documents(documents)


def add_metadata(chunks, user_id, session_id, file_name):
    for chunk in chunks:
        chunk.metadata.update({
            "user_id": str(user_id),
            "session_id": str(session_id),
            "file_name": file_name
        })
    return chunks


def get_embeddings():
    return OpenAIEmbeddings(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )


def get_user_vectorstore_path(user_id):
    return os.path.join(FAISS_BASE_DIR, f"faiss_{user_id}")


def create_or_load_vectorstore(chunks, user_id):
    path = get_user_vectorstore_path(user_id)
    embeddings = get_embeddings()
    if os.path.exists(path):
        vectorstore = FAISS.load_local(
            path, embeddings, allow_dangerous_deserialization=True
        )
        vectorstore.add_documents(chunks)
    else:
        vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(path)
    return vectorstore


def load_existing_vectorstore(user_id):
    path = get_user_vectorstore_path(user_id)
    if not os.path.exists(path):
        return None
    embeddings = get_embeddings()
    return FAISS.load_local(
        path, embeddings, allow_dangerous_deserialization=True
    )


def get_context_from_query(vectorstore, query, user_id, session_id, selected_doc="All Documents"):
    docs = vectorstore.similarity_search(query, k=10)

    if selected_doc != "All Documents":
        docs = [d for d in docs if d.metadata.get("file_name") == selected_doc]

    session_docs = [
        d for d in docs
        if str(d.metadata.get("session_id")) == str(session_id)
        and str(d.metadata.get("user_id")) == str(user_id)
    ]

    if session_docs:
        context = "\n\n".join([d.page_content for d in session_docs[:3]])
        file_names = list(set([
            d.metadata.get("file_name", "Unknown") for d in session_docs
        ]))
        return context, "current", file_names

    return "", "none", []


def get_all_documents(vectorstore, user_id):
    if not vectorstore:
        return []
    try:
        docs = vectorstore.docstore._dict.values()
        return list(set([
            doc.metadata.get("file_name", "Unknown")
            for doc in docs
            if str(doc.metadata.get("user_id")) == str(user_id)
        ]))
    except Exception:
        return []


def get_session_documents(vectorstore, user_id, session_id):
    if not vectorstore:
        return []
    try:
        docs = vectorstore.docstore._dict.values()
        return list(set([
            doc.metadata.get("file_name", "Unknown")
            for doc in docs
            if str(doc.metadata.get("user_id")) == str(user_id)
            and str(doc.metadata.get("session_id")) == str(session_id)
        ]))
    except Exception:
        return []