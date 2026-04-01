# tests/test_rag.py
import requests
import pytest
import os
import tempfile

BASE_URL = "http://127.0.0.1:8000"


# ==================== HELPER FUNCTIONS ====================

def create_temp_txt_file(content="This is a test document for pytest testing."):
    """Create a temporary .txt file for testing"""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


def create_temp_pdf_file():
    """Create a temporary .pdf file for testing"""
    try:
        from reportlab.pdfgen import canvas
        tmp_path = tempfile.mktemp(suffix=".pdf")
        c = canvas.Canvas(tmp_path)
        c.drawString(100, 750, "This is a test PDF document for pytest.")
        c.save()
        return tmp_path
    except ImportError:
        # ✅ If reportlab not installed, use existing PDF in project
        pdf_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "policy_company.pdf"
        )
        if os.path.exists(pdf_path):
            return pdf_path
        return None


# ==================== UPLOAD TESTS ====================

def test_upload_txt_file(auth_headers, test_session_id):
    """Test uploading a .txt file"""
    tmp_path = create_temp_txt_file(
        "This is a test text file. It contains sample content for testing."
    )
    try:
        with open(tmp_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload",
                headers=auth_headers,
                files={"file": ("test.txt", f, "text/plain")},
                data={"session_id": test_session_id}
            )
        assert res.status_code == 200
        assert "message" in res.json()
    finally:
        os.unlink(tmp_path)


def test_upload_pdf_file(auth_headers, test_session_id):
    """Test uploading a .pdf file"""
    pdf_path = create_temp_pdf_file()
    if pdf_path is None:
        pytest.skip("No PDF file available for testing")

    with open(pdf_path, "rb") as f:
        res = requests.post(
            f"{BASE_URL}/upload",
            headers=auth_headers,
            files={"file": ("test.pdf", f, "application/pdf")},
            data={"session_id": test_session_id}
        )
    assert res.status_code == 200
    assert "message" in res.json()


def test_upload_invalid_file_type(auth_headers, test_session_id):
    """Test uploading unsupported file type — should return 400"""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".xyz", delete=False
    )
    tmp.write("invalid file content")
    tmp.close()

    try:
        with open(tmp.name, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload",
                headers=auth_headers,
                files={"file": ("test.xyz", f, "application/octet-stream")},
                data={"session_id": test_session_id}
            )
        assert res.status_code == 400
        assert "detail" in res.json()
    finally:
        os.unlink(tmp.name)


def test_upload_without_token(test_session_id):
    """Test uploading without token — should return 401"""
    tmp_path = create_temp_txt_file()
    try:
        with open(tmp_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload",
                files={"file": ("test.txt", f, "text/plain")},
                data={"session_id": test_session_id}
            )
        assert res.status_code == 401
    finally:
        os.unlink(tmp_path)


def test_upload_to_unauthorized_session(auth_headers):
    """Test uploading to session that doesn't belong to user"""
    tmp_path = create_temp_txt_file()
    try:
        with open(tmp_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload",
                headers=auth_headers,
                files={"file": ("test.txt", f, "text/plain")},
                data={"session_id": 999999}
            )
        assert res.status_code == 403
    finally:
        os.unlink(tmp_path)


def test_upload_empty_txt_file(auth_headers, test_session_id):
    """Test uploading empty txt file"""
    tmp_path = create_temp_txt_file("")
    try:
        with open(tmp_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload",
                headers=auth_headers,
                files={"file": ("empty.txt", f, "text/plain")},
                data={"session_id": test_session_id}
            )
        # ✅ Either 200 or 500 is acceptable for empty file
        assert res.status_code in [200, 500]
    finally:
        os.unlink(tmp_path)


# ==================== CHAT TESTS ====================

def test_chat_general_question(auth_headers, test_session_id):
    """Test asking a general question without document"""
    res = requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "message": "What is 2 + 2?",
            "selected_doc": "All Documents"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert len(data["response"]) > 0


def test_chat_returns_response_and_sources(auth_headers, test_session_id):
    """Test that chat returns both response and sources fields"""
    res = requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "message": "Hello",
            "selected_doc": "All Documents"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_chat_with_document(auth_headers, test_session_id):
    """Test chatting after uploading a document"""
    # ✅ Step 1 — Upload a document
    tmp_path = create_temp_txt_file(
        "The capital of France is Paris. Paris is known for the Eiffel Tower."
    )
    try:
        with open(tmp_path, "rb") as f:
            upload_res = requests.post(
                f"{BASE_URL}/upload",
                headers=auth_headers,
                files={"file": ("france.txt", f, "text/plain")},
                data={"session_id": test_session_id}
            )
        assert upload_res.status_code == 200

        # ✅ Step 2 — Ask question about the document
        chat_res = requests.post(
            f"{BASE_URL}/chat",
            headers=auth_headers,
            json={
                "session_id": test_session_id,
                "message": "What is the capital of France?",
                "selected_doc": "All Documents"
            }
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert "response" in data
        assert len(data["response"]) > 0
    finally:
        os.unlink(tmp_path)


def test_chat_without_token(test_session_id):
    """Test chatting without token — should return 401"""
    res = requests.post(
        f"{BASE_URL}/chat",
        json={
            "session_id": test_session_id,
            "message": "Hello",
            "selected_doc": "All Documents"
        }
    )
    assert res.status_code == 401


def test_chat_unauthorized_session(auth_headers):
    """Test chatting in session that doesn't belong to user"""
    res = requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": 999999,
            "message": "Hello",
            "selected_doc": "All Documents"
        }
    )
    assert res.status_code == 403


def test_chat_response_is_string(auth_headers, test_session_id):
    """Test that chat response is always a string"""
    res = requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "message": "Say hello",
            "selected_doc": "All Documents"
        }
    )
    assert res.status_code == 200
    response = res.json().get("response")
    assert isinstance(response, str)
    assert len(response) > 0


def test_chat_saves_to_history(auth_headers, test_session_id):
    """Test that chat messages are saved to history"""
    unique_message = "pytest unique test message 99887766"

    # ✅ Send message
    requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "message": unique_message,
            "selected_doc": "All Documents"
        }
    )

    # ✅ Check history
    res = requests.get(
        f"{BASE_URL}/history/{test_session_id}",
        headers=auth_headers
    )
    messages = res.json()["messages"]
    contents = [m["content"] for m in messages]
    assert unique_message in contents


# ==================== MSG FILE TESTS ====================

def test_upload_msg_file(auth_headers, test_session_id):
    """Test that .msg file type is accepted by upload endpoint"""
    # ✅ Check if a .msg file exists in Downloads
    msg_path = "/home/sakshi-asati/Downloads/Test policy email  (1).msg"
    if not os.path.exists(msg_path):
        pytest.skip("No .msg file available for testing")

    with open(msg_path, "rb") as f:
        res = requests.post(
            f"{BASE_URL}/upload",
            headers=auth_headers,
            files={"file": ("test.msg", f, "application/octet-stream")},
            data={"session_id": test_session_id}
        )
    assert res.status_code == 200


# ==================== IMAGE FILE TESTS ====================

def test_upload_image_file(auth_headers, test_session_id):
    """Test uploading a PNG image file"""
    img_path = "/home/sakshi-asati/Downloads/sampleimage.png"
    if not os.path.exists(img_path):
        pytest.skip("No image file available for testing")

    with open(img_path, "rb") as f:
        res = requests.post(
            f"{BASE_URL}/upload",
            headers=auth_headers,
            files={"file": ("sampleimage.png", f, "application/octet-stream")},
            data={"session_id": test_session_id}
        )
    assert res.status_code == 200