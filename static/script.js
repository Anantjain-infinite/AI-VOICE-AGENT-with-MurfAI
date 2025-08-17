let ws;
let mediaRecorder;
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
startBtn.addEventListener("click", async () => {
  // connect websocket
  ws = new WebSocket("ws://127.0.0.1:8000/ws");
    stopBtn.disabled = false
    startBtn.disabled = true

  ws.onopen = async () => {
    console.log("WebSocket connected");

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
        event.data.arrayBuffer().then(buffer => {
          ws.send(buffer); // send binary chunk
        });
      }
    };

    mediaRecorder.start(500); // send every 500ms
    console.log("Recording and streaming...");
  };
});

stopBtn.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
  }
  stopBtn.disabled = true
  startBtn.disabled = false
  if (ws && ws.readyState === WebSocket.OPEN) {
    // ws.send("STOP"); // signal server
    ws.close();
  }
  console.log("Stopped recording and streaming");
});
