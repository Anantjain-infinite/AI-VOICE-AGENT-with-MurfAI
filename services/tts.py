import requests
import config
from utils.logger import logger

MURF_TTS_URL = "https://api.murf.ai/v1/speech/generate"


def murf_tts(text: str, voice_id: str = "en-IN-rohan", fmt: str = "MP3", style: str = None) -> str:
    """
    NOTE: reads config.MURF_API_KEY at call time (not import time) so that
    keys updated via the /get-api-keys sidebar form actually take effect.
    The original code captured MURF_API_KEY into a local module-level
    constant at import time, so runtime key updates from the sidebar never
    reached this function.
    """
    headers = {
        "Authorization": f"Bearer {config.MURF_API_KEY}",
        "Content-Type": "application/json",
        "api-key": config.MURF_API_KEY,
    }
    payload = {"text": text, "voiceId": voice_id, "format": fmt}
    if style:
        payload["style"] = style

    r = requests.post(MURF_TTS_URL, headers=headers, json=payload)
    if r.status_code != 200:
        logger.error(f"Murf TTS error: {r.status_code} {r.text}")
        raise RuntimeError(f"Murf TTS error: {r.status_code} {r.text}")
    return r.json().get("audioFile")
