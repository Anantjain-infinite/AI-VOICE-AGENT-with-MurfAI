"""
Central SQLite persistence layer.

Replaces the old in-memory dicts (CHAT_SESSIONS, CHAT_SESSIONS_REAL) with a
durable store so chat history, uploaded documents, and long-term user memory
all survive a server restart.

Kept intentionally simple (SQLite, no ORM) since this is a single-instance
app -- swapping to Postgres later just means changing the connection string
if this ever needs to run multi-instance.
"""
import sqlite3
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_session
            ON documents(session_id)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fact TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user
            ON memories(user_id)
        """)

        # Tracks which sessions have already been mined for memory facts,
        # so we don't re-extract from turns we've already processed.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_extraction_log (
                session_id TEXT PRIMARY KEY,
                last_message_id INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
