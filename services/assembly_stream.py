import asyncio
import logging
from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions, StreamingParameters, StreamingSessionParameters,
    StreamingEvents, StreamingError, BeginEvent, TurnEvent, TerminationEvent
)
from config import ASSEMBLY_AI_API_KEY

from utils.logger import logger

def create_assembly_client(api_key: str, loop, websocket, stream_gemini_response, connected_flag):
    client = StreamingClient( StreamingClientOptions(
        api_key=ASSEMBLY_AI_API_KEY,
        api_host="streaming.assemblyai.com", ) )
    def on_turn(self: StreamingClient, event: TurnEvent):
        if event.end_of_turn and event.turn_is_formatted and connected_flag["value"]:
            logger.info(f"[FINAL] Transcript: {event.transcript}")

            if event.transcript.strip():
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    websocket.send_text(event.transcript)
                )
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    stream_gemini_response(event.transcript)
                )

        if event.end_of_turn and not event.turn_is_formatted:
            params = StreamingSessionParameters(format_turns=True)
            self.set_params(params)

    def on_begin(self: StreamingClient, event: BeginEvent):
        logger.info(f"AssemblyAI session started: {event.id}")

    def on_terminated(self: StreamingClient, event: TerminationEvent):
        logger.info(f"AssemblyAI session terminated after {event.audio_duration_seconds:.2f}s")

    def on_error(self: StreamingClient, error: StreamingError):
        logger.error(f"AssemblyAI streaming error: {error}")

    client.on(StreamingEvents.Begin, on_begin)
    client.on(StreamingEvents.Turn, on_turn)
    client.on(StreamingEvents.Termination, on_terminated)
    client.on(StreamingEvents.Error, on_error)

    client.connect(
        StreamingParameters(sample_rate=16000, format_turns=True)
    )
    return client
