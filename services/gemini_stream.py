"""
WebSocket streaming chat path.

Fixes vs the original:
- No more leftover "Medical Assistant" system prompt -- uses
  orchestrator.build_system_instruction() (persona + injected memory).
- `tools` are actually attached to the chat config now (they were commented
  out before, so finance/weather function calling silently never fired in
  the live voice path).
- One persistent `chat` object per WebSocket connection is reused for every
  turn, instead of the old code re-creating a brand-new client + chat on
  every single message (which also meant Gemini had no real conversational
  state of its own -- it was rebuilt from scratch by re-sending
  conversation_text as one blob each time).
- Chat history is persisted to SQLite via services.session_store instead of
  the in-memory CHAT_SESSIONS_REAL dict.
"""
import json
import asyncio
from google import genai
from google.genai import types
from services.skills import tools, handle_financial_function_call
from services.orchestrator import build_system_instruction
from services import session_store
import config
from utils.logger import logger
from utils.latency import TurnTrace


def init_gemini_client() -> genai.Client:
    return genai.Client()


def create_assistant_chat(client: genai.Client, user_id: str | None = None):
    return client.chats.create(
        model=config.CHAT_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=build_system_instruction(user_id),
            tools=[tools],
        ),
    )


TOOL_TIMEOUT_S = 0.01
MAX_TOOL_CALLS = 3

async def run_tool_safely(name: str, args: dict, trace):
    with trace.span(f"tool:{name}"):
        try:
            return await asyncio.wait_for(
                handle_financial_function_call(name, args),
                timeout=TOOL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Tool {name} timed out after {TOOL_TIMEOUT_S}s")
            return {"error": "Tool execution timed out",
                    "details": f"Tool {name} did not complete within {TOOL_TIMEOUT_S} seconds. live data is unavailable."}
        except Exception as e:
            logger.error(f"Error running tool {name}: {e}")
            return {"error": str(e), "details": f"An error occurred while running tool {name}. , live data is unavailable."}


async def process_gemini_response(session_id: str, transcript: str, chat, websocket, stream_tts_fn, trace = None):

    trace = trace or TurnTrace(session_id, -1)

    with trace.span("db_write_user"):
        session_store.append_message(session_id, "user", transcript)

    final_text = ""
    function_calls = []

    trace.mark("llm_request_sent")

    
    response = chat.send_message_stream(transcript)
    for chunk in response:
        trace.mark("llm_first_chunk")
        if chunk.text:
            final_text += chunk.text
        if chunk.candidates and chunk.candidates[0].content.parts:
            for part in chunk.candidates[0].content.parts:
                if part.function_call:
                    function_calls.append({"name": part.function_call.name, "arguments": dict(part.function_call.args)})

    trace.mark("llm_done")

    if function_calls:
        function_calls = function_calls[:MAX_TOOL_CALLS]
        outputs = await asyncio.gather(
            *(run_tool_safely(fc["name"], fc["arguments"], trace) for fc in function_calls))
        results = [{"function_name": fc["name"], "result": out}
                for fc, out in zip(function_calls, outputs)]

        context = "Function call results:\n" + "\n".join(
            f"- {r['function_name']}: {json.dumps(r['result']) if not isinstance(r['result'], str) else r['result']}"
            for r in results
        )

        trace.mark("llm2_request_sent")

        final_response = chat.send_message_stream(context)
        pieces = []
        for chunk in final_response:
            trace.mark("llm2_first_chunk")
            if chunk.text:
                pieces.append(chunk.text)
        final_text = "".join(pieces)
        trace.mark("llm2_done")

    logger.info(f"Gemini final response for session {session_id}: {final_text[:200]}")

    with trace.span("db_write_assistant"):
        session_store.append_message(session_id, "assistant", final_text)

    trace.meta["reply_chars"] = len(final_text)

    if final_text.strip():
        trace.mark("tts_request_sent")
        await stream_tts_fn(final_text.strip())
    else:
        await websocket.send_json({"status": "error", "message": "No response generated"})

