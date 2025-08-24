let ws, audioCtx, processor, source, stream;

// Audio streaming variables
let audioContext;
let audioBuffer = [];
let isPlayingAudio = false;
let playheadTime = 0;
let wavHeaderProcessed = false;
let contextId = null;


function getOrCreateSessionId() {
  const url = new URL(window.location.href);
  let sid = url.searchParams.get("session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    url.searchParams.set("session_id", sid);
    window.history.replaceState({}, "", url.toString());
  }
  return sid;
}

const sessionId = getOrCreateSessionId();

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

function generateContextId() {
  return 'ctx_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function updateStatus(elementId, message, isLoading = false) {
  const element = document.getElementById(elementId);
  if (element) {
    element.textContent = message;
    element.classList.toggle('loading', isLoading);
    element.classList.add('fade-in');
  }
}

function updateTranscript(text) {
  const transcriptDiv = document.getElementById("transcript");
  if (transcriptDiv) {
    transcriptDiv.textContent = text;
    transcriptDiv.classList.add('fade-in');
  }
}

// Initialize audio context for playback
function initializeAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 44100 });
    playheadTime = audioContext.currentTime;
    console.log('🎵 Audio context initialized, state:', audioContext.state);
    
    // Handle audio context state changes
    audioContext.addEventListener('statechange', () => {
      console.log('🎵 Audio context state changed to:', audioContext.state);
    });
  }
  return audioContext;
}

// Enable audio context on user interaction
function enableAudioContext() {
  if (audioContext && audioContext.state === 'suspended') {
    console.log('🎵 Attempting to resume audio context...');
    audioContext.resume().then(() => {
      console.log('✅ Audio context resumed successfully');
    }).catch(err => {
      console.error('❌ Failed to resume audio context:', err);
    });
  }
}

// Convert base64 audio to Float32Array (handling WAV format)
function base64ToFloat32Array(base64Audio) {
  try {
    if (!base64Audio || typeof base64Audio !== 'string') {
      console.error('Invalid base64 audio data');
      return null;
    }

    const binaryString = atob(base64Audio);
    const bytes = new Uint8Array(binaryString.length);
    
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    console.log(`📄 Raw audio data: ${bytes.length} bytes`);

    // Skip WAV header (44 bytes) on first chunk only
    const offset = wavHeaderProcessed ? 0 : 44;
    if (!wavHeaderProcessed) {
      console.log('📋 Processing WAV header, skipping first 44 bytes');
      console.log('WAV header:', Array.from(bytes.slice(0, 44)).map(b => b.toString(16)).join(' '));
      wavHeaderProcessed = true;
    }

    const audioData = bytes.slice(offset);
    const sampleCount = audioData.length / 2; // 16-bit samples
    
    if (sampleCount === 0) {
      console.warn('No audio samples found after header removal');
      return null;
    }
    
    const float32Array = new Float32Array(sampleCount);
    
    // Convert 16-bit PCM to float32
    const dataView = new DataView(audioData.buffer, audioData.byteOffset);
    for (let i = 0; i < sampleCount; i++) {
      const sample = dataView.getInt16(i * 2, true); // little-endian
      float32Array[i] = sample / 32768.0; // normalize to [-1, 1]
    }

    console.log(`✅ Converted to ${sampleCount} float32 samples`);
    console.log(`Sample range: ${Math.min(...float32Array).toFixed(4)} to ${Math.max(...float32Array).toFixed(4)}`);
    
    return float32Array;
  } catch (error) {
    console.error('❌ Error converting base64 to Float32Array:', error);
    return null;
  }
}

// Queue and play audio chunks seamlessly
function queueAudioChunk(float32Data) {
  if (!float32Data || float32Data.length === 0) {
    console.warn('Received empty audio data');
    return;
  }
  
  console.log(`📥 Queueing audio chunk: ${float32Data.length} samples`);
  audioBuffer.push(float32Data);
  
  // Start playing immediately if not already playing
  if (!isPlayingAudio) {
    console.log('🎵 Starting audio playback...');
    isPlayingAudio = true;
    
    // Small delay to ensure audio context is ready
    setTimeout(() => {
      playNextChunk();
    }, 10);
  } else {
    console.log(`📦 Audio chunk queued (${audioBuffer.length} chunks in buffer)`);
  }
}

function playNextChunk() {
  if (audioBuffer.length === 0) {
    isPlayingAudio = false;
    console.log('No more audio chunks to play');
    return;
  }

  isPlayingAudio = true;
  const chunkData = audioBuffer.shift();
  
  try {
    // Initialize or resume audio context
    if (!audioContext) {
      initializeAudioContext();
    }
    
    if (audioContext.state === 'suspended') {
      console.log('Resuming audio context...');
      audioContext.resume().then(() => {
        console.log('Audio context resumed');
      });
    }

    // Create audio buffer
    const buffer = audioContext.createBuffer(1, chunkData.length, 44100);
    buffer.copyToChannel(chunkData, 0);
    
    // Create source node
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    
    // Schedule playback - ensure continuous playback
    const currentTime = audioContext.currentTime;
    const scheduleTime = Math.max(playheadTime, currentTime + 0.01);
    
    source.start(scheduleTime);
    playheadTime = scheduleTime + buffer.duration;
    
    console.log(`🔊 Playing audio chunk: ${chunkData.length} samples, duration: ${buffer.duration.toFixed(3)}s, scheduled at: ${scheduleTime.toFixed(3)}s`);
    
    // Set up next chunk - use setTimeout as backup
    source.onended = () => {
      console.log('Audio chunk ended, checking for next...');
      if (audioBuffer.length > 0) {
        playNextChunk();
      } else {
        isPlayingAudio = false;
        console.log('✅ Audio playback completed');
      }
    };
    
    // Backup trigger in case onended doesn't fire
    setTimeout(() => {
      if (audioBuffer.length > 0 && !isPlayingAudio) {
        console.log('Backup trigger: starting next chunk');
        playNextChunk();
      }
    }, buffer.duration * 1000 + 10);
    
  } catch (error) {
    console.error('❌ Error playing audio chunk:', error);
    isPlayingAudio = false;
    
    // Try to continue with next chunk despite error
    if (audioBuffer.length > 0) {
      setTimeout(() => playNextChunk(), 50);
    }
  }
}

// Reset audio streaming state
function resetAudioState() {
  audioBuffer = [];
  isPlayingAudio = false;
  wavHeaderProcessed = false;
  playheadTime = audioContext ? audioContext.currentTime : 0;
  contextId = generateContextId();
  console.log('Audio state reset with new context ID:', contextId);
}

// Show audio player with blob URL for download/replay
function showAudioPlayer(audioChunks) {
  if (audioChunks.length === 0) return;
  
  try {
    // Combine all audio chunks into a single WAV file
    const combinedAudio = combineAudioChunks(audioChunks);
    const blob = new Blob([combinedAudio], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    
    const audioElement = document.getElementById('recorded-audio');
    const audioSection = document.getElementById('audio-section');
    
    if (audioElement && audioSection) {
      audioElement.src = url;
      audioSection.style.display = 'block';
      audioSection.classList.add('fade-in');
    }
  } catch (error) {
    console.error('Error creating audio player:', error);
  }
}

// Combine base64 audio chunks into a single WAV file
function combineAudioChunks(base64Chunks) {
  if (base64Chunks.length === 0) return new Uint8Array();
  
  const pcmChunks = [];
  let totalPcmLength = 0;
  
  base64Chunks.forEach((base64Audio, index) => {
    const binaryString = atob(base64Audio);
    const bytes = new Uint8Array(binaryString.length);
    
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    
    // Skip WAV header only for first chunk
    const pcmData = index === 0 ? bytes.slice(44) : bytes;
    pcmChunks.push(pcmData);
    totalPcmLength += pcmData.length;
  });
  
  // Create WAV header
  const wavHeader = createWavHeader(totalPcmLength);
  
  // Combine header + PCM data
  const combinedAudio = new Uint8Array(wavHeader.length + totalPcmLength);
  combinedAudio.set(wavHeader, 0);
  
  let offset = wavHeader.length;
  pcmChunks.forEach(chunk => {
    combinedAudio.set(chunk, offset);
    offset += chunk.length;
  });
  
  return combinedAudio;
}

// Create WAV header
function createWavHeader(dataLength, sampleRate = 44100, numChannels = 1, bitsPerSample = 16) {
  const buffer = new ArrayBuffer(44);
  const view = new DataView(buffer);
  
  // Helper to write string
  const writeString = (offset, string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };
  
  const blockAlign = numChannels * bitsPerSample / 8;
  const byteRate = sampleRate * blockAlign;
  
  // RIFF header
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeString(8, 'WAVE');
  
  // fmt chunk
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  
  // data chunk
  writeString(36, 'data');
  view.setUint32(40, dataLength, true);
  
  return new Uint8Array(buffer);
}

async function startStreaming() {
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const signal = document.getElementById('signal');
  const audioSection = document.getElementById('audio-section');

  startBtn.disabled = true;
  stopBtn.disabled = false;
  signal.classList.add('active');
  
  // Hide previous audio player
  if (audioSection) {
    audioSection.style.display = 'none';
  }

  // Initialize audio context for playback and enable it
  initializeAudioContext();
  enableAudioContext(); // Ensure audio context is active
  resetAudioState();

  updateStatus('upload-status', '🔄 Connecting to server...', true);
  updateStatus('trans-status', 'Initializing speech recognition...', true);
  updateTranscript('Listening for your voice...');

  ws = new WebSocket(`ws://127.0.0.1:8000/ws/${sessionId}`);
  ws.binaryType = 'arraybuffer';

  const receivedAudioChunks = []; // Store for final audio player

  ws.onopen = () => {
    console.log('WebSocket connected');
    updateStatus('upload-status', '✅ Connected - Start speaking!');
    updateStatus('trans-status', '👂 Listening...');
  };

  ws.onmessage = (evt) => {
    try {
      // Check if it's a string message (transcript or JSON)
      if (typeof evt.data === 'string') {
        // Try to parse as JSON first
        try {
          const data = JSON.parse(evt.data);
          
          // Handle JSON messages (audio chunks, status, etc.)
          if (data.audio_chunk) {
            console.log('Received audio chunk:', data.chunk_number || 'unknown');
            receivedAudioChunks.push(data.audio_chunk);
            
            // Convert and queue for immediate real-time playback
            const float32Data = base64ToFloat32Array(data.audio_chunk);
            if (float32Data && float32Data.length > 0) {
              console.log(`Queueing audio chunk: ${float32Data.length} samples`);
              queueAudioChunk(float32Data);
              updateStatus('trans-status', '🔊 Playing AI response...');
            }
          }
          
          if (data.status === 'final_audio') {
            console.log('Final audio received, total chunks:', data.total_chunks);
            updateStatus('trans-status', '✅ Response complete');
            
            // Show combined audio player after a brief delay
            setTimeout(() => {
              showAudioPlayer(receivedAudioChunks);
            }, 1000);
          }
          
          if (data.status === 'error') {
            console.error('Server error:', data.message);
            updateStatus('trans-status', `❌ Error: ${data.message}`);
          }
          
        } catch (jsonError) {
          // If JSON parsing fails, treat as plain transcript message
          const message = evt.data.trim();
          if (message && !message.startsWith('{')) {
            console.log('[Transcript]', message);
            updateTranscript(`You said: "${message}"`);
            updateStatus('trans-status', '🤖 AI is thinking...');
          }
        }
      }
    } catch (error) {
      console.error('Error processing WebSocket message:', error);
    }
  };

  ws.onerror = (e) => {
    console.error('WebSocket error', e);
    updateStatus('upload-status', '❌ Connection error');
    updateStatus('trans-status', 'Connection failed');
    startBtn.disabled = false;
    stopBtn.disabled = true;
    signal.classList.remove('active');
  };

  ws.onclose = () => {
    console.log('WebSocket closed');
    updateStatus('upload-status', '🔌 Disconnected');
    startBtn.disabled = false;
    stopBtn.disabled = true;
    signal.classList.remove('active');
  };

  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
    updateStatus('upload-status', '🎤 Recording audio...');
    
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
    source = audioCtx.createMediaStreamSource(stream);

    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const down = downsampleTo16k(input, audioCtx.sampleRate);
      const int16 = floatTo16BitPCM(down);
      if (ws && ws.readyState === 1) {
        ws.send(int16.buffer);
      }
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
    
  } catch (error) {
    console.error('Error accessing microphone:', error);
    updateStatus('upload-status', '❌ Microphone access denied');
    updateStatus('trans-status', 'Please allow microphone access');
    startBtn.disabled = false;
    stopBtn.disabled = true;
    signal.classList.remove('active');
  }
}

async function stopStreaming() {
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const signal = document.getElementById('signal');

  updateStatus('upload-status', '⏹️ Stopping recording...');
  updateStatus('trans-status', 'Processing final audio...');

  if (processor) { 
    processor.disconnect(); 
    processor.onaudioprocess = null; 
  }
  if (source) source.disconnect();
  if (audioCtx && audioCtx.state !== 'closed') await audioCtx.close();
  if (stream) stream.getTracks().forEach(t => t.stop());
  if (ws && ws.readyState === 1) ws.close();

  startBtn.disabled = false;
  stopBtn.disabled = true;
  signal.classList.remove('active');
  
  updateStatus('upload-status', '✅ Recording stopped');
}

// Event listeners
document.getElementById('start-btn').onclick = startStreaming;
document.getElementById('stop-btn').onclick = stopStreaming;

// Add click handler to enable audio context on any user interaction
document.addEventListener('click', enableAudioContext, { once: true });
document.addEventListener('touchstart', enableAudioContext, { once: true });

// Initialize button states
document.getElementById('start-btn').disabled = false;
document.getElementById('stop-btn').disabled = true;

console.log('🎵 Enhanced audio streaming script loaded');