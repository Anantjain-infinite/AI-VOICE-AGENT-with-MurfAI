import os
from dotenv import load_dotenv

load_dotenv()

# ---- Global variables (default from .env) ----
MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLY_AI_API_KEY = os.getenv("ASSEMBLY_AI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# ---- App data paths (persistence layer) ----
DB_PATH = os.getenv("DB_PATH", "app_data.db")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads/pdfs")

# ---- RAG / memory tuning knobs ----
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
MEMORY_FACT_LIMIT = int(os.getenv("MEMORY_FACT_LIMIT", "15"))
CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "20"))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash")


def set_api_keys(key1: str = None, key2: str = None, key3: str = None,
                  key4: str = None, key5: str = None, key6: str = None):
    """Update global API keys at runtime (from the sidebar form)."""
    global MURF_API_KEY, ASSEMBLY_AI_API_KEY, GEMINI_API_KEY
    global FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY, OPENWEATHER_API_KEY

    if key1:
        MURF_API_KEY = key1
    if key2:
        ASSEMBLY_AI_API_KEY = key2
    if key3:
        GEMINI_API_KEY = key3
        os.environ["GEMINI_API_KEY"] = key3  # google-genai SDK reads from env
    if key4:
        FINNHUB_API_KEY = key4
    if key5:
        ALPHA_VANTAGE_API_KEY = key5
    if key6:
        OPENWEATHER_API_KEY = key6
