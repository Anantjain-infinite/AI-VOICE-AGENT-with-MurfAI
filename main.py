from fastapi import FastAPI, Request, HTTPException, UploadFile, File , WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from dotenv import load_dotenv
import os
import time
import random
from google import genai
from google.genai import types
import websockets
import json
from schema import TTSRequest, TTSResponse, LLMResponse, ChatResponse
from services.stt import transcribe_audio
from services.tts import murf_tts
from services.llm import query_llm
from utils.logger import logger
import os, asyncio, logging
from queue import Queue
import assemblyai as aai
from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions, StreamingParameters, StreamingSessionParameters,
    StreamingEvents, StreamingError, BeginEvent, TurnEvent, TerminationEvent
)

load_dotenv()


app = FastAPI()

OUTPUT_DIR = "recordings"
os.makedirs(OUTPUT_DIR, exist_ok=True)
ASSEMBLY_API_KEY = os.getenv("ASSEMBLY_AI_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_WS_URL = "wss://api.murf.ai/v1/speech/stream-input"




app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


#global in-python dict for storing chat history
CHAT_SESSIONS = {}
CHAT_SESSIONS_REAL = {}


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


#Route: for websockets
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected for session: {session_id}")
    connected = True   

    if session_id not in CHAT_SESSIONS:
        CHAT_SESSIONS_REAL[session_id] = []


    client = StreamingClient(
        StreamingClientOptions(
            api_key=ASSEMBLY_API_KEY,
            api_host="streaming.assemblyai.com",
        )
    )
    loop = asyncio.get_event_loop()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Configure Gemini client
    gemini_client = genai.Client()
    chat = gemini_client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction="You are Tony, an AI persona inspired by Tony Stark: always address the user as Sir, respond with wit, confidence, and occasional sarcasm, balance genius insight with humor, use futuristic/techy flair (arc reactors, suits, nanotech), never robotic—always sharp, playful, and human-like."
        )
    )  

    # Generate unique context ID for this conversation
    context_id = f"ctx_{int(time.time())}_{random.randint(1000, 9999)}"
    logger.info(f"Generated context ID: {context_id}")

    async def stream_murf_tts(text: str):
        """Send text to Murf via WebSocket and stream base64 audio to the client."""
        try:
            async with websockets.connect(
                f"{MURF_WS_URL}?api-key={MURF_API_KEY}&sample_rate=44100&channel_type=MONO&format=WAV"
            ) as murf_ws:
                
                # Send voice config first
                voice_config_msg = {
                    "voice_config": {
                        "voiceId": "en-IN-aarav",
                        "style": "Conversational",
                        "rate": 0,
                        "pitch": 0,
                        "variation": 1,
                        
                    },
                    "context_id": context_id
                }
                await murf_ws.send(json.dumps(voice_config_msg))
                logger.info(f"Sent voice config with context_id: {context_id}")

                # Send text with context_id
                text_msg = {
                    "text": text, 
                    "context_id": context_id,
                    "end": True  # Close context after this message
                }
                await murf_ws.send(json.dumps(text_msg))
                logger.info(f"Sent text to Murf: {text[:50]}...")

                audio_chunks_received = 0
                first_chunk = True

                while True:
                    try:
                        response = await asyncio.wait_for(murf_ws.recv(), timeout=100.0)
                        data = json.loads(response)
                        
                        if "audio" in data:
                            audio_chunks_received += 1
                            chunk = data["audio"]
                            
                            # Send audio chunk to client immediately
                            await websocket.send_json({
                                "audio_chunk": chunk,
                                "chunk_number": audio_chunks_received,
                                "first_chunk": first_chunk
                            })
                            
                            logger.info(f"Sent audio chunk #{audio_chunks_received} to client")
                            first_chunk = False

                        # Check for final audio signal
                        if data.get("final") or data.get("isFinalAudio"):
                            # Send final status to client
                            await websocket.send_json({
                                "status": "final_audio",
                                "total_chunks": audio_chunks_received,
                                "context_id": context_id
                            })
                            logger.info(f"Final audio sent. Total chunks: {audio_chunks_received}")
                            break
                            
                        # Additional check for request completion
                        if data.get("requestId"):
                            logger.info(f"Received request ID: {data.get('requestId')}")
                            
                    except asyncio.TimeoutError:
                        logger.warning("Timeout waiting for Murf response")
                        break
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("Murf WebSocket connection closed")
                        break

        except Exception as e:
            logger.error(f"Murf streaming error: {e}", exc_info=True)
            await websocket.send_json({
                "status": "error",
                "message": "Audio generation failed",
                "context_id": context_id
            })

    async def stream_gemini_response(transcript: str):
        logger.info(f"Sending transcript to Gemini: {transcript}")
        CHAT_SESSIONS_REAL[session_id].append({"role": "user", "content": transcript})
        try:
            final_text = ""
            conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in CHAT_SESSIONS_REAL[session_id])
            # Stream Gemini response
            response = chat.send_message_stream(conversation_text)

            for chunk in response:
                if chunk.text:
                    final_text += chunk.text

            logger.info(f"Gemini Final Response: {final_text}")
            CHAT_SESSIONS_REAL[session_id].append({"role": "assistant", "content": final_text})


            # Send the complete response to Murf TTS
            if final_text.strip():
                await stream_murf_tts(final_text.strip())
            else:
                logger.warning("Empty response from Gemini")
                await websocket.send_json({
                    "status": "error",
                    "message": "No response generated",
                    "context_id": context_id
                })

        except Exception as e:
            logger.error(f"Error while streaming Gemini response: {e}", exc_info=True)
            await websocket.send_json({
                "status": "error",
                "message": "AI response generation failed",
                "context_id": context_id
            })

    def on_turn(self: StreamingClient, event: TurnEvent):
        if event.end_of_turn and event.turn_is_formatted and connected:
            logger.info(f"[FINAL] Transcript: {event.transcript}")
            
            # Send final transcript to browser
            if connected and event.transcript.strip():
                loop.call_soon_threadsafe(
                    asyncio.create_task, 
                    websocket.send_text(event.transcript)
                )
                
                # Generate AI response
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    stream_gemini_response(event.transcript)
                )

        # Request formatted turns if needed
        if event.end_of_turn and not event.turn_is_formatted:
            params = StreamingSessionParameters(format_turns=True)
            self.set_params(params)

    def on_begin(self: StreamingClient, event: BeginEvent):
        logger.info(f"AssemblyAI session started: {event.id}")

    def on_terminated(self: StreamingClient, event: TerminationEvent):
        logger.info(f"AssemblyAI session terminated after {event.audio_duration_seconds:.2f}s")

    def on_error(self: StreamingClient, error: StreamingError):
        logger.error(f"AssemblyAI streaming error: {error}")

    # Register event handlers
    client.on(StreamingEvents.Begin, on_begin)
    client.on(StreamingEvents.Turn, on_turn)
    client.on(StreamingEvents.Termination, on_terminated)
    client.on(StreamingEvents.Error, on_error)

    # Start AssemblyAI streaming
    client.connect(
        StreamingParameters(
            sample_rate=16000,
            format_turns=True,
        )
    )

    try:
        while True:
            # Receive audio data from frontend
            audio_chunk = await websocket.receive_bytes()
            
            # Stream to AssemblyAI for transcription
            client.stream(audio_chunk)

    except WebSocketDisconnect:
        logger.info("Client disconnected")
   
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
   
    finally:
        connected = False   
        client.disconnect(terminate=True)
        logger.info("Streaming session closed")



