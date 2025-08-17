from fastapi import FastAPI, Request, HTTPException, UploadFile, File , WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from dotenv import load_dotenv
import os

from schema import TTSRequest, TTSResponse, LLMResponse, ChatResponse
from services.stt import transcribe_audio
from services.tts import murf_tts
from services.llm import query_llm
from utils.logger import logger

load_dotenv()


app = FastAPI()

OUTPUT_DIR = "recordings"
os.makedirs(OUTPUT_DIR, exist_ok=True)



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


#Route for websockets

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Create a unique filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = os.path.join(OUTPUT_DIR, f"recording_{timestamp}.webm")
    print(f"Saving to {filename}")

    with open(filename, "wb") as f:
        try:
            while True:
                # Receive raw bytes directly
                audio_chunk = await websocket.receive_bytes()
                f.write(audio_chunk)

        except WebSocketDisconnect:
            print("Client disconnected")

    print(f"Recording saved: {filename}")