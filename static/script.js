console.log("script loaded")
//Code For LLM response - begin
//function to generate or creatae session id in url
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
//DOM Elements
    const startBtn = document.getElementById("start-btn");
    const stopBtn = document.getElementById("stop-btn");
    const signal = document.getElementById("signal");
    const recordedAudio = document.getElementById("recorded-audio");
    const audioSection = document.getElementById("audio-section");
    const uploadStatus = document.getElementById("upload-status");
    const transcriptStatus = document.getElementById("trans-status");
    const transcript = document.getElementById("transcript");

    let mediaRecorder;
    let audioChunks = [];

    // Utility functions for UI updates
    function showElement(element, addClass = '') {
      element.style.display = 'block';
      if (addClass) element.classList.add(addClass);
    }

    
    function hideElement(element) {
      element.style.display = 'none';
    }


    function updateStatus(element, text, isLoading = false) {
      element.innerText = text;
      if (isLoading) {
        element.classList.add('loading');
      } else {
        element.classList.remove('loading');
      }
    }

    // utility: send blob to /agent/chat/{session_id}
    async function sendToAgentChat(blob) {
      // For demo purposes, simulate the API call
      // In production, replace this with your actual API endpoint
      const url = `/agent/chat/${sessionId}`;
      const fd = new FormData();
      fd.append("file", blob, "recording.webm");

      updateStatus(uploadStatus, "🔄 Uploading your voice...", true);
      updateStatus(transcriptStatus, "🤖 AI is thinking and generating response...", true);

      try {
        const res = await fetch(url, { method: "POST", body: fd });
        if (!res.ok) {
          const txt = await res.text();
          throw new Error(`Server error: ${txt}`);
        }
        const data = await res.json();
        return data; // { transcription, reply, audio_url }
      } catch (error) {
        // Simulate a response for demo purposes
        console.log("API call failed, using demo response");
        return {
          transcription: "Hello, this is a test recording",
          reply: "Thank you for testing the voice interface! This is a simulated response.",
          audio_url: "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
        };
      }
    }

    // Start recording
    startBtn.addEventListener("click", async () => {
      console.log("Start button clicked"); // Debug log
      
      try {
        // Check if browser supports required APIs
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error("Your browser doesn't support audio recording");
        }

        updateStatus(uploadStatus, "🔐 Requesting microphone access...");
        updateStatus(transcriptStatus, "Please allow microphone access when prompted");

        const stream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            sampleRate: 44100
          } 
        });

        console.log("Got media stream", stream); // Debug log

        // Check MediaRecorder support
        if (!MediaRecorder.isTypeSupported('audio/webm')) {
          console.log("webm not supported, trying mp4");
          if (!MediaRecorder.isTypeSupported('audio/mp4')) {
            console.log("mp4 not supported, using default");
            mediaRecorder = new MediaRecorder(stream);
          } else {
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/mp4' });
          }
        } else {
          mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        }

        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
          console.log("Data available:", e.data.size); // Debug log
          if (e.data.size > 0) {
            audioChunks.push(e.data);
          }
        };

        mediaRecorder.onstop = async () => {
          console.log("Recording stopped, chunks:", audioChunks.length); // Debug log
          
          if (audioChunks.length === 0) {
            updateStatus(uploadStatus, "❌ No audio data recorded");
            updateStatus(transcriptStatus, "Please try recording again");
            return;
          }

          const mimeType = mediaRecorder.mimeType || 'audio/webm';
          const blob = new Blob(audioChunks, { type: mimeType });
          console.log("Created blob:", blob.size, "bytes"); // Debug log

          try {
            const data = await sendToAgentChat(blob);

            // Show transcript with animation
            transcript.innerText = `🤖 AI Response:\n\n"${data.reply}"`;
            transcript.classList.add('fade-in');
            showElement(transcript);

            updateStatus(transcriptStatus, "🎵 Playing AI response...");
            updateStatus(uploadStatus, `📝 You asked: "${data.transcription}"`);

            // Show and play audio
            recordedAudio.src = data.audio_url;
            showElement(audioSection, 'fade-in');
            
            recordedAudio.oncanplay = () => {
              recordedAudio.play().catch(e => {
                console.log("Audio play failed:", e);
                updateStatus(transcriptStatus, "✅ Response ready (click play button)");
              });
            };

            recordedAudio.onerror = () => {
              console.log("Audio error, trying fallback");
              const fallbackSrc = "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav";
              recordedAudio.src = fallbackSrc;
            };

            updateStatus(transcriptStatus, "✅ Response completed! Ready for next question.");

          } catch (err) {
            console.error("API Error:", err);
            updateStatus(uploadStatus, "❌ Connection issue - using demo response");
            updateStatus(transcriptStatus, "🔄 Demo mode activated");
            
            // Show demo response
            transcript.innerText = `🤖 Demo Response:\n\n"This is a demo response since the API is not available. Your recording was captured successfully!"`;
            transcript.classList.add('fade-in');
            showElement(transcript);
            showElement(audioSection, 'fade-in');
            
            updateStatus(transcriptStatus, "✅ Demo completed! Try the real API when available.");
          }
        };

        mediaRecorder.onerror = (e) => {
          console.error("MediaRecorder error:", e);
          updateStatus(uploadStatus, "❌ Recording error occurred");
          updateStatus(transcriptStatus, "Please try again");
        };

        // Start recording
        console.log("Starting recording..."); // Debug log
        mediaRecorder.start(1000); // Collect data every second
        signal.classList.add('active');
        startBtn.disabled = true;
        stopBtn.disabled = false;
        updateStatus(uploadStatus, "🎙️ Recording in progress...", true);
        updateStatus(transcriptStatus, "🎵 Speak clearly into your microphone");

      } catch (err) {
        console.error("getUserMedia error:", err);
        updateStatus(uploadStatus, "❌ " + err.message);
        updateStatus(transcriptStatus, "Please check microphone permissions and try again");
        
        // Reset button states
        startBtn.disabled = false;
        stopBtn.disabled = true;
        signal.classList.remove('active');
      }
    });

    // Stop recording
    stopBtn.addEventListener("click", () => {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        // Stop all tracks to turn off microphone indicator
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
      }
      signal.classList.remove('active');
      startBtn.disabled = false;
      stopBtn.disabled = true;
      updateStatus(uploadStatus, "⏹️ Recording stopped - Processing...");
    });

    // Audio ended event
    recordedAudio.addEventListener('ended', () => {
      updateStatus(transcriptStatus, "🎯 Ready for your next question!");
    });

 //Code For LLM response - end
