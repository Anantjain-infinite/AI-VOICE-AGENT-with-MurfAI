import requests
import os
from dotenv import load_dotenv
from config import MURF_API_KEY

load_dotenv()

MURF_API_KEY = MURF_API_KEY
MURF_TTS_URL = "https://api.murf.ai/v1/speech/generate"

def murf_tts(text: str, voice_id="en-IN-rohan", fmt="MP3", style=None) -> str:
    headers = {
        "Authorization": f"Bearer {MURF_API_KEY}",
        "Content-Type": "application/json",
        "api-key": MURF_API_KEY
    }
    payload = {"text": text, "voiceId": voice_id, "format": fmt}
    if style:
        payload["style"] = style

    r = requests.post(MURF_TTS_URL, headers=headers, json=payload)
    if r.status_code != 200:
        raise RuntimeError(f"Murf TTS error: {r.status_code} {r.text}")
    return r.json().get("audioFile")
