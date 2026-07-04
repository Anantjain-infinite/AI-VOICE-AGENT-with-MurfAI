"""
Consolidated LLM entrypoint for the plain HTTP chat route (/agent/chat).
Replaces the old llm.py, which used a hardcoded 10-word limit and no tools.
"""
from google import genai
from services.orchestrator import run_tool_calling_turn
from utils.logger import logger


async def query_llm(messages: list[dict], user_id: str | None = None) -> str:
    conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    client = genai.Client()
    try:
        return await run_tool_calling_turn(client, conversation_text, user_id)
    except Exception as e:
        logger.error(f"LLM query failed: {e}", exc_info=True)
        return "Sorry, I ran into an error generating a response."
