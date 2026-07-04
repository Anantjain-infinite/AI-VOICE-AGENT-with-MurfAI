import asyncio
from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions, StreamingParameters, StreamingSessionParameters,
    StreamingEvents, StreamingError, BeginEvent, TurnEvent, TerminationEvent
)
import config
from utils.logger import logger


def create_assembly_client(loop, websocket, on_final_transcript, connected_flag):
    """
    on_final_transcript: async callable invoked with the finalized transcript
    text once AssemblyAI marks a turn as complete and formatted.
    """
    client = StreamingClient(StreamingClientOptions(
        api_key=config.ASSEMBLY_AI_API_KEY,
        api_host="streaming.assemblyai.com",
    ))

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
                    on_final_transcript(event.transcript)
                )

        if event.end_of_turn and not event.turn_is_formatted:
            self.set_params(StreamingSessionParameters(format_turns=True))

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

    client.connect(StreamingParameters(sample_rate=16000, format_turns=True))
    return client
