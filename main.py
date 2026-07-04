from fastapi import FastAPI, Request, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import time
import random
import uuid
import asyncio

import config
from schema import (
    TTSRequest, TTSResponse, ChatResponse,
    RagUploadResponse, RagChatRequest, RagChatResponse, DocumentInfo,
    MemoryListResponse,
)
from services.stt import transcribe_audio
from services.tts import murf_tts
from services.llm_service import query_llm
from services import session_store, db
from services.db import get_conn
from utils.logger import logger

from services.assembly_stream import create_assembly_client
from services.gemini_stream import init_gemini_client, create_assistant_chat, process_gemini_response
from services.murf_stream import stream_murf_tts

from services.rag.pdf_processor import extract_and_chunk
from services.rag.vector_store import add_chunks, delete_document
from services.rag.rag_chat import rag_answer

from services.memory.memory_store import get_facts, delete_fact
from services.memory.memory_extractor import extract_and_store_new_facts

app = FastAPI()

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(config.UPLOAD_DIR, exist_ok=True)

MURF_WS_URL = "wss://api.murf.ai/v1/speech/stream-input"

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/health")
async def health_check():
    """Lightweight endpoint for uptime monitors (UptimeRobot, etc.) — avoids
    hitting the full UI/template render or a DB query just to check liveness."""
    return {"status": "ok"}

@app.on_event("startup")
def on_startup():
    db.init_db()
    logger.info("Database initialized")


# ---------------------------------------------------------------------------
# API key configuration
# ---------------------------------------------------------------------------
@app.post("/get-api-keys")
async def set_api_keys(request: Request):
    try:
        data = await request.json()
        config.set_api_keys(
            data.get("api_key_1"), data.get("api_key_2"), data.get("api_key_3"),
            data.get("api_key_4"), data.get("api_key_5"), data.get("api_key_6"),
        )
        return {"success": True}
    except Exception as e:
        logger.error(f"Error while configuring API keys: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to configure API keys")


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# Core voice endpoints (TTS / STT)
# ---------------------------------------------------------------------------
@app.post("/generate-audio", response_model=TTSResponse)
def generate_audio(req: TTSRequest):
    audio_url = murf_tts(req.text)
    return {"audio_url": audio_url}


@app.post("/transcribe/file")
async def transcribe_file(file: UploadFile = File(...)):
    audio_data = await file.read()
    transcription = transcribe_audio(audio_data)
    return {"transcription": transcription}


# ---------------------------------------------------------------------------
# HTTP chat (transcribe -> LLM w/ tools & memory -> TTS)
# ---------------------------------------------------------------------------
@app.post("/agent/chat/{session_id}", response_model=ChatResponse)
async def agent_chat(session_id: str, file: UploadFile = File(...), user_id: str = None, request: Request = None):
    audio_bytes = await file.read()
    transcription = transcribe_audio(audio_bytes)

    user_ip = request.client.host if request and request.client else "unknown"
    logger.info(f"Transcript from IP {user_ip} (session {session_id}): {transcription}")

    session_store.append_message(session_id, "user", transcription)
    history = session_store.get_history(session_id)
    llm_reply = await query_llm(history, user_id=user_id)
    session_store.append_message(session_id, "assistant", llm_reply)

    audio_url = murf_tts(llm_reply)
    return {"transcription": transcription, "reply": llm_reply, "audio_url": audio_url}


# ---------------------------------------------------------------------------
# RAG: PDF upload + document Q&A
# ---------------------------------------------------------------------------
@app.post("/rag/upload/{session_id}", response_model=RagUploadResponse)
async def upload_pdf(session_id: str, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    doc_id = str(uuid.uuid4())
    file_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}.pdf")

    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        chunks = extract_and_chunk(file_path)
        if not chunks:
            raise HTTPException(status_code=400, detail="Couldn't extract any text from this PDF")

        add_chunks(session_id, doc_id, file.filename, chunks)

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO documents (doc_id, session_id, filename, chunk_count) VALUES (?, ?, ?, ?)",
                (doc_id, session_id, file.filename, len(chunks))
            )

        return {"doc_id": doc_id, "filename": file.filename, "chunks_indexed": len(chunks)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process PDF")


@app.post("/rag/chat/{session_id}", response_model=RagChatResponse)
async def rag_chat_endpoint(session_id: str, req: RagChatRequest):
    result = rag_answer(session_id, req.question)
    return result


@app.get("/rag/documents/{session_id}")
async def list_documents(session_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT doc_id, filename, chunk_count, uploaded_at FROM documents WHERE session_id = ? ORDER BY uploaded_at DESC",
            (session_id,)
        ).fetchall()
    return {"documents": [dict(r) for r in rows]}


@app.delete("/rag/documents/{session_id}/{doc_id}")
async def delete_document_endpoint(session_id: str, doc_id: str):
    delete_document(session_id, doc_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE doc_id = ? AND session_id = ?", (doc_id, session_id))

    file_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}.pdf")
    if os.path.exists(file_path):
        os.remove(file_path)

    return {"success": True}


# ---------------------------------------------------------------------------
# Memory: view / delete long-term facts
# ---------------------------------------------------------------------------
@app.get("/memory/{user_id}", response_model=MemoryListResponse)
async def get_memory(user_id: str):
    facts = get_facts(user_id)
    return {"user_id": user_id, "facts": [
        {"id": f["id"], "fact": f["fact"], "category": f["category"], "created_at": str(f["created_at"])}
        for f in facts
    ]}


@app.delete("/memory/{user_id}/{fact_id}")
async def delete_memory_fact(user_id: str, fact_id: int):
    deleted = delete_fact(user_id, fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"success": True}


# ---------------------------------------------------------------------------
# WebSocket: real-time streaming voice chat
# ---------------------------------------------------------------------------
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    user_id = websocket.query_params.get("user_id")
    logger.info(f"WebSocket connected for session: {session_id} (user_id={user_id})")
    connected_flag = {"value": True}

    user_ip = getattr(websocket.client, "host", "unknown")
    logger.info(f"WebSocket session {session_id} from IP {user_ip}")

    loop = asyncio.get_event_loop()
    gemini_client = init_gemini_client()
    chat = create_assistant_chat(gemini_client, user_id=user_id)

    context_id = f"ctx_{int(time.time())}_{random.randint(1000, 9999)}"
    logger.info(f"Generated context ID: {context_id}")

    async def on_final_transcript(transcript: str):
        logger.info(f"Transcript from IP {user_ip}: {transcript}")
        try:
            await process_gemini_response(
                session_id,
                transcript,
                chat,
                websocket,
                lambda text, ws=websocket: stream_murf_tts(
                    text, ws, MURF_WS_URL, config.MURF_API_KEY, context_id
                ),
            )
        except Exception as e:
            logger.error(f"Error while processing Gemini response: {e}", exc_info=True)
            try:
                await websocket.send_json({
                    "status": "error",
                    "message": "AI response generation failed",
                    "context_id": context_id,
                })
            except Exception:
                logger.warning("Failed to notify client about Gemini error")

    try:
        client = create_assembly_client(loop, websocket, on_final_transcript, connected_flag)
    except Exception as e:
        logger.error(f"Failed to initialize AssemblyAI client: {e}", exc_info=True)
        await websocket.send_json({
            "status": "error",
            "message": "Failed to initialize speech-to-text service",
            "context_id": context_id,
        })
        return

    try:
        while True:
            try:
                audio_chunk = await websocket.receive_bytes()
                client.stream(audio_chunk)
            except WebSocketDisconnect:
                logger.info("Client disconnected")
                break
            except Exception as e:
                logger.error(f"Error while streaming audio: {e}", exc_info=True)
                await websocket.send_json({
                    "status": "error",
                    "message": "Audio streaming failed",
                    "context_id": context_id,
                })
                break
    finally:
        connected_flag["value"] = False
        try:
            client.disconnect(terminate=True)
        except Exception as e:
            logger.warning(f"Error while disconnecting AssemblyAI client: {e}")

        # Mine this session's new turns for long-term memory facts.
        if user_id:
            try:
                new_facts = extract_and_store_new_facts(session_id, user_id)
                if new_facts:
                    logger.info(f"Stored {len(new_facts)} new memory facts for user {user_id}")
            except Exception as e:
                logger.warning(f"Memory extraction failed on disconnect: {e}")

        logger.info("Streaming session closed")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
