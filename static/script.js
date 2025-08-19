// let ws;
// let mediaRecorder;
// const startBtn = document.getElementById("start-btn");
// const stopBtn = document.getElementById("stop-btn");
// startBtn.addEventListener("click", async () => {
//   // connect websocket
//   ws = new WebSocket("ws://127.0.0.1:8000/ws");
//     stopBtn.disabled = false
//     startBtn.disabled = true

//   ws.onopen = async () => {
//     console.log("WebSocket connected");

//     const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

//     mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

//     mediaRecorder.ondataavailable = (event) => {
//       if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
//         event.data.arrayBuffer().then(buffer => {
//           ws.send(buffer); // send binary chunk
//         });
//       }
//     };

//     mediaRecorder.start(500); // send every 500ms
//     console.log("Recording and streaming...");
//   };
// });

// stopBtn.addEventListener("click", () => {
//   if (mediaRecorder && mediaRecorder.state !== "inactive") {
//     mediaRecorder.stop();
//     mediaRecorder.stream.getTracks().forEach(track => track.stop());
//   }
//   stopBtn.disabled = true
//   startBtn.disabled = false
//   if (ws && ws.readyState === WebSocket.OPEN) {
//     // ws.send("STOP"); // signal server
//     ws.close();
//   }
//   console.log("Stopped recording and streaming");
// });


let ws, audioCtx, processor, source, stream;

function downsampleTo16k(float32Buffer, inputSampleRate) {
  if (inputSampleRate === 16000) return float32Buffer;

  const ratio = inputSampleRate / 16000;
  const outLength = Math.floor(float32Buffer.length / ratio);
  const result = new Float32Array(outLength);
  let offset = 0;
  let pos = 0;

  while (offset < outLength) {
    const nextPos = Math.floor((offset + 1) * ratio);
    let sum = 0, count = 0;
    for (let i = pos; i < nextPos && i < float32Buffer.length; i++) {
      sum += float32Buffer[i];
      count++;
    }
    result[offset++] = sum / (count || 1);
    pos = nextPos;
  }
  return result;
}

function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return out;
}

async function startStreaming() {
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const transcriptDiv = document.getElementById("transcript");
  transcriptDiv.innerText = "Your conversation will appear here...";

  startBtn.disabled = true;
  stopBtn.disabled = false;

  ws = new WebSocket("ws://127.0.0.1:8000/ws");
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => console.log('WS connected');
  ws.onmessage = (evt) => {
    console.log('[Transcript]', evt.data);
    transcriptDiv.innerText += "\n" + evt.data;
  };
  ws.onerror = (e) => {
    console.error('WS error', e);
    startBtn.disabled = false;
    stopBtn.disabled = true;
  };
  ws.onclose = () => {
    console.log('WS closed');
    startBtn.disabled = false;
    stopBtn.disabled = true;
  };

  stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });

  audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
  source = audioCtx.createMediaStreamSource(stream);

  processor = audioCtx.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    const down = downsampleTo16k(input, audioCtx.sampleRate);
    const int16 = floatTo16BitPCM(down);
    if (ws && ws.readyState === 1) ws.send(int16.buffer);
  };

  source.connect(processor);
  processor.connect(audioCtx.destination);
}

async function stopStreaming() {
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');

  if (processor) { processor.disconnect(); processor.onaudioprocess = null; }
  if (source) source.disconnect();
  if (audioCtx) await audioCtx.close();
  if (stream) stream.getTracks().forEach(t => t.stop());
  if (ws && ws.readyState === 1) ws.close();

  startBtn.disabled = false;
  stopBtn.disabled = true;
}

document.getElementById('start-btn').onclick = startStreaming;
document.getElementById('stop-btn').onclick = stopStreaming;

// initialize button states
document.getElementById('start-btn').disabled = false;
document.getElementById('stop-btn').disabled = true;
