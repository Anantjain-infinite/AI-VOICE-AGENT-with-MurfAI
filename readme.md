# Signal — AI Voice Agent with RAG & Long-Term Memory

A full-stack conversational AI voice assistant: record your voice in the browser, get
transcribed via AssemblyAI, get smart tool-using replies from Google Gemini, and hear
natural speech back via Murf AI — with two Gen-AI additions layered on top of the base
voice pipeline: **document-grounded RAG** and **long-term user memory**.

---

## ✨ What's here

- 🎙️ Real-time voice streaming (record → transcribe → respond → speak) over WebSocket
- 🤖 Gemini function calling for live stock/crypto/news/weather data
- 📄 **RAG**: upload a PDF, ask questions grounded in it, get page-cited answers
- 🧠 **Long-term memory**: facts extracted from past sessions persist across restarts
  and get woven back into future conversations
- 💾 Persistent SQLite store for chat history, uploaded documents, and memory (no more
  in-memory dicts that vanish on restart)
- 🖥️ Rebuilt frontend: three panels (Voice / Documents / Memory) instead of one
  cramped page, with a live waveform visualizer during recording

---

## 🏗️ Architecture

```
                        ┌─────────────────────────┐
                        │        Browser           │
                        │  Voice | Documents | Mem  │
                        └──────────┬───────────────┘
                                   │
                     WebSocket (/ws) + REST (/rag, /memory, /agent)
                                   │
                        ┌──────────▼───────────────┐
                        │        FastAPI            │
                        │  services/orchestrator.py │  ← single system prompt +
                        │  services/gemini_stream   │    memory injection point
                        └──┬────────┬────────┬──────┘
                           │        │        │
                 ┌─────────▼─┐ ┌────▼────┐ ┌─▼──────────┐
                 │ AssemblyAI │ │  Gemini │ │  Murf AI    │
                 │   (STT)    │ │ (LLM +  │ │   (TTS)     │
                 │            │ │ tools)  │ │             │
                 └────────────┘ └────┬────┘ └─────────────┘
                                     │
                     ┌───────────────┼────────────────┐
                     │               │                │
              ┌──────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐
              │  skills.py │  │  ChromaDB    │  │   SQLite    │
              │ (finance,  │  │ (RAG vector  │  │ (chat hist, │
              │  weather)  │  │  store, per- │  │  documents, │
              │            │  │  session)    │  │  memories)  │
              └────────────┘  └──────────────┘  └─────────────┘
```

### RAG flow
`PDF upload → pdfplumber extracts text per page → chunked with overlap → embedded
(Gemini text-embedding-004) → stored in a per-session Chroma collection → question comes
in → embedded → top-k chunks retrieved → injected into a Gemini prompt → answer returned
with page-level citations.`

### Memory flow
`Voice session ends → new (unprocessed) turns pulled from SQLite → sent to Gemini with
an extraction prompt asking for durable facts → facts stored under the user's persistent
user_id → next session's system prompt is built with those facts injected → the
assistant "remembers" without re-reading the whole chat history.`

---

## 🧩 Design decisions worth knowing

- **`session_id` vs `user_id`**: `session_id` resets per browser tab (query param) and
  scopes chat history + uploaded RAG documents. `user_id` persists in `localStorage`
  and scopes long-term memory. This split is what makes "remembers across sessions"
  actually mean something — if memory were keyed by `session_id` it would reset with
  everything else.
- **SQLite over Postgres**: this is a single-instance app; SQLite is zero-setup and
  sufficient. The `services/db.py` module is the only place that would need to change
  to move to Postgres later.
- **Chunking**: PDF chunks are built per-page (not across page boundaries) so every
  chunk can carry an accurate page number for citations, with character-overlap within
  a page to avoid cutting sentences at chunk boundaries.
- **Memory extraction is incremental**: a `memory_extraction_log` table tracks the last
  processed message id per session, so re-running extraction (or a session that never
  cleanly closes) doesn't create duplicate facts.
- **User-controllable memory**: facts are visible and individually deletable via the
  Memory panel / `DELETE /memory/{user_id}/{fact_id}` — memory that a user can't see or
  remove is a trust problem, not just an engineering one.

---

## 🐛 Bugs fixed from the original version

- The Gemini system prompt was a leftover **"Medical Assistant" consultation script**
  that had nothing to do with this app — replaced with a proper assistant persona.
- Finance/weather **tools were never actually attached** to the live chat config
  (`tools=[tools]` was commented out) — function calling silently did nothing in the
  streaming path. Now wired in and used by both the WebSocket and HTTP chat routes.
- `MURF_API_KEY` / `ASSEMBLY_AI_API_KEY` were captured into module-level constants at
  **import time**, so updating keys at runtime via the sidebar never actually took
  effect. Services now read `config.py` at call time.
- Chat history lived in plain Python dicts (`CHAT_SESSIONS`, `CHAT_SESSIONS_REAL`) and
  was lost on every restart — replaced with SQLite persistence.

---

## 🛠️ Tech stack

- **Backend:** FastAPI, WebSockets, SQLite
- **STT:** AssemblyAI streaming
- **LLM:** Google Gemini (function calling, streaming, embeddings)
- **TTS:** Murf AI streaming
- **RAG:** pdfplumber + ChromaDB (persistent, per-session collections)
- **Frontend:** vanilla HTML/CSS/JS, Web Audio API for recording/playback + waveform viz

---

## 🚀 Getting started

```sh
git clone <your-repo-url>
cd ai-voice-agent-genai
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
uvicorn main:app --reload
```

Visit [http://localhost:8000](http://localhost:8000). You can also configure API keys
at runtime from the "Configure keys" drawer in the UI instead of `.env`.

---

## 📝 API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Main UI |
| POST | `/get-api-keys` | Set API keys at runtime |
| POST | `/transcribe/file` | Transcribe an uploaded audio file |
| POST | `/generate-audio` | Text → speech (Murf) |
| POST | `/agent/chat/{session_id}` | Full HTTP chat turn (transcribe → LLM w/ tools & memory → TTS) |
| WS | `/ws/{session_id}?user_id=` | Real-time streaming voice chat |
| POST | `/rag/upload/{session_id}` | Upload + index a PDF |
| POST | `/rag/chat/{session_id}` | Ask a question grounded in uploaded docs |
| GET | `/rag/documents/{session_id}` | List indexed documents for a session |
| DELETE | `/rag/documents/{session_id}/{doc_id}` | Remove a document |
| GET | `/memory/{user_id}` | List long-term memory facts |
| DELETE | `/memory/{user_id}/{fact_id}` | Delete a memory fact |

---

## ⚠️ Notes

- API keys are required for all cloud services (Murf, AssemblyAI, Gemini, Finnhub,
  Alpha Vantage, OpenWeather).
- Uploaded PDFs are stored under `uploads/pdfs/`; vector data under `chroma_db/`; all
  structured data in `app_data.db` (SQLite).
- This is an educational/portfolio project — check each provider's rate limits and
  terms before any real usage.

## 📄 License

MIT
