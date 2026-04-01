# tests/test_nl2sql.py
import requests
import pytest
import os
import tempfile
import pandas as pd

BASE_URL = "http://127.0.0.1:8000"


# ==================== HELPER FUNCTIONS ====================

def create_temp_csv_file():
    """Create a temporary CSV file for testing"""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    )
    tmp.write("name,age,salary,gender\n")
    tmp.write("Alice,30,50000,female\n")
    tmp.write("Bob,25,45000,male\n")
    tmp.write("Charlie,35,60000,male\n")
    tmp.write("Diana,28,55000,female\n")
    tmp.write("Eve,32,70000,female\n")
    tmp.close()
    return tmp.name


def create_temp_excel_file():
    """Create a temporary Excel file for testing"""
    tmp_path = tempfile.mktemp(suffix=".xlsx")
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Diana"],
        "age": [30, 25, 35, 28],
        "salary": [50000, 45000, 60000, 55000],
        "gender": ["female", "male", "male", "female"]
    })
    df.to_excel(tmp_path, index=False)
    return tmp_path


def upload_csv(auth_headers, csv_path=None):
    """Helper to upload CSV and return response"""
    if csv_path is None:
        csv_path = create_temp_csv_file()
        cleanup = True
    else:
        cleanup = False

    try:
        with open(csv_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload_sql",
                headers=auth_headers,
                files={"file": ("test_data.csv", f, "text/csv")}
            )
        return res
    finally:
        if cleanup and os.path.exists(csv_path):
            os.unlink(csv_path)


# ==================== UPLOAD SQL FILE TESTS ====================

def test_upload_csv_file(auth_headers):
    """Test uploading a CSV file"""
    res = upload_csv(auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "table_name" in data
    assert "columns" in data
    assert isinstance(data["columns"], list)
    assert len(data["columns"]) > 0


def test_upload_csv_returns_correct_columns(auth_headers):
    """Test that uploaded CSV returns correct column names"""
    csv_path = create_temp_csv_file()
    try:
        with open(csv_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload_sql",
                headers=auth_headers,
                files={"file": ("test_data.csv", f, "text/csv")}
            )
        assert res.status_code == 200
        columns = res.json()["columns"]
        assert "name" in columns
        assert "age" in columns
        assert "salary" in columns
        assert "gender" in columns
    finally:
        os.unlink(csv_path)


def test_upload_excel_file(auth_headers):
    """Test uploading an Excel file"""
    excel_path = create_temp_excel_file()
    try:
        with open(excel_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload_sql",
                headers=auth_headers,
                files={"file": ("test_data.xlsx", f, "application/octet-stream")}
            )
        assert res.status_code == 200
        data = res.json()
        assert "table_name" in data
        assert "columns" in data
    finally:
        os.unlink(excel_path)


def test_upload_sql_without_token():
    """Test uploading SQL file without token — should return 401"""
    csv_path = create_temp_csv_file()
    try:
        with open(csv_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload_sql",
                files={"file": ("test_data.csv", f, "text/csv")}
            )
        assert res.status_code == 401
    finally:
        os.unlink(csv_path)


def test_upload_sql_returns_table_name(auth_headers):
    """Test that uploaded file returns a valid table name"""
    csv_path = create_temp_csv_file()
    try:
        with open(csv_path, "rb") as f:
            res = requests.post(
                f"{BASE_URL}/upload_sql",
                headers=auth_headers,
                files={"file": ("my_table.csv", f, "text/csv")}
            )
        assert res.status_code == 200
        table_name = res.json()["table_name"]
        assert isinstance(table_name, str)
        assert len(table_name) > 0
    finally:
        os.unlink(csv_path)


# ==================== TABLE INFO TESTS ====================

def test_get_table_info(auth_headers):
    """Test getting table info after upload"""
    # ✅ Upload first
    upload_csv(auth_headers)

    # ✅ Get table info
    res = requests.get(
        f"{BASE_URL}/table_info",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "loaded" in data
    assert data["loaded"] is True
    assert "table_name" in data
    assert "columns" in data


def test_get_table_info_without_token():
    """Test getting table info without token — should return 401"""
    res = requests.get(f"{BASE_URL}/table_info")
    assert res.status_code == 401


def test_get_table_info_has_row_count(auth_headers):
    """Test that table info includes row count"""
    upload_csv(auth_headers)

    res = requests.get(
        f"{BASE_URL}/table_info",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    if data["loaded"]:
        assert "row_count" in data
        assert isinstance(data["row_count"], int)
        assert data["row_count"] > 0


# ==================== SQL QUERY TESTS ====================

def test_query_sql_select_all(auth_headers):
    """Test basic SELECT all query"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show all rows"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "sql_query" in data
    assert "type" in data
    assert data["type"] == "select"
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


def test_query_sql_with_filter(auth_headers):
    """Test SELECT query with WHERE filter"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show rows where gender is female"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "select"
    # ✅ All returned rows should be female
    for row in data["data"]:
        assert row["gender"] == "female"


def test_query_sql_count(auth_headers):
    """Test COUNT query"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "count total number of rows"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "sql_query" in data
    assert "SELECT" in data["sql_query"].upper()


def test_query_sql_returns_sql_query(auth_headers):
    """Test that query response includes the generated SQL"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show top 3 rows"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "sql_query" in data
    sql = data["sql_query"]
    assert isinstance(sql, str)
    assert len(sql) > 0
    assert "SELECT" in sql.upper()


def test_query_sql_returns_summary(auth_headers):
    """Test that query response includes a summary"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show all rows"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert isinstance(data["summary"], str)


def test_query_sql_without_token():
    """Test querying without token — should return 401"""
    res = requests.post(
        f"{BASE_URL}/query_sql",
        json={"message": "show all rows"}
    )
    assert res.status_code == 401


def test_query_sql_without_uploading_file(auth_headers):
    """Test querying without uploading file first"""
    # ✅ Create a new user that hasn't uploaded anything
    import random
    new_user = f"fresh_user_{random.randint(10000, 99999)}"
    requests.post(f"{BASE_URL}/register", json={
        "username": new_user,
        "password": "testpass123"
    })
    login_res = requests.post(f"{BASE_URL}/login", json={
        "username": new_user,
        "password": "testpass123"
    })
    new_token = login_res.json()["access_token"]
    new_headers = {"Authorization": f"Bearer {new_token}"}

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=new_headers,
        json={"message": "show all rows"}
    )
    assert res.status_code == 500
    assert "detail" in res.json()


def test_query_sql_max_rows(auth_headers):
    """Test limiting rows in query"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show top 2 rows"}
    )
    assert res.status_code == 200
    data = res.json()
    if data["type"] == "select":
        assert data["row_count"] <= 2


def test_query_sql_aggregation(auth_headers):
    """Test SUM aggregation query"""
    upload_csv(auth_headers)

    res = requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show sum of salary"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "sql_query" in data
    assert "SUM" in data["sql_query"].upper()


# ==================== NL2SQL HISTORY TESTS ====================

def test_get_sql_history(auth_headers):
    """Test getting NL2SQL query history"""
    # ✅ First do a query to ensure history exists
    upload_csv(auth_headers)
    requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show all rows"}
    )

    # ✅ Get history
    res = requests.get(
        f"{BASE_URL}/history_sql",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "history" in data
    assert isinstance(data["history"], list)


def test_sql_history_has_correct_format(auth_headers):
    """Test that SQL history entries have correct format"""
    upload_csv(auth_headers)
    requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": "show all rows"}
    )

    res = requests.get(
        f"{BASE_URL}/history_sql",
        headers=auth_headers
    )
    history = res.json()["history"]

    if history:
        entry = history[0]
        assert "question" in entry
        assert "sql_query" in entry
        assert "summary" in entry
        assert "result_type" in entry
        assert "row_count" in entry
        assert "timestamp" in entry


def test_sql_history_saves_query(auth_headers):
    """Test that executed query is saved in history"""
    upload_csv(auth_headers)

    unique_message = "show rows where age is greater than 20"
    requests.post(
        f"{BASE_URL}/query_sql",
        headers=auth_headers,
        json={"message": unique_message}
    )

    res = requests.get(
        f"{BASE_URL}/history_sql",
        headers=auth_headers
    )
    history = res.json()["history"]
    questions = [h["question"] for h in history]
    assert unique_message in questions


def test_get_sql_history_without_token():
    """Test getting SQL history without token — should return 401"""
    res = requests.get(f"{BASE_URL}/history_sql")
    assert res.status_code == 401