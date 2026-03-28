import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"
st.set_page_config(layout="wide", page_title="RAG Chatbot")

# -------------------- SESSION STATE --------------------
for key, default in {
    "token": None,
    "session_id": None,
    "selected_doc": "All Documents",
    "uploaded_files": {},        # {session_id: set of file keys}
    "renaming_session": None,    # session_id being renamed
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
                    # ✅ User does not exist
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


# ==================== MAIN APP ====================
headers = {"Authorization": f"Bearer {st.session_state.token}"}

# ==================== SIDEBAR ====================
with st.sidebar:
    st.title("💬 Chats")

    if st.button("➕ New Chat", use_container_width=True):
        res = requests.post(f"{API_URL}/create_chat", headers=headers)
        st.session_state.session_id = res.json()["session_id"]
        st.session_state.selected_doc = "All Documents"
        st.rerun()

    st.markdown("---")

    # Load sessions
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
                    requests.put(f"{API_URL}/rename_session", headers=headers, json={
                        "session_id": sid, "title": new_title
                    })
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
                        f"{API_URL}/delete_session/{sid}", headers=headers
                    )
                    if st.session_state.session_id == sid:
                        st.session_state.session_id = None
                    st.rerun()

    st.markdown("---")

    # ✅ Show documents for current session only
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
        "Filter by document",
        ["All Documents"] + session_docs
    )
    st.session_state.selected_doc = selected


# ==================== AUTO CREATE SESSION ====================
if not st.session_state.session_id:
    res = requests.post(f"{API_URL}/create_chat", headers=headers)
    st.session_state.session_id = res.json()["session_id"]

st.title("💬 RAG Chatbot")

# ==================== MAIN AREA ====================
col1, col2 = st.columns([1, 3])

# -------------------- UPLOAD --------------------
with col1:
    st.subheader("📄 Upload Document")

    # ✅ Show existing docs for this session
    if session_docs:
        st.success(f"📎 {len(session_docs)} doc(s) loaded for this chat")
        for d in session_docs:
            st.caption(f"• {d}")

    uploaded_file = st.file_uploader(
        "Upload new file",
        type=["pdf", "txt", "csv", "docx"]
    )

    if uploaded_file:
        sid = st.session_state.session_id
        file_key = f"{uploaded_file.name}_{uploaded_file.size}"

        # ✅ Track per session
        if sid not in st.session_state.uploaded_files:
            st.session_state.uploaded_files[sid] = set()

        if file_key not in st.session_state.uploaded_files[sid]:
            with st.spinner("Processing document..."):
                res = requests.post(
                    f"{API_URL}/upload",
                    headers=headers,
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

# -------------------- CHAT --------------------
with col2:
    st.subheader("💬 Chat")

    # Load and display history
    res = requests.get(
        f"{API_URL}/history/{st.session_state.session_id}",
        headers=headers
    )
    messages = res.json().get("messages", [])

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
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