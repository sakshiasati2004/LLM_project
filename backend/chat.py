from backend.db import get_chat_history, save_message, get_message_count, rename_session, get_last_standalone_question
from backend.llm import llm_call, generate_chat_title
from backend.rag import get_context_from_query


# -------------------- STANDALONE QUESTION HELPERS --------------------

def _is_context_dependent(user_message: str, last_standalone: str) -> bool:
    """
    Ask LLM whether the new message depends on prior conversation context.
    Returns True if it does, False if it is already standalone.
    """
    prompt = (
        f"Previous message: \"{last_standalone}\"\n"
        f"New message: \"{user_message}\"\n\n"
        "Does the new message depend on the previous message to be fully understood? "
        "For example: follow-up questions, references like 'it', 'that', 'explain more', "
        "'give examples', 'what about', 'tell me more', 'advantages?', 'elaborate', "
        "'more about it', 'what is it', 'what about it', etc.\n"
        "Reply with only YES or NO."
    )
    try:
        result = llm_call([{"role": "user", "content": prompt}])
        return result.strip().upper().startswith("YES")
    except Exception:
        return False


def _rewrite_standalone_question(user_message: str, last_standalone: str) -> str:
    """
    Use LLM to rewrite a context-dependent message into a fully standalone question.
    Uses previous standalone question as context for chaining.
    """
    prompt = (
        f"Previous standalone question: \"{last_standalone}\"\n"
        f"Follow-up message: \"{user_message}\"\n\n"
        "Rewrite the follow-up as a fully standalone question that can be understood "
        "without any reference to the previous message. Replace all pronouns and "
        "vague references with the actual subject from the previous standalone question. "
        "Reply with ONLY the rewritten question, nothing else."
    )
    try:
        result = llm_call([{"role": "user", "content": prompt}])
        return result.strip() if result.strip() else user_message
    except Exception:
        return user_message


def _get_standalone_question(
    user_message: str,
    history: list,
    last_standalone: str,
    last_uploaded_doc: str,
    session_docs: list
) -> tuple:
    """
    Main standalone question logic.

    Priority order:
    1. New doc just uploaded → ALWAYS use that doc regardless of history
       → search ONLY that doc (returns search_doc = last_uploaded_doc)
    2. Clear standalone question → return as-is, search ALL docs
    3. Vague question + previous standalone exists → chain from previous standalone, search ALL docs
    4. Vague question + no previous standalone + 1 doc → assume "it" = that doc, search ALL docs
    5. Vague question + no previous standalone + 2+ docs → ask user to clarify

    Returns:
        (standalone_question: str, needs_clarification: bool, search_doc: str or None)
        search_doc — if set, restrict retrieval to this specific doc only
                   — None means search All Documents
    """

    # ✅ PRIORITY 1: New doc just uploaded → ALWAYS treat "it" as that doc
    # This check happens FIRST — before any LLM call or history check
    # ✅ Returns search_doc = last_uploaded_doc to restrict retrieval to ONLY this doc
    if last_uploaded_doc:
        rewritten = _rewrite_standalone_question(
            user_message,
            f"the document {last_uploaded_doc}"
        )
        return rewritten, False, last_uploaded_doc  # ✅ search ONLY this new doc

    # If no history — first message with no uploaded doc, return as-is
    if not history:
        return user_message, False, None  # search All Docs

    # Use last standalone as context for dependency check
    context_for_check = last_standalone if last_standalone else ""

    # If no previous standalone, use last user message from history
    if not context_for_check:
        for entry in reversed(history):
            if entry["role"] == "user":
                context_for_check = entry["content"]
                break

    if not context_for_check:
        return user_message, False, None  # search All Docs

    # ✅ PRIORITY 2: Check if message is standalone (no context needed)
    is_dependent = _is_context_dependent(user_message, context_for_check)

    if not is_dependent:
        # Already a standalone question — search ALL docs
        return user_message, False, None

    # --- Context-dependent question — apply remaining priority rules ---

    # ✅ PRIORITY 3: Previous standalone exists → chain from it, search ALL docs
    if last_standalone:
        rewritten = _rewrite_standalone_question(user_message, last_standalone)
        return rewritten, False, None  # search All Docs

    # ✅ PRIORITY 4: No previous standalone + exactly 1 doc → assume "it" = that doc
    if session_docs and len(session_docs) == 1:
        rewritten = _rewrite_standalone_question(
            user_message,
            f"the document {session_docs[0]}"
        )
        return rewritten, False, None  # search All Docs (only 1 doc anyway)

    # ✅ PRIORITY 5: No previous standalone + 2+ docs → need clarification
    if session_docs and len(session_docs) > 1:
        return user_message, True, None

    # Fallback — return as-is, search All Docs
    return user_message, False, None


def _build_multi_doc_answer(session_docs_list, user_message: str, history: list) -> tuple:
    """
    Build separate answers per document source and combine with source labels.
    session_docs_list: list of LangChain Document objects with metadata
    Returns (combined_response, sources_list)
    """
    # Group Document objects by file_name
    doc_chunks = {}
    for doc in session_docs_list:
        file_name = doc.metadata.get("file_name", "Unknown")
        if file_name not in doc_chunks:
            doc_chunks[file_name] = []
        doc_chunks[file_name].append(doc.page_content)

    if not doc_chunks:
        return None, []

    responses = []
    sources = []

    for doc_name, chunks in doc_chunks.items():
        doc_context = "\n\n".join(chunks)
        prompt = f"""You are a helpful assistant.

You have access to the following document content from "{doc_name}":
{doc_context}

Answer the question below following these rules:
1. Answer ONLY from the document content provided above
2. If the question is not answerable from this document, reply with exactly: NOT_RELEVANT
3. Do NOT mention the word "context" in your answer
4. Answer naturally and helpfully
5. The document content may have been extracted from images, PDFs, or scanned files using OCR — treat it as regular text
6. Never say you cannot view images or files — the text has already been extracted

Question:
{user_message}

Answer:"""

        try:
            answer = llm_call(history + [{"role": "user", "content": prompt}])
            answer = answer.strip()
            if answer and "NOT_RELEVANT" not in answer:
                responses.append(f"{answer}\n\n📄 **Source: {doc_name}**")
                sources.append(doc_name)
        except Exception:
            continue

    if responses:
        return "\n\n---\n\n".join(responses), sources

    return None, []


# -------------------- MAIN CHAT FUNCTION --------------------

def chat(
    user_id,
    session_id,
    user_message,
    vectorstore=None,
    selected_doc="All Documents",
    last_uploaded_doc=None,
    session_docs=None
):
    # Check if this is the first message (for auto title generation)
    is_first_message = get_message_count(user_id, session_id) == 0

    # Get chat history for memory
    history = get_chat_history(user_id, session_id)

    # ✅ Get last standalone question from DB for chaining
    last_standalone = get_last_standalone_question(user_id, session_id)

    if session_docs is None:
        session_docs = []

    # -------------------- STANDALONE QUESTION REWRITING --------------------
    # ✅ Now returns 3 values: standalone_question, needs_clarification, search_doc
    # search_doc is set ONLY when new doc was just uploaded — restricts retrieval to that doc only
    # search_doc is None for all other cases — means search All Documents
    standalone_question, needs_clarification, search_doc = _get_standalone_question(
        user_message=user_message,
        history=history,
        last_standalone=last_standalone,
        last_uploaded_doc=last_uploaded_doc,
        session_docs=session_docs
    )

    # ✅ If clarification needed — return clarification message directly
    if needs_clarification:
        doc_list = ", ".join(session_docs)
        clarification = (
            f"I have multiple documents uploaded: **{doc_list}**. "
            f"Could you please clarify which document you are referring to, "
            f"or ask a more specific question?"
        )
        save_message(user_id, session_id, "user", user_message, standalone_question=user_message)
        save_message(user_id, session_id, "assistant", clarification)
        if is_first_message:
            title = generate_chat_title(user_message)
            rename_session(session_id, title, user_id)
        return clarification, []

    retrieval_query = standalone_question  # always use standalone for retrieval

    # ✅ ONLY restrict to specific doc when new doc was just uploaded (PRIORITY 1)
    # All other cases search All Documents
    retrieval_doc_filter = search_doc if search_doc else "All Documents"

    context = ""
    file_names = []
    context_docs = []  # list of LangChain Document objects

    # -------------------- RAG RETRIEVAL --------------------
    if vectorstore:
        context, context_docs, file_names = get_context_from_query(
            vectorstore,
            retrieval_query,
            user_id,
            session_id,
            retrieval_doc_filter  # ✅ specific doc for new upload, All Docs otherwise
        )

    # -------------------- BUILD PROMPT --------------------
    if context and len(context.strip()) > 20:

        # ✅ Check unique sources from actual Document objects
        unique_sources = list(set(
            doc.metadata.get("file_name", "")
            for doc in context_docs
            if doc.metadata.get("file_name")
        )) if context_docs else []

        if len(unique_sources) > 1 and context_docs:
            # ✅ Multi-doc — separate answers per document with source labels
            response, file_names = _build_multi_doc_answer(
                context_docs, user_message, history
            )
            if not response:
                # Fallback to general if all docs returned NOT_RELEVANT
                response = llm_call(
                    history + [{"role": "user", "content": user_message}]
                )
                file_names = []
        else:
            # Single doc or merged context — existing behavior unchanged
            prompt = f"""You are a helpful assistant.

You have access to the following document content:
{context}

Answer the question below following these rules:
1. If the question is related to the document content above, answer from it
2. If the question is NOT related to the document, answer from your own general knowledge normally
3. Do NOT say you cannot answer or that the context does not contain the information
4. Do NOT mention the word "context" in your answer
5. Answer naturally and helpfully
6. The document content may have been extracted from images, PDFs, or scanned files using OCR — treat it as regular text and answer from it directly
7. Never say you cannot view images or files — the text has already been extracted and is provided above

Question:
{user_message}

Answer:"""
            messages = history + [{"role": "user", "content": prompt}]
            response = llm_call(messages)

    else:
        # No document context — pure normal chat mode
        messages = history + [{"role": "user", "content": user_message}]
        response = llm_call(messages)
        file_names = []

    # -------------------- SAVE TO DB --------------------
    save_message(user_id, session_id, "user", user_message, standalone_question=standalone_question)
    save_message(user_id, session_id, "assistant", response)

    # -------------------- AUTO TITLE GENERATION --------------------
    if is_first_message:
        title = generate_chat_title(user_message)
        rename_session(session_id, title, user_id)

    # -------------------- RETURN --------------------
    sources = (
        list(file_names)
        if (context and len(context.strip()) > 20 and file_names)
        else []
    )
    return response, sources