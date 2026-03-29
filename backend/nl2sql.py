import os
import pandas as pd
import sqlite3
from datetime import datetime
from backend.llm import llm_call

# -------------------- SESSION MEMORY --------------------
nl2sql_sessions = {}


# -------------------- LOAD FILE --------------------
def load_file(file_path, user_id):

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(file_path)

    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)

    elif ext == ".db":
        conn = sqlite3.connect(file_path)
        table_name = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table';",
            conn
        ).iloc[0, 0]
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        conn.close()

    else:
        raise ValueError("Unsupported file type")

    table_name = os.path.splitext(os.path.basename(file_path))[0]

    # Save session memory
    nl2sql_sessions[user_id] = {
        "df": df,
        "table_name": table_name,
        "file_path": file_path
    }

    return table_name, list(df.columns)


# -------------------- GENERATE SQL --------------------
def generate_sql(user_id, user_query):

    session = nl2sql_sessions.get(user_id)

    if not session:
        raise ValueError("No file uploaded")

    columns = session["df"].columns.tolist()
    table_name = session["table_name"]

    prompt = f"""
You are an SQL expert.

Table name: {table_name}
Columns: {columns}

Convert the user query into SQL.

User Query:
{user_query}

Only return SQL query. No explanation.
"""

    messages = [{"role": "user", "content": prompt}]
    sql_query = llm_call(messages)

    return sql_query.strip().replace("```sql", "").replace("```", "")


# -------------------- EXECUTE SQL --------------------
def execute_sql(user_id, sql_query):

    session = nl2sql_sessions.get(user_id)

    if not session:
        raise ValueError("No file uploaded")

    df = session["df"]
    table_name = session["table_name"]

    conn = sqlite3.connect(":memory:")
    df.to_sql(table_name, conn, index=False, if_exists="replace")

    cursor = conn.cursor()

    try:
        cursor.execute(sql_query)

        # ---------------- SELECT ----------------
        if sql_query.strip().lower().startswith("select"):
            result = pd.read_sql(sql_query, conn)
            conn.close()

            return {
                "type": "select",
                "data": result.to_dict(orient="records"),
                "columns": list(result.columns),
                "sql": sql_query
            }

        # ---------------- INSERT / UPDATE / DELETE ----------------
        else:
            conn.commit()

            updated_df = pd.read_sql(f"SELECT * FROM {table_name}", conn)

            # Save updated file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_file = f"{table_name}_updated_{timestamp}.csv"

            updated_df.to_csv(new_file, index=False)

            conn.close()

            return {
                "type": "modify",
                "message": "Query executed successfully ✅",
                "download_file": new_file,
                "sql": sql_query
            }

    except Exception as e:
        conn.close()
        return {
            "type": "error",
            "message": str(e),
            "sql": sql_query
        }