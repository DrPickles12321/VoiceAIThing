const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const startBtn = document.getElementById("startBtn");

function log(line) {
  logEl.textContent += line + "\n";
  logEl.scrollTop = logEl.scrollHeight;
}

function setStatus(text) {
  statusEl.textContent = text;
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  try {
    await startCall();
  } catch (err) {
    log(`[error] ${err}`);
    setStatus("error");
    startBtn.disabled = false;
  }
});

async function startCall() {
  setStatus("connecting...");

  const audioCtx = new AudioContext();
  await audioCtx.audioWorklet.addModule("/pcm-worklet.js");

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const micSource = audioCtx.createMediaStreamSource(stream);
  const workletNode = new AudioWorkletNode(audioCtx, "pcm-capture-processor");
  micSource.connect(workletNode); // not connected to destination -- avoid echoing the mic back

  const ws = new WebSocket(`ws://${location.host}/media`);
  ws.binaryType = "arraybuffer";

  let sendingEnabled = false;
  let pendingAudio = null; // { markName, sampleRate } set by the last audio_start message
  let nextPlayTime = 0;

  ws.onopen = () => {
    setStatus("connected -- doctor is introducing the call");
    ws.send(JSON.stringify({ type: "start", sampleRate: audioCtx.sampleRate }));
  };

  workletNode.port.onmessage = (event) => {
    if (sendingEnabled && ws.readyState === WebSocket.OPEN) {
      ws.send(event.data);
    }
  };

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
      const msg = JSON.parse(event.data);
      handleControlMessage(msg);
    } else {
      playPcm16(event.data);
    }
  };

  ws.onclose = () => {
    setStatus("call ended");
    stream.getTracks().forEach((t) => t.stop());
  };

  function handleControlMessage(msg) {
    switch (msg.type) {
      case "state":
        sendingEnabled = msg.state === "LISTENING";
        setStatus(msg.state.toLowerCase().replaceAll("_", " "));
        log(`[state] ${msg.state}`);
        break;
      case "audio_start":
        pendingAudio = { markName: msg.markName, sampleRate: msg.sampleRate };
        break;
      case "transcript":
        log(`[patient] ${msg.text}`);
        break;
      case "mapping":
        log(
          `[claude] mapped_value=${msg.mapped_value} confidence=${msg.confidence} ` +
            `needs_clarification=${msg.needs_clarification}`,
        );
        break;
      case "gait_link":
        log(`[gait-checker] link: ${msg.url} (sent via SMS: ${msg.sent_via_sms})`);
        break;
      case "survey_submitted":
        log(`[gait-checker] survey submitted: ${msg.ok}`);
        break;
      case "error":
        log(`[error] ${msg.text}`);
        break;
    }
  }

  function playPcm16(arrayBuffer) {
    const { markName, sampleRate } = pendingAudio ?? { markName: null, sampleRate: 24000 };
    const int16 = new Int16Array(arrayBuffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;

    const buffer = audioCtx.createBuffer(1, float32.length, sampleRate);
    buffer.copyToChannel(float32, 0);

    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    src.connect(audioCtx.destination);

    const startAt = Math.max(audioCtx.currentTime, nextPlayTime);
    src.start(startAt);
    nextPlayTime = startAt + buffer.duration;

    if (markName) {
      const delayMs = Math.max(0, (nextPlayTime - audioCtx.currentTime) * 1000);
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "playback_done", markName }));
        }
      }, delayMs);
    }
  }
}
