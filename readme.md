# AI Voice Agent with MurfAI

A full-stack conversational AI voice assistant web app. Record your voice in the browser, transcribe speech to text, get smart replies from Google Gemini (with chat history and function calling), and hear natural-sounding responses via Murf AI TTS—all in real time. The app supports advanced skills like financial data, weather, and more.

---

## 🛠️ Technologies Used

- **Frontend:** HTML, CSS, JavaScript 
- **Backend:** Python, FastAPI, WebSockets
- **Speech-to-Text:** [AssemblyAI Streaming API](https://www.assemblyai.com/)
- **LLM:** [Google Gemini](https://ai.google.dev/) (function calling, streaming)
- **Text-to-Speech:** [Murf AI Streaming API](https://murf.ai/)
- **Templating:** Jinja2
- **Environment Management:** python-dotenv
- **Async HTTP:** aiohttp

---

## 🏗️ Architecture

```
[User Browser]
    |
    |  (WebSocket: Stream Audio)
    v
[FastAPI Server] <--- [Frontend: HTML/CSS/JS]
    |
    |--(STT)-------> [AssemblyAI Streaming API]
    |--(LLM)-------> [Google Gemini API]
    |--(TTS)-------> [Murf AI Streaming API]
    |
    |--(Serve Audio/HTML/JS/CSS)
    v
[User Browser]
```

- **Frontend:** Single-page app served from FastAPI, handles recording, playback, and UI updates.
- **Backend:** FastAPI endpoints for audio upload, transcription, LLM chat, TTS, and a WebSocket endpoint for real-time streaming.
- **Session Management:** Each browser session gets a unique `session_id` for chat history and context.
- **Skills:** Financial data (stocks, crypto, news, portfolio), weather, and more via Gemini function calling.

---

## ✨ Features

- 🎙️ **Record your voice** in the browser (no plugins needed)
- 📝 **Real-time transcription** using AssemblyAI streaming
- 🤖 **Smart, context-aware replies** using Google Gemini LLM (with chat history)
- 🔊 **Natural voice responses** using Murf AI TTS (streamed for low latency)
- 💬 **Chat history** per session for contextual conversations
- 📈 **Financial skills:** Stock/crypto prices, news, portfolio analysis, comparisons
- 🌦️ **Weather skills:** Real-time weather and forecasts
- ⚡ **Modern UI** with real-time status updates and error handling
- 🔐 **API key configuration** via sidebar (no hardcoding in frontend)
- 🕒 **Streaming architecture** for low-latency, interactive conversations

---

## 📸 Screenshots

> ![Screenshot of the Voice AI Agent UI](posts/day27.PNG)
> 
> ![Another screenshot](posts/day11.PNG)

---

## 🚀 Getting Started

### 1. Clone the repository

```sh
git clone https://github.com/Anantjain-infinite/AI-VOICE-AGENT-with-MurfAI.git
cd AI-VOICE-AGENT-with-MurfAI
```

### 2. Install dependencies

Requires Python 3.9+.

```sh
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in the root directory with the following keys:

```
MURF_API_KEY=your-murf-api-key
ASSEMBLY_AI_API_KEY=your-assemblyai-api-key
GEMINI_API_KEY=your-gemini-api-key
FINNHUB_API_KEY=your-finnhub-api-key
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-api-key
OPENWEATHER_API_KEY=your-openweather-api-key
```

> **Note:** You must obtain API keys from [Murf AI](https://murf.ai/), [AssemblyAI](https://www.assemblyai.com/), [Google AI Studio](https://ai.google.dev/), [Finnhub](https://finnhub.io/), [Alpha Vantage](https://www.alphavantage.co/), and [OpenWeather](https://openweathermap.org/).

### 4. Run the FastAPI server

```sh
uvicorn main:app --reload
```

- The app will be available at [http://localhost:8000](http://localhost:8000)

---

## 🧩 Project Structure

```
.
├── main.py
├── schema.py
├── skills.py
├── config.py
├── .env
├── requirements.txt
├── posts/                # Example screenshots/media
├── static/
│   └── script.js         # Frontend JS logic
├── templates/
│   └── index.html        # Main UI
├── uploads/              # Uploaded audio files
├── recordings/           # Temporary/streamed audio
├── services/
│   ├── stt.py            # Speech-to-text logic
│   ├── tts.py            # Text-to-speech logic
│   ├── llm.py            # LLM (Gemini) logic
│   ├── assembly_stream.py
│   ├── gemini_stream.py
│   └── murf_stream.py
├── utils/
│   └── logger.py         # Logging utility
└── README.md
```

---

## 📝 API Endpoints

- `GET /` — Main UI
- `POST /get-api-keys` — Set API keys from frontend
- `POST /transcribe/file` — Transcribes uploaded audio
- `POST /generate-audio` — Generate TTS audio from text
- `POST /agent/chat/{session_id}` — Full chat flow: transcribe, chat history, Gemini, Murf TTS
- `WS /ws/{session_id}` — Real-time streaming: audio in, transcript + Gemini + TTS out

---

## ⚠️ Notes

- API keys are required for all cloud services.
- Uploaded audio is stored in the `uploads/` directory.
- For production, secure your API keys and consider deploying behind HTTPS.
- The app is for educational/research use; check API rate limits and terms.

---

## 📄 License

MIT License

---

## 🙏 Acknowledgements

- [AssemblyAI](https://www.assemblyai.com/)
- [Google Gemini](https://ai.google.dev/)
- [Murf AI](https://murf.ai/)
- [Finnhub](https://finnhub.io/)
- [Alpha Vantage](https://www.alphavantage.co/)
- [OpenWeather](https://openweathermap.org/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Jinja2](https://jinja.palletsprojects.com/)