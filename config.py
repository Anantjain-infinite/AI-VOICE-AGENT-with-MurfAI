import os
from dotenv import load_dotenv

load_dotenv()

# Global variables (default from .env)
MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLY_AI_API_KEY =os.getenv("ASSEMBLY_AI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FINNHUB_API_KEY=os.getenv("FINNHUB_API_KEY")
ALPHA_VANTAGE_API_KEY=os.getenv("ALPHA_VANTAGE_API_KEY")
OPENWEATHER_API_KEY=os.getenv("OPENWEATHER_API_KEY")

def set_api_keys(key1: str = None, key2: str = None,  key3: str = None , key4: str = None,  key5: str = None,  key6: str = None):
    """Update global API keys at runtime"""
    global MURF_API_KEY, ASSEMBLY_AI_API_KEY,GEMINI_API_KEY,FINNHUB_API_KEY,ALPHA_VANTAGE_API_KEY,OPENWEATHER_API_KEY
    if key1:
        MURF_API_KEY = key1
    if key2:
        ASSEMBLY_AI_API_KEY = key2
    if key3:
        GEMINI_API_KEY = key3
    if key4:
        FINNHUB_API_KEY = key4
    if key5:
        ALPHA_VANTAGE_API_KEY = key5
    if key6:
        OPENWEATHER_API_KEY = key6