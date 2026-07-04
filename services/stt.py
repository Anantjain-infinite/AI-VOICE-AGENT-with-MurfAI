import assemblyai as aai
import config
from utils.logger import logger


def transcribe_audio(audio_bytes: bytes) -> str:
    aai.settings.api_key = config.ASSEMBLY_AI_API_KEY
    transcription_config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
    transcriber = aai.Transcriber(config=transcription_config)
    transcript = transcriber.transcribe(audio_bytes)

    if transcript.status == "error":
        logger.error(f"AssemblyAI transcription error: {transcript.error}")
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")

    return transcript.text
