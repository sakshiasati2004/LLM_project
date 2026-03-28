import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ✅ Validate API key at startup — fail loud, not silent
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY is not set in .env file!")

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)


def llm_call(messages: list) -> str:
    """Main LLM call for chat responses"""
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"Error from LLM: {str(e)}"


def generate_chat_title(first_message: str) -> str:
    """
    ✅ Generates a short ChatGPT-style title from the first user message.
    Called only once — when the first message is sent in a new session.
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a short 4-6 word title for a chat conversation "
                        "that starts with the message below.\n"
                        "Rules:\n"
                        "- Reply with ONLY the title\n"
                        "- No quotes, no punctuation, no explanation\n"
                        "- Make it descriptive and meaningful\n\n"
                        f"Message: {first_message}"
                    )
                }
            ],
            max_tokens=20,
            temperature=0.5,
        )
        title = response.choices[0].message.content.strip()

        # ✅ Fallback if LLM returns empty or too long
        if not title or len(title) > 60:
            return " ".join(first_message.split()[:5])

        return title

    except Exception:
        # ✅ Safe fallback — never crash the chat just for a title
        return " ".join(first_message.split()[:5])