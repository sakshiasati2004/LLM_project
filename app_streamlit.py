import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"
st.set_page_config(layout="wide", page_title="RAG + NL2SQL Chatbot")

# -------------------- SESSION STATE --------------------
for key, default in {
    "token": None,
    "session_id": None,
    "selected_doc": "All Documents",
    "uploaded_files": {},
    "renaming_session": None,
    "sql_file_uploaded": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ==================== AUTH PAGE ====================
if not st.session_state.token:
    st.title("🔐 Login / Register")
    option = st.selectbox("Choose", ["Login", "Register"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if option == "Register":
        if st.button("Register"):
            res = requests.post(f"{API_URL}/register", json={
                "username": username, "password": password
            })
            if res.status_code == 200:
                st.success("Registered successfully ✅")
            else:
                st.error(res.json().get("detail", "Error"))

    if option == "Login":
        if st.button("Login"):
            res = requests.post(f"{API_URL}/login", json={
                "username": username, "password": password
            })
            data = res.json()

            if res.status_code == 404:
                st.error("❌ User does not exist. Please register first.")
            elif res.status_code == 401:
                st.error("❌ Incorrect password.")
            elif "access_token" in data:
                st.session_state.token = data["access_token"]
                headers = {"Authorization": f"Bearer {st.session_state.token}"}

                # ✅ Create new session on every login (as you want)
                res2 = requests.post(f"{API_URL}/create_chat", headers=headers)
                st.session_state.session_id = res2.json()["session_id"]
                st.rerun()
            else:
                st.error(data.get("detail", "Login failed"))

    st.stop()


# ==================== MAIN ====================
headers = {"Authorization": f"Bearer {st.session_state.token}"}

# ✅ Auto create session if none exists
if not st.session_state.session_id:
    res = requests.post(f"{API_URL}/create_chat", headers=headers)
    st.session_state.session_id = res.json()["session_id"]

tab1, tab2 = st.tabs(["💬 RAG Chat", "🧮 NL2SQL"])


# =========================================================
# ==================== TAB 1: RAG =========================
# =========================================================
with tab1:

    with st.sidebar:
        st.title("💬 Chats")

        if st.button("➕ New Chat", use_container_width=True):
            res = requests.post(f"{API_URL}/create_chat", headers=headers)
            st.session_state.session_id = res.json()["session_id"]
            st.session_state.selected_doc = "All Documents"
            st.rerun()

        st.markdown("---")

        res = requests.get(f"{API_URL}/sessions", headers=headers)
        sessions = res.json().get("sessions", [])

        for session in sessions:
            sid = session["id"]
            title = session["title"] or f"Chat {sid}"
            is_active = st.session_state.session_id == sid

            # ✅ Rename mode
            if st.session_state.renaming_session == sid:
                new_title = st.text_input(
                    "Rename", value=title,
                    key=f"rename_input_{sid}"
                )
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("Save", key=f"save_{sid}"):
                        requests.put(
                            f"{API_URL}/rename_session",
                            headers=headers,
                            json={"session_id": sid, "title": new_title}
                        )
                        st.session_state.renaming_session = None
                        st.rerun()
                with col_cancel:
                    if st.button("Cancel", key=f"cancel_{sid}"):
                        st.session_state.renaming_session = None
                        st.rerun()
            else:
                col_title, col_rename, col_del = st.columns([3, 1, 1])
                with col_title:
                    label = f"**{title}**" if is_active else title
                    if st.button(label, key=f"select_{sid}", use_container_width=True):
                        st.session_state.session_id = sid
                        st.session_state.selected_doc = "All Documents"
                        st.rerun()
                with col_rename:
                    if st.button("✏️", key=f"rename_{sid}"):
                        st.session_state.renaming_session = sid
                        st.rerun()
                with col_del:
                    if st.button("🗑", key=f"del_{sid}"):
                        requests.delete(
                            f"{API_URL}/delete_session/{sid}",
                            headers=headers
                        )
                        if st.session_state.session_id == sid:
                            remaining = [s for s in sessions if s["id"] != sid]
                            if remaining:
                                st.session_state.session_id = remaining[0]["id"]
                            else:
                                st.session_state.session_id = None
                        st.rerun()

        st.markdown("---")

        st.title("📄 Documents")
        if st.session_state.session_id:
            res = requests.get(
                f"{API_URL}/documents/{st.session_state.session_id}",
                headers=headers
            )
            session_docs = res.json().get("documents", [])
        else:
            session_docs = []

        selected = st.selectbox(
            "Filter",
            ["All Documents"] + session_docs
        )
        st.session_state.selected_doc = selected

    # ==================== MAIN CHAT AREA ====================
    st.title("💬 RAG Chatbot")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("📄 Upload")

        if session_docs:
            st.success(f"📎 {len(session_docs)} doc(s) loaded")
            for d in session_docs:
                st.caption(f"• {d}")

        uploaded_file = st.file_uploader(
            "Upload file",
            type=["pdf", "txt", "csv", "docx"]
        )

        if uploaded_file:
            sid = st.session_state.session_id
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"

            if sid not in st.session_state.uploaded_files:
                st.session_state.uploaded_files[sid] = set()

            if file_key not in st.session_state.uploaded_files[sid]:
                with st.spinner("Processing document..."):
                    res = requests.post(
                        f"{API_URL}/upload",
                        headers=headers,
                        # ✅ FIXED — correct file upload format
                        files={"file": (uploaded_file.name, uploaded_file, uploaded_file.type)},
                        data={"session_id": sid}
                    )
                if res.status_code == 200:
                    st.session_state.uploaded_files[sid].add(file_key)
                    st.success("Uploaded ✅")
                    st.rerun()
                else:
                    st.error(f"Upload failed: {res.json().get('detail', 'Unknown error')}")
            else:
                st.info("✅ Already uploaded this session")

    with col2:
        st.subheader("💬 Chat")

        res = requests.get(
            f"{API_URL}/history/{st.session_state.session_id}",
            headers=headers
        )
        messages = res.json().get("messages", [])

        for msg in messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("Ask anything...")

        if user_input:
            with st.chat_message("user"):
                st.write(user_input)

            with st.spinner("Thinking..."):
                res = requests.post(
                    f"{API_URL}/chat",
                    headers=headers,
                    json={
                        "session_id": st.session_state.session_id,
                        "message": user_input,
                        "selected_doc": st.session_state.selected_doc
                    }
                )

            if res.status_code == 200:
                data = res.json()
                response = data.get("response", "")
                sources = data.get("sources", [])

                with st.chat_message("assistant"):
                    st.write(response)
                    if sources:
                        st.caption(f"📄 Source: {', '.join(sources)}")
            else:
                st.error("⚠️ Server error. Please try again.")

            st.rerun()


# =========================================================
# ==================== TAB 2: NL2SQL ======================
# =========================================================
with tab2:

    st.title("🧮 NL2SQL Assistant")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("📂 Upload Table File")

        sql_file = st.file_uploader(
            "Upload CSV / Excel / DB",
            type=["csv", "xlsx", "db"]
        )

        if sql_file:
            with st.spinner("Processing..."):
                res = requests.post(
                    f"{API_URL}/upload_sql",
                    headers=headers,
                    files={"file": sql_file}
                )

            if res.status_code == 200:
                data = res.json()
                st.success("Uploaded ✅")
                st.write("Table:", data["table_name"])
                st.write("Columns:", data["columns"])
                st.session_state.sql_file_uploaded = True
            else:
                st.error(res.json().get("detail"))

    with col2:
        st.subheader("💬 Ask SQL Queries")

        if not st.session_state.sql_file_uploaded:
            st.info("Upload a file first 👈")
        else:
            query = st.chat_input("Ask like: show top 5 rows")

            if query:
                with st.spinner("Generating SQL..."):
                    res = requests.post(
                        f"{API_URL}/query_sql",
                        headers=headers,
                        json={"message": query}
                    )

                if res.status_code == 200:
                    data = res.json()

                    st.write("🧠 SQL:")
                    st.code(data.get("sql_query", ""), language="sql")

                    if data.get("type") == "select":
                        st.dataframe(data.get("data"))

                    elif data.get("type") == "modify":
                        file_path = data.get("download_file")
                        st.success("File updated ✅")

                        download_res = requests.get(
                            f"{API_URL}/download_sql",
                            headers=headers,
                            params={"file_path": file_path}
                        )

                        st.download_button(
                            "⬇️ Download Updated File",
                            download_res.content,
                            file_name="updated_file.csv"
                        )
                else:
                    st.error("Query failed ❌")