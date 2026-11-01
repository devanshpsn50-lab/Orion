"""
Orion — nlp_parser.py
Parses natural language filter constraints from a search query.

Examples:
  "videos from last month larger than 500MB" →
    { type:"video", date:"month", size_min:524288000 }

  "pdf files bigger than 10mb modified this week" →
    { type:"document", extension:"pdf", size_min:10485760, date:"week" }
"""

import re
from datetime import datetime, timedelta

# ── Size patterns ─────────────────────────────────────────────────────────────
SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}

_SIZE_PATTERN = re.compile(
    r"(larger|bigger|more|greater|over|above|smaller|less|under|below)?\s*"
    r"than\s*([\d.]+)\s*(tb|gb|mb|kb|b)\b",
    re.IGNORECASE
)

_SIZE_RANGE_PATTERN = re.compile(
    r"between\s*([\d.]+)\s*(tb|gb|mb|kb|b)\s*and\s*([\d.]+)\s*(tb|gb|mb|kb|b)",
    re.IGNORECASE
)

# ── Date patterns ─────────────────────────────────────────────────────────────
_DATE_KEYWORDS = {
    "today":      "today",
    "yesterday":  "yesterday",
    "this week":  "week",
    "last week":  "last_week",
    "this month": "month",
    "last month": "last_month",
    "this year":  "year",
    "last year":  "last_year",
}

_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

# ── Duration patterns (for audio/video) ───────────────────────────────────────
_DURATION_PATTERN = re.compile(
    r"(longer|shorter|more|less)?\s*than\s*([\d.]+)\s*(hour|hr|minute|min|second|sec)s?",
    re.IGNORECASE
)

# ── Resolution patterns ───────────────────────────────────────────────────────
_RESOLUTION_MAP = {
    "4k": "4k", "2160p": "4k", "uhd": "4k",
    "1080p": "1080p", "fhd": "1080p", "full hd": "1080p",
    "720p": "720p", "hd": "720p",
    "480p": "480p", "360p": "360p",
}

# ── File type keywords ────────────────────────────────────────────────────────
_TYPE_KEYWORDS = {
    # Documents
    "pdf": ("document", "pdf"),
    "word": ("document", "docx"),
    "excel": ("document", "xlsx"),
    "spreadsheet": ("document", "xlsx"),
    "powerpoint": ("document", "pptx"),
    "presentation": ("document", "pptx"),
    "text": ("document", "txt"),
    "ebook": ("document", "epub"),
    "book": ("document", None),
    "document": ("document", None),
    "doc": ("document", None),

    # Images
    "photo": ("image", None),
    "photos": ("image", None),
    "picture": ("image", None),
    "pictures": ("image", None),
    "image": ("image", None),
    "images": ("image", None),
    "screenshot": ("image", None),
    "jpg": ("image", "jpg"),
    "jpeg": ("image", "jpg"),
    "png": ("image", "png"),
    "gif": ("image", "gif"),

    # Videos
    "video": ("video", None),
    "videos": ("video", None),
    "movie": ("video", None),
    "movies": ("video", None),
    "clip": ("video", None),
    "footage": ("video", None),
    "mp4": ("video", "mp4"),
    "mkv": ("video", "mkv"),

    # Audio
    "music": ("audio", None),
    "audio": ("audio", None),
    "song": ("audio", None),
    "songs": ("audio", None),
    "track": ("audio", None),
    "mp3": ("audio", "mp3"),
    "flac": ("audio", "flac"),
    "podcast": ("audio", None),

    # Archives
    "zip": ("archive", "zip"),
    "archive": ("archive", None),
    "compressed": ("archive", None),
    "rar": ("archive", "rar"),

    # Code
    "code": ("code", None),
    "script": ("code", None),
    "python": ("code", "py"),
    "javascript": ("code", "js"),
    "html": ("code", "html"),
}


def parse_filters(query: str) -> dict:
    """
    Extract structured filters from a natural language query.
    Returns a dict with keys: type, extension, size_min, size_max,
    date, year, duration_min, duration_max, resolution, clean_query.
    """
    filters = {
        "type":         None,
        "extension":    None,
        "size_min":     None,
        "size_max":     None,
        "date":         None,
        "year":         None,
        "duration_min": None,
        "duration_max": None,
        "resolution":   None,
    }

    q = query.lower()
    consumed_spans = []   # track which parts of query were parsed as filters

    # ── File type detection ───────────────────────────────────────────────────
    for keyword, (ftype, ext) in _TYPE_KEYWORDS.items():
        if re.search(r'\b' + re.escape(keyword) + r'\b', q):
            if filters["type"] is None:
                filters["type"] = ftype
            if ext and filters["extension"] is None:
                filters["extension"] = ext

    # ── Size range (between X and Y) ─────────────────────────────────────────
    m = _SIZE_RANGE_PATTERN.search(q)
    if m:
        v1   = float(m.group(1)) * SIZE_UNITS.get(m.group(2).lower(), 1)
        v2   = float(m.group(3)) * SIZE_UNITS.get(m.group(4).lower(), 1)
        filters["size_min"] = int(min(v1, v2))
        filters["size_max"] = int(max(v1, v2))
        consumed_spans.append(m.span())

    # ── Single size constraint ────────────────────────────────────────────────
    if not consumed_spans:
        m = _SIZE_PATTERN.search(q)
        if m:
            direction = (m.group(1) or "larger").lower()
            value     = float(m.group(2)) * SIZE_UNITS.get(m.group(3).lower(), 1)
            if direction in ("larger", "bigger", "more", "greater", "over", "above"):
                filters["size_min"] = int(value)
            else:
                filters["size_max"] = int(value)
            consumed_spans.append(m.span())

    # ── Date detection ────────────────────────────────────────────────────────
    for phrase, key in _DATE_KEYWORDS.items():
        if phrase in q:
            filters["date"] = key
            break

    # ── Year detection ────────────────────────────────────────────────────────
    m = _YEAR_PATTERN.search(q)
    if m:
        filters["year"] = int(m.group(1))

    # ── Duration detection ────────────────────────────────────────────────────
    m = _DURATION_PATTERN.search(q)
    if m:
        direction = (m.group(1) or "longer").lower()
        value     = float(m.group(2))
        unit      = m.group(3).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            seconds = value * 3600
        elif unit.startswith("min"):
            seconds = value * 60
        else:
            seconds = value
        if direction in ("longer", "more"):
            filters["duration_min"] = int(seconds)
        else:
            filters["duration_max"] = int(seconds)

    # ── Resolution detection ─────────────────────────────────────────────────
    for keyword, res in _RESOLUTION_MAP.items():
        if keyword in q:
            filters["resolution"] = res
            break

    # ── Build clean query (remove filter-consumed words) ─────────────────────
    clean = query
    remove_phrases = list(_DATE_KEYWORDS.keys()) + list(_RESOLUTION_MAP.keys())
    for phrase in remove_phrases:
        clean = re.sub(r'\b' + re.escape(phrase) + r'\b', '', clean, flags=re.IGNORECASE)
    # Remove size / duration phrases from clean query
    clean = _SIZE_RANGE_PATTERN.sub('', clean)
    clean = _SIZE_PATTERN.sub('', clean)
    clean = _DURATION_PATTERN.sub('', clean)
    # Remove type keywords (they are implicit filters)
    for keyword in _TYPE_KEYWORDS:
        clean = re.sub(r'\b' + re.escape(keyword) + r'\b', '', clean, flags=re.IGNORECASE)
    # Remove filler words
    for word in ["of", "the", "a", "an", "from", "in", "on", "at", "with",
                 "than", "and", "or", "is", "are", "my", "all", "some"]:
        clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean, flags=re.IGNORECASE)

    clean = re.sub(r'\s{2,}', ' ', clean).strip()
    filters["clean_query"] = clean if clean else query.strip()

    return filters


def date_filter_to_timestamps(date_key: str) -> tuple[int | None, int | None]:
    """Convert a date filter key to (start_ts, end_ts) Unix timestamps."""
    now   = datetime.now()
    today = datetime(now.year, now.month, now.day)

    mapping = {
        "today":      (today, today + timedelta(days=1)),
        "yesterday":  (today - timedelta(days=1), today),
        "week":       (today - timedelta(days=today.weekday()), now),
        "last_week":  (today - timedelta(days=today.weekday()+7),
                       today - timedelta(days=today.weekday())),
        "month":      (today.replace(day=1), now),
        "last_month": (
            (today.replace(day=1) - timedelta(days=1)).replace(day=1),
            today.replace(day=1),
        ),
        "year":       (today.replace(month=1, day=1), now),
        "last_year":  (
            today.replace(year=today.year-1, month=1, day=1),
            today.replace(month=1, day=1),
        ),
    }

    pair = mapping.get(date_key)
    if not pair:
        return None, None
    return int(pair[0].timestamp()), int(pair[1].timestamp())
