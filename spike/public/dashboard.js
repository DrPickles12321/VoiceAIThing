const callsBody = document.getElementById("callsBody");
const listView = document.getElementById("listView");
const detail = document.getElementById("detail");
const detailContent = document.getElementById("detailContent");
const backLink = document.getElementById("backLink");

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  });
  children.forEach((c) => node.appendChild(c));
  return node;
}

async function loadCallList() {
  const res = await fetch("/api/calls");
  const calls = await res.json();

  callsBody.replaceChildren();
  for (const call of calls) {
    const patient = call.patients ?? {};
    const row = el("tr", { class: "call-row" }, [
      el("td", { text: call.started_at ? new Date(call.started_at).toLocaleString() : "--" }),
      el("td", { text: `${patient.full_name ?? "unknown"} (${patient.patient_code ?? "?"})` }),
      el("td", { text: patient.condition_category ?? "--" }),
      el("td", {}, [el("span", { class: `status status-${call.status}`, text: call.status })]),
    ]);
    row.addEventListener("click", () => showCallDetail(call.id));
    callsBody.appendChild(row);
  }

  if (calls.length === 0) {
    callsBody.appendChild(
      el("tr", {}, [el("td", { colspan: "4", text: "No calls yet -- place one from the start page." })]),
    );
  }
}

async function showCallDetail(callId) {
  const res = await fetch(`/api/calls/${callId}`);
  if (!res.ok) {
    detailContent.replaceChildren(el("p", { text: "Failed to load call." }));
  } else {
    const { call, responses } = await res.json();
    renderDetail(call, responses);
  }

  listView.style.display = "none";
  detail.style.display = "block";
  backLink.style.display = "inline-block";
  window.scrollTo(0, 0);
}

function renderDetail(call, responses) {
  const patient = call.patients ?? {};
  const container = el("div");

  container.appendChild(el("h2", { text: `${patient.full_name ?? "Unknown patient"} (${patient.patient_code ?? "?"})` }));
  container.appendChild(
    el("p", {
      text:
        `Condition: ${patient.condition_category ?? "--"} | Status: ${call.status} | ` +
        `Started: ${call.started_at ? new Date(call.started_at).toLocaleString() : "--"} | ` +
        `Ended: ${call.ended_at ? new Date(call.ended_at).toLocaleString() : "--"}`,
    }),
  );

  container.appendChild(el("h3", { text: "Structured answers" }));
  const table = el("table");
  const thead = el("tr", {}, [
    el("th", { text: "Question" }),
    el("th", { text: "Answer" }),
    el("th", { text: "Confidence" }),
    el("th", { text: "Confirmed" }),
    el("th", { text: "Attempts" }),
    el("th", { text: "Flag" }),
  ]);
  table.appendChild(el("thead", {}, [thead]));
  const tbody = el("tbody");
  for (const r of responses) {
    const q = r.survey_questions ?? {};
    tbody.appendChild(
      el("tr", {}, [
        el("td", { text: q.prompt_text ?? q.code ?? "?" }),
        el("td", { text: r.mapped_value_label ?? String(r.mapped_value_code) }),
        el("td", { text: r.llm_confidence != null ? Number(r.llm_confidence).toFixed(2) : "--" }),
        el("td", { text: r.confirmed_by_patient ? "yes" : "no" }),
        el("td", { text: String(r.clarification_attempts ?? 0) }),
        el("td", {}, r.needs_human_review ? [el("span", { class: "flag", text: "needs review" })] : []),
      ]),
    );
  }
  table.appendChild(tbody);
  container.appendChild(table);

  container.appendChild(el("h3", { text: "Transcript" }));
  const transcriptDiv = el("div");
  const transcript = Array.isArray(call.full_transcript) ? call.full_transcript : [];
  if (transcript.length === 0) {
    transcriptDiv.appendChild(el("p", { text: "No transcript recorded." }));
  }
  for (const line of transcript) {
    transcriptDiv.appendChild(
      el("div", { class: `transcript-line ${line.speaker}`, text: `[${line.speaker}] ${line.text}` }),
    );
  }
  container.appendChild(transcriptDiv);

  detailContent.replaceChildren(container);
}

backLink.addEventListener("click", (e) => {
  e.preventDefault();
  detail.style.display = "none";
  listView.style.display = "block";
});

loadCallList();
