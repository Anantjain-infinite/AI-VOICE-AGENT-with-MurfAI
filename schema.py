from pydantic import BaseModel

class TTSRequest(BaseModel):
    text: str

class GeminiRequest(BaseModel):
    content: str

class TranscriptionResponse(BaseModel):
    transcription: str

class TTSResponse(BaseModel):
    audio_url: str

class LLMResponse(BaseModel):
    response: str
    audio_url: str

class ChatResponse(BaseModel):
    transcription: str
    reply: str
    audio_url: str
