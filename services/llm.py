from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def query_llm(messages: list) -> str:
    conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=conversation_text,
        config=types.GenerateContentConfig(system_instruction="Answer in max 10 words")
    )
    return response.text
