import os
from dotenv import load_dotenv
from langchain_community.document_loaders import (
    PyPDFLoader, TextLoader, CSVLoader, UnstructuredWordDocumentLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

load_dotenv()

FAISS_BASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "faiss_indexes"
)
os.makedirs(FAISS_BASE_DIR, exist_ok=True)


def load_document(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    loaders = {
        ".pdf": PyPDFLoader,
        ".txt": TextLoader,
        ".csv": CSVLoader,
        ".doc": UnstructuredWordDocumentLoader,
        ".docx": UnstructuredWordDocumentLoader,
    }
    if ext not in loaders:
        raise ValueError(f"Unsupported file type: {ext}")
    return loaders[ext](file_path).load()


def load_and_split(file_path):
    documents = load_document(file_path)
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
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
    return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)


def get_context_from_query(vectorstore, query, user_id, session_id, selected_doc="All Documents"):
    docs = vectorstore.similarity_search(query, k=10)

    # ✅ Filter by selected doc first
    if selected_doc != "All Documents":
        docs = [d for d in docs if d.metadata.get("file_name") == selected_doc]

    # ✅ STRICT: Only use docs from THIS session — no cross-session bleed
    session_docs = [
        d for d in docs
        if str(d.metadata.get("session_id")) == str(session_id)
        and str(d.metadata.get("user_id")) == str(user_id)
    ]

    if session_docs:
        context = "\n\n".join([d.page_content for d in session_docs[:3]])
        file_names = list(set([d.metadata.get("file_name", "Unknown") for d in session_docs]))
        return context, "current", file_names

    # ✅ No cross-session fallback — new chat = clean slate
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
    """✅ Get documents uploaded in a specific session"""
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