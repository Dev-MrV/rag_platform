/**
 * app.js — Enterprise RAG Platform Frontend
 * Handles: File upload, WebSocket CRAG pipeline, log rendering, citations
 */

// ── Configuration ─────────────────────────────────────────────
const API_BASE = 'http://localhost:8000';
const WS_BASE  = 'ws://localhost:8000';

// ── State ─────────────────────────────────────────────────────
let ws = null;
let sessionId = generateSessionId();
let isRunning = false;
let wsConnected = false;
let reconnectTimer = null;
let activeDocIds = [];
let currentThinkingEl = null;

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateSessionBadge();
  connectWebSocket();
  loadDocuments();
  document.getElementById('query-input').addEventListener('input', syncSendBtn);
});

// ── Session ───────────────────────────────────────────────────
function generateSessionId() {
  return 'ses-' + Math.random().toString(36).slice(2, 10);
}
function updateSessionBadge() {
  document.getElementById('session-badge').textContent = `Session: ${sessionId.slice(0,12)}`;
}

// ── WebSocket ─────────────────────────────────────────────────
function connectWebSocket() {
  if (ws) { try { ws.close(); } catch(e){} }

  setWsStatus('connecting');
  ws = new WebSocket(`${WS_BASE}/chat`);

  ws.onopen = () => {
    wsConnected = true;
    setWsStatus('connected');
    document.getElementById('send-btn').disabled = false;
    appendLog('system', '🔗 Connected to RAG backend.', 'SYSTEM');
  };

  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      handlePipelineEvent(data);
    } catch(e) {
      console.error('WS message parse error:', e);
    }
  };

  ws.onclose = () => {
    wsConnected = false;
    setWsStatus('error');
    document.getElementById('send-btn').disabled = true;
    appendLog('error', '⚠️ Connection lost. Reconnecting in 4s…', 'WS');
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectWebSocket, 4000);
  };

  ws.onerror = () => {
    wsConnected = false;
    setWsStatus('error');
  };
}

function setWsStatus(state) {
  const dot = document.getElementById('ws-status-dot');
  const label = document.getElementById('ws-status-label');
  dot.className = 'status-dot';
  if (state === 'connected')   { dot.classList.add('connected'); label.textContent = 'Connected'; }
  else if (state === 'error')  { dot.classList.add('error');     label.textContent = 'Disconnected'; }
  else                         {                                  label.textContent = 'Connecting…'; }
}

// ── Pipeline Event Handler ────────────────────────────────────
function handlePipelineEvent(event) {
  const step   = event.step || '';
  const status = event.status || '';
  const msg    = event.message || '';

  switch(step) {
    case 'retrieve':
      setTraceActive('trace-retrieve');
      appendLog('retrieve', `🔍 ${msg}`, 'RETRIEVE');
      break;

    case 'grade':
      setTraceActive('trace-grade');
      if (status === 'ACCURATE') {
        appendLog('grade-ok',
          `✅ ${msg}${event.avg_score !== undefined ? ` (avg score: ${event.avg_score})` : ''}`,
          'GRADE ✓');
        setTraceDone('trace-retrieve');
        setTraceDone('trace-grade');
        setTraceSkipped('trace-rewrite');
        setTraceSkipped('trace-web');
      } else {
        appendLog('grade-fail',
          `⚠️ ${msg}`,
          'GRADE ✗');
        setTraceDone('trace-retrieve');
        setTraceDone('trace-grade');
      }
      break;

    case 'rewrite':
      setTraceActive('trace-rewrite');
      appendLog('rewrite', `✏️ ${msg}`, 'REWRITE');
      if (status === 'done') setTraceDone('trace-rewrite');
      break;

    case 'web_search':
      setTraceActive('trace-web');
      appendLog('websearch', `🌐 ${msg}`, 'WEB');
      if (status === 'done') {
        setTraceDone('trace-web');
        if (event.sources && event.sources.length > 0) {
          event.sources.forEach(s => {
            appendLog('websearch', `   └─ ${s.title} — ${s.url}`, 'SRC');
          });
        }
      }
      break;

    case 'generate':
      setTraceActive('trace-generate');
      appendLog('generate', `🤖 ${msg}`, 'GEN');
      break;

    case 'complete':
      setTraceDone('trace-generate');
      removeThinking();
      renderAnswer(event);
      setRunning(false);
      appendLog('done', '🎉 Pipeline complete.', 'DONE');
      break;

    case 'error':
      removeThinking();
      appendLog('error', `❌ Error: ${event.error || 'Unknown error'}`, 'ERR');
      renderError(event.error || 'An error occurred.');
      setRunning(false);
      break;
  }
}

// ── Sending Query ─────────────────────────────────────────────
function sendQuery() {
  const input = document.getElementById('query-input');
  const query = input.value.trim();
  if (!query || isRunning || !wsConnected) return;

  // Get selected doc IDs
  const checkboxes = Array.from(document.querySelectorAll('.doc-filter-cb'));
  const docIds = checkboxes
    .filter(cb => cb.checked && cb.value !== '')
    .map(cb => cb.value);

  // Add user message
  appendUserMessage(query);
  appendThinking();
  resetTrace();
  input.value = '';
  autoResizeTextarea(input);
  setRunning(true);

  // Hide welcome card
  const wc = document.getElementById('welcome-card');
  if (wc) wc.remove();

  // Send via WebSocket
  ws.send(JSON.stringify({
    query,
    doc_ids: docIds,
    session_id: sessionId,
  }));

  appendLog('system', `📤 Query sent: "${query.slice(0,80)}${query.length>80?'…':''}"`, 'USER');
}

function handleQueryKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQuery();
  }
}

function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function syncSendBtn() {
  const input = document.getElementById('query-input');
  const btn   = document.getElementById('send-btn');
  btn.disabled = !input.value.trim() || isRunning || !wsConnected;
}

function setRunning(state) {
  isRunning = state;
  const btn = document.getElementById('send-btn');
  btn.disabled = state || !wsConnected;
  btn.classList.toggle('loading', state);
}

// ── Chat Rendering ────────────────────────────────────────────
function appendUserMessage(text) {
  const chat = document.getElementById('chat-container');
  const wrap = document.createElement('div');
  wrap.className = 'message-wrap user';
  wrap.innerHTML = `
    <div class="message-bubble">${escapeHtml(text)}</div>
    <div class="message-meta">${formatTime()}</div>
  `;
  chat.appendChild(wrap);
  scrollChatToBottom();
}

function appendThinking() {
  const chat = document.getElementById('chat-container');
  const wrap = document.createElement('div');
  wrap.className = 'message-wrap assistant';
  wrap.id = 'thinking-indicator';
  wrap.innerHTML = `
    <div class="thinking-wrap">
      <div class="thinking-dots"><span></span><span></span><span></span></div>
    </div>
    <div class="message-meta">Processing…</div>
  `;
  chat.appendChild(wrap);
  currentThinkingEl = wrap;
  scrollChatToBottom();
}

function removeThinking() {
  if (currentThinkingEl) {
    currentThinkingEl.remove();
    currentThinkingEl = null;
  }
}

function renderAnswer(event) {
  const chat = document.getElementById('chat-container');
  const answer  = event.answer  || '(No answer generated)';
  const citations = event.citations || [];
  const path = (event.pipeline_path || []).join(' → ');

  const wrap = document.createElement('div');
  wrap.className = 'message-wrap assistant';

  // Format answer text with citation markers styled
  let formattedAnswer = escapeHtml(answer)
    .replace(/\[Doc (\d+)\]/g, '<span style="color:var(--accent-2);font-weight:600;">[Doc $1]</span>')
    .replace(/\[Web (\d+)\]/g, '<span style="color:var(--accent-purple);font-weight:600;">[Web $1]</span>');

  let citationsHtml = '';
  if (citations.length > 0) {
    const cItems = citations.map((c, i) => {
      if (c.type === 'document') {
        const score = c.grade_score !== undefined
          ? `<span class="citation-score">${c.grade_score.toFixed ? c.grade_score.toFixed(3) : c.grade_score}</span>`
          : '';
        return `
          <div class="citation-card">
            <span class="citation-tag doc-tag">${escapeHtml(c.label || 'Doc ' + (i+1))}</span>
            <div class="citation-info">
              <div class="citation-title">📄 ${escapeHtml(c.filename)}</div>
              <div class="citation-sub">Page ${c.page}</div>
              ${c.snippet ? `<div class="citation-snippet">"${escapeHtml(c.snippet)}…"</div>` : ''}
            </div>
            ${score}
          </div>`;
      } else {
        return `
          <div class="citation-card">
            <span class="citation-tag web-tag">Web ${i+1}</span>
            <div class="citation-info">
              <div class="citation-title">🌐 ${escapeHtml(c.label || c.url)}</div>
              <div class="citation-sub"><a href="${c.url}" target="_blank" style="color:var(--accent-purple);text-decoration:none;">${escapeHtml(c.url)}</a></div>
              ${c.snippet ? `<div class="citation-snippet">"${escapeHtml(c.snippet)}…"</div>` : ''}
            </div>
          </div>`;
      }
    }).join('');
    citationsHtml = `
      <div class="citations-block">
        <div class="citations-label">📎 Sources & Citations</div>
        ${cItems}
      </div>`;
  }

  const pathHtml = path
    ? `<div style="font-size:0.68rem;color:var(--text-muted);margin-top:10px;font-family:'Fira Code',monospace;">Pipeline: ${escapeHtml(path)}</div>`
    : '';

  wrap.innerHTML = `
    <div class="message-bubble" style="max-width:90%;">
      <div style="line-height:1.75;">${formattedAnswer}</div>
      ${pathHtml}
    </div>
    ${citationsHtml}
    <div class="message-meta">${formatTime()}</div>
  `;

  chat.appendChild(wrap);
  scrollChatToBottom();
}

function renderError(errorMsg) {
  const chat = document.getElementById('chat-container');
  const wrap = document.createElement('div');
  wrap.className = 'message-wrap assistant';
  wrap.innerHTML = `
    <div class="message-bubble" style="border-color:rgba(255,77,109,0.3);background:rgba(255,77,109,0.07);">
      <span style="color:var(--accent-red);">❌ Error:</span> ${escapeHtml(errorMsg)}
    </div>
    <div class="message-meta">${formatTime()}</div>
  `;
  chat.appendChild(wrap);
  scrollChatToBottom();
}

function scrollChatToBottom() {
  const chat = document.getElementById('chat-container');
  setTimeout(() => { chat.scrollTop = chat.scrollHeight; }, 50);
}

// ── Log Terminal ──────────────────────────────────────────────
function appendLog(type, message, badge) {
  const terminal = document.getElementById('log-terminal');
  const entry = document.createElement('div');
  const badgeClassMap = {
    'retrieve':  'badge-retrieve',
    'grade-ok':  'badge-grade',
    'grade-fail':'badge-fail',
    'rewrite':   'badge-rewrite',
    'websearch': 'badge-web',
    'generate':  'badge-generate',
    'done':      'badge-done',
    'error':     'badge-error',
    'system':    '',
  };
  const badgeCls = badgeClassMap[type] || '';
  const badgeHtml = badge && badgeCls
    ? `<span class="log-badge ${badgeCls}">${escapeHtml(badge)}</span>`
    : `<span class="log-time">${formatTime()}</span>`;

  entry.className = `log-entry log-${type}`;
  entry.innerHTML = `${badgeHtml}<span class="log-msg">${escapeHtml(message)}</span>`;
  terminal.appendChild(entry);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearLogs() {
  const terminal = document.getElementById('log-terminal');
  terminal.innerHTML = `<div class="log-entry log-system"><span class="log-time">SYSTEM</span><span class="log-msg">Log cleared.</span></div>`;
}

// ── Pipeline Trace ────────────────────────────────────────────
function resetTrace() {
  ['trace-retrieve','trace-grade','trace-rewrite','trace-web','trace-generate'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.className = 'trace-node inactive';
  });
}
function setTraceActive(id) {
  const el = document.getElementById(id);
  if (el) el.className = 'trace-node active';
}
function setTraceDone(id) {
  const el = document.getElementById(id);
  if (el) el.className = 'trace-node done';
}
function setTraceSkipped(id) {
  const el = document.getElementById(id);
  if (el) el.className = 'trace-node skipped';
}

// ── Documents ─────────────────────────────────────────────────
async function loadDocuments() {
  try {
    const res = await fetch(`${API_BASE}/documents`);
    const data = await res.json();
    renderDocumentList(data.documents || []);
    updateDocFilterSelect(data.documents || []);
  } catch(e) {
    console.error('Failed to load documents:', e);
  }
}

function renderDocumentList(docs) {
  const list = document.getElementById('documents-list');
  if (!docs || docs.length === 0) {
    list.innerHTML = '<p class="empty-hint">No documents indexed yet. Upload a PDF to begin.</p>';
    return;
  }
  list.innerHTML = docs.map(doc => `
    <div class="doc-item" id="doc-${doc.doc_id}">
      <span class="doc-item-icon">📄</span>
      <div class="doc-item-info">
        <div class="doc-item-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</div>
        <div class="doc-item-meta">
          <span class="doc-meta-chip">${doc.total_pages} pages</span>
          <span class="doc-meta-chip">${doc.total_chunks} chunks</span>
        </div>
      </div>
      <button class="doc-delete-btn" onclick="deleteDocument('${doc.doc_id}')" title="Delete document" aria-label="Delete ${escapeHtml(doc.filename)}">🗑</button>
    </div>
  `).join('');
}

function toggleFilterDropdown(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  const btn = document.getElementById('doc-filter-btn');
  const dropdown = document.getElementById('doc-filter-dropdown');
  if (!btn || !dropdown) return;
  const isOpen = !dropdown.hidden;
  
  if (isOpen) {
    dropdown.hidden = true;
    btn.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
  } else {
    dropdown.hidden = false;
    btn.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
  }
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
  const btn = document.getElementById('doc-filter-btn');
  const dropdown = document.getElementById('doc-filter-dropdown');
  if (btn && dropdown && !dropdown.hidden) {
    if (!btn.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.hidden = true;
      btn.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    }
  }
});

function updateDocFilterSelect(docs) {
  const dropdown = document.getElementById('doc-filter-dropdown');
  if (!dropdown) return;
  
  let html = `
    <label class="filter-option">
      <input type="checkbox" value="" class="doc-filter-cb" onchange="handleFilterChange(this)" checked>
      <span class="filter-option-text">All Documents</span>
    </label>
  `;
  
  docs.forEach(doc => {
    html += `
      <label class="filter-option">
        <input type="checkbox" value="${escapeHtml(doc.doc_id)}" class="doc-filter-cb" onchange="handleFilterChange(this)">
        <span class="filter-option-text" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
      </label>
    `;
  });
  
  dropdown.innerHTML = html;
  updateFilterText();
}

function handleFilterChange(changedCb) {
  const checkboxes = Array.from(document.querySelectorAll('.doc-filter-cb'));
  const allCb = checkboxes.find(cb => cb.value === '');
  
  if (changedCb.value === '') {
    if (changedCb.checked) {
      checkboxes.forEach(cb => { if (cb.value !== '') cb.checked = false; });
    } else {
      const othersChecked = checkboxes.some(cb => cb.value !== '' && cb.checked);
      if (!othersChecked) changedCb.checked = true;
    }
  } else {
    if (changedCb.checked) {
      if (allCb) allCb.checked = false;
    } else {
      const othersChecked = checkboxes.some(cb => cb.value !== '' && cb.checked);
      if (!othersChecked && allCb) allCb.checked = true;
    }
  }
  updateFilterText();
}

function updateFilterText() {
  const textEl = document.getElementById('doc-filter-text');
  if (!textEl) return;
  const checkboxes = Array.from(document.querySelectorAll('.doc-filter-cb'));
  const checked = checkboxes.filter(cb => cb.checked);
  
  if (checked.length === 0 || checkboxes.some(cb => cb.value === '' && cb.checked)) {
    textEl.textContent = 'All Documents';
  } else if (checked.length === 1) {
    textEl.textContent = checked[0].nextElementSibling.textContent;
  } else {
    textEl.textContent = `${checked.length} documents selected`;
  }
}

async function deleteDocument(docId) {
  if (!confirm('Delete this document and all its indexed chunks?')) return;
  try {
    await fetch(`${API_BASE}/documents/${docId}`, { method: 'DELETE' });
    appendLog('system', `🗑 Document deleted.`, 'SYS');
    loadDocuments();
  } catch(e) {
    appendLog('error', `Failed to delete document: ${e.message}`, 'ERR');
  }
}

// ── File Upload ───────────────────────────────────────────────
function handleDragEnter(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.add('dragover');
}
function handleDragLeave(e) {
  document.getElementById('drop-zone').classList.remove('dragover');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
  if (files.length === 0) { alert('Please drop PDF files only.'); return; }
  uploadFiles(files);
}
function handleFileSelect(e) {
  const files = Array.from(e.target.files);
  if (files.length > 0) uploadFiles(files);
  e.target.value = '';
}

async function uploadFiles(files) {
  for (const file of files) {
    await uploadSingleFile(file);
  }
  loadDocuments();
}

async function uploadSingleFile(file) {
  const progressWrap = document.getElementById('upload-progress-wrap');
  const progressBar  = document.getElementById('upload-progress-bar');
  const progressLabel = document.getElementById('upload-progress-label');

  progressWrap.hidden = false;
  progressBar.style.width = '10%';
  progressLabel.textContent = `Uploading ${file.name}…`;
  appendLog('system', `📤 Uploading "${file.name}"…`, 'UPLOAD');

  const formData = new FormData();
  formData.append('file', file);
  formData.append('session_id', sessionId);

  try {
    progressBar.style.width = '40%';
    const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    progressBar.style.width = '80%';
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || 'Upload failed');

    progressBar.style.width = '100%';
    progressLabel.textContent = `✅ "${file.name}" indexed — ${data.total_chunks} chunks`;
    appendLog('done', `✅ Indexed "${file.name}" — ${data.total_pages} pages, ${data.total_chunks} chunks.`, 'DONE');
  } catch(e) {
    progressBar.style.backgroundColor = 'var(--accent-red)';
    progressLabel.textContent = `❌ Failed: ${e.message}`;
    appendLog('error', `❌ Upload failed for "${file.name}": ${e.message}`, 'ERR');
  }

  setTimeout(() => {
    progressWrap.hidden = true;
    progressBar.style.width = '0%';
    progressBar.style.backgroundColor = '';
  }, 3000);
}

// ── Utilities ─────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime() {
  return new Date().toLocaleTimeString('en-US', { hour12: false, hour:'2-digit', minute:'2-digit', second:'2-digit' });
}
