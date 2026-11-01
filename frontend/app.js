/* ============================================================
   Orion — app.js
   All frontend logic: search, filters, results, preview, settings
   ============================================================ */

'use strict';

const API = 'http://127.0.0.1:8472/api';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  currentQuery:   '',
  allResults:     [],
  filteredResults:[],
  activeType:     null,
  activeDate:     '',
  activeSize:     '',
  activeDrive:    '',
  viewMode:       localStorage.getItem('orion-view') || 'list',
  theme:          localStorage.getItem('orion-theme') || 'dark',
  searchStart:    0,
  selectedResult: null,
  indexPollTimer: null,
  // Scan page
  scanPolling:    false,
  scanTimeline:   [],   // [{time, phase, msg}]
  lastPhase:      null,
};

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applyTheme(state.theme);
  setView(state.viewMode, false);
  loadRecentFiles();
  pollIndexStatus();
  loadDrives();
  setupSearchListeners();
});

// ── Theme ─────────────────────────────────────────────────────────────────────
function toggleTheme() {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  setTheme(t);
}
function setTheme(t) {
  state.theme = t;
  localStorage.setItem('orion-theme', t);
  applyTheme(t);
  fetch(`${API}/settings`, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ theme: t }) });
}
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  document.getElementById('btn-theme').textContent = t === 'dark' ? '☀️' : '🌙';
}

// ── Navigation ────────────────────────────────────────────────────────────────
function showPage(name) {
  ['home-screen','results-page','stats-page','dupes-page','settings-page','scan-page']
    .forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.style.display = 'none'; el.classList.remove('visible'); }
    });
  const target = document.getElementById(name);
  if (target) { target.style.display = 'flex'; target.classList.add('visible'); }

  const headerWrap = document.getElementById('header-search-wrap');
  headerWrap.style.display = name === 'home-screen' ? 'none' : 'flex';

  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const navMap = {
    'home-screen':   'nav-search',
    'results-page':  'nav-search',
    'stats-page':    'nav-stats',
    'dupes-page':    'nav-dupes',
    'settings-page': 'nav-settings',
    'scan-page':     'nav-scan',
  };
  const nb = document.getElementById(navMap[name]);
  if (nb) nb.classList.add('active');

  ['btn-stats','btn-dupes','btn-settings','btn-scan'].forEach(id => {
    document.getElementById(id)?.classList.remove('active');
  });
  const iconMap = {
    'stats-page':    'btn-stats',
    'dupes-page':    'btn-dupes',
    'settings-page': 'btn-settings',
    'scan-page':     'btn-scan',
  };
  if (iconMap[name]) document.getElementById(iconMap[name])?.classList.add('active');
}

function showHome()     { showPage('home-screen'); document.getElementById('home-search')?.focus(); }
function showStats()    { showPage('stats-page');    loadStats(); }
function showDupes()    { showPage('dupes-page'); }
function showSettings() { showPage('settings-page'); loadSettings(); }
function showScan()     { showPage('scan-page');     startScanPolling(); }

// ── Search setup ──────────────────────────────────────────────────────────────
function setupSearchListeners() {
  const homeInput   = document.getElementById('home-search');
  const headerInput = document.getElementById('header-search');

  [homeInput, headerInput].forEach(input => {
    if (!input) return;
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') doSearch(input.value);
      if (e.key === 'Escape') closeAutocomplete();
    });
    input.addEventListener('input', () => {
      syncSearchBars(input.value);
      fetchAutocomplete(input.value);
      document.getElementById('header-search-clear').style.display =
        input.value ? 'block' : 'none';
    });
  });
}

function syncSearchBars(val) {
  document.getElementById('home-search').value   = val;
  document.getElementById('header-search').value = val;
}

function clearHeaderSearch() {
  syncSearchBars('');
  document.getElementById('header-search-clear').style.display = 'none';
  closeAutocomplete();
}

// ── Autocomplete ──────────────────────────────────────────────────────────────
let acTimer = null;

function getActiveAutocompleteEl() {
  // Return the correct dropdown based on which page is showing
  const headerWrap = document.getElementById('header-search-wrap');
  return (headerWrap && headerWrap.style.display !== 'none')
    ? document.getElementById('header-autocomplete')
    : document.getElementById('autocomplete');
}

function closeAutocomplete() {
  document.getElementById('autocomplete')?.classList.remove('visible');
  const hac = document.getElementById('header-autocomplete');
  if (hac) { hac.classList.remove('visible'); hac.innerHTML = ''; }
}

async function fetchAutocomplete(val) {
  clearTimeout(acTimer);
  closeAutocomplete();
  if (!val || val.length < 2) return;

  acTimer = setTimeout(async () => {
    try {
      const r = await fetch(`${API}/history`);
      const d = await r.json();
      const matches = (d.history || [])
        .filter(h => h.toLowerCase().startsWith(val.toLowerCase()))
        .slice(0, 6);
      if (matches.length) showAutocomplete(matches, val);
    } catch {}
  }, 200);
}

function showAutocomplete(items, typed) {
  // Only render into whichever container is currently active
  const ac = getActiveAutocompleteEl();
  if (!ac) return;
  ac.innerHTML = items.map(item =>
    `<div class="autocomplete-item" onclick="doSearch('${escHtml(item)}');closeAutocomplete();">
       <span class="ac-icon">🕒</span> ${escHtml(item)}
     </div>`
  ).join('');
  ac.classList.add('visible');
}

// toggleHeaderHistory — shows recent searches from the clock button
async function toggleHeaderHistory() {
  const ac = document.getElementById('header-autocomplete');
  if (!ac) return;
  if (ac.classList.contains('visible')) { closeAutocomplete(); return; }
  try {
    const r = await fetch(`${API}/history`);
    const d = await r.json();
    const items = (d.history || []).slice(0, 10);
    if (!items.length) {
      ac.innerHTML = '<div class="autocomplete-item" style="color:var(--text3);cursor:default;">🕒 No recent searches</div>';
    } else {
      ac.innerHTML = `
        <div class="autocomplete-item" style="color:var(--text3);font-size:0.75rem;cursor:default;padding:8px 16px 4px;">RECENT SEARCHES</div>
        ${items.map(item =>
          `<div class="autocomplete-item" onclick="doSearch('${escHtml(item)}');closeAutocomplete();">
             <span class="ac-icon">🕒</span> ${escHtml(item)}
           </div>`
        ).join('')}`;
    }
    ac.classList.add('visible');
  } catch {}
}


// ── Search ────────────────────────────────────────────────────────────────────
async function doSearch(queryOverride) {
  const q = (queryOverride || document.getElementById('home-search').value ||
             document.getElementById('header-search').value || '').trim();
  if (!q) return;

  syncSearchBars(q);
  closeAutocomplete();
  state.currentQuery = q;
  state.searchStart  = performance.now();

  // Switch to results page
  showPage('results-page');
  document.getElementById('results-container').innerHTML =
    '<div class="loading-shimmer"></div>'.repeat(6);

  // Build query string
  const params = new URLSearchParams({ q });
  if (state.activeDate)  params.append('date',  state.activeDate);
  if (state.activeDrive) params.append('drive', state.activeDrive);
  applySizeToParams(params);

  try {
    const res  = await fetch(`${API}/search?${params}`);
    const data = await res.json();
    state.allResults      = data.results || [];
    state.filteredResults = [...state.allResults];
    applyTypeFilter(state.activeType, false);
    renderResults();
    updateTypeCounts();
  } catch (e) {
    showError('Search failed. Is the Orion server running?');
    console.error(e);
  }
}

function applySizeToParams(params) {
  const sizeMap = {
    tiny:   [null,       102400],
    small:  [102400,     10485760],
    medium: [10485760,   524288000],
    large:  [524288000,  2147483648],
    huge:   [2147483648, null],
  };
  const range = sizeMap[state.activeSize];
  if (!range) return;
  if (range[0]) params.append('size_min', range[0]);
  if (range[1]) params.append('size_max', range[1]);
}

// ── Filters ───────────────────────────────────────────────────────────────────
function setTypeFilter(type) {
  state.activeType = type;
  document.querySelectorAll('[id^="ftype-"]').forEach(el => el.classList.remove('active'));
  document.getElementById('ftype-' + (type || 'all'))?.classList.add('active');
  applyTypeFilter(type, true);
}

function applyTypeFilter(type, rerender = true) {
  if (!type) {
    state.filteredResults = [...state.allResults];
  } else {
    state.filteredResults = state.allResults.filter(r => r.file_type === type);
  }
  if (rerender) renderResults();
}

function applyFilters() {
  state.activeDate  = document.getElementById('filter-date').value;
  state.activeSize  = document.getElementById('filter-size').value;
  state.activeDrive = document.getElementById('filter-drive').value;
  if (state.currentQuery) doSearch(state.currentQuery);
}

function updateTypeCounts() {
  const counts = {};
  state.allResults.forEach(r => { counts[r.file_type] = (counts[r.file_type]||0)+1; });
  ['document','image','video','audio','archive','code'].forEach(t => {
    const el = document.getElementById('count-' + t);
    if (el) el.textContent = counts[t] || '0';
  });
  const countAll = document.getElementById('count-all');
  if (countAll) countAll.textContent = state.allResults.length;
}

// ── Render Results ────────────────────────────────────────────────────────────
function renderResults() {
  const container  = document.getElementById('results-container');
  const countLabel = document.getElementById('results-count-label');
  const timeLabel  = document.getElementById('results-time-label');
  const elapsed    = ((performance.now() - state.searchStart) / 1000).toFixed(2);

  const sorted = getSortedResults();
  countLabel.innerHTML = `<strong>${sorted.length}</strong> results`;
  timeLabel.textContent = `(${elapsed}s)`;

  if (!sorted.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🔍</div>
        <div class="empty-state-text">No results for "${escHtml(state.currentQuery)}"</div>
        <div class="empty-state-sub">Try different keywords or check your filters</div>
      </div>`;
    return;
  }

  container.innerHTML = '';
  const frag = document.createDocumentFragment();
  sorted.forEach((r, i) => {
    const card = buildResultCard(r, i);
    frag.appendChild(card);
  });
  container.appendChild(frag);
}

function getSortedResults() {
  const sort = document.getElementById('sort-select').value;
  const arr  = [...state.filteredResults];
  switch (sort) {
    case 'modified-desc': return arr.sort((a,b) => b.modified - a.modified);
    case 'modified-asc':  return arr.sort((a,b) => a.modified - b.modified);
    case 'size-desc':     return arr.sort((a,b) => b.size - a.size);
    case 'size-asc':      return arr.sort((a,b) => a.size - b.size);
    case 'name-asc':      return arr.sort((a,b) => a.filename.localeCompare(b.filename));
    default:              return arr.sort((a,b) => b.score - a.score);
  }
}

function sortResults() { renderResults(); }

function buildResultCard(r, index) {
  const card   = document.createElement('div');
  card.className = 'result-card';
  card.style.animationDelay = `${Math.min(index * 40, 400)}ms`;
  card.dataset.path = r.path;
  card.onclick = () => openPreview(r);

  const isFolder = r.file_type === 'folder';
  const isImage  = r.file_type === 'image' && !isFolder;

  // Icon: thumbnail for images, emoji icon for everything else
  const iconHtml = isImage
    ? `<img src="${API}/thumbnail?path=${encodeURIComponent(r.path)}"
            onerror="this.parentElement.textContent='${r.icon}'"
            style="width:100%;height:100%;object-fit:cover;border-radius:7px;"/>`
    : r.icon;

  card.innerHTML = `
    <div class="result-icon" title="${escHtml(r.file_type)}">${iconHtml}</div>
    <div class="result-info">
      <div class="result-name" title="${escHtml(r.path)}">${escHtml(r.filename)}</div>
      <div class="result-path">${escHtml(r.folder)}</div>
    </div>
    <div class="result-meta">
      <span class="result-badge">${escHtml(r.extension || r.file_type)}</span>
      <span class="result-size">${r.size_label}</span>
      <span class="result-date">${r.modified_label}</span>
      <span class="result-score">${r.score}%</span>
    </div>
    <div class="result-actions" onclick="event.stopPropagation()">
      <button class="result-action-btn" onclick="openFolder('${escJs(r.path)}')" title="Open folder">📂 Folder</button>
      <button class="result-action-btn" onclick="copyPath('${escJs(r.path)}')" title="Copy path">📋</button>
    </div>`;

  return card;
}

// ── Preview Panel ─────────────────────────────────────────────────────────────
async function openPreview(r) {
  state.selectedResult = r;
  // Highlight selected
  document.querySelectorAll('.result-card').forEach(c => c.classList.remove('selected'));
  document.querySelector(`.result-card[data-path="${CSS.escape(r.path)}"]`)?.classList.add('selected');

  const panel   = document.getElementById('preview-panel');
  const content = document.getElementById('preview-content');
  panel.classList.add('visible');

  content.innerHTML = `
    <div class="preview-icon-large">${r.icon}</div>
    <div class="preview-body">
      <div class="preview-filename">${escHtml(r.filename)}</div>
      <div class="preview-meta-row">
        <span class="preview-meta-label">Type</span>
        <span class="preview-meta-value">${escHtml(r.extension?.toUpperCase() || r.file_type)}</span>
      </div>
      <div class="preview-meta-row">
        <span class="preview-meta-label">Size</span>
        <span class="preview-meta-value">${r.size_label}</span>
      </div>
      <div class="preview-meta-row">
        <span class="preview-meta-label">Modified</span>
        <span class="preview-meta-value">${r.modified_label}</span>
      </div>
      <div class="preview-meta-row">
        <span class="preview-meta-label">Location</span>
        <span class="preview-meta-value" title="${escHtml(r.folder)}">${escHtml(r.folder)}</span>
      </div>
      <div class="preview-meta-row">
        <span class="preview-meta-label">Match score</span>
        <span class="preview-meta-value" style="color:var(--primary)">${r.score}%</span>
      </div>
      ${r.ai_description ? `<div class="preview-meta-row">
        <span class="preview-meta-label">AI Description</span>
        <span class="preview-meta-value">${escHtml(r.ai_description)}</span>
      </div>` : ''}
    </div>
    <div class="preview-actions">
      <button class="preview-btn preview-btn-primary" onclick="openFolder('${escJs(r.path)}')">📂 Open Folder</button>
      <button class="preview-btn preview-btn-secondary" onclick="copyPath('${escJs(r.path)}')">📋 Copy Path</button>
    </div>`;

  // Fetch richer metadata asynchronously
  try {
    const res  = await fetch(`${API}/meta?path=${encodeURIComponent(r.path)}`);
    const meta = await res.json();
    enrichPreview(meta, r);
  } catch {}
}

function enrichPreview(meta, r) {
  const content = document.getElementById('preview-content');

  // Replace icon with actual thumbnail for images
  if (meta.thumbnail) {
    const iconEl = content.querySelector('.preview-icon-large');
    if (iconEl) {
      iconEl.outerHTML = `<img class="preview-image"
        src="data:image/jpeg;base64,${meta.thumbnail}"
        alt="${escHtml(r.filename)}"/>`;
    }
  }

  // Add extra metadata rows
  const body = content.querySelector('.preview-body');
  if (!body) return;
  const extras = [];

  if (meta.width && meta.height)
    extras.push(['Resolution', `${meta.width} × ${meta.height} (${meta.resolution_label?.toUpperCase() || ''})`]);
  if (meta.camera_make && meta.camera_model)
    extras.push(['Camera', `${meta.camera_make} ${meta.camera_model}`]);
  if (meta.date_taken)
    extras.push(['Date Taken', meta.date_taken]);
  if (meta.duration)
    extras.push(['Duration', formatDuration(meta.duration)]);
  if (meta.artist)
    extras.push(['Artist', meta.artist]);
  if (meta.album)
    extras.push(['Album', meta.album]);
  if (meta.bitrate)
    extras.push(['Bitrate', `${Math.round(meta.bitrate/1000)} kbps`]);

  extras.forEach(([label, val]) => {
    const row = document.createElement('div');
    row.className = 'preview-meta-row';
    row.innerHTML = `<span class="preview-meta-label">${escHtml(label)}</span>
                     <span class="preview-meta-value">${escHtml(String(val))}</span>`;
    body.appendChild(row);
  });
}

function closePreview() {
  document.getElementById('preview-panel').classList.remove('visible');
  document.querySelectorAll('.result-card').forEach(c => c.classList.remove('selected'));
  state.selectedResult = null;
}

// ── View mode ─────────────────────────────────────────────────────────────────
function setView(mode, save = true) {
  state.viewMode = mode;
  if (save) localStorage.setItem('orion-view', mode);
  const container = document.getElementById('results-container');
  container?.classList.toggle('grid-view', mode === 'grid');
  container?.classList.toggle('list-view', mode === 'list');
  document.getElementById('view-list')?.classList.toggle('active', mode === 'list');
  document.getElementById('view-grid')?.classList.toggle('active', mode === 'grid');
}

// ── File actions ──────────────────────────────────────────────────────────────
async function openFolder(path) {
  try {
    const res = await fetch(`${API}/open-folder`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ path })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(`❌ ${err.detail || 'Could not open folder'}`, 'error');
    } else {
      showToast('📂 Opened in Explorer');
    }
  } catch { showToast('❌ Failed — is Orion running?', 'error'); }
}

// Opens a folder directly (used by folder-type results — the path IS the folder)
async function openFolderDirect(folderPath) {
  try {
    const res = await fetch(`${API}/open-folder`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ path: folderPath, is_folder: true })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(`❌ ${err.detail || 'Could not open folder'}`, 'error');
    } else {
      showToast('📂 Opened in Explorer');
    }
  } catch { showToast('❌ Failed — is Orion running?', 'error'); }
}

async function copyPath(path) {
  try {
    await fetch(`${API}/copy-path`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ path })
    });
    showToast('📋 Path copied to clipboard');
  } catch {
    // Fallback to browser clipboard
    try { await navigator.clipboard.writeText(path); showToast('📋 Copied!'); }
    catch { showToast('Could not copy', 'error'); }
  }
}

// ── Recent Files ──────────────────────────────────────────────────────────────
async function loadRecentFiles() {
  try {
    const res  = await fetch(`${API}/recent?limit=12`);
    const data = await res.json();
    renderRecentFiles(data.files || []);
  } catch {}
}

function renderRecentFiles(files) {
  const grid = document.getElementById('recent-files-grid');
  const sec  = document.getElementById('recent-section');
  if (!files.length) { sec.style.display = 'none'; return; }

  grid.innerHTML = files.map((f, i) => `
    <div class="mini-card" style="animation-delay:${i*30}ms"
         onclick="openFolder('${escJs(f.path)}')">
      <div class="mini-card-icon">${f.icon}</div>
      <div class="mini-card-name" title="${escHtml(f.filename)}">${escHtml(f.filename)}</div>
      <div class="mini-card-meta">${f.size_label} · ${f.modified_label}</div>
    </div>`
  ).join('');
}

// ── Index status polling ──────────────────────────────────────────────────────
async function pollIndexStatus() {
  try {
    const res  = await fetch(`${API}/index/status`);
    const data = await res.json();
    updateIndexBanner(data);
    if (data.phase !== 'done' && data.phase !== 'idle' && data.phase !== 'error') {
      state.indexPollTimer = setTimeout(pollIndexStatus, 2000);
    } else {
      if (data.phase === 'done') {
        setTimeout(() => { document.getElementById('index-banner').classList.remove('visible'); }, 2000);
        loadRecentFiles();
        loadDrives();
      }
      state.indexPollTimer = setTimeout(pollIndexStatus, 30000);
    }
  } catch {
    state.indexPollTimer = setTimeout(pollIndexStatus, 10000);
  }
}

function updateIndexBanner(data) {
  const banner = document.getElementById('index-banner');
  const text   = document.getElementById('index-status-text');
  const bar    = document.getElementById('index-progress-bar');
  const count  = document.getElementById('index-file-count');

  if (data.phase === 'idle') { banner.classList.remove('visible'); return; }

  banner.classList.add('visible');

  if (data.phase === 'scanning') {
    text.textContent = 'Scanning drive…';
    bar.style.width  = '30%';
  } else if (data.phase === 'inserting') {
    const pct = data.total_estimate > 0
      ? Math.round((data.indexed_files / data.total_estimate) * 100) : 50;
    text.textContent = `Indexing files… ${pct}%`;
    bar.style.width  = `${pct}%`;
  } else if (data.phase === 'done') {
    text.textContent = `✅ Index complete — ${data.indexed_files.toLocaleString()} files`;
    bar.style.width  = '100%';
  } else if (data.phase === 'error') {
    text.textContent = '⚠️ Indexing encountered an error';
  }

  if (data.indexed_files)
    count.textContent = data.indexed_files.toLocaleString() + ' files';
}

async function triggerReindex() {
  try {
    await fetch(`${API}/index/start`, { method: 'POST' });
    showToast('🔄 Re-indexing started');
    pollIndexStatus();
  } catch { showToast('Failed to start indexing', 'error'); }
}

// ── Drives ────────────────────────────────────────────────────────────────────
async function loadDrives() {
  try {
    const res  = await fetch(`${API}/stats`);
    const data = await res.json();
    const sel  = document.getElementById('filter-drive');
    const current = sel.value;
    // Keep first option, rebuild rest
    while (sel.options.length > 1) sel.remove(1);
    (data.by_drive || []).forEach(d => {
      const opt = document.createElement('option');
      opt.value = opt.textContent = d.drive + ':';
      sel.appendChild(opt);
    });
    sel.value = current;
  } catch {}
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  const content = document.getElementById('stats-content');
  content.innerHTML = '<div class="loading-shimmer"></div>'.repeat(4);
  try {
    const res  = await fetch(`${API}/stats`);
    const d    = await res.json();
    const max  = Math.max(...(d.by_type||[]).map(t=>t.cnt), 1);

    content.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-card-value">${(d.total_files||0).toLocaleString()}</div>
          <div class="stat-card-label">Total Files Indexed</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-value">${d.total_size_label||'0 B'}</div>
          <div class="stat-card-label">Total Size</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-value">${(d.by_drive||[]).length}</div>
          <div class="stat-card-label">Drives Indexed</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-value">${d.last_indexed_label||'Never'}</div>
          <div class="stat-card-label">Last Indexed</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
        <div>
          <div class="section-title" style="margin-bottom:12px;">By File Type</div>
          <div class="stat-breakdown">
            ${(d.by_type||[]).map(t => `
              <div class="stat-row">
                <span class="stat-row-icon">${(d.icons||{})[t.file_type]||'📁'}</span>
                <span class="stat-row-label">${t.file_type}</span>
                <div class="stat-row-bar-wrap">
                  <div class="stat-row-bar" style="width:${Math.round(t.cnt/max*100)}%"></div>
                </div>
                <span class="stat-row-val">${t.cnt.toLocaleString()}</span>
              </div>`).join('')}
          </div>
        </div>
        <div>
          <div class="section-title" style="margin-bottom:12px;">By Drive</div>
          <div class="stat-breakdown">
            ${(d.by_drive||[]).map(dr => `
              <div class="stat-row">
                <span class="stat-row-icon">💾</span>
                <span class="stat-row-label">${escHtml(dr.drive)}</span>
                <span class="stat-row-val">${dr.cnt.toLocaleString()} files</span>
              </div>`).join('')}
          </div>
        </div>
      </div>`;
  } catch { content.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">Could not load stats</div></div>'; }
}

// ── Duplicates ────────────────────────────────────────────────────────────────
async function scanDupes() {
  document.getElementById('scan-dupes-btn').disabled = true;
  document.getElementById('dupe-status').textContent = 'Scanning…';
  await fetch(`${API}/duplicates/scan`, { method: 'POST' });
  pollDupeStatus();
}

async function pollDupeStatus() {
  try {
    const res  = await fetch(`${API}/duplicates/status`);
    const data = await res.json();
    const s    = document.getElementById('dupe-status');
    if (data.phase === 'hashing') {
      s.textContent = `Hashing ${data.done}/${data.total} files…`;
      setTimeout(pollDupeStatus, 1500);
    } else {
      s.textContent = '';
      document.getElementById('scan-dupes-btn').disabled = false;
      loadDupes();
    }
  } catch { setTimeout(pollDupeStatus, 3000); }
}

async function loadDupes() {
  const content = document.getElementById('dupes-content');
  content.innerHTML = '<div class="loading-shimmer"></div>'.repeat(3);
  try {
    const res  = await fetch(`${API}/duplicates`);
    const data = await res.json();
    const groups = data.groups || [];

    if (!groups.length) {
      content.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">✅</div>
        <div class="empty-state-text">No duplicates found</div>
        <div class="empty-state-sub">All your files appear to be unique</div>
      </div>`;
      return;
    }

    content.innerHTML = groups.map(g => `
      <div class="dupe-group">
        <div class="dupe-header">
          <span class="dupe-badge">${g.count} copies</span>
          <span style="color:var(--text2)">Same content</span>
          <span class="dupe-size">${formatSize(g.size)} each</span>
        </div>
        ${g.files.map(f => `
          <div class="dupe-file">
            <span class="dupe-path">${escHtml(f.path)}</span>
            <span class="dupe-open" onclick="openFolder('${escJs(f.path)}')">📂 Open</span>
          </div>`).join('')}
      </div>`).join('');
  } catch { content.innerHTML = ''; }
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function loadSettings() {
  // Load excluded paths
  try {
    const res  = await fetch(`${API}/exclude`);
    const data = await res.json();
    renderExcluded(data.paths || []);
  } catch {}
}

function renderExcluded(paths) {
  document.getElementById('excluded-list').innerHTML = paths.map(p => `
    <div class="excluded-item">
      <span>📁 ${escHtml(p)}</span>
      <button class="excluded-remove" onclick="removeExclude('${escJs(p)}')" title="Remove">✕</button>
    </div>`).join('');
}

async function addExclude() {
  const val = document.getElementById('exclude-input').value.trim();
  if (!val) return;
  await fetch(`${API}/exclude`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: val })
  });
  document.getElementById('exclude-input').value = '';
  showToast('Folder excluded');
  loadSettings();
}

async function removeExclude(path) {
  await fetch(`${API}/exclude`, {
    method: 'DELETE', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path })
  });
  showToast('Removed from exclusions');
  loadSettings();
}

async function saveGeminiKey() {
  const key = document.getElementById('gemini-key-input').value.trim();
  if (!key) return;
  await fetch(`${API}/settings`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ gemini_api_key: key })
  });
  document.getElementById('gemini-key-input').value = '';
  showToast('✅ API key saved');
}

async function clearHistory() {
  await fetch(`${API}/history`, { method: 'DELETE' });
  showToast('Search history cleared');
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => {
    el.style.animation = 'toastOut 0.3s ease forwards';
    setTimeout(() => el.remove(), 300);
  }, 3000);
}
function showError(msg) { showToast(msg, 'error'); }

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escJs(s) { return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }

function formatDuration(sec) {
  if (!sec) return '';
  const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = sec%60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
           : `${m}:${String(s).padStart(2,'0')}`;
}
function formatSize(b) {
  if (!b) return '0 B';
  const u = ['B','KB','MB','GB','TB'];
  let i = 0; let v = b;
  while (v >= 1024 && i < u.length-1) { v /= 1024; i++; }
  return `${v.toFixed(i?1:0)} ${u[i]}`;
}

// ── Scan Page ─────────────────────────────────────────────────────────────────
let _scanPollInterval = null;

function startScanPolling() {
  refreshScanPage();
  if (_scanPollInterval) clearInterval(_scanPollInterval);
  _scanPollInterval = setInterval(refreshScanPage, 3000);
}

async function refreshScanPage() {
  try {
    const res  = await fetch(`${API}/index/status`);
    const d    = await res.json();
    updateScanPage(d);
  } catch {
    // server might be restarting, no-op
  }
}

function updateScanPage(d) {
  const phase = d.phase || 'idle';

  // ── LIVE badge ────────────────────────────────────────────────
  const badge = document.getElementById('scan-live-badge');
  if (badge) badge.style.display = d.indexing ? 'inline' : 'none';

  // ── Phase pipeline ────────────────────────────────────────────
  const phaseOrder = ['idle', 'scanning', 'inserting', 'done'];
  const phaseIdx   = phaseOrder.indexOf(phase);
  const lines      = document.querySelectorAll('.phase-line');

  phaseOrder.forEach((p, i) => {
    const el = document.getElementById('phase-' + p);
    if (!el) return;
    el.classList.remove('active', 'done');
    if (i < phaseIdx)  el.classList.add('done');
    if (i === phaseIdx && phase !== 'idle') el.classList.add('active');
    if (phase === 'done') el.classList.add('done');
  });
  lines.forEach((l, i) => {
    l.classList.remove('active', 'done');
    if (i < phaseIdx - 1) l.classList.add('done');
    if (i === phaseIdx - 1) l.classList.add('active');
  });

  // ── Stat cards ────────────────────────────────────────────────
  set('ss-elapsed', formatElapsed(d.elapsed_seconds));
  set('ss-dirs',    d.dirs_visited   ? d.dirs_visited.toLocaleString()  : '—');
  set('ss-found',   d.files_found    ? d.files_found.toLocaleString()   : '—');
  set('ss-indexed', d.indexed_files  ? d.indexed_files.toLocaleString() : '—');
  set('ss-rate',    d.files_per_second ? `${d.files_per_second.toLocaleString()}/s` : '—');
  set('ss-eta',     d.eta_seconds != null ? formatElapsed(d.eta_seconds) : (phase === 'done' ? '✅ Done!' : '—'));

  // ── Progress bar (inserting only) ─────────────────────────────
  const pw = document.getElementById('scan-progress-wrap');
  if (pw) {
    pw.style.display = phase === 'inserting' ? 'block' : 'none';
    if (phase === 'inserting' && d.total_estimate > 0) {
      const pct = Math.min(100, Math.round(d.indexed_files / d.total_estimate * 100));
      document.getElementById('scan-progress-bar').style.width = pct + '%';
      document.getElementById('scan-pct').textContent = pct + '%';
    }
  }

  // ── Timeline log ──────────────────────────────────────────────
  if (phase !== state.lastPhase) {
    state.lastPhase = phase;
    addTimelineEntry(phase, getPhaseMessage(phase, d));
  }
  // Live scanning update every 5 entries
  if (phase === 'scanning' && d.dirs_visited > 0 &&
      state.scanTimeline.length % 5 === 0) {
    addTimelineEntry(phase,
      `Visited ${d.dirs_visited.toLocaleString()} folders, ` +
      `found ${d.files_found.toLocaleString()} files so far…`, true);
  }
}

function getPhaseMessage(phase, d) {
  const drive = d.current_drive || 'your drive';
  switch (phase) {
    case 'scanning':  return `Started scanning ${drive}. Walking every folder to collect file paths. Please wait — this is the longest phase.`;
    case 'inserting': return `Scanning complete! Found ${(d.files_found||d.total_estimate||'?').toLocaleString()} files. Now writing metadata to the database in batches of 5,000…`;
    case 'done':      return `✅ Index complete! ${d.indexed_files.toLocaleString()} files indexed in ${formatElapsed(d.elapsed_seconds)}. Your database is ready — search away!`;
    case 'error':     return '⚠️ An error occurred during indexing. Check console or click Re-index Now.';
    default:          return 'Orion is idle. Click Re-index Now to start a manual scan.';
  }
}

function addTimelineEntry(phase, msg, isUpdate = false) {
  const now = new Date().toLocaleTimeString('en-IN', { hour12: false });
  if (isUpdate) {
    // Replace last "scanning update" entry instead of appending
    const existing = state.scanTimeline.findLast?.(e => e.isUpdate);
    if (existing) { existing.msg = msg; renderTimeline(); return; }
  }
  state.scanTimeline.push({ time: now, phase, msg, isUpdate });
  renderTimeline();
}

function renderTimeline() {
  const el = document.getElementById('scan-timeline');
  if (!el) return;
  el.innerHTML = [...state.scanTimeline].reverse().map(e => `
    <div class="timeline-entry">
      <div class="timeline-dot ${e.phase}"></div>
      <span class="timeline-time">${e.time}</span>
      <span class="timeline-msg">${escHtml(e.msg)}</span>
    </div>`).join('');
}

function formatElapsed(secs) {
  if (!secs && secs !== 0) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── Close autocomplete on outside click

document.addEventListener('click', e => {
  if (!e.target.closest('#home-search-wrap') && !e.target.closest('#header-search-wrap'))
    closeAutocomplete();
});

// Keyboard shortcut: Ctrl+K to focus search
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const inp = document.getElementById('home-search').closest('#home-screen')?.style.display !== 'none'
      ? document.getElementById('home-search')
      : document.getElementById('header-search');
    inp?.focus();
  }
});
