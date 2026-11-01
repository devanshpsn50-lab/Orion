"""
Orion — search.py
Search engine: query parsing, FTS5 full-text search, multi-signal ranking.
"""

import time
import logging
from datetime import datetime

from config import get_db, FILE_TYPE_ICONS, get_file_type
from nlp_parser import parse_filters, date_filter_to_timestamps
from media_meta import format_size, format_duration

log = logging.getLogger("orion.search")

MAX_RESULTS = 200


# ── Scoring weights ────────────────────────────────────────────────────────────
W_FILENAME_ALL   = 45   # all query words in filename
W_FILENAME_SOME  = 20   # some query words in filename
W_EXT_MATCH      = 20   # extension matches query intent
W_PATH_MATCH     = 15   # query words appear in folder path
W_RECENT_7D      = 10   # modified in last 7 days
W_RECENT_30D     =  5   # modified in last 30 days
W_EXACT_NAME     = 25   # exact filename match (bonus)


def _score_result(row: dict, tokens: list[str], ext_filter: str | None) -> int:
    score      = 0
    fname_low  = row["filename"].lower()
    path_low   = row["path"].lower()
    folder_low = path_low[: len(path_low) - len(fname_low)].lower()

    # Count how many tokens appear in the filename
    matches = sum(1 for t in tokens if t in fname_low)
    if matches == len(tokens) and tokens:
        score += W_FILENAME_ALL
    elif matches > 0:
        score += W_FILENAME_SOME * (matches / len(tokens))

    # Exact filename match (without extension)
    stem = fname_low.rsplit(".", 1)[0]
    if tokens and " ".join(tokens) == stem:
        score += W_EXACT_NAME

    # Folder path match
    path_matches = sum(1 for t in tokens if t in folder_low)
    if path_matches:
        score += W_PATH_MATCH * (path_matches / max(len(tokens), 1))

    # Extension / type match
    if ext_filter and row["extension"] == ext_filter:
        score += W_EXT_MATCH
    elif ext_filter is None:
        score += 0   # neutral

    # Recency boost
    now = time.time()
    age = now - (row["modified"] or 0)
    if age < 7 * 86400:
        score += W_RECENT_7D
    elif age < 30 * 86400:
        score += W_RECENT_30D

    return min(int(score), 100)


def _build_sql_filters(filters: dict) -> tuple[str, list]:
    """Build the WHERE clause and params list for optional filters."""
    clauses = []
    params  = []

    if filters.get("type"):
        clauses.append("f.file_type = ?")
        params.append(filters["type"])

    if filters.get("extension"):
        clauses.append("f.extension = ?")
        params.append(filters["extension"].lstrip("."))

    if filters.get("size_min") is not None:
        clauses.append("f.size >= ?")
        params.append(filters["size_min"])

    if filters.get("size_max") is not None:
        clauses.append("f.size <= ?")
        params.append(filters["size_max"])

    if filters.get("date"):
        ts_start, ts_end = date_filter_to_timestamps(filters["date"])
        if ts_start:
            clauses.append("f.modified >= ?")
            params.append(ts_start)
        if ts_end:
            clauses.append("f.modified <= ?")
            params.append(ts_end)

    if filters.get("year"):
        import calendar
        y = filters["year"]
        ts_start = int(datetime(y, 1, 1).timestamp())
        ts_end   = int(datetime(y, 12, 31, 23, 59, 59).timestamp())
        clauses.append("f.modified BETWEEN ? AND ?")
        params += [ts_start, ts_end]

    if filters.get("drive"):
        clauses.append("f.drive = ?")
        params.append(filters["drive"].upper().rstrip("\\"))

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def search(query: str, extra_filters: dict | None = None) -> list[dict]:
    """
    Main search function. Returns a list of ranked result dicts.
    Folder names are also searched and returned above file results.
    """
    start_ts = time.time()

    filters = parse_filters(query)
    if extra_filters:
        for k, v in extra_filters.items():
            if v is not None:
                filters[k] = v

    clean_query = filters.get("clean_query") or query
    tokens      = [t.lower() for t in clean_query.split() if len(t) > 1]

    conn    = get_db()
    results = []

    # ── Full-text search via FTS5 ─────────────────────────────────────────────
    if tokens:
        filter_where, filter_params = _build_sql_filters(filters)
        filter_sql = filter_where.replace("WHERE ", "AND ", 1) if filter_where else ""
        fts_query  = " OR ".join(f'"{t}"' for t in tokens)

        sql = f"""
            SELECT
                f.id, f.path, f.filename, f.extension, f.drive,
                f.size, f.modified, f.created, f.file_type,
                f.md5_hash, f.ai_description,
                fts.rank AS fts_rank
            FROM files_fts fts
            INNER JOIN files f ON fts.rowid = f.id
            WHERE files_fts MATCH ?
            {filter_sql}
            ORDER BY fts.rank
            LIMIT {MAX_RESULTS * 2}
        """
        try:
            rows = conn.execute(sql, [fts_query] + filter_params).fetchall()
        except Exception as e:
            log.warning("FTS5 query failed (%s), falling back to LIKE", e)
            rows = _fallback_like_search(conn, tokens, filters)
    else:
        filter_where, filter_params = _build_sql_filters(filters)
        sql = f"""
            SELECT f.id, f.path, f.filename, f.extension, f.drive,
                   f.size, f.modified, f.created, f.file_type,
                   f.md5_hash, f.ai_description, 0 AS fts_rank
            FROM files f {filter_where}
            ORDER BY f.modified DESC LIMIT {MAX_RESULTS}
        """
        rows = conn.execute(sql, filter_params).fetchall()

    # ── Folder search — no re-index needed ───────────────────────────────────
    # Only runs when no type/extension filter is active (folders have no type)
    folder_results = []
    if tokens and not filters.get("type") and not filters.get("extension"):
        folder_results = _search_folders(conn, tokens, max_results=15)

    conn.close()

    # ── Score & format file results ───────────────────────────────────────────
    for row in rows:
        r           = dict(row)
        score       = _score_result(r, tokens, filters.get("extension"))
        modified_dt = datetime.fromtimestamp(r["modified"]) if r["modified"] else None
        results.append({
            "id":             r["id"],
            "path":           r["path"],
            "filename":       r["filename"],
            "extension":      r["extension"],
            "drive":          r["drive"],
            "file_type":      r["file_type"],
            "icon":           FILE_TYPE_ICONS.get(r["file_type"], "📄"),
            "size":           r["size"],
            "size_label":     format_size(r["size"]),
            "modified":       r["modified"],
            "modified_label": modified_dt.strftime("%d %b %Y, %H:%M") if modified_dt else "",
            "score":          score,
            "folder":         str(r["path"]).rsplit("\\", 1)[0] if "\\" in str(r["path"]) else r["path"],
            "ai_description": r["ai_description"],
        })

    # ── Phase 2: blend in AI understanding (file contents, meaning, visuals) ──
    try:
        import ai_search
        results = ai_search.augment(results, query, clean_query, tokens, filters)
    except Exception as e:
        log.warning("AI ranking skipped: %s", e)

    results.sort(key=lambda x: x["score"], reverse=True)

    # Folders float to top, then ranked file results
    final   = folder_results + results[:MAX_RESULTS]
    elapsed = (time.time() - start_ts) * 1000
    log.info("Search '%s' → %d results (%d folders) in %.1fms",
             query, len(final), len(folder_results), elapsed)
    return final


def _fallback_like_search(conn, tokens: list[str], filters: dict) -> list:
    """LIKE-based search fallback when FTS5 match fails."""
    like_clauses  = " AND ".join(f"(f.path LIKE ?)" for _ in tokens)
    like_params   = [f"%{t}%" for t in tokens]
    filter_where, filter_params = _build_sql_filters(filters)
    filter_extra  = filter_where.replace("WHERE ", "AND ", 1) if filter_where else ""

    sql = f"""
        SELECT
            f.id, f.path, f.filename, f.extension, f.drive,
            f.size, f.modified, f.created, f.file_type,
            f.md5_hash, f.ai_description,
            0 AS fts_rank
        FROM files f
        WHERE {like_clauses}
        {filter_extra}
        ORDER BY f.modified DESC
        LIMIT 400
    """
    return conn.execute(sql, like_params + filter_params).fetchall()


# ── Folder name search ─────────────────────────────────────────────────────────
def _search_folders(conn, tokens: list[str], max_results: int = 15) -> list[dict]:
    """
    Find unique folder names matching the query by parsing paths of indexed files.
    No schema changes or re-indexing required — works on existing data instantly.

    Example: searching 'cpp' returns folders like 'learn cpp', 'cpp projects', etc.
    """
    found: dict[str, dict] = {}   # folder_path → result dict

    for token in tokens:
        # Match any file whose path contains a word starting with the token.
        # Uses the FTS index on `path` (fast) instead of a LIKE scan over every row.
        safe = token.replace('"', "")
        try:
            rows = conn.execute(
                "SELECT f.path, f.filename, f.modified, f.drive FROM files_fts "
                "JOIN files f ON f.id = files_fts.rowid "
                "WHERE files_fts MATCH ? LIMIT 800",
                (f'path : "{safe}"*',)
            ).fetchall()
        except Exception:
            try:
                rows = conn.execute(
                    "SELECT path, filename, modified, drive FROM files "
                    "WHERE lower(path) LIKE lower(?) LIMIT 800",
                    (f"%\\{token}%",)
                ).fetchall()
            except Exception:
                continue

        for row in rows:
            path     = row["path"] or ""
            filename = row["filename"] or ""

            # Strip filename to get the directory portion
            if filename and path.endswith(filename):
                dir_part = path[: len(path) - len(filename)].rstrip("\\/")
            else:
                dir_part = path.rsplit("\\", 1)[0]

            if not dir_part or len(dir_part) <= 3:   # skip bare drive roots e.g. "C:"
                continue

            # Walk every segment of the directory path and find the matching one
            segments = dir_part.replace("/", "\\").split("\\")
            for i, seg in enumerate(segments):
                if not seg or len(seg) <= 1:
                    continue
                if token.lower() in seg.lower():
                    folder_path = "\\".join(segments[: i + 1])
                    if folder_path not in found:
                        try:
                            modified_dt = datetime.fromtimestamp(row["modified"]) if row["modified"] else None
                        except Exception:
                            modified_dt = None
                        found[folder_path] = {
                            "id":             None,
                            "path":           folder_path,
                            "filename":       seg,          # the folder's own name
                            "extension":      "",
                            "drive":          row["drive"] or "",
                            "file_type":      "folder",
                            "icon":           "📁",
                            "size":           0,
                            "size_label":     "Folder",
                            "modified":       row["modified"],
                            "modified_label": modified_dt.strftime("%d %b %Y, %H:%M") if modified_dt else "",
                            "score":          90,           # always above files
                            "folder":         "\\".join(segments[:i]) if i > 0 else folder_path,
                            "ai_description": None,
                        }
                    break   # take the shallowest matching segment per path

        if len(found) >= max_results:
            break

    # Exact name match first, then alphabetical
    token_set = set(tokens)
    return sorted(
        list(found.values())[:max_results],
        key=lambda x: (0 if x["filename"].lower() in token_set else 1, x["filename"].lower())
    )



def get_recent_files(limit: int = 30) -> list[dict]:
    """Return the most recently modified files for the home screen."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, path, filename, extension, drive, size, modified, file_type
        FROM files
        WHERE modified > 0
        ORDER BY modified DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        modified_dt = datetime.fromtimestamp(r["modified"]) if r["modified"] else None
        results.append({
            "id":             r["id"],
            "path":           r["path"],
            "filename":       r["filename"],
            "extension":      r["extension"],
            "drive":          r["drive"],
            "file_type":      r["file_type"],
            "icon":           FILE_TYPE_ICONS.get(r["file_type"], "📁"),
            "size":           r["size"],
            "size_label":     format_size(r["size"]),
            "modified":       r["modified"],
            "modified_label": modified_dt.strftime("%d %b %Y, %H:%M") if modified_dt else "",
            "folder":         str(r["path"]).rsplit("\\", 1)[0],
        })
    return results


def get_stats() -> dict:
    """Return index statistics for the dashboard."""
    conn = get_db()

    total        = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    total_size   = conn.execute("SELECT SUM(size) FROM files").fetchone()[0] or 0
    by_type      = conn.execute(
        "SELECT file_type, COUNT(*) as cnt, SUM(size) as total_size "
        "FROM files GROUP BY file_type ORDER BY cnt DESC"
    ).fetchall()
    by_drive     = conn.execute(
        "SELECT drive, COUNT(*) as cnt, SUM(size) as total_size "
        "FROM files GROUP BY drive ORDER BY cnt DESC"
    ).fetchall()
    last_indexed = conn.execute(
        "SELECT MAX(indexed_at) FROM files"
    ).fetchone()[0]

    conn.close()

    return {
        "total_files":   total,
        "total_size":    total_size,
        "total_size_label": format_size(total_size),
        "by_type":       [dict(r) for r in by_type],
        "by_drive":      [dict(r) for r in by_drive],
        "last_indexed":  last_indexed,
        "last_indexed_label": (
            datetime.fromtimestamp(last_indexed).strftime("%d %b %Y, %H:%M")
            if last_indexed else "Never"
        ),
        "icons": FILE_TYPE_ICONS,
    }


def save_to_history(query: str):
    """Persist a search query to history (max 50 entries)."""
    conn = get_db()
    conn.execute(
        "INSERT INTO search_history(query, searched_at) VALUES (?, ?)",
        (query.strip(), int(time.time()))
    )
    # Keep only last 50
    conn.execute(
        """
        DELETE FROM search_history
        WHERE id NOT IN (
            SELECT id FROM search_history
            ORDER BY searched_at DESC
            LIMIT 50
        )
        """
    )
    conn.commit()
    conn.close()


def get_history() -> list[str]:
    """Return last 50 search queries (most recent first, unique)."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT DISTINCT query
        FROM search_history
        ORDER BY searched_at DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()
    return [r["query"] for r in rows]


def clear_history():
    conn = get_db()
    conn.execute("DELETE FROM search_history")
    conn.commit()
    conn.close()
