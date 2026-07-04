"""
Single source of truth for:
1. The assistant's system prompt (previously a leftover "Medical Assistant"
   prompt was duplicated across gemini_stream.py and skills.py -- fixed here).
2. Injecting long-term memory facts into that prompt.
3. Running the Gemini function-calling loop (finance/weather tools) so both
   the WebSocket streaming path and the plain HTTP chat path share one
   implementation instead of two divergent ones.
"""
import json
from google import genai
from google.genai import types
import config
from services.skills import tools, handle_financial_function_call
from services.memory.memory_store import get_facts
from utils.logger import logger

BASE_SYSTEM_PROMPT = """You are a helpful, concise voice assistant.

You can help with general conversation, and you have live tools available for:
- Stock and cryptocurrency prices, comparisons, and portfolio analysis
- Current weather and short-term forecasts for any location

Use those tools whenever a question calls for current data instead of guessing.
Keep spoken responses natural and reasonably short, since they will be converted to speech.
"""


def build_system_instruction(user_id: str | None = None) -> str:
    """Base persona + any long-term facts we've learned about this user."""
    if not user_id:
        return BASE_SYSTEM_PROMPT

    facts = get_facts(user_id)
    if not facts:
        return BASE_SYSTEM_PROMPT

    facts_block = "\n".join(f"- {f['fact']}" for f in facts)
    return (
        f"{BASE_SYSTEM_PROMPT}\n"
        f"What you remember about this user from earlier sessions:\n{facts_block}\n"
        f"Use these naturally if relevant. Don't force them into every reply."
    )


async def run_tool_calling_turn(client: genai.Client, conversation_text: str, user_id: str | None = None) -> str:
    """
    One-shot (non-streaming-chat-object) turn: send conversation, execute any
    function calls Gemini requests, then get the final grounded response.
    Used by the plain HTTP /agent/chat route.
    """
    response = client.models.generate_content(
        model=config.CHAT_MODEL,
        contents=conversation_text,
        config=types.GenerateContentConfig(
            system_instruction=build_system_instruction(user_id),
            tools=[tools],
        ),
    )

    function_calls = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append({"name": part.function_call.name, "arguments": dict(part.function_call.args)})

    if not function_calls:
        return response.text or ""

    results = []
    for fc in function_calls:
        result = await handle_financial_function_call(fc["name"], fc["arguments"])
        results.append({"function_name": fc["name"], "result": result})

    tool_context = "Tool results:\n" + "\n".join(
        f"- {r['function_name']}: {json.dumps(r['result']) if not isinstance(r['result'], str) else r['result']}"
        for r in results
    )

    final_response = client.models.generate_content(
        model=config.CHAT_MODEL,
        contents=f"{conversation_text}\n\n{tool_context}",
        config=types.GenerateContentConfig(system_instruction=build_system_instruction(user_id)),
    )
    return final_response.text or ""
