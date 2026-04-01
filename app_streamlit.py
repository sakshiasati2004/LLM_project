import streamlit as st
import requests
import pandas as pd
import speech_recognition as sr

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
    "sql_table_info": None,
    "sql_results": [],
    "sql_file_key": None,
    "sql_pending_query": None,
    "mic_text": "",
    "mic_listening": False,
    "last_uploaded_doc": None,   # ✅ NEW: track last uploaded doc name
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
            if not username or not password:
                st.warning("Please enter username and password")
            else:
                res = requests.post(f"{API_URL}/register", json={
                    "username": username, "password": password
                })
                if res.status_code == 200:
                    st.success("Registered successfully! Please login ✅")
                else:
                    st.error(res.json().get("detail", "Registration failed"))

    if option == "Login":
        if st.button("Login"):
            if not username or not password:
                st.warning("Please enter username and password")
            else:
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
                    res2 = requests.post(f"{API_URL}/create_chat", headers=headers)
                    st.session_state.session_id = res2.json()["session_id"]
                    st.rerun()
                else:
                    st.error("Login failed")

    st.stop()


# ==================== MAIN ====================
headers = {"Authorization": f"Bearer {st.session_state.token}"}

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
            st.session_state.last_uploaded_doc = None  # ✅ reset on new chat
            st.rerun()

        st.markdown("---")

        res = requests.get(f"{API_URL}/sessions", headers=headers)
        sessions = res.json().get("sessions", [])

        for session in sessions:
            sid = session["id"]
            title = session["title"] or f"Chat {sid}"
            is_active = st.session_state.session_id == sid

            if st.session_state.renaming_session == sid:
                new_title = st.text_input(
                    "Rename", value=title, key=f"rename_input_{sid}"
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
                        st.session_state.last_uploaded_doc = None  # ✅ reset on session switch
                        st.rerun()
                with col_rename:
                    if st.button("✏️", key=f"rename_{sid}"):
                        st.session_state.renaming_session = sid
                        st.rerun()
                with col_del:
                    if st.button("🗑", key=f"del_{sid}"):
                        requests.delete(
                            f"{API_URL}/delete_session/{sid}", headers=headers
                        )
                        if st.session_state.session_id == sid:
                            remaining = [s for s in sessions if s["id"] != sid]
                            st.session_state.session_id = remaining[0]["id"] if remaining else None
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

        # ✅ CHANGED: removed dropdown filter, just show uploaded docs list
        if session_docs:
            for d in session_docs:
                st.caption(f"• {d}")
        else:
            st.caption("No documents uploaded yet")

    # ==================== RAG MAIN ====================
    st.title("💬 RAG Chatbot")
    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("📄 Upload")

        if session_docs:
            st.success(f"📎 {len(session_docs)} doc(s) loaded")
            for d in session_docs:
                st.caption(f"• {d}")

        st.markdown("""
            <script>
            const interval = setInterval(() => {
                const input = document.querySelector('input[type="file"]');
                if (input) {
                    input.setAttribute('accept', '.pdf,.txt,.doc,.docx,.msg,.chm,.jpg,.jpeg,.png,.ppt,.pptx,application/vnd.ms-outlook');
                    clearInterval(interval);
                }
            }, 300);
            </script>
        """, unsafe_allow_html=True)

        uploaded_file = st.file_uploader(
            "Upload file (PDF, TXT, DOC, DOCX, MSG, CHM, JPG, PNG, PPT, PPTX)",
            type=["pdf", "txt", "doc", "docx", "msg", "chm", "jpg", "jpeg", "png", "ppt", "pptx"]
        )

        if uploaded_file:
            allowed_ext = ["pdf", "txt", "doc", "docx", "msg", "chm", "jpg", "jpeg", "png", "ppt", "pptx"]
            file_ext = uploaded_file.name.split(".")[-1].lower()

            if file_ext not in allowed_ext:
                st.error(f"❌ Unsupported file type: .{file_ext}")
                st.stop()

            sid = st.session_state.session_id
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"

            if sid not in st.session_state.uploaded_files:
                st.session_state.uploaded_files[sid] = set()

            if file_key not in st.session_state.uploaded_files[sid]:
                with st.spinner("Processing document..."):
                    res = requests.post(
                        f"{API_URL}/upload",
                        headers=headers,
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/octet-stream")},
                        data={"session_id": sid}
                    )
                if res.status_code == 200:
                    st.session_state.uploaded_files[sid].add(file_key)
                    st.session_state.last_uploaded_doc = uploaded_file.name  # ✅ NEW: track last uploaded
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

        mic_col, _ = st.columns([1, 3])
        with mic_col:
            mic_label = "🔴 Stop Listening" if st.session_state.mic_listening else "🎤 Speak"
            if st.button(mic_label, key="mic_button"):
                if not st.session_state.mic_listening:
                    st.session_state.mic_listening = True
                    st.session_state.mic_text = ""
                    st.rerun()
                else:
                    st.session_state.mic_listening = False
                    st.rerun()

        if st.session_state.mic_listening:
            st.info("🎤 Listening... Please speak now")
            try:
                recognizer = sr.Recognizer()
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
                text = recognizer.recognize_google(audio)
                st.session_state.mic_text = text
                st.session_state.mic_listening = False
                st.rerun()
            except sr.WaitTimeoutError:
                st.session_state.mic_listening = False
                st.warning("⏱️ No speech detected. Please try again.")
                st.rerun()
            except sr.UnknownValueError:
                st.session_state.mic_listening = False
                st.warning("❓ Could not understand. Please try again.")
                st.rerun()
            except Exception as e:
                st.session_state.mic_listening = False
                st.error(f"Mic error: {str(e)}")
                st.rerun()

        if st.session_state.mic_text:
            st.markdown("**🗣️ Transcribed — edit if needed:**")
            edited_text = st.text_area(
                "Edit your query",
                value=st.session_state.mic_text,
                key="mic_edit_box",
                label_visibility="collapsed"
            )
            if st.button("📨 Send", key="mic_send_button"):
                if edited_text.strip():
                    with st.chat_message("user"):
                        st.write(edited_text)
                    with st.spinner("Thinking..."):
                        res = requests.post(
                            f"{API_URL}/chat",
                            headers=headers,
                            json={
                                "session_id": st.session_state.session_id,
                                "message": edited_text,
                                "selected_doc": "All Documents",
                                "last_uploaded_doc": st.session_state.last_uploaded_doc,  # ✅ NEW
                                "session_docs": session_docs                               # ✅ NEW
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
                    st.session_state.mic_text = ""
                    st.session_state.last_uploaded_doc = None  # ✅ NEW: clear after use
                    st.rerun()

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
                        "selected_doc": "All Documents",
                        "last_uploaded_doc": st.session_state.last_uploaded_doc,  # ✅ NEW
                        "session_docs": session_docs                               # ✅ NEW
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

            st.session_state.last_uploaded_doc = None  # ✅ NEW: clear after first use
            st.rerun()


# =========================================================
# ==================== TAB 2: NL2SQL ======================
# =========================================================
with tab2:
    st.title("🧮 NL2SQL Assistant")

    with st.sidebar:
        st.markdown("---")
        st.title("🧮 NL2SQL History")

        res_hist = requests.get(f"{API_URL}/history_sql", headers=headers)
        sql_history = res_hist.json().get("history", []) if res_hist.status_code == 200 else []

        if not sql_history:
            st.caption("No queries yet")
        else:
            for item in sql_history:
                with st.expander(f"🔍 {item['question'][:40]}..."):
                    st.caption(f"🕐 {item['timestamp']}")
                    st.code(item["sql_query"], language="sql")
                    if item.get("summary"):
                        st.info(item["summary"])
                    if item["result_type"] == "select":
                        st.caption(f"📊 {item['row_count']} rows returned")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("📂 Upload Data File")

        sql_file = st.file_uploader(
            "Upload CSV / Excel / SQLite",
            type=["csv", "xlsx", "xls", "db"]
        )

        if sql_file:
            file_key = f"{sql_file.name}_{sql_file.size}"

            if st.session_state.sql_file_key != file_key:
                with st.spinner("Processing..."):
                    res = requests.post(
                        f"{API_URL}/upload_sql",
                        headers=headers,
                        files={"file": (sql_file.name, sql_file, sql_file.type)}
                    )
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.sql_file_uploaded = True
                    st.session_state.sql_table_info = data
                    st.session_state.sql_results = []
                    st.session_state.sql_file_key = file_key
                    st.success("Uploaded ✅")
                else:
                    st.error(res.json().get("detail", "Upload failed"))
            else:
                st.success("✅ File already loaded")

        if st.session_state.sql_table_info:
            st.markdown("---")
            st.subheader("📊 Table Info")
            info = st.session_state.sql_table_info
            st.write(f"**Table:** `{info.get('table_name', '')}`")
            cols = info.get('columns', [])
            st.write(f"**Columns ({len(cols)}):**")
            for col in cols:
                st.caption(f"• {col}")

    with col2:
        st.subheader("💬 Ask SQL Queries")

        if not st.session_state.sql_file_uploaded:
            st.info("👈 Upload a CSV, Excel, or SQLite file first")
        else:
            # ✅ Render all past results from session_state (survives reruns)
            for result in st.session_state.sql_results:
                with st.container():
                    with st.chat_message("user"):
                        st.write(result["question"])

                    with st.chat_message("assistant"):
                        if result.get("error"):
                            st.error(f"❌ {result['error']}")
                        else:
                            st.markdown("**🧠 Generated SQL:**")
                            st.code(result["sql"], language="sql")

                            if result.get("summary"):
                                st.info(f"💬 {result['summary']}")

                            if result["type"] == "select":
                                if result["records"]:
                                    st.markdown(f"**📊 Results ({result['row_count']} rows):**")
                                    df = pd.DataFrame(result["records"])
                                    st.dataframe(df, use_container_width=True)

                                    csv = df.to_csv(index=False)
                                    st.download_button(
                                        "⬇️ Download Results as CSV",
                                        csv,
                                        file_name="query_results.csv",
                                        mime="text/csv",
                                        key=f"download_{result['id']}"
                                    )
                                else:
                                    st.warning("No records found matching your query.")

                    st.markdown("---")

            if st.session_state.sql_pending_query:
                with st.chat_message("user"):
                    st.write(st.session_state.sql_pending_query)

                with st.chat_message("assistant"):
                    with st.spinner("Generating SQL and fetching results..."):
                        res = requests.post(
                            f"{API_URL}/query_sql",
                            headers=headers,
                            json={"message": st.session_state.sql_pending_query}
                        )

                    if res.status_code == 200:
                        data = res.json()
                        result_obj = {
                            "id": len(st.session_state.sql_results),
                            "question": st.session_state.sql_pending_query,
                            "sql": data.get("sql_query", ""),
                            "summary": data.get("summary", ""),
                            "type": data.get("type", ""),
                            "records": data.get("data", []),
                            "columns": data.get("columns", []),
                            "row_count": data.get("row_count", 0),
                            "error": None,
                        }
                    else:
                        err = res.json().get("detail", "Query failed")
                        result_obj = {
                            "id": len(st.session_state.sql_results),
                            "question": st.session_state.sql_pending_query,
                            "sql": "",
                            "summary": "",
                            "type": "error",
                            "records": [],
                            "columns": [],
                            "row_count": 0,
                            "error": err,
                        }

                    st.session_state.sql_results.append(result_obj)

                st.session_state.sql_pending_query = None
                st.rerun()

            query = st.chat_input(
                "Ask like: show rows where gender is female / show top 5 salaries..."
            )

            if query:
                st.session_state.sql_pending_query = query
                st.rerun()