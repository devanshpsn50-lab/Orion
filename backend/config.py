"""
Orion — config.py
Central configuration, database schema, and shared constants.
"""

import os
import sqlite3
import json
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent          # project root
DATA_DIR   = BASE_DIR / "data"
DB_PATH    = DATA_DIR / "orion.db"
ASSETS_DIR = BASE_DIR / "assets"
FRONTEND_DIR = BASE_DIR / "frontend"

DATA_DIR.mkdir(exist_ok=True)

# ── Server ────────────────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 8472

# ── Indexing ─────────────────────────────────────────────────────────────────
REINDEX_INTERVAL_HOURS = 4
MAX_SEARCH_RESULTS     = 200
THUMBNAIL_SIZE         = (320, 240)

# Default folders to skip during indexing
DEFAULT_EXCLUDED = [
    r"C:\Windows",
    r"C:\ProgramData",
    r"C:\$Recycle.Bin",
    r"C:\System Volume Information",
    r"C:\Recovery",
    r"C:\bootmgr",
    "node_modules",
    ".git",
    "__pycache__",
    ".vs",
    "AppData\\Local\\Temp",
]

# ── File Type Classification ──────────────────────────────────────────────────
EXTENSION_MAP = {
    # Documents
    "pdf":  "document", "doc": "document", "docx": "document",
    "xls":  "document", "xlsx": "document", "ppt": "document",
    "pptx": "document", "txt": "document",  "md": "document",
    "odt":  "document", "ods": "document",  "csv": "document",
    "rtf":  "document", "epub": "document",

    # Images
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image",
    "bmp": "image", "webp": "image", "tiff": "image", "tif": "image",
    "svg": "image", "raw": "image",  "cr2": "image", "nef": "image",
    "heic": "image", "heif": "image", "ico": "image",

    # Videos
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video",
    "wmv": "video", "flv": "video", "webm": "video", "m4v": "video",
    "3gp": "video", "ts": "video",  "mts": "video",

    # Audio
    "mp3": "audio", "flac": "audio", "wav": "audio", "aac": "audio",
    "ogg": "audio", "wma": "audio",  "m4a": "audio", "opus": "audio",
    "aiff": "audio", "ape": "audio",

    # Archives
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive",
    "gz":  "archive", "bz2": "archive", "xz": "archive",

    # Code
    "py": "code",  "js": "code",  "ts": "code",  "html": "code",
    "css": "code", "java": "code","cpp": "code",  "c": "code",
    "h":   "code", "cs": "code",  "go": "code",   "rs": "code",
    "php": "code", "rb": "code",  "sh": "code",   "bat": "code",
    "sql": "code", "json": "code","xml": "code",  "yaml": "code",
    "yml": "code", "toml": "code","ini": "code",  "cfg": "code",
}

FILE_TYPE_ICONS = {
    "document": "📄",
    "image":    "🖼️",
    "video":    "🎬",
    "audio":    "🎵",
    "archive":  "🗜️",
    "code":     "💻",
    "other":    "📁",
}

def get_file_type(extension: str) -> str:
    """Return the broad file type category for an extension."""
    return EXTENSION_MAP.get(extension.lower().lstrip("."), "other")


# ── Database ──────────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")   # 64 MB cache
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    conn = get_db()
    cur  = conn.cursor()

    # Main files table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT    UNIQUE NOT NULL,
            filename    TEXT    NOT NULL,
            extension   TEXT    DEFAULT '',
            drive       TEXT    DEFAULT '',
            size        INTEGER DEFAULT 0,
            modified    INTEGER DEFAULT 0,
            created     INTEGER DEFAULT 0,
            file_type   TEXT    DEFAULT 'other',
            md5_hash    TEXT    DEFAULT NULL,
            ai_description TEXT DEFAULT NULL,
            indexed_at  INTEGER DEFAULT 0
        )
    """)

    # Full-text search virtual table (FTS5)
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
            path,
            filename,
            tokenize = 'unicode61 separators ''_-. ()[]{}#@!''',
            content  = 'files',
            content_rowid = 'id'
        )
    """)

    # FTS5 triggers to keep index in sync
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, path, filename)
            VALUES (new.id, new.path, new.filename);
        END
    """)
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, path, filename)
            VALUES ('delete', old.id, old.path, old.filename);
        END
    """)
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, path, filename)
            VALUES ('delete', old.id, old.path, old.filename);
            INSERT INTO files_fts(rowid, path, filename)
            VALUES (new.id, new.path, new.filename);
        END
    """)

    # Search history
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            query       TEXT    NOT NULL,
            searched_at INTEGER NOT NULL
        )
    """)

    # Excluded paths
    cur.execute("""
        CREATE TABLE IF NOT EXISTS excluded_paths (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT    UNIQUE NOT NULL
        )
    """)

    # Settings key-value store
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Indexes for fast filtering
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_type     ON files(file_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_size     ON files(size)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_drive    ON files(drive)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_ext      ON files(extension)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_md5      ON files(md5_hash)")

    # ── Phase 2: AI tables ────────────────────────────────────────────────────
    # One row per file the AI has looked at (so it never redoes work)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_items (
            file_id       INTEGER PRIMARY KEY,
            kind          TEXT,              -- image | video | doc
            status        TEXT,              -- done | empty | skipped | error
            file_modified INTEGER,           -- files.modified when processed
            processed_at  INTEGER,
            tags          TEXT,              -- "cat, animal, pet"
            title         TEXT,
            info          TEXT
        )
    """)
    # Meaning vectors (CLIP for visuals, BGE for text). Several rows per file allowed.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_vectors (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            space   TEXT    NOT NULL,        -- clip | text
            model   TEXT    NOT NULL,
            vec     BLOB    NOT NULL         -- float16 array
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_aivec_file  ON ai_vectors(file_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_aivec_space ON ai_vectors(space, model)")
    # Full-text index over what is INSIDE files (rowid = files.id)
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
            tags, body, tokenize = 'porter unicode61'
        )
    """)
    # When the indexer removes a deleted file, drop its AI data too
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ai_cleanup AFTER DELETE ON files BEGIN
            DELETE FROM ai_items    WHERE file_id = old.id;
            DELETE FROM ai_vectors  WHERE file_id = old.id;
            DELETE FROM content_fts WHERE rowid   = old.id;
        END
    """)

    # Seed excluded paths with defaults
    for p in DEFAULT_EXCLUDED:
        cur.execute("INSERT OR IGNORE INTO excluded_paths(path) VALUES (?)", (p,))

    conn.commit()
    conn.close()


def get_setting(key: str, default=None):
    conn = get_db()
    row  = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default


def set_setting(key: str, value):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        (key, json.dumps(value))
    )
    conn.commit()
    conn.close()


def get_excluded_paths() -> list[str]:
    conn  = get_db()
    rows  = conn.execute("SELECT path FROM excluded_paths").fetchall()
    conn.close()
    return [r["path"] for r in rows]
