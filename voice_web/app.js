let sessionId = null;
let recorder = null;
let chunks = [];

const conversation = document.querySelector("#conversation");
const recordButton = document.querySelector("#record");
const status = document.querySelector("#status");

function addLine(speaker, text) {
  const line = document.createElement("p");
  line.className = speaker;
  line.textContent = `${speaker === "assistant" ? "Survey" : "You"}: ${text}`;
  conversation.appendChild(line);
  line.scrollIntoView({ behavior: "smooth", block: "end" });
}

function speak(text) {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}

document.querySelector("#start").addEventListener("click", async () => {
  const patientCode = document.querySelector("#patient").value.trim();
  conversation.replaceChildren();
  status.textContent = "Starting...";
  const response = await fetch(`/api/sessions?patient_code=${encodeURIComponent(patientCode)}`, {
    method: "POST",
  });
  const data = await response.json();
  if (!response.ok) {
    status.textContent = data.detail || "Could not start the survey.";
    return;
  }
  sessionId = data.session_id;
  addLine("assistant", data.prompt);
  speak(data.prompt);
  recordButton.disabled = false;
  status.textContent = "Ready. Click the button, speak, then click it again to send.";
});

recordButton.addEventListener("click", async () => {
  if (recorder?.state === "recording") {
    recorder.stop();
    recordButton.disabled = true;
    status.textContent = "Transcribing with Deepgram...";
    return;
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
  recorder.addEventListener("stop", async () => {
    stream.getTracks().forEach((track) => track.stop());
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    const form = new FormData();
    form.append("audio", blob, "answer.webm");
    const response = await fetch(`/api/sessions/${sessionId}/audio`, {
      method: "POST",
      body: form,
    });
    const data = await response.json();
    if (!response.ok) {
      status.textContent = data.detail || "Could not process the recording.";
      recordButton.disabled = false;
      return;
    }
    addLine("user", data.transcript);
    addLine("assistant", data.prompt);
    speak(data.prompt);
    recordButton.disabled = data.state === "complete" || data.state === "escalated";
    status.textContent = recordButton.disabled ? "Survey finished." : "Ready for the next response.";
  });
  recorder.start();
  recordButton.textContent = "Stop and send";
  status.textContent = "Listening...";
});
