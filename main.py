from fastapi import FastAPI, Request, HTTPException, UploadFile, File , WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from dotenv import load_dotenv
import os
import time
import random
import aiohttp
from google import genai
from google.genai import types
import websockets
import json
import config
from config import GEMINI_API_KEY , ASSEMBLY_AI_API_KEY , MURF_API_KEY
from schema import TTSRequest, TTSResponse, LLMResponse, ChatResponse
from services.stt import transcribe_audio
from services.tts import murf_tts
from services.llm import query_llm
from utils.logger import logger
import os, asyncio
from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions, StreamingParameters, StreamingSessionParameters,
    StreamingEvents, StreamingError, BeginEvent, TurnEvent, TerminationEvent
)
from services.assembly_stream import create_assembly_client
from services.gemini_stream import init_gemini_client, create_tony_stark_chat, process_gemini_response
from services.murf_stream import stream_murf_tts

load_dotenv()



app = FastAPI()

OUTPUT_DIR = "recordings"
os.makedirs(OUTPUT_DIR, exist_ok=True)
ASSEMBLY_API_KEY = ASSEMBLY_AI_API_KEY
MURF_API_KEY = MURF_API_KEY
MURF_WS_URL = "wss://api.murf.ai/v1/speech/stream-input"




app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


#global in-python dict for storing chat history
CHAT_SESSIONS = {}
CHAT_SESSIONS_REAL = {}


@app.post("/get-api-keys")
async def set_api_keys(request: Request):

    try:
        data = await request.json()

        # Client-provided keys (or None if not provided)
        key1 = data.get("api_key_1")
        key2 = data.get("api_key_2")
        key3 = data.get("api_key_3")
        key4 = data.get("api_key_4")
        key5 = data.get("api_key_5")
        key6 = data.get("api_key_6")

        # Update global keys (fallback to existing ones in config)
        config.set_api_keys(key1 , key2 , key3, key4 , key5, key6)

        return {
        "success" :"true"
        }
    except Exception as e:
            logger.error(f"Error while configuration: {e}", exc_info=True)


#Route : to serve HTML page
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


#Route: for Text to Speech
@app.post("/generate-audio", response_model=TTSResponse)
def generate_audio(req: TTSRequest):
    audio_url = murf_tts(req.text)
    return {"audio_url": audio_url}


#Route : for speech to text
@app.post("/transcribe/file")
async def transcribe_file(file: UploadFile = File(...)):
    audio_data = await file.read()
    transcription = transcribe_audio(audio_data)
    return {"transcription": transcription}


#Route: for generating response from LLM
@app.post("/agent/chat/{session_id}", response_model=ChatResponse)
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    audio_bytes = await file.read()
    transcription = transcribe_audio(audio_bytes)

    if session_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[session_id] = []

    CHAT_SESSIONS[session_id].append({"role": "user", "content": transcription})
    llm_reply = query_llm(CHAT_SESSIONS[session_id])
    CHAT_SESSIONS[session_id].append({"role": "assistant", "content": llm_reply})

    audio_url = murf_tts(llm_reply)
    return {"transcription": transcription, "reply": llm_reply, "audio_url": audio_url}


#Route: for websocket
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected for session: {session_id}")
    connected_flag = {"value": True}

    if session_id not in CHAT_SESSIONS_REAL:
        CHAT_SESSIONS_REAL[session_id] = []

    loop = asyncio.get_event_loop()
    gemini_client = init_gemini_client()
    chat = create_tony_stark_chat(gemini_client)

    context_id = f"ctx_{int(time.time())}_{random.randint(1000, 9999)}"
    logger.info(f"Generated context ID: {context_id}")

    async def stream_gemini_response(transcript: str):
        try:
            await process_gemini_response(
                session_id,
                transcript,
                chat,
                websocket,
                lambda text, ws=websocket: stream_murf_tts(
                    text, ws, MURF_WS_URL, MURF_API_KEY, context_id
                ),
                CHAT_SESSIONS_REAL,
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
        client = create_assembly_client(
            ASSEMBLY_API_KEY, loop, websocket, stream_gemini_response, connected_flag
        )
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
        logger.info("Streaming session closed")
