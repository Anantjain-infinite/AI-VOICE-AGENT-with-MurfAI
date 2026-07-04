// ============================================================================
// voice.js — mic capture -> WebSocket streaming -> AssemblyAI/Gemini/Murf ->
// queued real-time playback. Logic carried over from the original script.js,
// cleaned up and wired to a canvas waveform visualizer.
// ============================================================================

let ws, audioCtx, processor, source, stream, analyser;
let audioContext;
let isProcessingQueue = false;
let wavHeaderProcessed = false;
let currentAudioSource = null;
let scheduledTime = 0;
let audioQueue = [];
let waveformRAF = null;

const sessionId = window.SIGNAL.sessionId;
const userId = window.SIGNAL.userId;

// ---- Waveform canvas ----
const canvas = document.getElementById("waveform");
const ctx2d = canvas.getContext("2d");

function drawIdleWaveform() {
  ctx2d.clearRect(0, 0, canvas.width, canvas.height);
  ctx2d.strokeStyle = "#262b38";
  ctx2d.lineWidth = 1.5;
  ctx2d.beginPath();
  ctx2d.moveTo(0, canvas.height / 2);
  ctx2d.lineTo(canvas.width, canvas.height / 2);
  ctx2d.stroke();
}
drawIdleWaveform();

function drawLiveWaveform() {
  if (!analyser) return;
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  analyser.getByteTimeDomainData(dataArray);

  ctx2d.clearRect(0, 0, canvas.width, canvas.height);
  const barCount = 64;
  const step = Math.floor(bufferLength / barCount);
  const barWidth = canvas.width / barCount;

  for (let i = 0; i < barCount; i++) {
    const sample = dataArray[i * step] / 128.0 - 1.0;
    const barHeight = Math.max(2, Math.abs(sample) * canvas.height * 1.6);
    const x = i * barWidth;
    const y = (canvas.height - barHeight) / 2;
    ctx2d.fillStyle = i % 2 === 0 ? "#e8a34c" : "#4fd1c5";
    ctx2d.fillRect(x, y, barWidth - 2, barHeight);
  }

  waveformRAF = requestAnimationFrame(drawLiveWaveform);
}

function stopWaveform() {
  if (waveformRAF) cancelAnimationFrame(waveformRAF);
  waveformRAF = null;
  drawIdleWaveform();
}

// ---- Helpers ----
function downsampleTo16k(float32Buffer, inputSampleRate) {
  if (inputSampleRate === 16000) return float32Buffer;
  const ratio = inputSampleRate / 16000;
  const outLength = Math.floor(float32Buffer.length / ratio);
  const result = new Float32Array(outLength);
  let offset = 0, pos = 0;
  while (offset < outLength) {
    const nextPos = Math.floor((offset + 1) * ratio);
    let sum = 0, count = 0;
    for (let i = pos; i < nextPos && i < float32Buffer.length; i++) { sum += float32Buffer[i]; count++; }
    result[offset++] = sum / (count || 1);
    pos = nextPos;
  }
  return result;
}

function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function updateStatus(elementId, message) {
  const el = document.getElementById(elementId);
  if (el) el.textContent = message;
}

function updateTranscript(text) {
  const el = document.getElementById("transcript");
  if (el) el.textContent = text;
}

function initializeAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 44100, latencyHint: "interactive",
    });
    scheduledTime = audioContext.currentTime + 0.1;
  }
  return audioContext;
}

function enableAudioContext() {
  if (audioContext && audioContext.state === "suspended") {
    audioContext.resume().then(() => {
      if (audioQueue.length > 0) processAudioQueue();
    });
  }
}

function base64ToFloat32Array(base64Audio) {
  try {
    const binaryString = atob(base64Audio);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);

    const offset = wavHeaderProcessed ? 0 : 44;
    wavHeaderProcessed = true;

    const audioData = bytes.slice(offset);
    const sampleCount = audioData.length / 2;
    if (sampleCount === 0) return null;

    const float32Array = new Float32Array(sampleCount);
    const dataView = new DataView(audioData.buffer, audioData.byteOffset);
    for (let i = 0; i < sampleCount; i++) {
      float32Array[i] = dataView.getInt16(i * 2, true) / 32768.0;
    }
    return float32Array;
  } catch (error) {
    console.error("Error converting base64 audio:", error);
    return null;
  }
}

function queueAudioChunk(float32Data) {
  if (!float32Data || float32Data.length === 0) return;
  audioQueue.push({ data: float32Data, timestamp: Date.now() });
  if (!isProcessingQueue) processAudioQueue();
}

function processAudioQueue() {
  if (isProcessingQueue || audioQueue.length === 0) return;
  if (!audioContext) initializeAudioContext();
  if (audioContext.state !== "running") return;

  isProcessingQueue = true;
  const processNextChunk = () => {
    if (audioQueue.length === 0) { isProcessingQueue = false; return; }
    const chunk = audioQueue.shift();
    playAudioChunk(chunk.data, processNextChunk);
  };
  processNextChunk();
}

function playAudioChunk(float32Data, onComplete) {
  try {
    const buffer = audioContext.createBuffer(1, float32Data.length, 44100);
    buffer.copyToChannel(float32Data, 0);

    const src = audioContext.createBufferSource();
    src.buffer = buffer;
    src.connect(audioContext.destination);

    const currentTime = audioContext.currentTime;
    const scheduleTime = Math.max(scheduledTime, currentTime + 0.01);
    scheduledTime = scheduleTime + buffer.duration - 0.005;

    src.onended = () => { if (onComplete) setTimeout(onComplete, 5); };
    src.start(scheduleTime);
    currentAudioSource = src;

    setTimeout(() => { if (onComplete && audioQueue.length > 0) onComplete(); }, buffer.duration * 1000 + 50);
  } catch (error) {
    console.error("Error playing audio chunk:", error);
    if (onComplete) setTimeout(onComplete, 50);
  }
}

function resetAudioState() {
  audioQueue = [];
  isProcessingQueue = false;
  wavHeaderProcessed = false;
  if (currentAudioSource) { try { currentAudioSource.stop(); } catch (e) {} currentAudioSource = null; }
  if (audioContext) scheduledTime = audioContext.currentTime + 0.1;
}

function createWavHeader(dataLength, sampleRate = 44100, numChannels = 1, bitsPerSample = 16) {
  const buffer = new ArrayBuffer(44);
  const view = new DataView(buffer);
  const writeString = (offset, string) => { for (let i = 0; i < string.length; i++) view.setUint8(offset + i, string.charCodeAt(i)); };
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const byteRate = sampleRate * blockAlign;

  writeString(0, "RIFF"); view.setUint32(4, 36 + dataLength, true); writeString(8, "WAVE");
  writeString(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true); view.setUint16(32, blockAlign, true); view.setUint16(34, bitsPerSample, true);
  writeString(36, "data"); view.setUint32(40, dataLength, true);
  return new Uint8Array(buffer);
}

function combineAudioChunks(base64Chunks) {
  if (base64Chunks.length === 0) return new Uint8Array();
  const pcmChunks = []; let totalPcmLength = 0;
  base64Chunks.forEach((base64Audio, index) => {
    const binaryString = atob(base64Audio);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);
    const pcmData = index === 0 ? bytes.slice(44) : bytes;
    pcmChunks.push(pcmData);
    totalPcmLength += pcmData.length;
  });
  const wavHeader = createWavHeader(totalPcmLength);
  const combined = new Uint8Array(wavHeader.length + totalPcmLength);
  combined.set(wavHeader, 0);
  let offset = wavHeader.length;
  pcmChunks.forEach((chunk) => { combined.set(chunk, offset); offset += chunk.length; });
  return combined;
}

function showAudioPlayer(audioChunks) {
  if (audioChunks.length === 0) return;
  try {
    const combined = combineAudioChunks(audioChunks);
    const blob = new Blob([combined], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);
    const audioElement = document.getElementById("recorded-audio");
    const audioSection = document.getElementById("audio-section");
    if (audioElement && audioSection) {
      audioElement.src = url;
      audioSection.style.display = "block";
    }
  } catch (error) {
    console.error("Error creating audio player:", error);
  }
}

// ---- Recording / streaming ----
async function startStreaming() {
  const startBtn = document.getElementById("start-btn");
  const stopBtn = document.getElementById("stop-btn");
  const signal = document.getElementById("signal");
  const audioSection = document.getElementById("audio-section");

  startBtn.disabled = true;
  stopBtn.disabled = false;
  signal.classList.add("active");
  if (audioSection) audioSection.style.display = "none";

  initializeAudioContext();
  enableAudioContext();
  resetAudioState();

  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/${sessionId}?user_id=${userId}`;

  updateStatus("upload-status", "Connecting to server…");
  updateStatus("trans-status", "Initializing speech recognition…");
  updateTranscript("Listening for your voice…");

  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";

  const receivedAudioChunks = [];

  ws.onopen = () => {
    updateStatus("upload-status", "Connected — start speaking");
    updateStatus("trans-status", "Listening…");
  };

  ws.onmessage = (evt) => {
    if (typeof evt.data !== "string") return;
    try {
      const data = JSON.parse(evt.data);

      if (data.audio_chunk) {
        receivedAudioChunks.push(data.audio_chunk);
        const float32Data = base64ToFloat32Array(data.audio_chunk);
        if (float32Data && float32Data.length > 0) {
          queueAudioChunk(float32Data);
          updateStatus("trans-status", "Playing response…");
        }
      }
      if (data.status === "final_audio") {
        updateStatus("trans-status", "Response complete");
        setTimeout(() => showAudioPlayer(receivedAudioChunks), 800);
      }
      if (data.status === "error") {
        updateStatus("trans-status", `Error: ${data.message}`);
      }
    } catch (jsonError) {
      const message = evt.data.trim();
      if (message) {
        updateTranscript(`You said: "${message}"`);
        updateStatus("trans-status", "Thinking…");
      }
    }
  };

  ws.onerror = () => {
    updateStatus("upload-status", "Connection error");
    startBtn.disabled = false; stopBtn.disabled = true; signal.classList.remove("active");
  };

  ws.onclose = () => {
    updateStatus("upload-status", "Disconnected");
    startBtn.disabled = false; stopBtn.disabled = true; signal.classList.remove("active");
    stopWaveform();
  };

  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
    updateStatus("upload-status", "Recording…");

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
    source = audioCtx.createMediaStreamSource(stream);

    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    drawLiveWaveform();

    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const down = downsampleTo16k(input, audioCtx.sampleRate);
      const int16 = floatTo16BitPCM(down);
      if (ws && ws.readyState === 1) ws.send(int16.buffer);
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
  } catch (error) {
    console.error("Microphone access error:", error);
    updateStatus("upload-status", "Microphone access denied");
    startBtn.disabled = false; stopBtn.disabled = true; signal.classList.remove("active");
  }
}

async function stopStreaming() {
  const startBtn = document.getElementById("start-btn");
  const stopBtn = document.getElementById("stop-btn");
  const signal = document.getElementById("signal");

  updateStatus("upload-status", "Stopping…");
  updateStatus("trans-status", "Processing final audio…");

  if (processor) { processor.disconnect(); processor.onaudioprocess = null; }
  if (source) source.disconnect();
  if (audioCtx && audioCtx.state !== "closed") await audioCtx.close();
  if (stream) stream.getTracks().forEach((t) => t.stop());
  if (ws && ws.readyState === 1) ws.close();

  stopWaveform();
  startBtn.disabled = false; stopBtn.disabled = true; signal.classList.remove("active");
  updateStatus("upload-status", "Recording stopped");
}

document.getElementById("start-btn").addEventListener("click", startStreaming);
document.getElementById("stop-btn").addEventListener("click", stopStreaming);
document.addEventListener("click", enableAudioContext, { once: true });
document.addEventListener("touchstart", enableAudioContext, { once: true });
