"""
Orion — duplicates.py
Detects duplicate files using MD5 content hashing.
Groups files with identical content regardless of name or location.
"""

import os
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from config import get_db

log = logging.getLogger("orion.duplicates")

_running  = False
_progress = {"done": 0, "total": 0, "phase": "idle"}
_lock     = threading.Lock()


def _md5_of_file(path: str, chunk: int = 1 << 20) -> str | None:
    """Compute MD5 hash of a file. Returns hex string or None on error."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def compute_hashes(limit: int = 50_000):
    """
    Compute MD5 hashes for files that don't have one yet.
    Skips very large files (> 4 GB) to stay fast.
    Stores hashes back into the files table.
    """
    global _running, _progress

    with _lock:
        if _running:
            return
        _running = True
        _progress = {"done": 0, "total": 0, "phase": "hashing"}

    conn  = get_db()
    rows  = conn.execute(
        "SELECT id, path, size FROM files WHERE md5_hash IS NULL "
        "AND size > 0 AND size < 4294967296 "   # skip > 4 GB
        "LIMIT ?",
        (limit,)
    ).fetchall()

    with _lock:
        _progress["total"] = len(rows)

    log.info("Computing hashes for %d files", len(rows))

    def hash_row(row):
        digest = _md5_of_file(row["path"])
        return row["id"], digest

    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (file_id, digest) in enumerate(pool.map(hash_row, rows)):
            if digest:
                conn.execute(
                    "UPDATE files SET md5_hash=? WHERE id=?",
                    (digest, file_id)
                )
            with _lock:
                _progress["done"] = i + 1

    conn.commit()
    conn.close()

    with _lock:
        _running         = False
        _progress["phase"] = "done"

    log.info("Hashing complete")


def get_duplicates(min_size: int = 1024) -> list[dict]:
    """
    Return groups of duplicate files (same MD5, same size, > 1 file).
    Each group: { hash, size, count, files: [{id, path, filename, size, modified}] }
    """
    conn = get_db()
    groups_raw = conn.execute(
        """
        SELECT md5_hash, size, COUNT(*) as cnt
        FROM files
        WHERE md5_hash IS NOT NULL AND size >= ?
        GROUP BY md5_hash
        HAVING cnt > 1
        ORDER BY size DESC
        LIMIT 500
        """,
        (min_size,)
    ).fetchall()

    result = []
    for grp in groups_raw:
        files = conn.execute(
            """
            SELECT id, path, filename, size, modified
            FROM files
            WHERE md5_hash = ?
            ORDER BY modified DESC
            """,
            (grp["md5_hash"],)
        ).fetchall()

        result.append({
            "hash":  grp["md5_hash"],
            "size":  grp["size"],
            "count": grp["cnt"],
            "files": [dict(f) for f in files],
        })

    conn.close()
    return result


def duplicate_scan_status() -> dict:
    with _lock:
        return dict(_progress)


def start_duplicate_scan():
    """Run hash computation in a background thread."""
    t = threading.Thread(target=compute_hashes, daemon=True, name="orion-dupes")
    t.start()
