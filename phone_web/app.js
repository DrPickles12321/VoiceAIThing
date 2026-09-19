const dialer = document.querySelector("#dialer");
const statusLine = document.querySelector("#status");
const configLine = document.querySelector("#config");
const transcript = document.querySelector("#transcript");
const button = dialer.querySelector("button");

let pollTimer = null;

async function loadConfig() {
  const response = await fetch("/api/config");
  const data = await response.json();
  if (data.ready) {
    configLine.textContent = `Ready. Calls originate from your Twilio number via ${data.public_base_url}.`;
    return;
  }
  const missing = [];
  if (!data.twilio_configured) missing.push("Twilio credentials");
  if (!data.deepgram_configured) missing.push("Deepgram key");
  if (!data.public_base_url) missing.push("PUBLIC_BASE_URL");
  configLine.textContent = `Not ready: set ${missing.join(", ")} in .env.`;
  button.disabled = true;
}

function renderTranscript(lines) {
  transcript.replaceChildren();
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    transcript.appendChild(item);
  }
}

function pollCall(sessionId) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const response = await fetch(`/api/calls/${sessionId}`);
    if (!response.ok) return;
    const record = await response.json();
    renderTranscript(record.transcript);
    if (record.status === "completed") {
      clearInterval(pollTimer);
      statusLine.textContent = `Call finished (${record.final_status}). ${record.answers.length} answers confirmed.`;
      button.disabled = false;
    }
  }, 1500);
}

dialer.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  transcript.replaceChildren();
  statusLine.textContent = "Dialing...";
  const response = await fetch("/api/calls", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      to_number: document.querySelector("#to").value.trim(),
      patient_code: document.querySelector("#patient").value,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    statusLine.textContent = data.detail || "Could not place the call.";
    button.disabled = false;
    return;
  }
  statusLine.textContent = `Calling ${data.to_number} (${data.status}). Answer the phone to start the survey.`;
  pollCall(data.session_id);
});

loadConfig();
