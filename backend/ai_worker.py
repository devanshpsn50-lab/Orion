"""
Orion — ai_worker.py
Background AI scanner. Runs in its own thread, in parallel with the indexer.

For every image / video / document / code file it hasn't seen yet (or that has
changed since), it:
  • images    → CLIP vector + auto-tags (cat → animal, pet)
  • videos    → 5 frames → CLIP vectors + tags
  • documents → reads the text → BGE meaning vectors + full-text content index
                (scanned PDFs with no text get their first page "looked at" by CLIP)
  • code      → reads the source → BGE vector + content index

Two scopes:
  SMART (default) — your own files only: skips Windows/Program Files/AppData,
                    app icons (<20 KB or <128 px), library/build folders.
  SUPER           — everything Orion has indexed, no exceptions.

Work is saved after every batch, so closing Orion never loses progress.
"""

import os
import re
import time
import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from config import get_db, get_setting, set_setting

log = logging.getLogger("orion.aiworker")

# ── Scope rules ───────────────────────────────────────────────────────────────
USER_HOME = os.environ.get("USERPROFILE", r"C:\Users").lower()

SYSTEM_MARKERS = (
    "\\windows\\", "\\program files", "\\programdata\\", "\\appdata\\",
    "\\$recycle.bin", "\\system volume information", "\\recovery\\",
    "site-packages", "dist-packages", "node_modules", "\\.git\\", "\\__pycache__\\",
    "\\.venv\\", "\\venv\\", "\\env\\lib\\", "\\.cache\\", "\\.gemini\\", "\\.vscode",
    "\\.ollama\\", "\\.nuget\\", "\\.gradle\\", "\\.m2\\", "\\.cargo\\", "\\.rustup\\",
    "\\.android\\", "\\anaconda", "\\miniconda", "\\steamapps\\", "\\steamlibrary\\",
    "\\epic games\\", "\\riot games\\", "\\.idea\\", "\\.conda\\", "\\go\\pkg\\",
    "\\library\\packagecache", "\\.platformio\\", "\\arduino15\\",
)
CODE_EXTRA_MARKERS = (
    "\\build\\", "\\dist\\", "\\out\\", "\\obj\\", "\\bin\\", "\\target\\",
    "\\vendor\\", "\\third_party\\", "\\external\\", "\\packages\\", ".min.js", ".min.css",
)
IMAGE_EXTS       = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff"}
IMAGE_EXTS_SUPER = IMAGE_EXTS | {"ico"}
VIDEO_EXTS       = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "3gp", "mts"}

PHASES = ["image", "doc", "video", "code"]
PHASE_LABELS = {"image": "Images", "doc": "Documents, music & archives",
                "video": "Videos", "code": "Code files"}


def _in_smart_scope(path_lower: str) -> bool:
    if any(m in path_lower for m in SYSTEM_MARKERS):
        return False
    return path_lower.startswith(USER_HOME) or not path_lower.startswith("c:")


# ── Shared state (polled by the frontend) ─────────────────────────────────────
_state_lock = threading.Lock()
state: dict = {
    "status":      "starting",   # starting|loading|collecting|running|paused|done|off|error|unavailable
    "mode":        "smart",
    "phase":       None,
    "phase_label": None,
    "totals":      {p: 0 for p in PHASES},
    "done":        {p: 0 for p in PHASES},
    "processed":   0,
    "total":       0,
    "per_sec":     0.0,
    "eta_sec":     None,
    "current":     None,
    "error":       None,
    "device":      None,
    "model":       None,
    "started_at":  None,
    "finished_at": None,
}
_recent: deque = deque(maxlen=14)          # last tagged items (live feed in UI)


def _set(**kw):
    with _state_lock:
        state.update(kw)


def get_state() -> dict:
    with _state_lock:
        s = dict(state)
        s["totals"] = dict(state["totals"])
        s["done"] = dict(state["done"])
        s["recent"] = list(_recent)
    s["enabled"] = bool(get_setting("ai_enabled", True))
    return s


# ── Control ───────────────────────────────────────────────────────────────────
_wake    = threading.Event()
_paused  = threading.Event()
_restart = threading.Event()
_thread: threading.Thread | None = None


def start():
    """Start the background AI thread (called at server startup)."""
    global _thread
    import ai_engine as eng
    if not eng.available():
        _set(status="unavailable", error="PyTorch is not installed — AI features are off.")
        return
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_loop, name="orion-ai", daemon=True)
    _thread.start()


def start_scan(mode: str = "smart"):
    mode = "super" if mode == "super" else "smart"
    set_setting("ai_scan_mode", mode)
    set_setting("ai_enabled", True)
    _paused.clear()
    _restart.set()
    _wake.set()
    start()


def pause():
    _paused.set()


def resume():
    _paused.clear()


def set_enabled(on: bool):
    set_setting("ai_enabled", bool(on))
    if on:
        _paused.clear()
        _restart.set()
        _wake.set()
        start()
    else:
        _restart.set()


def notify_new_files():
    """Called by the indexer after a scan so new files get processed."""
    _wake.set()


def _checkpoint() -> bool:
    """Between batches: honour pause; return False if the scan should abort."""
    if _restart.is_set() or not get_setting("ai_enabled", True):
        return False
    if _paused.is_set():
        prev = state["status"]
        _set(status="paused")
        while _paused.is_set():
            if _restart.is_set():
                return False
            time.sleep(0.4)
        _set(status=prev if prev != "paused" else "running")
    return True


# ── Main loop ─────────────────────────────────────────────────────────────────
def _loop():
    import ai_engine as eng
    _set(status="loading", error=None)
    if not eng.load_models():
        _set(status="error", error=f"Could not load AI models: {eng.load_error()}")
        return
    eng.load_vectors_from_db()
    _set(device=eng.device(), model=f"CLIP {eng.clip_name()} + BGE-small")

    retried = False
    while True:
        if not get_setting("ai_enabled", True):
            _set(status="off", phase=None, current=None)
            _wake.wait()
            _wake.clear()
            continue
        _restart.clear()
        _wake.clear()
        mode = get_setting("ai_scan_mode", "smart")
        try:
            _run_scan(mode)
        except Exception as e:
            log.exception("AI scan crashed: %s", e)
            _set(status="error", error=str(e))
        if _restart.is_set():
            retried = False
            continue
        # Slow cloud files (e.g. Google Drive books) get ONE patient second try right away
        if not retried and _has_retries():
            retried = True
            log.info("Retrying slow cloud files with a longer timeout")
            continue
        retried = False
        _wake.wait(timeout=1800)      # re-check for new files every 30 min or when woken


def _has_retries() -> bool:
    conn = get_db()
    try:
        return conn.execute("SELECT 1 FROM ai_items WHERE status='retry' LIMIT 1").fetchone() is not None
    finally:
        conn.close()


def _run_scan(mode: str):
    _set(status="collecting", mode=mode, phase=None, phase_label=None, current=None,
         error=None, started_at=time.time(), finished_at=None)
    queues = _collect(mode)
    totals = {p: len(queues[p]) for p in PHASES}
    _set(status="running", totals=totals, done={p: 0 for p in PHASES},
         total=sum(totals.values()), processed=0, per_sec=0.0, eta_sec=None)
    log.info("AI %s scan: %s", mode, totals)
    _rate["t0"], _rate["n0"] = time.time(), 0

    handlers = {"image": _process_images, "doc": _process_docs,
                "video": _process_videos, "code": _process_code}
    for phase in PHASES:
        if not queues[phase]:
            continue
        _set(phase=phase, phase_label=PHASE_LABELS[phase])
        handlers[phase](queues[phase], mode)
        if _restart.is_set() or not get_setting("ai_enabled", True):
            return
    _set(status="done", phase=None, phase_label=None, current=None,
         eta_sec=0, finished_at=time.time())
    log.info("AI scan finished")


def _collect(mode: str) -> dict[str, list]:
    smart = mode != "super"
    q: dict[str, list] = {p: [] for p in PHASES}
    from ai_extract import can_extract
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT f.id, f.path, f.filename, f.extension, f.file_type, f.size, f.modified,
                   a.status AS ai_status
            FROM files f LEFT JOIN ai_items a ON a.file_id = f.id
            WHERE f.file_type IN ('image','video','document','code','audio','archive')
              AND (a.file_id IS NULL OR a.file_modified != f.modified OR a.status = 'retry')
        """).fetchall()
    finally:
        conn.close()

    for r in rows:
        size, ext, ft = r["size"] or 0, (r["extension"] or "").lower(), r["file_type"]
        if size <= 0:
            continue
        pl = r["path"].lower()
        if smart and not _in_smart_scope(pl):
            continue
        if ft == "image":
            if ext not in (IMAGE_EXTS if smart else IMAGE_EXTS_SUPER):
                continue
            if (smart and size < 20 * 1024) or size > 300 * 1024 * 1024:
                continue
            q["image"].append(r)
        elif ft == "video":
            if ext in VIDEO_EXTS:
                q["video"].append(r)
        elif ft == "code":
            if not can_extract(ext, ft):
                continue
            if smart and (size > 1024 * 1024 or any(m in pl for m in CODE_EXTRA_MARKERS)):
                continue
            q["code"].append(r)
        elif can_extract(ext, ft):
            q["doc"].append(r)

    for p in PHASES:                       # newest files first — most likely to be searched
        q[p].sort(key=lambda r: r["modified"] or 0, reverse=True)
    return q


# ── Progress ──────────────────────────────────────────────────────────────────
_rate = {"t0": time.time(), "n0": 0}


def _progress(phase: str, n: int, current: str | None = None):
    with _state_lock:
        state["done"][phase] += n
        state["processed"] += n
        el = time.time() - _rate["t0"]
        if el > 1:
            state["per_sec"] = round((state["processed"] - _rate["n0"]) / el, 1)
            remaining = state["total"] - state["processed"]
            state["eta_sec"] = int(remaining / state["per_sec"]) if state["per_sec"] > 0 else None
        if current:
            state["current"] = current


def _feed(name: str, kind: str, tags: list[str], extra: str = ""):
    _recent.appendleft({"name": name, "kind": kind, "tags": tags[:6], "extra": extra[:120]})


# ── Saving ────────────────────────────────────────────────────────────────────
def _save(conn, results: list[dict]):
    """Write a batch of AI results to SQLite and to the in-memory GPU index."""
    import ai_engine as eng
    if not results:
        return
    ids = [(r["file_id"],) for r in results]
    conn.executemany("DELETE FROM ai_vectors WHERE file_id=?", ids)
    conn.executemany("DELETE FROM content_fts WHERE rowid=?", ids)

    vec_rows = []
    mem = {"clip": ([], []), "text": ([], [])}
    for r in results:
        for sp, model in (("clip", eng.clip_name()), ("text", eng.TEXT_MODEL)):
            vecs = r.get(sp)
            if vecs is None or len(vecs) == 0:
                continue
            for v in vecs:
                vec_rows.append((r["file_id"], sp, model, v.astype(np.float16).tobytes()))
            mem[sp][0].extend([r["file_id"]] * len(vecs))
            mem[sp][1].append(np.asarray(vecs, dtype=np.float16))
    if vec_rows:
        conn.executemany("INSERT INTO ai_vectors(file_id, space, model, vec) VALUES (?,?,?,?)", vec_rows)

    fts_rows = [(r["file_id"], ", ".join(r.get("tags") or []), r.get("body") or "")
                for r in results if r.get("tags") or r.get("body")]
    if fts_rows:
        conn.executemany("INSERT INTO content_fts(rowid, tags, body) VALUES (?,?,?)", fts_rows)

    now = int(time.time())
    conn.executemany(
        "INSERT OR REPLACE INTO ai_items(file_id, kind, status, file_modified, processed_at, tags, title, info) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(r["file_id"], r["kind"], r["status"], r["modified"], now,
          ", ".join(r.get("tags") or []) or None, r.get("title"), r.get("info"))
         for r in results],
    )
    conn.commit()

    for sp in ("clip", "text"):
        fids, arrs = mem[sp]
        if fids:
            eng.space(sp).add(fids, np.concatenate(arrs))


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _prefetched(pool, fn, items: list, batch: int):
    """Yield (batch_rows, results) while the NEXT batch is already loading."""
    batches = list(_chunks(items, batch))
    if not batches:
        return
    nxt = [pool.submit(fn, r) for r in batches[0]]
    for i, b in enumerate(batches):
        cur = nxt
        if i + 1 < len(batches):
            nxt = [pool.submit(fn, r) for r in batches[i + 1]]
        yield b, [f.result() for f in cur]


# ═════════════════════════════════════════════════════════════════════════════
#  IMAGES
# ═════════════════════════════════════════════════════════════════════════════
def _load_image(row, smart: bool):
    import ai_engine as eng
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 300_000_000
    try:
        with Image.open(row["path"]) as im:
            if smart and min(im.size) < 128:
                return None, "small"
            im.draft("RGB", (448, 448))              # fast reduced-size JPEG decode
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            return eng.preprocess_image(im), None
    except Exception as e:
        return None, f"error: {e}"[:200]


def _process_images(items: list, mode: str):
    import ai_engine as eng
    from ai_tags import expand_tags
    smart = mode != "super"
    conn = get_db()
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for batch, loaded in _prefetched(pool, lambda r: _load_image(r, smart), items, 32):
                if not _checkpoint():
                    return
                results, good = [], []
                for r, (tensor, err) in zip(batch, loaded):
                    if tensor is None:
                        results.append({"file_id": r["id"], "kind": "image", "modified": r["modified"],
                                        "status": "skipped" if err == "small" else "error", "info": err})
                    else:
                        good.append((r, tensor))
                if good:
                    vecs = eng.encode_image_tensors([t for _, t in good])
                    for (r, _), v in zip(good, vecs):
                        top = eng.tags_for_vector(v)
                        tags = expand_tags([t for t, _ in top])
                        results.append({"file_id": r["id"], "kind": "image", "modified": r["modified"],
                                        "status": "done", "tags": tags, "clip": v[None, :],
                                        "info": ", ".join(f"{t} {p:.0%}" for t, p in top)})
                    r0 = good[-1][0]
                    _feed(r0["filename"], "image", results[-1]["tags"])
                _save(conn, results)
                _progress("image", len(batch), batch[-1]["filename"])
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
#  VIDEOS
# ═════════════════════════════════════════════════════════════════════════════
def _load_video(row):
    import ai_engine as eng
    import cv2
    from PIL import Image
    try:
        cap = cv2.VideoCapture(row["path"])
        if not cap.isOpened():
            return None, "cannot open"
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        positions = [0.08, 0.27, 0.5, 0.73, 0.92] if n > 30 else [0.0]
        tensors = []
        for f in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * f))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail((448, 448))
            tensors.append(eng.preprocess_image(img))
        cap.release()
        return (tensors or None), (None if tensors else "no frames decoded")
    except Exception as e:
        return None, f"error: {e}"[:200]


def _process_videos(items: list, mode: str):
    import ai_engine as eng
    from ai_tags import expand_tags
    conn = get_db()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for batch, loaded in _prefetched(pool, _load_video, items, 6):
                if not _checkpoint():
                    return
                results = []
                for r, (frames, err) in zip(batch, loaded):
                    if not frames:
                        results.append({"file_id": r["id"], "kind": "video", "modified": r["modified"],
                                        "status": "error", "info": err})
                        continue
                    vecs = eng.encode_image_tensors(frames)           # [frames, D]
                    mean = vecs.astype(np.float32).mean(0)
                    mean = (mean / np.linalg.norm(mean)).astype(np.float16)
                    top = eng.tags_for_vector(mean, max_tags=5)
                    tags = expand_tags([t for t, _ in top])
                    results.append({"file_id": r["id"], "kind": "video", "modified": r["modified"],
                                    "status": "done", "tags": tags, "clip": vecs,
                                    "info": f"{len(frames)} frames · " + ", ".join(t for t, _ in top)})
                    _feed(r["filename"], "video", tags)
                _save(conn, results)
                _progress("video", len(batch), batch[-1]["filename"])
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
#  DOCUMENTS (+ audio tags, archives) and CODE
# ═════════════════════════════════════════════════════════════════════════════
_SEP = re.compile(r"[_\-.+]+")


def _header(row, title: str) -> str:
    p = Path(row["path"])
    folders = " / ".join(p.parent.parts[-3:])
    return f"{_SEP.sub(' ', p.stem)}. {title or ''}. Folder: {folders}."


def _text_chunks(header: str, text: str, max_chunks: int) -> list[str]:
    """First chunk = header + opening text; extra chunks sampled across the rest."""
    CH = 1500
    chunks = [f"{header} {text[:CH]}"]
    rest = text[CH:]
    if max_chunks > 1 and len(rest) > 300:
        n = min(max_chunks - 1, max(1, len(rest) // CH))
        starts = np.linspace(0, max(0, len(rest) - CH), n).astype(int)
        for s in starts:
            chunks.append(f"{header} {rest[s:s + CH]}")
    return chunks


def _load_doc(row, max_chars: int):
    """Runs in a worker thread: read the file's contents."""
    import ai_engine as eng
    from ai_extract import extract
    res = extract(row["path"], row["extension"], row["file_type"], max_chars=max_chars,
                  patient=(row["ai_status"] == "retry"))
    if res and res.get("_timeout"):
        return res, None
    cover = None
    # Scanned PDF (no text layer): the PDF helper sends a picture of page 1 for CLIP
    if res and res.get("cover"):
        try:
            import base64, io
            from PIL import Image
            img = Image.open(io.BytesIO(base64.b64decode(res.pop("cover")))).convert("RGB")
            cover = eng.preprocess_image(img)
        except Exception:
            pass
    if res and not res.get("text"):
        res = None if cover is None else res
    return res, cover


def _process_text_kind(items: list, mode: str, phase: str):
    import ai_engine as eng
    from ai_tags import expand_tags
    is_code = phase == "code"
    smart = mode != "super"
    max_chars = (4000 if smart else 2000) if is_code else 20000
    max_chunks = 1 if is_code else 4
    batch_size = 96 if is_code else 32
    conn = get_db()
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for batch, loaded in _prefetched(pool, lambda r: _load_doc(r, max_chars), items, batch_size):
                if not _checkpoint():
                    return
                results, all_chunks, owners, covers = [], [], [], []
                for r, (res, cover) in zip(batch, loaded):
                    if res and res.get("_timeout"):
                        again = r["ai_status"] == "retry"
                        results.append({"file_id": r["id"], "kind": "code" if is_code else "doc",
                                        "modified": r["modified"], "status": "error" if again else "retry",
                                        "info": "cloud file too slow to download" if again else "slow - will retry"})
                        continue
                    text = (res or {}).get("text", "") if res else ""
                    item = {"file_id": r["id"], "kind": "code" if is_code else "doc",
                            "modified": r["modified"], "status": "done" if (text or cover is not None) else "empty",
                            "title": (res or {}).get("title") or None, "body": text or None}
                    if res and res.get("pages"):
                        item["info"] = f"{res['pages']} pages"
                    results.append(item)
                    if text:
                        for c in _text_chunks(_header(r, item["title"]), text, max_chunks):
                            all_chunks.append(c)
                            owners.append(len(results) - 1)
                    if cover is not None:
                        covers.append((len(results) - 1, cover))

                if all_chunks:
                    vecs = eng.encode_documents(all_chunks)
                    per: dict[int, list] = {}
                    for idx, v in zip(owners, vecs):
                        per.setdefault(idx, []).append(v)
                    for idx, vs in per.items():
                        results[idx]["text"] = np.stack(vs)

                if covers:
                    cv = eng.encode_image_tensors([c for _, c in covers])
                    for (idx, _), v in zip(covers, cv):
                        top = eng.tags_for_vector(v)
                        results[idx]["clip"] = v[None, :]
                        results[idx]["tags"] = expand_tags([t for t, _ in top])
                        results[idx]["info"] = (results[idx].get("info") or "") + " · scanned page"

                for it, r in zip(results, batch):
                    if it.get("body"):
                        _feed(r["filename"], phase, it.get("tags") or [],
                              it.get("title") or it["body"][:120])
                        break
                _save(conn, results)
                _progress(phase, len(batch), batch[-1]["filename"])
    finally:
        conn.close()


def _process_docs(items: list, mode: str):
    _process_text_kind(items, mode, "doc")


def _process_code(items: list, mode: str):
    _process_text_kind(items, mode, "code")


# ── Stats for the AI page ─────────────────────────────────────────────────────
def db_stats() -> dict:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT kind, status, COUNT(*) AS n FROM ai_items GROUP BY kind, status"
        ).fetchall()
        out: dict = {}
        for r in rows:
            out.setdefault(r["kind"], {})[r["status"]] = r["n"]
        return out
    finally:
        conn.close()
