import os
import re
import sqlite3
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

user_data_store = {}

MODIFIED_DIR = "modified_files"
os.makedirs(MODIFIED_DIR, exist_ok=True)


def _clean_table_name(name):
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    name = name.strip('_')
    if name and name[0].isdigit():
        name = f"t_{name}"
    return name or "data_table"


def load_file(file_path, user_id):
    """Load CSV, Excel, SQLite into memory for a user"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(file_path)
        raw_name = os.path.splitext(os.path.basename(file_path))[0]
        table_name = _clean_table_name(raw_name)
        source_type = "csv"
        db_path = _save_to_sqlite(df, table_name, user_id)

    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
        raw_name = os.path.splitext(os.path.basename(file_path))[0]
        table_name = _clean_table_name(raw_name)
        source_type = "excel"
        db_path = _save_to_sqlite(df, table_name, user_id)

    elif ext == ".db":
        db_path = _copy_db(file_path, user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()

        if not tables:
            raise ValueError("No tables found in SQLite database")

        table_name = tables[0][0]
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(f"SELECT * FROM '{table_name}'", conn)
        conn.close()
        source_type = "sqlite"

    else:
        raise ValueError(f"Unsupported file type: {ext}")

    columns = df.columns.tolist()

    user_data_store[user_id] = {
        "df": df,
        "table_name": table_name,
        "columns": columns,
        "source_type": source_type,
        "db_path": db_path
    }

    return table_name, columns


def load_postgres(connection_string, user_id):
    """Load PostgreSQL table"""
    try:
        from sqlalchemy import create_engine, inspect

        engine = create_engine(connection_string)
        conn = engine.connect()

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables:
            raise ValueError("No tables found in PostgreSQL database")

        table_name = tables[0]
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        conn.close()

        columns = df.columns.tolist()
        db_path = _save_to_sqlite(df, table_name, user_id)

        user_data_store[user_id] = {
            "df": df,
            "table_name": table_name,
            "columns": columns,
            "source_type": "postgres",
            "db_path": db_path,
            "postgres_conn": connection_string
        }

        return table_name, columns

    except Exception as e:
        raise ValueError(f"PostgreSQL connection failed: {str(e)}")


def _save_to_sqlite(df, table_name, user_id):
    """Save DataFrame to user-specific SQLite DB"""
    table_name = _clean_table_name(table_name)
    db_path = os.path.join(MODIFIED_DIR, f"{user_id}_data.db")
    conn = sqlite3.connect(db_path)
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()
    return db_path


def _df_to_sqlite(df, table_name, user_id):
    return _save_to_sqlite(df, table_name, user_id)


def _copy_db(file_path, user_id):
    """Copy uploaded SQLite DB to modified_files/"""
    import shutil
    db_path = os.path.join(MODIFIED_DIR, f"{user_id}_data.db")
    shutil.copy2(file_path, db_path)
    return db_path


# -------------------- STANDALONE QUESTION HELPERS (NL2SQL) --------------------

def _sql_is_context_dependent(user_message: str, last_question: str) -> bool:
    """
    Ask LLM whether the new NL2SQL message depends on prior question context.
    Returns True if it does, False if it is already standalone.
    """
    prompt = (
        f"Previous question: \"{last_question}\"\n"
        f"New question: \"{user_message}\"\n\n"
        "Does the new question depend on the previous question to be fully understood? "
        "For example: follow-up queries, references like 'same filter', 'those records', "
        "'now sort by', 'also show', 'instead', 'add a condition for', etc.\n"
        "Reply with only YES or NO."
    )
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0
        )
        result = response.choices[0].message.content.strip().upper()
        return result.startswith("YES")
    except Exception:
        return False


def _sql_rewrite_standalone(user_message: str, last_question: str) -> str:
    """
    Use LLM to rewrite a context-dependent NL2SQL message into a fully standalone question.
    """
    prompt = (
        f"Previous question: \"{last_question}\"\n"
        f"Follow-up question: \"{user_message}\"\n\n"
        "Rewrite the follow-up as a fully standalone data query that can be understood "
        "without any reference to the previous question. "
        "Reply with ONLY the rewritten question, nothing else."
    )
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0
        )
        result = response.choices[0].message.content.strip()
        return result if result else user_message
    except Exception:
        return user_message


def get_sql_standalone_question(user_message: str, sql_history: list):
    """
    Main logic for NL2SQL standalone question rewriting:
    - If no history → first query, always standalone, return None
    - If history exists → ask LLM if context-dependent
        - YES → rewrite and return standalone question
        - NO  → return None (original is already standalone)
    sql_history is a list of dicts with at least a 'question' key (from get_sql_history).
    """
    if not sql_history:
        return None

    # Last question asked by this user in NL2SQL
    last_question = sql_history[0].get("question", "")
    if not last_question:
        return None

    if _sql_is_context_dependent(user_message, last_question):
        return _sql_rewrite_standalone(user_message, last_question)

    return None


# -------------------- EXISTING FUNCTIONS (UNCHANGED) --------------------

def generate_sql(user_id, user_message):
    """Generate SQL from natural language using LLM"""
    if user_id not in user_data_store:
        raise ValueError("No data loaded. Please upload a file first.")

    store = user_data_store[user_id]
    table_name = store["table_name"]
    columns = store["columns"]

    # ✅ FIX: Wrap each column name in double quotes so the LLM sees exactly
    # how they should appear in the query — handles spaces, slashes, special chars
    quoted_columns = ', '.join([f'"{col}"' for col in columns])

    prompt = f"""You are an expert SQL query generator.

Table name: "{table_name}"
Columns: {quoted_columns}

User request: {user_message}

Rules:
1. Generate a valid SQLite SQL query
2. ALWAYS wrap the table name in double quotes: "{table_name}"
3. ALWAYS wrap every column name in double quotes exactly as shown above
4. This is critical for columns with spaces or special characters like "College Name", "Pass/Fail", "Student ID" etc.
5. For SELECT queries, use appropriate WHERE, ORDER BY, LIMIT clauses
6. For UPDATE queries, always include a WHERE clause
7. For DELETE queries, always include a WHERE clause
8. For INSERT queries, include all required columns
9. Return ONLY the SQL query, nothing else, no explanation, no markdown

SQL Query:"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0
    )

    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql


def execute_sql(user_id, sql_query):
    """Execute SQL and return results with user-friendly summary"""
    if user_id not in user_data_store:
        raise ValueError("No data loaded. Please upload a file first.")

    store = user_data_store[user_id]
    db_path = store["db_path"]
    table_name = store["table_name"]

    sql_upper = sql_query.strip().upper()
    conn = sqlite3.connect(db_path)

    try:
        if sql_upper.startswith("SELECT"):
            df_result = pd.read_sql_query(sql_query, conn)
            conn.close()

            row_count = len(df_result)
            summary = _generate_summary(
                user_id=user_id,
                sql_query=sql_query,
                operation="SELECT",
                result_df=df_result
            )

            return {
                "type": "select",
                "data": df_result.to_dict(orient="records"),
                "columns": df_result.columns.tolist(),
                "row_count": row_count,
                "summary": summary
            }

        elif sql_upper.startswith("UPDATE"):
            cursor = conn.cursor()
            cursor.execute(sql_query)
            affected = cursor.rowcount
            conn.commit()

            df_updated = pd.read_sql(f"SELECT * FROM '{table_name}'", conn)
            conn.close()

            file_path = _save_modified_file(df_updated, user_id, store["source_type"])
            summary = _generate_summary(
                user_id=user_id,
                sql_query=sql_query,
                operation="UPDATE",
                affected_rows=affected
            )

            return {
                "type": "modify",
                "operation": "UPDATE",
                "affected_rows": affected,
                "download_file": file_path,
                "summary": summary
            }

        elif sql_upper.startswith("DELETE"):
            cursor = conn.cursor()
            cursor.execute(sql_query)
            affected = cursor.rowcount
            conn.commit()

            df_updated = pd.read_sql(f"SELECT * FROM '{table_name}'", conn)
            conn.close()

            file_path = _save_modified_file(df_updated, user_id, store["source_type"])
            summary = _generate_summary(
                user_id=user_id,
                sql_query=sql_query,
                operation="DELETE",
                affected_rows=affected
            )

            return {
                "type": "modify",
                "operation": "DELETE",
                "affected_rows": affected,
                "download_file": file_path,
                "summary": summary
            }

        elif sql_upper.startswith("INSERT"):
            cursor = conn.cursor()
            cursor.execute(sql_query)
            conn.commit()

            df_updated = pd.read_sql(f"SELECT * FROM '{table_name}'", conn)
            conn.close()

            file_path = _save_modified_file(df_updated, user_id, store["source_type"])
            summary = _generate_summary(
                user_id=user_id,
                sql_query=sql_query,
                operation="INSERT",
                affected_rows=1
            )

            return {
                "type": "modify",
                "operation": "INSERT",
                "affected_rows": 1,
                "download_file": file_path,
                "summary": summary
            }

        else:
            conn.close()
            raise ValueError(f"Unsupported SQL operation: {sql_query[:20]}")

    except Exception as e:
        conn.close()
        raise ValueError(f"SQL execution error: {str(e)}")


def _save_modified_file(df, user_id, source_type):
    """Save modified DataFrame back to original format"""
    if source_type in ["csv", "sqlite", "postgres"]:
        file_path = os.path.join(MODIFIED_DIR, f"{user_id}_modified.csv")
        df.to_csv(file_path, index=False)
    elif source_type == "excel":
        file_path = os.path.join(MODIFIED_DIR, f"{user_id}_modified.xlsx")
        df.to_excel(file_path, index=False)
    else:
        file_path = os.path.join(MODIFIED_DIR, f"{user_id}_modified.csv")
        df.to_csv(file_path, index=False)
    return file_path


def _generate_summary(user_id, sql_query, operation, result_df=None, affected_rows=None):
    """Generate plain English summary of SQL result using LLM"""
    try:
        if operation == "SELECT" and result_df is not None:
            row_count = len(result_df)
            if row_count == 0:
                data_preview = "No rows returned."
            else:
                preview = result_df.head(5).to_string(index=False)
                data_preview = f"{row_count} rows returned. Preview:\n{preview}"

            prompt = f"""Given this SQL query and its result, write a short user-friendly summary in 2-3 sentences.

SQL: {sql_query}
Result: {data_preview}

Write a plain English summary of what was found:"""

        else:
            prompt = f"""Given this SQL operation, write a short user-friendly summary.

SQL: {sql_query}
Operation: {operation}
Rows affected: {affected_rows}

Write a plain English summary of what was done:"""

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.5
        )

        return response.choices[0].message.content.strip()

    except Exception:
        if operation == "SELECT":
            return f"Found {len(result_df)} records matching your query."
        else:
            return f"{operation} operation completed. {affected_rows} row(s) affected."


def get_table_info(user_id):
    """Get current table info for a user"""
    if user_id not in user_data_store:
        return None
    store = user_data_store[user_id]
    return {
        "table_name": store["table_name"],
        "columns": store["columns"],
        "source_type": store["source_type"],
        "row_count": len(store["df"])
    }