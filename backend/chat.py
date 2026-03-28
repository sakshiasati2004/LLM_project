from backend.db import get_chat_history, save_message
from backend.llm import llm_call
from backend.rag import get_context_from_query

vectorstore = None

def set_vectorstore(vs):
    global vectorstore
    vectorstore = vs


def chat(user_id, session_id, user_message, selected_doc="All Documents"):

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

    # -------------------- SMART DECISION --------------------
    # ✅ Only use RAG if context is meaningful
    if context and len(context.strip()) > 100:

        prompt = f"""
You are a helpful assistant.

Use the context below ONLY if it is relevant to the question.
If the context is not useful, answer normally using your own knowledge.

Context:
{context}

Question:
{user_message}
"""

        messages = history + [{"role": "user", "content": prompt}]

    else:
        # ✅ Normal ChatGPT mode
        messages = history + [{"role": "user", "content": user_message}]
        file_names = []

    # -------------------- LLM CALL --------------------
    response = llm_call(messages)

    # -------------------- SOURCE ATTACHMENT --------------------
    if context and len(context.strip()) > 100 and file_names:
        response += f"\n\nSource: {', '.join(file_names)}"

    # -------------------- SAVE HISTORY --------------------
    save_message(user_id, session_id, "user", user_message)
    save_message(user_id, session_id, "assistant", response)

    return response