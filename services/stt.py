import assemblyai as aai
import os
from dotenv import load_dotenv

load_dotenv()

aai.settings.api_key = os.getenv("ASSEMBLY_AI_API_KEY")

def transcribe_audio(audio_bytes: bytes) -> str:
    config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_bytes)

    if transcript.status == "error":
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")

    return transcript.text
