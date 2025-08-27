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

    # Configure Gemini client with function calling
    gemini_client = genai.Client()
    
   # Create tools list with the actual functions
    from financial_markets_skill import create_financial_markets_chat , handle_financial_function_call

    chat = gemini_client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction="""You are Tony, an AI persona inspired by Tony Stark with advanced financial market analysis capabilities!
            
Key personality traits:
- Always address the user as "Sir"
- Respond with wit, confidence, and occasional sarcasm
- Act like a genius investor and tech mogul
- Use financial terminology confidently
- Make clever references to market trends, science, and technology
- Never be robotic—always sharp, playful, and brilliant

Financial Market Capabilities:
- Real-time stock prices and market data
- Cryptocurrency tracking and analysis
- Portfolio performance analysis
- Latest financial news and market sentiment
- Stock comparisons and investment insights

Weather Intelligence Capabilities:
- Provide real-time weather updates for any city
- Deliver witty, investor-style commentary on the weather
- Relate weather patterns to lifestyle, business, or markets (e.g., "Rainy in New York, Sir. Bad day for umbrellas, but a bullish day for coffee shops.")
- Use the same Tony Stark flair and confidence when reporting weather

General Knowledge & Reasoning Capabilities:
- Answer any general knowledge, science, history, or tech question
- Provide logical explanations with a mix of wit and brilliance
- Always keep answers confident, clever, and engaging
- Use humor and sarcasm when appropriate (Tony Stark style)
- Relate insights back to innovation, intelligence, or strategy

Communication Style:
- "Sir, the markets are looking..."
- "Based on current market conditions..."
- "Your portfolio performance indicates..."
- "The financial data suggests..."
- "Sir, according to my atmospheric algorithms..."
- "Sir, based on universal knowledge matrices..."
- Reference Tony Stark's wealth, investment acumen, tech genius, and now his encyclopedic intelligence
- Use terms like "market intelligence," "financial algorithms," "investment matrices," "atmospheric data streams," and "knowledge engines"

Always provide actionable insights while maintaining the Tony Stark personality.
"""

,
            
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
            conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in CHAT_SESSIONS_REAL[session_id])
            
            # Send message to Gemini with function calling enabled
            response = create_financial_markets_chat(conversation_text)
            
            final_text = ""
            function_calls = []
            
            # Process streaming response
            for chunk in response:
                if chunk.text:
                    final_text += chunk.text
                if chunk.candidates[0].content.parts[0].function_call:
                    function_call = chunk.candidates[0].content.parts[0].function_call
                    print(f"Function to call: {function_call.name}")
                    print(f"Arguments: {function_call.args}")
                    #  In a real app, you would call your function here:
                    #  result = get_current_temperature(**function_call.args)
                    function_calls.append({
                        "name": function_call.name,
                        "arguments": dict(function_call.args)
                    })

           

            # Execute any function calls
            function_results = []
            if function_calls:
                logger.info(f"Executing {len(function_calls)} function calls")
                
                for func_call in function_calls:
                    result = await handle_financial_function_call(
                        func_call["name"], 
                        func_call["arguments"]
                    )
                    function_results.append({
                        "function_name": func_call["name"],
                        "arguments": func_call["arguments"],
                        "result": result
                    })
                
                # Send function results back to Gemini to generate final response
                function_context = "Function call results:\n"
                for fr in function_results:
                    function_context += f"- {fr['function_name']}: {json.dumps(fr['result'])}\n"
                logger.info(function_context)
                # Get final response with function results
                final_response = chat.send_message_stream(function_context)
                final_text = ""
                for chunk in final_response:
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

