"""
Turns a chunk of conversation into a short list of durable facts about the
user (preferences, holdings, location, recurring interests, etc.), then
stores anything new. This is what makes memory persist *across* sessions
instead of just within one chat's history.
"""
import json
from google import genai
import config
from services.db import get_conn
from services.session_store import get_full_history
from services.memory.memory_store import add_fact
from utils.logger import logger

_EXTRACTION_PROMPT = """Extract durable facts about the user from this conversation snippet.
Only include facts that would still be useful to remember in a future, unrelated conversation
(e.g. stated preferences, personal details, stock/crypto holdings mentioned, location, recurring interests).
Do NOT include one-off questions or small talk.

Return ONLY a JSON array of short strings, nothing else. If there is nothing worth remembering, return [].

Conversation:
{conversation}
"""


def extract_facts_from_text(conversation_text: str) -> list[str]:
    if not conversation_text.strip():
        return []
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=config.CHAT_MODEL,
            contents=_EXTRACTION_PROMPT.format(conversation=conversation_text),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[4:] if raw.lower().startswith("json") else raw
        facts = json.loads(raw)
        return [f.strip() for f in facts if isinstance(f, str) and f.strip()]
    except Exception as e:
        logger.warning(f"Memory extraction failed (non-fatal): {e}")
        return []


def _get_last_extracted_id(session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_message_id FROM memory_extraction_log WHERE session_id = ?",
            (session_id,)
        ).fetchone()
    return row["last_message_id"] if row else 0


def _set_last_extracted_id(session_id: str, message_id: int):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO memory_extraction_log (session_id, last_message_id)
               VALUES (?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 last_message_id = excluded.last_message_id,
                 updated_at = CURRENT_TIMESTAMP""",
            (session_id, message_id)
        )


def extract_and_store_new_facts(session_id: str, user_id: str) -> list[str]:
    """
    Call this when a session ends (or periodically). Only mines messages
    that haven't already been processed for this session, so restarting a
    session or calling this multiple times doesn't create duplicate facts.
    """
    history = get_full_history(session_id)
    last_id = _get_last_extracted_id(session_id)
    new_messages = [m for m in history if m["id"] > last_id]

    if not new_messages:
        return []

    conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in new_messages)
    facts = extract_facts_from_text(conversation_text)

    for fact in facts:
        add_fact(user_id, fact)

    _set_last_extracted_id(session_id, new_messages[-1]["id"])
    return facts
