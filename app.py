from backend.db import create_tables
from backend.chat import chat, set_vectorstore
from backend.rag import load_and_split, create_or_load_vectorstore
import os

create_tables()

user_id = "user_1"  # TODO: replace with real auth
session_id = 1

file_path = os.path.join(os.getcwd(), "policy_company.pdf")

try:
    chunks = load_and_split(file_path)
    vectorstore = create_or_load_vectorstore(chunks, user_id)
    set_vectorstore(vectorstore)
    print("Document loaded successfully ✅")
except Exception as e:
    print("Error loading document:", e)
    exit()

print("Chatbot started! Type 'exit' to quit.\n")

while True:
    user_input = input("You: ")

    if user_input.lower() == "exit":
        break

    response = chat(user_id, session_id, user_input)
    print("Bot:", response)