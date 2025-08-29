import json
import logging
import websockets
import asyncio

from utils.logger import logger

async def stream_murf_tts(text: str, websocket, murf_ws_url, murf_api_key, context_id):
    try:
        async with websockets.connect(
            f"{murf_ws_url}?api-key={murf_api_key}&sample_rate=44100&channel_type=MONO&format=WAV"
        ) as murf_ws:
            await murf_ws.send(json.dumps({
                "voice_config": {
                    "voiceId": "en-IN-aarav",
                    "style": "Conversational",
                    "rate": 0, "pitch": 0, "variation": 1,
                },
                "context_id": context_id
            }))

            await murf_ws.send(json.dumps({
                "text": text, "context_id": context_id, "end": True
            }))

            chunk_no, first_chunk = 0, True
            while True:
                try:
                    resp = await asyncio.wait_for(murf_ws.recv(), timeout=100.0)
                    data = json.loads(resp)
                    if "audio" in data:
                        chunk_no += 1
                        await websocket.send_json({
                            "audio_chunk": data["audio"],
                            "chunk_number": chunk_no,
                            "first_chunk": first_chunk
                        })
                        first_chunk = False
                    if data.get("final") or data.get("isFinalAudio"):
                        await websocket.send_json({
                            "status": "final_audio", "total_chunks": chunk_no, "context_id": context_id
                        })
                        break
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for Murf response")
                    break
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Murf WebSocket connection closed")
                    break
    except Exception as e:
        logger.error(f"Murf streaming error: {e}", exc_info=True)
        await websocket.send_json({"status": "error", "message": "Audio generation failed"})
