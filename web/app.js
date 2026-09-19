const $ = (id) => document.getElementById(id);
const terminal = new Set(['complete', 'escalated', 'stopped']);
const labels = ['Going up or down stairs', 'Walking on an uneven surface', 'Rising from sitting', 'Picking up an object', 'Lying in bed', 'Sitting'];
let session = null;
let busy = false;
let failed = false;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'The request failed. Start a new survey to try again.');
  }
  return response.json();
}

function scrollToLatest() {
  const panel = document.querySelector('.conversation');
  panel.scrollTop = panel.scrollHeight;
}

function message(text, role) {
  const row = document.createElement('div');
  row.className = `message ${role}`;
  if (role === 'assistant') {
    const avatar = document.createElement('span');
    avatar.className = 'avatar'; avatar.textContent = '✳'; avatar.setAttribute('aria-hidden', 'true');
    row.append(avatar);
  }
  const body = document.createElement('div'); body.className = 'message-body';
  const speaker = document.createElement('p'); speaker.className = 'speaker';
  speaker.textContent = role === 'assistant' ? 'Survey assistant' : 'You';
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  bubble.textContent = text; // Transcripts and model output are always plain text.
  body.append(speaker, bubble); row.append(body); $('messages').append(row);
  scrollToLatest();
}

function controls() {
  const ended = !session || terminal.has(session.state);
  $('answer').disabled = busy || ended || failed;
  $('send').disabled = busy || ended || failed || !$('answer').value.trim();
  $('restart').disabled = busy;
  $('mode').disabled = busy;
  $('thinking').hidden = !busy;
  $('suggestions').querySelectorAll('button').forEach(button => button.disabled = busy || failed);
}

function render() {
  $('progress').value = session.answered_count;
  $('progress-label').textContent = `${session.answered_count} of ${session.question_count}`;
  document.querySelectorAll('#questions li').forEach((item, index) => {
    item.className = index < session.answered_count ? 'done' : index === session.answered_count && !terminal.has(session.state) ? 'current' : '';
  });
  $('suggestions').replaceChildren();
  const replies = terminal.has(session.state) ? [] : session.state === 'confirming' ? ['Yes', 'No'] : ['None', 'Mild', 'Moderate', 'Severe', 'Extreme'];
  for (const reply of replies) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = reply;
    button.addEventListener('click', () => send(reply)); $('suggestions').append(button);
  }
  $('hint').textContent = terminal.has(session.state) ? 'This survey has ended. Start a new survey to try again.' : `${session.answered_count} of 6 confirmed · Enter to send, Shift + Enter for a new line · Say “stop” to end`;
  $('results').hidden = session.state !== 'complete';
  if (session.state === 'complete') {
    $('result-list').replaceChildren();
    Object.values(session.responses).forEach((answer, index) => {
      const row = document.createElement('div'); row.className = 'result-row';
      const label = document.createElement('span'); label.textContent = labels[index];
      const value = document.createElement('strong'); value.textContent = answer.value;
      row.append(label, value); $('result-list').append(row);
    });
  }
  controls(); scrollToLatest();
}

function showError(error) {
  failed = true;
  $('error').textContent = `${error.message || 'Connection lost.'} Your last message may have been processed. Start a new survey to continue.`;
  $('error').hidden = false;
  scrollToLatest();
}

async function start() {
  if (busy) return;
  busy = true; failed = false; controls();
  $('error').hidden = true;
  try {
    const next = await api('/api/sessions', {mode: $('mode').value});
    session = next;
    $('messages').replaceChildren(); $('answer').value = '';
    $('mode-note').textContent = session.mode === 'offline' ? 'Offline: choose an answer below.' : 'AI mode: describe your answer naturally.';
    message(session.prompt, 'assistant');
  } catch (error) { showError(error); }
  finally {
    busy = false;
    if (session) render(); else controls();
    if (!failed) $('answer').focus();
  }
}

async function send(text) {
  text = text.trim();
  if (!text || busy || failed || !session || terminal.has(session.state)) return;
  busy = true; controls(); $('error').hidden = true;
  message(text, 'user'); $('answer').value = '';
  try {
    session = {...session, ...await api(`/api/sessions/${session.session_id}/turns`, {transcript: text})};
    message(session.prompt, 'assistant');
  } catch (error) { showError(error); }
  finally { busy = false; render(); if (!failed) $('answer').focus(); }
}

$('composer').addEventListener('submit', event => {event.preventDefault(); send($('answer').value);});
$('answer').addEventListener('input', controls);
$('answer').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); send($('answer').value);}
});
$('restart').addEventListener('click', start);
$('mode').addEventListener('change', start);
(async () => {
  try {
    const config = await api('/api/config');
    $('mode').querySelector('[value="openai"]').disabled = !config.openai_available;
    $('mode').value = config.default_mode;
    if (!config.openai_available) $('mode').querySelector('[value="openai"]').textContent = 'OpenAI (add key to .env)';
    await start();
  } catch (error) { showError(error); controls(); }
})();
