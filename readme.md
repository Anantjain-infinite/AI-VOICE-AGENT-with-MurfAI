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

## ✅ Testing locally

Before deploying anywhere, confirm each layer works on your machine:

```sh
pip install -r requirements.txt
cp .env.example .env   # fill in your real keys
uvicorn main:app --reload
```

1. **Sanity check the server boots**: visit `http://localhost:8000` — you should see the
   Signal UI with Voice / Documents / Memory tabs, and the FastAPI logs should show
   `Database initialized` on startup (confirms `app_data.db` was created).
2. **API keys**: open the "Configure keys" drawer, paste in real keys, submit — you
   should see "Keys configured ✓" and the status dot in the top bar turn teal.
3. **Voice path**: click Start, speak a sentence, click Stop. Check for:
   - the waveform animating while you talk
   - the transcript appearing under "You said: ..."
   - spoken audio playing back, and a downloadable player appearing after
   If nothing plays, open browser dev tools → Console/Network and check the WebSocket
   connection at `ws://localhost:8000/ws/<session_id>` for errors — most issues here are
   a bad `MURF_API_KEY`/`ASSEMBLY_AI_API_KEY` or the mic permission being denied.
4. **Finance/weather tools**: say something like "what's the price of AAPL" or "what's
   the weather in Mumbai" — this exercises Gemini function calling end-to-end. If it just
   answers generically without real numbers, check `FINNHUB_API_KEY` /
   `OPENWEATHER_API_KEY` are valid.
5. **RAG**: switch to the Documents tab, drag in a PDF, wait for "Indexed N chunks", then
   ask a question you know the answer to from that PDF. Confirm the answer cites a page
   number. Try deleting the document and re-asking — you should get the "couldn't find
   anything" fallback.
6. **Memory**: have a voice conversation that mentions a preference (e.g. "I prefer
   Celsius", "I hold some Tesla stock"), click Stop to end the session cleanly, then check
   the server logs for `Stored N new memory facts for user ...`. Switch to the Memory tab
   and confirm the fact shows up. Reload the page (same browser = same `user_id` in
   localStorage) and confirm it's still there. Try deleting a fact and refreshing.
7. **Restart test** (the whole point of Phase 1): stop the `uvicorn` process, start it
   again, and confirm your documents/memory from before are still there — this is what
   proves you're not back to in-memory dicts.

If you want to inspect the SQLite data directly at any point:
```sh
sqlite3 app_data.db "select * from messages;"
sqlite3 app_data.db "select * from memories;"
sqlite3 app_data.db "select * from documents;"
```

---

## 🚢 Deployment

This app needs **persistent disk** (SQLite file, Chroma vectors, uploaded PDFs) and
**native WebSocket support**, which rules out pure serverless platforms like Vercel or
Netlify functions. Two supported paths are included:

### Option A — Render (recommended, easiest persistent disk + WebSockets)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at your repo — it will read `render.yaml`
   automatically and provision the web service + a 1GB persistent disk mounted at `/data`.
3. In the Render dashboard, fill in the env vars marked `sync: false` (your six API keys)
   — these are secrets, so they're intentionally left out of `render.yaml`.
4. Deploy. Render builds the `Dockerfile` and serves on the assigned URL, with
   `wss://` WebSockets working automatically over the same domain.
5. Confirm persistence: use the app, redeploy (or restart) the service from the
   dashboard, and check your documents/memory survived — the disk is what makes that
   true here (without it, a redeploy wipes SQLite/Chroma just like a local restart would).

If you'd rather not use the blueprint, you can create the Web Service manually with the
same settings: Docker runtime, add a disk at `/data`, and set `DB_PATH`, `CHROMA_PATH`,
`UPLOAD_DIR` to paths under `/data` (already defaulted in `render.yaml`).

### Option B — Any Docker host (Railway, Fly.io, a VPS, etc.)

```sh
docker build -t signal-voice-agent .
docker run -d -p 8000:8000 \
  -e MURF_API_KEY=... -e ASSEMBLY_AI_API_KEY=... -e GEMINI_API_KEY=... \
  -e FINNHUB_API_KEY=... -e ALPHA_VANTAGE_API_KEY=... -e OPENWEATHER_API_KEY=... \
  -v signal_data:/app/data \
  -e DB_PATH=/app/data/app_data.db \
  -e CHROMA_PATH=/app/data/chroma_db \
  -e UPLOAD_DIR=/app/data/uploads/pdfs \
  signal-voice-agent
```

The `-v signal_data:/app/data` volume is the non-negotiable part — without a mounted
volume, every container restart wipes your SQLite DB and vector store, same failure mode
as the original in-memory dicts, just one layer down.

On Railway/Fly.io specifically: both support Docker deploys and persistent volumes
directly from their dashboards/CLIs; the same env vars and volume mount pattern applies.

### What to skip until you actually need it

- Postgres instead of SQLite, or a hosted vector DB (Pinecone/Qdrant Cloud) instead of
  local Chroma — only worth it if you expect concurrent multi-instance traffic. Good
  "how would you scale this" talking point for an interview even if you don't build it.
- HTTPS is handled automatically by Render/Railway/Fly's default domains — only worry
  about certs yourself if you're deploying to a bare VPS.

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
