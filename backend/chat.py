from backend.db import get_chat_history, save_message, get_message_count, rename_session
from backend.llm import llm_call, generate_chat_title
from backend.rag import get_context_from_query


def chat(user_id, session_id, user_message, vectorstore=None, selected_doc="All Documents"):

    # ✅ Check if this is the first message (for auto title generation)
    is_first_message = get_message_count(user_id, session_id) == 0

    # ✅ Get chat history for memory
    history = get_chat_history(user_id, session_id)

    context = ""
    file_names = []

    # -------------------- RAG RETRIEVAL --------------------
    if vectorstore:
        context, _, file_names = get_context_from_query(
            vectorstore,
            user_message,
            user_id,
            session_id,
            selected_doc
        )

    # -------------------- BUILD PROMPT --------------------
    if context and len(context.strip()) > 20:
        # ✅ Document context available — inject into prompt
        prompt = f"""You are a helpful assistant.

Use the context below ONLY if it is relevant to the question.
If the context is not useful, answer from your own knowledge normally.

Context:
{context}

Question:
{user_message}"""

        messages = history + [{"role": "user", "content": prompt}]

    else:
        # ✅ No document context — pure normal chat mode
        messages = history + [{"role": "user", "content": user_message}]
        file_names = []

    # -------------------- LLM CALL --------------------
    response = llm_call(messages)

    # -------------------- SAVE TO DB --------------------
    save_message(user_id, session_id, "user", user_message)
    save_message(user_id, session_id, "assistant", response)

    # -------------------- AUTO TITLE GENERATION --------------------
    # ✅ Only on first message — LLM generates smart title like ChatGPT
    if is_first_message:
        title = generate_chat_title(user_message)
        rename_session(session_id, title, user_id)

    # -------------------- RETURN --------------------
    # ✅ Sources returned separately (not embedded in response string)
    sources = (
        list(file_names)
        if (context and len(context.strip()) > 20 and file_names)
        else []
    )

    return response, sources