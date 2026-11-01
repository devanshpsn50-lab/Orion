/* ============================================================
   Orion — ai.js   (Phase 2: AI Brain UI)
   Loaded after app.js. Adds: AI page, Smart/Super scan controls,
   AI badges + "why it matched" snippets on results, AI tags in the
   preview panel, and "Find similar".
   ============================================================ */
'use strict';

const ai = {
  status: null,
  pollTimer: null,
  lastStatus: null,
};

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  injectAiNav();
  injectAiPage();
  injectHomeAiBanner();
  replaceGeminiSettings();
  pollAiStatus();
  // Deep links:  http://127.0.0.1:8472/#ai   or   http://127.0.0.1:8472/#q=cat%20photos
  const h = location.hash || '';
  if (h === '#ai') setTimeout(showAI, 50);
  else if (h.startsWith('#q=')) setTimeout(() => doSearch(decodeURIComponent(h.slice(3))), 50);
});

// ── Navigation ────────────────────────────────────────────────────────────────
function injectAiNav() {
  const navScan = document.getElementById('nav-scan');
  if (navScan && !document.getElementById('nav-ai')) {
    const b = document.createElement('button');
    b.className = 'nav-btn';
    b.id = 'nav-ai';
    b.innerHTML = '<span class="nav-btn-icon">🧠</span> AI Brain <span class="nav-ai-dot" id="nav-ai-dot"></span>';
    b.onclick = showAI;
    navScan.insertAdjacentElement('afterend', b);
  }
  const btnStats = document.getElementById('btn-stats');
  if (btnStats && !document.getElementById('btn-ai')) {
    const b = document.createElement('button');
    b.className = 'icon-btn';
    b.id = 'btn-ai';
    b.title = 'AI Brain';
    b.textContent = '🧠';
    b.onclick = showAI;
    btnStats.insertAdjacentElement('beforebegin', b);
  }
}

// Make every other page hide the AI page (app.js's showPage has a fixed list)
const _origShowPage = showPage;
showPage = function (name) {
  const aiPage = document.getElementById('ai-page');
  if (aiPage && name !== 'ai-page') { aiPage.style.display = 'none'; aiPage.classList.remove('visible'); }
  document.getElementById('nav-ai')?.classList.remove('active');
  document.getElementById('btn-ai')?.classList.remove('active');
  _origShowPage(name);
};

function showAI() {
  showPage('ai-page');
  document.getElementById('nav-ai')?.classList.add('active');
  document.getElementById('btn-ai')?.classList.add('active');
  pollAiStatus(true);
}

// ── AI page ───────────────────────────────────────────────────────────────────
function injectAiPage() {
  const main = document.getElementById('main');
  if (!main || document.getElementById('ai-page')) return;
  const page = document.createElement('div');
  page.id = 'ai-page';
  page.innerHTML = `
    <div class="ai-head">
      <h2>🧠 AI Brain</h2>
      <span class="ai-pill" id="ai-pill">Starting…</span>
      <span class="ai-device" id="ai-device"></span>
    </div>
    <p class="ai-lead">
      Orion's AI <strong>looks at</strong> your photos and videos and <strong>reads</strong> your
      documents, so you can search by what's <em>inside</em> a file. Try
      <a href="#" onclick="doSearch('cat');return false;">cat</a>,
      <a href="#" onclick="doSearch('football match');return false;">football match</a>,
      <a href="#" onclick="doSearch('linear algebra pdf');return false;">linear algebra pdf</a>,
      <a href="#" onclick="doSearch('sunset beach');return false;">sunset beach</a>.
    </p>

    <div class="ai-controls">
      <button class="btn-primary" onclick="aiScan('smart')" title="Your own files only (skips system icons & app folders)">⚡ Smart Scan</button>
      <button class="btn-primary ai-super-btn" onclick="aiScan('super')" title="Every single file Orion has indexed">🔥 SUPER SCAN</button>
      <button class="btn-primary ai-ghost-btn" id="ai-pause-btn" onclick="aiTogglePause()">⏸ Pause</button>
      <label class="ai-switch" title="Turn AI on / off">
        <input type="checkbox" id="ai-enabled" onchange="aiSetEnabled(this.checked)" checked>
        <span class="ai-slider"></span><span class="ai-switch-label">AI enabled</span>
      </label>
    </div>

    <div class="ai-progress-card">
      <div class="ai-progress-top">
        <span id="ai-phase-text">—</span>
        <span id="ai-pct" class="ai-pct">0%</span>
      </div>
      <div class="ai-bar"><div class="ai-bar-fill" id="ai-bar"></div></div>
      <div class="ai-current" id="ai-current"></div>
      <div class="ai-phases" id="ai-phases"></div>
    </div>

    <div class="ai-stats">
      <div class="stat-card"><div class="stat-card-value" id="ai-st-understood">—</div><div class="stat-card-label">Files understood</div></div>
      <div class="stat-card"><div class="stat-card-value" id="ai-st-images">—</div><div class="stat-card-label">Images &amp; videos tagged</div></div>
      <div class="stat-card"><div class="stat-card-value" id="ai-st-docs">—</div><div class="stat-card-label">Documents &amp; code read</div></div>
      <div class="stat-card"><div class="stat-card-value" id="ai-st-speed">—</div><div class="stat-card-label">Speed (files / sec)</div></div>
      <div class="stat-card"><div class="stat-card-value" id="ai-st-eta">—</div><div class="stat-card-label">Time remaining</div></div>
      <div class="stat-card"><div class="stat-card-value" id="ai-st-vectors">—</div><div class="stat-card-label">Vectors in GPU memory</div></div>
    </div>

    <div class="section-title" style="margin:6px 0 10px;">👁️ Just understood (live)</div>
    <div class="ai-feed" id="ai-feed"><div class="ai-feed-empty">Nothing yet — the feed fills up while the AI works.</div></div>

    <div class="ai-info">
      <div class="ai-info-title">ℹ️ How Orion's AI works</div>
      <div class="ai-info-body">
        <b>🖼️ Images</b> — <b>CLIP</b> (a vision neural network by OpenAI) turns each picture into 768 numbers describing what it shows, and picks tags like <i>cat → animal, pet</i>.<br>
        <b>🎬 Videos</b> — 5 frames are pulled out of every video and CLIP looks at each one.<br>
        <b>📄 Documents</b> — Orion reads the text inside PDFs, Word, PowerPoint, Excel, EPUB and text files (for big books: title, table of contents and pages sampled across the whole book). A language model (<b>BGE</b>) turns that text into 384 numbers describing its <i>meaning</i>.<br>
        <b>💻 Code &amp; 🎵 Music</b> — source code is read; songs are understood from their tags (title, artist, album, genre).<br><br>
        When you search, your words are turned into the same kind of numbers and compared against every file on the <b>GPU</b> in milliseconds. That's why <i>linear algebra pdf</i> finds a book named <code>dhgfdshg.pdf</code>.<br><br>
        <b>⚡ Smart Scan</b> (default) — only <i>your</i> files: skips Windows, Program Files, AppData, tiny app icons (&lt;20 KB) and library/build folders.<br>
        <b>🔥 SUPER SCAN</b> — every file Orion has indexed, no exceptions. Much longer.<br>
        Everything runs <b>100% offline</b> on your PC. Progress is saved continuously — closing Orion never loses work.
      </div>
    </div>`;
  main.appendChild(page);
}

function injectHomeAiBanner() {
  const idx = document.getElementById('index-banner');
  if (!idx || document.getElementById('home-ai-banner')) return;
  const b = document.createElement('div');
  b.id = 'home-ai-banner';
  b.onclick = showAI;
  b.innerHTML = `<span class="hab-icon">🧠</span><span id="hab-text">AI starting…</span>
                 <div class="hab-bar"><div class="hab-fill" id="hab-fill"></div></div>`;
  idx.insertAdjacentElement('afterend', b);
}

function replaceGeminiSettings() {
  const key = document.getElementById('gemini-key-input');
  const sec = key?.closest('.settings-section');
  if (!sec) return;
  sec.innerHTML = `
    <h3>🧠 AI Search</h3>
    <label class="ai-switch">
      <input type="checkbox" id="ai-enabled-settings" onchange="aiSetEnabled(this.checked)" checked>
      <span class="ai-slider"></span><span class="ai-switch-label">Understand file contents with AI (runs offline on your GPU)</span>
    </label>
    <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap;">
      <button class="btn-primary" onclick="aiScan('smart')">⚡ Smart Scan</button>
      <button class="btn-primary ai-super-btn" onclick="aiScan('super')">🔥 SUPER SCAN</button>
      <button class="btn-primary ai-ghost-btn" onclick="showAI()">Open AI Brain →</button>
    </div>
    <p style="font-size:0.78rem;color:var(--text3);margin-top:8px;">
      Smart Scan = your own files. SUPER SCAN = absolutely everything (including system icons and code libraries).
    </p>`;
}

// ── Controls ──────────────────────────────────────────────────────────────────
async function aiScan(mode) {
  if (mode === 'super') {
    const ok = confirm(
      '🔥 SUPER SCAN\n\nThis makes the AI process EVERY image, video, document and code file ' +
      'Orion has indexed — including Windows, Program Files, AppData, tiny icons and code libraries.\n\n' +
      'It can take a long time (hours) and uses your GPU heavily.\n' +
      'Files already understood are NOT redone.\n\nStart SUPER SCAN?');
    if (!ok) return;
  }
  try {
    await fetch(`${API}/ai/scan`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }) });
    showToast(mode === 'super' ? '🔥 SUPER SCAN started' : '⚡ Smart Scan started');
    pollAiStatus(true);
  } catch { showError('Could not start AI scan'); }
}

async function aiTogglePause() {
  const paused = ai.status?.status === 'paused';
  await fetch(`${API}/ai/${paused ? 'resume' : 'pause'}`, { method: 'POST' });
  showToast(paused ? '▶ AI resumed' : '⏸ AI paused');
  setTimeout(() => pollAiStatus(true), 500);
}

async function aiSetEnabled(on) {
  await fetch(`${API}/ai/enable`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: on }) });
  showToast(on ? '🧠 AI enabled' : 'AI disabled');
  setTimeout(() => pollAiStatus(true), 500);
}

// ── Status polling ────────────────────────────────────────────────────────────
async function pollAiStatus(immediate = false) {
  clearTimeout(ai.pollTimer);
  try {
    const res = await fetch(`${API}/ai/status`);
    ai.status = await res.json();
    renderAiStatus(ai.status);
  } catch {}
  const busy = ai.status && ['loading', 'collecting', 'running', 'starting'].includes(ai.status.status);
  const onPage = document.getElementById('ai-page')?.classList.contains('visible');
  ai.pollTimer = setTimeout(pollAiStatus, (busy || onPage) ? 1500 : 10000);
}

const AI_STATUS_TEXT = {
  starting: 'Starting…', loading: 'Loading AI models…', collecting: 'Finding files…',
  running: 'Understanding files', paused: 'Paused', done: 'Up to date ✓',
  off: 'Off', error: 'Error', unavailable: 'Not installed',
};

function renderAiStatus(s) {
  const pct = s.total > 0 ? Math.min(100, Math.round((s.processed / s.total) * 100)) : (s.status === 'done' ? 100 : 0);
  const db = s.db || {};
  const sumKind = k => Object.entries(db[k] || {}).filter(([st]) => st === 'done').reduce((a, [, n]) => a + n, 0);
  const visual = sumKind('image') + sumKind('video');
  const textual = sumKind('doc') + sumKind('code');

  // nav dot
  const dot = document.getElementById('nav-ai-dot');
  if (dot) dot.className = 'nav-ai-dot ' + (s.status === 'running' || s.status === 'loading' || s.status === 'collecting' ? 'busy'
                                     : s.status === 'done' ? 'ok' : s.status === 'error' ? 'err' : '');

  // home banner
  const habText = document.getElementById('hab-text');
  const habFill = document.getElementById('hab-fill');
  const hab = document.getElementById('home-ai-banner');
  if (habText && hab) {
    hab.style.display = 'flex';
    if (s.status === 'running') habText.textContent = `AI is understanding your files… ${pct}% (${fmtN(s.processed)} / ${fmtN(s.total)})`;
    else if (s.status === 'loading') habText.textContent = 'AI is loading its neural networks onto the GPU…';
    else if (s.status === 'collecting') habText.textContent = 'AI is looking for new files…';
    else if (s.status === 'paused') habText.textContent = `AI paused at ${pct}% — click to resume`;
    else if (s.status === 'done') habText.textContent = `AI ready — ${fmtN(visual + textual)} files understood. Search by what's inside!`;
    else if (s.status === 'off') habText.textContent = 'AI search is turned off';
    else if (s.status === 'error') habText.textContent = 'AI error — click for details';
    else if (s.status === 'unavailable') hab.style.display = 'none';
    else habText.textContent = 'AI starting…';
    if (habFill) habFill.style.width = (s.status === 'done' ? 100 : pct) + '%';
  }

  // AI page
  const pill = document.getElementById('ai-pill');
  if (!pill) return;
  pill.textContent = (s.mode === 'super' && ['running', 'collecting', 'paused'].includes(s.status) ? '🔥 SUPER · ' : '')
                     + (AI_STATUS_TEXT[s.status] || s.status);
  pill.className = 'ai-pill ' + s.status;
  setText('ai-device', s.device ? `${s.device === 'cuda' ? '⚡ GPU (CUDA)' : '🐢 CPU'} · ${s.model || ''}` : '');

  const pauseBtn = document.getElementById('ai-pause-btn');
  if (pauseBtn) pauseBtn.textContent = s.status === 'paused' ? '▶ Resume' : '⏸ Pause';
  ['ai-enabled', 'ai-enabled-settings'].forEach(id => {
    const el = document.getElementById(id); if (el) el.checked = !!s.enabled;
  });

  let phaseText = s.phase_label ? `${s.phase_label}` : (AI_STATUS_TEXT[s.status] || '');
  if (s.status === 'error' && s.error) phaseText = '⚠️ ' + s.error;
  if (s.status === 'done') phaseText = s.total ? `Finished — ${fmtN(s.total)} files processed this run` : 'Everything is already understood ✓';
  setText('ai-phase-text', phaseText);
  setText('ai-pct', pct + '%');
  const bar = document.getElementById('ai-bar');
  if (bar) bar.style.width = pct + '%';
  setText('ai-current', s.current && s.status === 'running' ? `Now: ${s.current}` : '');

  const phases = document.getElementById('ai-phases');
  if (phases && s.totals) {
    const labels = { image: '🖼️ Images', doc: '📄 Documents, music & archives', video: '🎬 Videos', code: '💻 Code' };
    phases.innerHTML = Object.keys(labels).map(k => {
      const t = s.totals[k] || 0, d = Math.min(s.done?.[k] || 0, t);
      const p = t ? Math.round(d / t * 100) : 100;
      const active = s.phase === k ? ' active' : '';
      return `<div class="ai-phase${active}">
        <span class="ai-phase-name">${labels[k]}</span>
        <div class="ai-phase-bar"><div style="width:${t ? p : 0}%"></div></div>
        <span class="ai-phase-num">${t ? `${fmtN(d)} / ${fmtN(t)}` : '—'}</span></div>`;
    }).join('');
  }

  setText('ai-st-understood', fmtN(visual + textual));
  setText('ai-st-images', fmtN(visual));
  setText('ai-st-docs', fmtN(textual));
  setText('ai-st-speed', s.status === 'running' ? (s.per_sec || 0).toFixed(1) : '—');
  setText('ai-st-eta', s.status === 'running' && s.eta_sec != null ? formatElapsed(s.eta_sec) : (s.status === 'done' ? 'Done' : '—'));
  setText('ai-st-vectors', s.vectors ? fmtN((s.vectors.clip || 0) + (s.vectors.text || 0)) : '—');

  const feed = document.getElementById('ai-feed');
  if (feed && s.recent && s.recent.length) {
    const kindIcon = { image: '🖼️', video: '🎬', doc: '📄', code: '💻' };
    feed.innerHTML = s.recent.map(it => `
      <div class="ai-feed-item">
        <span class="ai-feed-icon">${kindIcon[it.kind] || '📁'}</span>
        <span class="ai-feed-name" title="${escHtml(it.name)}">${escHtml(it.name)}</span>
        <span class="ai-feed-tags">${(it.tags || []).map(t => `<span class="ai-tag">${escHtml(t)}</span>`).join('')}
          ${!it.tags?.length && it.extra ? `<span class="ai-feed-extra">“${escHtml(it.extra)}”</span>` : ''}</span>
      </div>`).join('');
  }
}

function fmtN(n) { return (n || 0).toLocaleString(); }
function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

// ── Results: AI badges, tags and "why it matched" snippet ─────────────────────
const MATCH_LABEL = {
  visual: ['👁️', 'Looks like your search (AI vision)'],
  meaning: ['🧠', 'About your search (AI reading)'],
  content: ['📖', 'Your words appear inside the file'],
  tag: ['🏷️', 'AI tag matches'],
};

const _origBuildResultCard = buildResultCard;
buildResultCard = function (r, index) {
  const card = _origBuildResultCard(r, index);
  try {
    const meta = card.querySelector('.result-meta');
    const info = card.querySelector('.result-info');
    const reasons = (r.match || []).filter(m => MATCH_LABEL[m]);
    if (meta && (r.ai_score || reasons.length)) {
      const badge = document.createElement('span');
      badge.className = 'ai-badge';
      badge.title = reasons.map(m => MATCH_LABEL[m][1]).join(' · ');
      badge.textContent = reasons.map(m => MATCH_LABEL[m][0]).join('') + (r.ai_score ? ` ${r.ai_score}%` : '');
      meta.insertBefore(badge, meta.firstChild);
    }
    if (info && r.snippet) {
      const sn = document.createElement('div');
      sn.className = 'ai-snippet';
      sn.innerHTML = escHtml(r.snippet).replace(/\[\[/g, '<mark>').replace(/\]\]/g, '</mark>');
      info.appendChild(sn);
    }
    if (info && r.tags && r.tags.length && !r.snippet) {
      const tg = document.createElement('div');
      tg.className = 'ai-tags-row';
      tg.innerHTML = r.tags.slice(0, 5).map(t => `<span class="ai-tag">${escHtml(t)}</span>`).join('');
      info.appendChild(tg);
    }
    // Video thumbnails aren't generated by Phase 1 — keep icon; images already have thumbnails.
  } catch (e) { console.warn(e); }
  return card;
};

// ── Preview panel: AI section + Find similar ──────────────────────────────────
const _origOpenPreview = openPreview;
openPreview = async function (r) {
  await _origOpenPreview(r);
  if (r.file_type === 'folder') return;
  const content = document.getElementById('preview-content');
  const actions = content?.querySelector('.preview-actions');
  if (actions && !actions.querySelector('.ai-similar-btn')) {
    const b = document.createElement('button');
    b.className = 'preview-btn preview-btn-secondary ai-similar-btn';
    b.textContent = '🔎 Find similar';
    b.onclick = () => findSimilar(r);
    actions.appendChild(b);
  }
  try {
    const res = await fetch(`${API}/ai/file?path=${encodeURIComponent(r.path)}`);
    const d = await res.json();
    if (state.selectedResult !== r) return;            // user clicked something else meanwhile
    const body = content.querySelector('.preview-body');
    if (!body) return;
    const box = document.createElement('div');
    box.className = 'ai-preview-box';
    if (!d.processed) {
      box.innerHTML = `<div class="ai-preview-title">🧠 AI</div>
        <div class="ai-preview-muted">Not understood yet${['image','video','document','code','audio','archive'].includes(r.file_type) ? ' — it will be processed during the next AI scan.' : ' (this file type has no readable content).'}</div>`;
    } else {
      const reasons = (r.match || []).filter(m => MATCH_LABEL[m]).map(m => `${MATCH_LABEL[m][0]} ${MATCH_LABEL[m][1]}`);
      box.innerHTML = `
        <div class="ai-preview-title">🧠 What the AI understood</div>
        ${reasons.length ? `<div class="ai-preview-why">${reasons.map(escHtml).join('<br>')}</div>` : ''}
        ${d.tags?.length ? `<div class="ai-tags-row">${d.tags.map(t => `<span class="ai-tag">${escHtml(t)}</span>`).join('')}</div>` : ''}
        ${d.title ? `<div class="ai-preview-line"><b>Title:</b> ${escHtml(d.title)}</div>` : ''}
        ${d.info ? `<div class="ai-preview-line"><b>Details:</b> ${escHtml(d.info)}</div>` : ''}
        ${d.excerpt ? `<div class="ai-preview-excerpt">“${escHtml(d.excerpt.slice(0, 400))}…”</div>` : ''}
        ${d.status === 'empty' ? '<div class="ai-preview-muted">No readable text found in this file.</div>' : ''}
        ${d.status === 'error' ? '<div class="ai-preview-muted">The AI could not open this file.</div>' : ''}`;
    }
    body.appendChild(box);
  } catch {}
};

async function findSimilar(r) {
  state.currentQuery = `similar to ${r.filename}`;
  state.searchStart = performance.now();
  syncSearchBars(state.currentQuery);
  showPage('results-page');
  document.getElementById('results-container').innerHTML = '<div class="loading-shimmer"></div>'.repeat(6);
  try {
    const res = await fetch(`${API}/similar?path=${encodeURIComponent(r.path)}`);
    const d = await res.json();
    if (d.error) showToast(d.error, 'error');
    state.allResults = d.results || [];
    state.filteredResults = [...state.allResults];
    document.getElementById('sort-select').value = 'score';
    applyTypeFilter(state.activeType, false);
    renderResults();
    updateTypeCounts();
  } catch { showError('Find similar failed'); }
}
