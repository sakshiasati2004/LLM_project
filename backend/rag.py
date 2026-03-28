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

load_dotenv()


# -------------------- LOAD DOCUMENT --------------------
def load_document(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        loader = PyPDFLoader(file_path)

    elif ext == ".txt":
        loader = TextLoader(file_path)

    elif ext == ".csv":
        loader = CSVLoader(file_path)

    elif ext in [".doc", ".docx"]:
        loader = UnstructuredWordDocumentLoader(file_path)

    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return loader.load()


# -------------------- SPLIT --------------------
def load_and_split(file_path):
    documents = load_document(file_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    return splitter.split_documents(documents)


# -------------------- ADD METADATA --------------------
def add_metadata(chunks, user_id, session_id, file_name):
    for chunk in chunks:
        # ✅ FIX: do not overwrite existing metadata
        chunk.metadata.update({
            "user_id": user_id,
            "session_id": session_id,
            "file_name": file_name
        })
    return chunks


# -------------------- EMBEDDINGS --------------------
def get_embeddings():
    return OpenAIEmbeddings(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )


# -------------------- PATH PER USER --------------------
def get_user_vectorstore_path(user_id):
    return f"faiss_index_{user_id}"


# -------------------- CREATE / LOAD VECTOR STORE --------------------
def create_or_load_vectorstore(chunks, user_id):
    path = get_user_vectorstore_path(user_id)
    embeddings = get_embeddings()

    # Load existing and append
    if os.path.exists(path):
        vectorstore = FAISS.load_local(
            path,
            embeddings,
            allow_dangerous_deserialization=True  # ⚠️ keep only for trusted env
        )
        vectorstore.add_documents(chunks)
    else:
        vectorstore = FAISS.from_documents(chunks, embeddings)

    vectorstore.save_local(path)

    return vectorstore


# -------------------- LOAD EXISTING --------------------
def load_existing_vectorstore(user_id):
    path = get_user_vectorstore_path(user_id)

    if not os.path.exists(path):
        return None

    embeddings = get_embeddings()

    return FAISS.load_local(
        path,
        embeddings,
        allow_dangerous_deserialization=True
    )


# -------------------- SMART RETRIEVAL --------------------
def get_context_from_query(vectorstore, query, user_id, session_id, selected_doc="All Documents"):

    docs = vectorstore.similarity_search(query, k=5)

    # ✅ FILTER: selected document
    if selected_doc != "All Documents":
        docs = [
            doc for doc in docs
            if doc.metadata.get("file_name") == selected_doc
        ]

    # ---------------- CURRENT SESSION ----------------
    current_docs = [
        doc for doc in docs
        if doc.metadata.get("session_id") == session_id
    ]

    if current_docs:
        context = "\n\n".join([
            doc.page_content for doc in current_docs[:3]
        ])

        file_names = list(set([
            doc.metadata.get("file_name", "Unknown")
            for doc in current_docs
        ]))

        return context, "current", file_names

    # ---------------- PREVIOUS USER DOCS ----------------
    user_docs = [
        doc for doc in docs
        if doc.metadata.get("user_id") == user_id
    ]

    if user_docs:
        context = "\n\n".join([
            doc.page_content for doc in user_docs[:3]
        ])

        file_names = list(set([
            doc.metadata.get("file_name", "Unknown")
            for doc in user_docs
        ]))

        return context, "previous", file_names

    return "", "none", []


# -------------------- GET ALL DOCUMENTS --------------------
def get_all_documents(vectorstore, user_id):
    if not vectorstore:
        return []

    docs = vectorstore.docstore._dict.values()

    file_names = list(set([
        doc.metadata.get("file_name", "Unknown")
        for doc in docs
        if doc.metadata.get("user_id") == user_id
    ]))

    return file_names


# -------------------- TEST --------------------
if __name__ == "__main__":
    file_path = "/home/sakshi-asati/Desktop/python/LLM_major_project/policy_company.pdf"

    user_id = "test_user"
    session_id = 1

    try:
        # Step 1: Load & split
        chunks = load_and_split(file_path)

        # Step 2: Add metadata
        chunks = add_metadata(chunks, user_id, session_id, "policy_company.pdf")

        print(f"\nTotal chunks created: {len(chunks)}\n")

        # Step 3: Create vector store
        vectorstore = create_or_load_vectorstore(chunks, user_id)
        print("Vector store saved/updated ✅\n")

        # Step 4: Query
        query = "leave policy"
        context, source, files = get_context_from_query(
            vectorstore,
            query,
            user_id,
            session_id
        )

        print(f"Query: {query}")
        print(f"Source Type: {source}")
        print(f"Files: {files}\n")
        print("Context:\n")
        print(context)

    except Exception as e:
        print("Error:", str(e))