# tests/test_documents.py
import requests
import pytest
import os
import tempfile

BASE_URL = "http://127.0.0.1:8000"


# ==================== HELPER ====================

def create_temp_txt_file(content="Test document content for document tests."):
    """Create a temporary .txt file for testing"""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


def upload_test_file(auth_headers, session_id, filename="testdoc.txt",
                     content="Sample content for document testing."):
    """Helper to upload a test file and return response"""
    tmp_path = create_temp_txt_file(content)
    try:
        with open(tmp_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload",
                headers=auth_headers,
                files={"file": (filename, f, "application/octet-stream")},
                data={"session_id": session_id}
            )
        return res
    finally:
        os.unlink(tmp_path)


# ==================== GET ALL DOCUMENTS TESTS ====================

def test_get_all_documents(auth_headers):
    """Test getting all documents for a user"""
    res = requests.get(
        f"{BASE_URL}/documents",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "documents" in data
    assert isinstance(data["documents"], list)


def test_get_all_documents_without_token():
    """Test getting documents without token — should return 401"""
    res = requests.get(f"{BASE_URL}/documents")
    assert res.status_code == 401


def test_get_all_documents_returns_list(auth_headers):
    """Test that documents endpoint always returns a list"""
    res = requests.get(
        f"{BASE_URL}/documents",
        headers=auth_headers
    )
    assert res.status_code == 200
    documents = res.json()["documents"]
    assert isinstance(documents, list)


# ==================== GET SESSION DOCUMENTS TESTS ====================

def test_get_session_documents(auth_headers, test_session_id):
    """Test getting documents for a specific session"""
    res = requests.get(
        f"{BASE_URL}/documents/{test_session_id}",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "documents" in data
    assert isinstance(data["documents"], list)


def test_get_session_documents_without_token(test_session_id):
    """Test getting session documents without token — should return 401"""
    res = requests.get(
        f"{BASE_URL}/documents/{test_session_id}"
    )
    assert res.status_code == 401


def test_get_session_documents_unauthorized(auth_headers):
    """Test getting documents for session that doesn't belong to user"""
    res = requests.get(
        f"{BASE_URL}/documents/999999",
        headers=auth_headers
    )
    assert res.status_code == 403


def test_get_session_documents_returns_list(auth_headers, test_session_id):
    """Test that session documents endpoint always returns a list"""
    res = requests.get(
        f"{BASE_URL}/documents/{test_session_id}",
        headers=auth_headers
    )
    assert res.status_code == 200
    documents = res.json()["documents"]
    assert isinstance(documents, list)


# ==================== DOCUMENT UPLOAD AND VERIFY TESTS ====================

def test_uploaded_document_appears_in_session(auth_headers):
    """Test that uploaded document appears in session documents"""
    # ✅ Step 1 — Create a fresh session
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Step 2 — Upload a document
    unique_filename = "unique_test_doc_12345.txt"
    upload_res = upload_test_file(
        auth_headers,
        session_id,
        filename=unique_filename,
        content="This is a unique test document for verification."
    )
    assert upload_res.status_code == 200

    # ✅ Step 3 — Check document appears in session
    res = requests.get(
        f"{BASE_URL}/documents/{session_id}",
        headers=auth_headers
    )
    documents = res.json()["documents"]
    assert unique_filename in documents


def test_uploaded_document_appears_in_all_documents(auth_headers):
    """Test that uploaded document appears in all documents list"""
    # ✅ Step 1 — Create a fresh session
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Step 2 — Upload a document
    unique_filename = "all_docs_test_99999.txt"
    upload_res = upload_test_file(
        auth_headers,
        session_id,
        filename=unique_filename,
        content="This document should appear in all documents list."
    )
    assert upload_res.status_code == 200

    # ✅ Step 3 — Check document appears in all documents
    res = requests.get(
        f"{BASE_URL}/documents",
        headers=auth_headers
    )
    documents = res.json()["documents"]
    assert unique_filename in documents


def test_multiple_documents_in_session(auth_headers):
    """Test uploading multiple documents to same session"""
    # ✅ Create a fresh session
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Upload 3 documents
    filenames = [
        "multi_doc_1.txt",
        "multi_doc_2.txt",
        "multi_doc_3.txt"
    ]
    for filename in filenames:
        upload_res = upload_test_file(
            auth_headers,
            session_id,
            filename=filename,
            content=f"Content of {filename} for multi document test."
        )
        assert upload_res.status_code == 200

    # ✅ Check all 3 documents appear in session
    res = requests.get(
        f"{BASE_URL}/documents/{session_id}",
        headers=auth_headers
    )
    documents = res.json()["documents"]
    for filename in filenames:
        assert filename in documents


def test_documents_isolated_between_sessions(auth_headers):
    """Test that documents from one session don't appear in another"""
    # ✅ Create session 1 and upload a doc
    res1 = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id_1 = res1.json()["session_id"]

    unique_filename = "isolated_doc_session1.txt"
    upload_test_file(
        auth_headers,
        session_id_1,
        filename=unique_filename,
        content="This doc belongs only to session 1."
    )

    # ✅ Create session 2 — should NOT have session 1's doc
    res2 = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id_2 = res2.json()["session_id"]

    res = requests.get(
        f"{BASE_URL}/documents/{session_id_2}",
        headers=auth_headers
    )
    documents = res.json()["documents"]
    assert unique_filename not in documents


def test_document_filter_in_chat(auth_headers):
    """Test that selected_doc filter works in chat"""
    # ✅ Create session
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Upload document
    filename = "filter_test_doc.txt"
    upload_test_file(
        auth_headers,
        session_id,
        filename=filename,
        content="The population of Tokyo is approximately 14 million people."
    )

    # ✅ Chat with selected_doc filter
    chat_res = requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "message": "What is the population of Tokyo?",
            "selected_doc": filename
        }
    )
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert "response" in data
    assert len(data["response"]) > 0


def test_no_documents_for_new_session(auth_headers):
    """Test that a brand new session has no documents"""
    # ✅ Create fresh session
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Check documents — should be empty
    res = requests.get(
        f"{BASE_URL}/documents/{session_id}",
        headers=auth_headers
    )
    assert res.status_code == 200
    documents = res.json()["documents"]
    assert isinstance(documents, list)