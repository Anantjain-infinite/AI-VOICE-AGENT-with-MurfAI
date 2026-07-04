from pydantic import BaseModel
from typing import List, Optional


# ---- Existing voice/chat schemas ----
class TTSRequest(BaseModel):
    text: str


class TTSResponse(BaseModel):
    audio_url: str


class TranscriptionResponse(BaseModel):
    transcription: str


class LLMResponse(BaseModel):
    response: str
    audio_url: str


class ChatResponse(BaseModel):
    transcription: str
    reply: str
    audio_url: str


# ---- RAG schemas ----
class RagUploadResponse(BaseModel):
    doc_id: str
    filename: str
    chunks_indexed: int


class RagChatRequest(BaseModel):
    question: str


class RagSource(BaseModel):
    doc_id: str
    filename: str
    page: int


class RagChatResponse(BaseModel):
    answer: str
    sources: List[RagSource]


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int
    uploaded_at: str


# ---- Memory schemas ----
class MemoryFact(BaseModel):
    id: int
    fact: str
    category: str
    created_at: str


class MemoryListResponse(BaseModel):
    user_id: str
    facts: List[MemoryFact]
