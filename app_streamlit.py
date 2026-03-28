import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(layout="wide")

# -------------------- SESSION --------------------
if "token" not in st.session_state:
    st.session_state.token = None

if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "selected_doc" not in st.session_state:
    st.session_state.selected_doc = "All Documents"


# ==================== AUTH ====================
if not st.session_state.token:

    st.title("🔐 Login / Register")

    option = st.selectbox("Choose", ["Login", "Register"])

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if option == "Register":
        if st.button("Register"):
            res = requests.post(f"{API_URL}/register", json={
                "username": username,
                "password": password
            })
            st.write(res.json())

    if option == "Login":
        if st.button("Login"):
            res = requests.post(f"{API_URL}/login", json={
                "username": username,
                "password": password
            })

            try:
                data = res.json()
            except:
                st.error("Server error")
                st.stop()

            if "access_token" in data:
                st.session_state.token = data["access_token"]

                # 🔥 AUTO CREATE CHAT AFTER LOGIN
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                res = requests.post(f"{API_URL}/create_chat", headers=headers)
                st.session_state.session_id = res.json()["session_id"]

                st.success("Login successful ✅")
                st.rerun()
            else:
                st.error(data.get("error"))


# ==================== MAIN APP ====================
else:
    headers = {
        "Authorization": f"Bearer {st.session_state.token}"
    }

    st.title("💬 RAG Chatbot")

    # ==================== SIDEBAR ====================
    st.sidebar.title("💬 Chats")

    # ➕ New Chat
    if st.sidebar.button("➕ New Chat"):
        res = requests.post(f"{API_URL}/create_chat", headers=headers)
        st.session_state.session_id = res.json()["session_id"]
        st.rerun()

    # 📜 Load sessions
    res = requests.get(f"{API_URL}/sessions", headers=headers)
    sessions = res.json().get("sessions", [])

    for session in sessions:
        session_id = session["id"]
        title = session["title"]

        if st.sidebar.button(title or f"Chat {session_id}", key=f"select_{session_id}"):
            st.session_state.session_id = session_id
            st.rerun()

    # ==================== DOCUMENT SELECT ====================
    st.sidebar.markdown("---")
    st.sidebar.title("📄 Documents")

    res = requests.get(f"{API_URL}/documents", headers=headers)
    docs = res.json().get("documents", [])

    selected = st.sidebar.selectbox(
        "Select document",
        ["All Documents"] + docs
    )

    st.session_state.selected_doc = selected

    # ==================== MAIN CHAT AREA ====================
    if not st.session_state.session_id:
        # 🔥 AUTO CREATE SESSION IF NOT EXISTS
        res = requests.post(f"{API_URL}/create_chat", headers=headers)
        st.session_state.session_id = res.json()["session_id"]

    # -------------------- UPLOAD + CHAT (SAME SCREEN) --------------------
    col1, col2 = st.columns([1, 3])

    # 📄 Upload Section (LEFT)
    with col1:
        st.subheader("📄 Upload")

        uploaded_file = st.file_uploader(
            "Upload file",
            type=["pdf", "txt", "csv", "docx"]
        )

        if uploaded_file:
            files = {"file": uploaded_file}

            requests.post(
                f"{API_URL}/upload",
                headers=headers,
                files=files,
                data={
                    "session_id": st.session_state.session_id
                }
            )

            st.success("Uploaded ✅")

    # 💬 Chat Section (RIGHT)
    with col2:

        st.subheader("💬 Chat")

        # 🔹 Load history
        res = requests.get(
            f"{API_URL}/history/{st.session_state.session_id}",
            headers=headers
        )

        messages = res.json().get("messages", [])

        # 🔹 Display messages
        for msg in messages:
            with st.chat_message(msg["role"]):
                content = msg["content"]

                if "Source:" in content:
                    main = content.split("Source:")[0]
                    src = content.split("Source:")[-1]

                    st.write(main)
                    st.caption(f"📄 Source: {src.strip()}")
                else:
                    st.write(content)

        # 🔹 Input
        user_input = st.chat_input("Ask anything...")

        if user_input:
            st.chat_message("user").write(user_input)

            res = requests.post(
                f"{API_URL}/chat",
                headers=headers,
                json={
                    "session_id": st.session_state.session_id,
                    "message": user_input,
                    "selected_doc": st.session_state.selected_doc
                }
            )

            try:
                data = res.json()
                response = data.get("response", "Error")
            except:
                response = "⚠️ Server error"

            with st.chat_message("assistant"):
                if "Source:" in response:
                    main = response.split("Source:")[0]
                    src = response.split("Source:")[-1]

                    st.write(main)
                    st.caption(f"📄 Source: {src.strip()}")
                else:
                    st.write(response)

            st.rerun()