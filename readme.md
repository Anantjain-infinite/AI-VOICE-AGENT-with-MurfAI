# Voice AI Agent

A conversational AI voice assistant web app that lets you record your voice, transcribes your speech, generates smart replies using Google Gemini, and responds with natural-sounding speech using Murf TTS. The app supports chat history for context-aware conversations.

---

## 🛠️ Technologies Used

- **Frontend:** HTML, CSS, JavaScript 
- **Backend:** Python, FastAPI
- **Speech-to-Text:** [AssemblyAI](https://www.assemblyai.com/)
- **LLM:** [Google Gemini](https://ai.google.dev/)
- **Text-to-Speech:** [Murf AI](https://murf.ai/)
- **Templating:** Jinja2
- **Environment Management:** python-dotenv

---

## 🏗️ Architecture

```
[User Browser]
    |
    |  (Record/Send Audio)
    v
[FastAPI Server] <--- [Frontend: HTML/CSS/JS]
    |
    |--(Transcribe)--> [AssemblyAI API]
    |--(LLM)---------> [Google Gemini API]
    |--(TTS)---------> [Murf AI API]
    |
    |--(Serve Audio/HTML/JS/CSS)
    v
[User Browser]
```

- **Frontend**: Single-page app served from FastAPI, handles recording, playback, and UI updates.
- **Backend**: FastAPI endpoints for audio upload, transcription, LLM chat, and TTS.
- **Session Management**: Each browser session gets a unique `session_id` for chat history.
- **Audio Files**: Uploaded audio is saved in the `uploads/` directory.

---

## ✨ Features

- 🎙️ **Record your voice** in the browser (no plugins needed)
- 📝 **Transcription** using AssemblyAI
- 🤖 **Smart replies** using Google Gemini LLM, with chat history for context
- 🔊 **Natural voice responses** using Murf AI TTS
- 💬 **Chat history** per session for contextual conversations
- ⚡ **Modern UI** with real-time status updates and error handling

---

## 📸 Screenshots

> ![Screenshot of the Voice AI Agent UI](posts/day1.PNG)
> 
> ![Another screenshot](posts/day11.PNG)

---

## 🚀 Getting Started

### 1. Clone the repository

```sh
git clone https://github.com/yourusername/voice-ai-agent.git
cd voice-ai-agent
```

### 2. Install dependencies

Make sure you have Python 3.9+ and Node.js (for frontend development, optional).

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
```

> **Note:** You must obtain API keys from [Murf AI](https://murf.ai/), [AssemblyAI](https://www.assemblyai.com/), and [Google AI Studio](https://ai.google.dev/).

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
├── .env
├── requirements.txt
├── posts/              # Example screenshots/media
├── static/
│   └── script.js       # Frontend JS logic
├── templates/
│   └── index.html      # Main UI
├── uploads/            # Uploaded audio files
└── README.md
```

---

## 📝 API Endpoints

- `GET /` — Main UI
- `POST /upload-audio` — Uploads audio file
- `POST /transcribe/file` — Transcribes uploaded audio
- `POST /tts/echo` — Echoes back your speech as Murf TTS
- `POST /llm/query` — Transcribes and generates Gemini response (no chat history)
- `POST /agent/chat/{session_id}` — Full chat flow: transcribe, chat history, Gemini, Murf TTS

---

## ⚠️ Notes

- API keys are required for all cloud services.
- Uploaded audio is stored in the `uploads/` directory.
- For production, secure your API keys and consider deploying behind HTTPS.

---

## 📄 License

MIT License

---

## 🙏 Acknowledgements