"""
Orion — indexer.py
Drives & file-system indexing engine.
- Uses Everything (es.exe) if installed → full 1 TB index in seconds
- Falls back to multithreaded os.walk when Everything is unavailable
- Stores everything in SQLite + FTS5
- Runs a background scheduler thread to re-index every N hours
"""

import os
import time
import shutil
import hashlib
import logging
import threading
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import (
    get_db, get_file_type, get_excluded_paths,
    REINDEX_INTERVAL_HOURS, EXTENSION_MAP
)

log = logging.getLogger("orion.indexer")

# ── Global state ──────────────────────────────────────────────────────────────
_state_lock           = threading.Lock()
_indexing             = False
_indexed_files        = 0
_total_files_estimate = 0
_index_start_time     = None
_index_phase          = "idle"
_dirs_visited         = 0
_files_found          = 0      # paths collected in scanning phase
_current_drive        = ""


def get_status() -> dict:
    with _state_lock:
        elapsed = time.time() - _index_start_time if _index_start_time else 0
        rate    = 0
        eta     = None

        if _index_phase == "inserting" and elapsed > 0:
            rate = _indexed_files / elapsed if elapsed else 0
            if _total_files_estimate > 0 and rate > 0:
                remaining = _total_files_estimate - _indexed_files
                eta = int(remaining / rate)

        return {
            "indexing":         _indexing,
            "indexed_files":    _indexed_files,
            "total_estimate":   _total_files_estimate,
            "phase":            _index_phase,
            "elapsed_seconds":  round(elapsed, 1),
            "dirs_visited":     _dirs_visited,
            "files_found":      _files_found,
            "current_drive":    _current_drive,
            "files_per_second": round(rate, 1),
            "eta_seconds":      eta,
        }


# ── Everything integration (HTTP API → es.exe IPC → os.walk) ─────────────────

EVERYTHING_EXE = str(
    Path(__file__).parent.parent / "tools" / "Everything" / "Everything.exe"
)
EVERYTHING_HTTP_PORT = 8481   # local HTTP API port


def _find_es_exe() -> str | None:
    """Locate es.exe (Everything command-line tool)."""
    _local = Path(__file__).parent.parent / "tools" / "Everything" / "es.exe"
    for c in [str(_local),
              r"C:\Program Files\Everything\es.exe",
              r"C:\Program Files (x86)\Everything\es.exe",
              shutil.which("es")]:
        if c and os.path.isfile(c):
            return c
    return None


def _ensure_everything_running():
    """Start Everything.exe with HTTP server enabled if not already running."""
    import ctypes
    exe = EVERYTHING_EXE if os.path.isfile(EVERYTHING_EXE) else None
    if not exe:
        for p in [r"C:\Program Files\Everything\Everything.exe",
                  r"C:\Program Files (x86)\Everything\Everything.exe"]:
            if os.path.isfile(p):
                exe = p
                break
    if not exe:
        return False

    # Check if already running
    try:
        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq Everything.exe"],
            capture_output=True, text=True
        )
        if "Everything.exe" in result.stdout:
            log.info("Everything.exe already running")
            return True
    except Exception:
        pass

    log.info("Starting Everything.exe with HTTP server on port %d", EVERYTHING_HTTP_PORT)
    subprocess.Popen(
        [exe, "-startup",
         "-http-server",
         f"-http-port", str(EVERYTHING_HTTP_PORT)],
        creationflags=0x00000008,  # DETACHED_PROCESS
    )
    time.sleep(5)   # give it time to build index
    return True


def _index_with_everything_http(excluded: list[str]) -> list[str] | None:
    """
    Query Everything's built-in HTTP server for all file paths.
    This avoids IPC elevation issues entirely.
    """
    import urllib.request
    import urllib.parse

    url = (
        f"http://localhost:{EVERYTHING_HTTP_PORT}/"
        f"?search=!folder:&count=9999999&path_column=1&"
        f"json=1&sort=path_ascending"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            import json as _json
            data = _json.loads(resp.read().decode("utf-8", errors="replace"))

        results_raw = data.get("results", [])
        excluded_lower = [e.lower() for e in excluded]

        paths = []
        for item in results_raw:
            p = item.get("path", "") + "\\" + item.get("name", "")
            if p and not any(p.lower().startswith(ex) for ex in excluded_lower):
                paths.append(p)

        log.info("Everything HTTP API returned %d paths", len(paths))
        return paths if paths else None

    except Exception as e:
        log.warning("Everything HTTP API failed: %s", e)
        return None


def _index_with_everything_es(excluded: list[str]) -> list[str] | None:
    """Use es.exe IPC (fallback to HTTP)."""
    es = _find_es_exe()
    if not es:
        return None
    try:
        result = subprocess.run(
            [es, "-full-path-and-name", "-n", "0",
             "-sort", "path-ascending", "!folder:"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        if result.returncode != 0:
            log.warning("es.exe error: %s", result.stderr[:200])
            return None
        paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
        excluded_lower = [e.lower() for e in excluded]
        paths = [p for p in paths
                 if not any(p.lower().startswith(ex) for ex in excluded_lower)]
        log.info("es.exe returned %d paths", len(paths))
        return paths or None
    except Exception as e:
        log.warning("es.exe failed: %s", e)
        return None


def _index_with_everything(excluded: list[str]) -> list[str] | None:
    """
    Try Everything HTTP API first (most reliable), then IPC es.exe, then give up.
    Returns list of paths or None to trigger os.walk fallback.
    """
    _ensure_everything_running()
    time.sleep(2)

    # 1. Try HTTP API (works regardless of elevation)
    paths = _index_with_everything_http(excluded)
    if paths:
        return paths

    # 2. Try es.exe IPC
    log.info("HTTP API unavailable, trying es.exe IPC…")
    paths = _index_with_everything_es(excluded)
    if paths:
        return paths

    log.info("Everything unavailable, will use os.walk")
    return None


# ── Fallback: multithreaded os.walk ───────────────────────────────────────────
def _get_all_drives() -> list[str]:
    """Return all available drive letters on Windows."""
    drives = []
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                drives.append(chr(65 + i) + ":\\")
    except Exception:
        drives = ["C:\\"]
    return drives


def _walk_drive(drive: str, excluded_lower: list[str]) -> list[str]:
    """Walk a single drive and return all file paths, updating progress counters."""
    global _dirs_visited, _files_found, _current_drive
    results = []
    local_dirs = 0
    for root, dirs, files in os.walk(drive, topdown=True, onerror=None):
        root_lower = root.lower()
        if any(root_lower.startswith(ex) for ex in excluded_lower):
            dirs.clear()
            continue
        dirs[:] = [
            d for d in dirs
            if not any(
                os.path.join(root, d).lower().startswith(ex)
                for ex in excluded_lower
            )
        ]
        local_dirs += 1
        for fname in files:
            results.append(os.path.join(root, fname))

        # Update shared counters every 500 dirs
        if local_dirs % 500 == 0:
            with _state_lock:
                _dirs_visited += 500
                _files_found   = len(results)
                _current_drive = drive

    with _state_lock:
        _dirs_visited += local_dirs % 500
        _files_found   = len(results)
    return results


def _index_with_walk(excluded: list[str]) -> list[str]:
    """Walk all drives using a thread per drive."""
    global _dirs_visited, _files_found
    with _state_lock:
        _dirs_visited = 0
        _files_found  = 0

    excluded_lower = [e.lower() for e in excluded]
    drives         = _get_all_drives()
    log.info("Walking drives: %s", drives)

    all_paths: list[str] = []
    with ThreadPoolExecutor(max_workers=len(drives)) as pool:
        futures = {pool.submit(_walk_drive, d, excluded_lower): d for d in drives}
        for fut in as_completed(futures):
            try:
                all_paths.extend(fut.result())
            except Exception as e:
                log.warning("Walk failed for drive: %s", e)

    return all_paths



# ── Metadata extraction ────────────────────────────────────────────────────────
def _extract_file_meta(path: str) -> dict | None:
    """Extract all relevant metadata for a single file path."""
    try:
        stat = os.stat(path)
    except (OSError, PermissionError):
        return None

    p         = Path(path)
    extension = p.suffix.lower().lstrip(".")
    drive     = Path(path).anchor.rstrip("\\/").upper()

    return {
        "path":       path,
        "filename":   p.name,
        "extension":  extension,
        "drive":      drive,
        "size":       stat.st_size,
        "modified":   int(stat.st_mtime),
        "created":    int(stat.st_ctime),
        "file_type":  get_file_type(extension),
        "indexed_at": int(time.time()),
    }


# ── Database insertion (batch) ─────────────────────────────────────────────────
BATCH_SIZE = 5_000

def _insert_batch(batch: list[dict], conn):
    """Insert or update a batch of file records."""
    conn.executemany(
        """
        INSERT INTO files
            (path, filename, extension, drive, size, modified, created,
             file_type, indexed_at)
        VALUES
            (:path, :filename, :extension, :drive, :size, :modified, :created,
             :file_type, :indexed_at)
        ON CONFLICT(path) DO UPDATE SET
            filename   = excluded.filename,
            extension  = excluded.extension,
            size       = excluded.size,
            modified   = excluded.modified,
            file_type  = excluded.file_type,
            indexed_at = excluded.indexed_at
        """,
        batch,
    )
    conn.commit()


def _remove_stale_files(conn, fresh_paths: set[str]):
    """Remove DB entries for files that no longer exist on disk."""
    cursor = conn.execute("SELECT id, path FROM files")
    stale  = [row["id"] for row in cursor if row["path"] not in fresh_paths]
    if stale:
        conn.executemany("DELETE FROM files WHERE id=?", [(i,) for i in stale])
        conn.commit()
        log.info("Removed %d stale file records", len(stale))


# ── Main indexing entry point ──────────────────────────────────────────────────
def run_index(force: bool = False):
    """
    Build or refresh the file index.
    Runs synchronously in the calling thread (call from a background thread).
    """
    global _indexing, _indexed_files, _total_files_estimate
    global _index_start_time, _index_phase

    with _state_lock:
        if _indexing and not force:
            log.info("Indexing already in progress, skipping")
            return
        _indexing          = True
        _indexed_files     = 0
        _index_start_time  = time.time()
        _index_phase       = "scanning"

    excluded = get_excluded_paths()
    log.info("Starting index. Excluded: %d paths", len(excluded))

    try:
        # ── Phase 1: Collect file paths ───────────────────────────────────────
        paths = _index_with_everything(excluded)
        if paths is None:
            log.info("Everything not available, falling back to os.walk")
            paths = _index_with_walk(excluded)

        with _state_lock:
            _total_files_estimate = len(paths)
            _index_phase          = "inserting"

        log.info("Collected %d paths, now inserting into DB", len(paths))

        # ── Phase 2: Extract metadata & insert in batches ─────────────────────
        conn  = get_db()
        batch: list[dict] = []
        fresh_paths: set[str] = set()

        with ThreadPoolExecutor(max_workers=8) as pool:
            for meta in pool.map(_extract_file_meta, paths, chunksize=200):
                if meta is None:
                    continue
                fresh_paths.add(meta["path"])
                batch.append(meta)

                if len(batch) >= BATCH_SIZE:
                    _insert_batch(batch, conn)
                    with _state_lock:
                        _indexed_files += len(batch)
                    batch.clear()

        if batch:
            _insert_batch(batch, conn)
            with _state_lock:
                _indexed_files += len(batch)

        # ── Phase 3: Remove stale records ────────────────────────────────────
        _remove_stale_files(conn, fresh_paths)
        conn.close()

        elapsed = time.time() - _index_start_time
        log.info("Index complete: %d files in %.1fs", _indexed_files, elapsed)

        with _state_lock:
            _index_phase = "done"

        # Phase 2: wake the AI worker so new/changed files get understood
        try:
            import ai_worker
            ai_worker.notify_new_files()
        except Exception:
            pass

    except Exception as e:
        log.exception("Indexing failed: %s", e)
        with _state_lock:
            _index_phase = "error"
    finally:
        with _state_lock:
            _indexing = False


# ── Background scheduler ──────────────────────────────────────────────────────
_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _scheduler_loop():
    """
    On startup: only scan if DB is empty OR last index is older than REINDEX_INTERVAL_HOURS.
    Then re-scan on that same interval automatically.
    """
    try:
        conn = get_db()
        row = conn.execute("SELECT MAX(indexed_at), COUNT(*) FROM files").fetchone()
        conn.close()
        last_indexed   = row[0] or 0
        indexed_count  = row[1] or 0
        age_hours      = (time.time() - last_indexed) / 3600
    except Exception:
        last_indexed, indexed_count, age_hours = 0, 0, 999

    if indexed_count == 0:
        log.info("Database empty — running first-time index")
        run_index()
    elif age_hours >= REINDEX_INTERVAL_HOURS:
        log.info("Index is %.1fh old (threshold: %dh) — re-indexing", age_hours, REINDEX_INTERVAL_HOURS)
        run_index()
    else:
        log.info(
            "Index is fresh (%.1fh old, %d files) — skipping startup scan. "
            "Next re-index in %.1fh.",
            age_hours, indexed_count, REINDEX_INTERVAL_HOURS - age_hours
        )

    # Periodic re-index loop
    while not _stop_event.wait(timeout=REINDEX_INTERVAL_HOURS * 3600):
        log.info("Scheduled re-index starting")
        run_index()


def start_background_indexer():
    """Start the background indexing scheduler (runs in daemon thread)."""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, name="orion-indexer", daemon=True
    )
    _scheduler_thread.start()
    log.info("Background indexer started")


def stop_background_indexer():
    """Signal the background indexer to stop."""
    _stop_event.set()


def trigger_reindex():
    """Manually trigger a re-index in a new thread (non-blocking)."""
    t = threading.Thread(target=run_index, name="orion-reindex", daemon=True)
    t.start()
