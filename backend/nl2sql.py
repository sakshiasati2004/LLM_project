import os
import sqlite3
import json
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# -------------------- STORAGE --------------------
# Per-user storage: {user_id: {"df": df, "table_name": str, "columns": [], "source_type": str, "db_path": str}}
user_data_store = {}

MODIFIED_DIR = "modified_files"
os.makedirs(MODIFIED_DIR, exist_ok=True)


# -------------------- LOAD FILE --------------------

def load_file(file_path, user_id):
    """Load CSV, Excel, SQLite into memory for a user"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(file_path)
        table_name = os.path.splitext(os.path.basename(file_path))[0]
        source_type = "csv"
        db_path = _save_to_sqlite(df, table_name, user_id)

    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
        table_name = os.path.splitext(os.path.basename(file_path))[0]
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
        import psycopg2
        from sqlalchemy import create_engine

        engine = create_engine(connection_string)
        conn = engine.connect()

        from sqlalchemy import text, inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables:
            raise ValueError("No tables found in PostgreSQL database")

        table_name = tables[0]
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        conn.close()

        columns = df.columns.tolist()

        # Save to local SQLite for query execution
        db_path = _df_to_sqlite(df, table_name, user_id)

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


# -------------------- INTERNAL HELPERS --------------------

def _save_to_sqlite(df, table_name, user_id):
    """Save DataFrame to user-specific SQLite DB"""
    # Clean table name
    table_name = table_name.replace(" ", "_").replace("-", "_")
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


# -------------------- SQL GENERATION --------------------

def generate_sql(user_id, user_message):
    """Generate SQL from natural language using LLM"""
    if user_id not in user_data_store:
        raise ValueError("No data loaded. Please upload a file first.")

    store = user_data_store[user_id]
    table_name = store["table_name"]
    columns = store["columns"]

    prompt = f"""You are an expert SQL query generator.

Table name: {table_name}
Columns: {', '.join(columns)}

User request: {user_message}

Rules:
1. Generate a valid SQLite SQL query
2. Use the exact table name and column names provided
3. For SELECT queries, use appropriate WHERE, ORDER BY, LIMIT clauses
4. For UPDATE queries, always include a WHERE clause
5. For DELETE queries, always include a WHERE clause
6. For INSERT queries, include all required columns
7. Return ONLY the SQL query, nothing else, no explanation, no markdown

SQL Query:"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0
    )

    sql = response.choices[0].message.content.strip()
    # Clean markdown if LLM adds it
    sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql


# -------------------- SQL EXECUTION --------------------

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
        # -------------------- SELECT --------------------
        if sql_upper.startswith("SELECT"):
            df_result = pd.read_sql_query(sql_query, conn)
            conn.close()

            row_count = len(df_result)
            col_count = len(df_result.columns)

            # ✅ Generate user-friendly summary
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

        # -------------------- UPDATE --------------------
        elif sql_upper.startswith("UPDATE"):
            cursor = conn.cursor()
            cursor.execute(sql_query)
            affected = cursor.rowcount
            conn.commit()

            # ✅ Save modified file
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

        # -------------------- DELETE --------------------
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

        # -------------------- INSERT --------------------
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


# -------------------- SAVE MODIFIED FILE --------------------

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


# -------------------- USER FRIENDLY SUMMARY --------------------

def _generate_summary(user_id, sql_query, operation, result_df=None, affected_rows=None):
    """Generate plain English summary of SQL result using LLM"""
    try:
        if operation == "SELECT" and result_df is not None:
            row_count = len(result_df)
            if row_count == 0:
                data_preview = "No rows returned."
            else:
                # Send first 5 rows as preview
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
        # Fallback summary without LLM
        if operation == "SELECT":
            return f"Found {len(result_df)} records matching your query."
        else:
            return f"{operation} operation completed. {affected_rows} row(s) affected."


# -------------------- GET TABLE INFO --------------------

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