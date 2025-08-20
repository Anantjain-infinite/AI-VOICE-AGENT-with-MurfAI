from fastapi import FastAPI, Request, HTTPException, UploadFile, File , WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from dotenv import load_dotenv
import os
from google import genai
from google.genai import types


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




app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


#global in-python dict for storing chat history
CHAT_SESSIONS = {}

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
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connected")
    connected = True   

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
    chat = gemini_client.chats.create(model="gemini-2.5-flash",
                                      config=types.GenerateContentConfig(system_instruction="Keep your response short and to the point")
                                      
                                      )  

    async def stream_gemini_response(transcript: str):
        logger.info(f"Sending transcript to Gemini: {transcript}")
        try:
            final_text = ""
            # Stream Gemini response
            
            response = chat.send_message_stream(transcript)

            for chunk in response:
                if chunk.text:
                    # print(chunk.text, end="", flush=True)
                    final_text += chunk.text

            print("\n--- Gemini Response Begin ---\n")   

            logger.info(f"Gemini Final Response: {final_text}")

            print("\n--- Gemini Response End ---\n")

        except Exception as e:
            logger.error(f"Error while streaming Gemini response: {e}", exc_info=True)

    def on_turn(self: StreamingClient, event: TurnEvent):
        if event.end_of_turn and event.turn_is_formatted and connected:
            logger.info(f"[FINAL] Transcript: {event.transcript}")
            # Send final transcript to browser
            if connected:
                loop.call_soon_threadsafe(
                    asyncio.create_task, websocket.send_text(event.transcript)
                )
                loop.create_task(stream_gemini_response(event.transcript))


        # Optional: request formatted turns if needed
        if event.end_of_turn and not event.turn_is_formatted:
            params = StreamingSessionParameters(format_turns=True)
            self.set_params(params)

    def on_begin(self: StreamingClient, event: BeginEvent):
            logger.info(f"Session started: {event.id}")

    def on_terminated(self: StreamingClient, event: TerminationEvent):
        logger.info(f"Session terminated after {event.audio_duration_seconds:.2f}s")

    def on_error(self: StreamingClient, error: StreamingError):
        logger.error(f"Streaming error: {error}")

    # Register async handlers
    client.on(StreamingEvents.Begin, on_begin)
    client.on(StreamingEvents.Turn, on_turn)
    client.on(StreamingEvents.Termination, on_terminated)
    client.on(StreamingEvents.Error, on_error)

    client.connect(
        StreamingParameters(
            sample_rate=16000,
            format_turns=True,
        )
    )

    try:
        while True:
            audio_chunk = await websocket.receive_bytes()
            client.stream(audio_chunk)

    except WebSocketDisconnect:
        logger.info("Client disconnected")
   
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
   
    finally:
        connected = False   
        client.disconnect(terminate=True)
        logger.info("Streaming session closed")