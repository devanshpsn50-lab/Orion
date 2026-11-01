"""
Orion — ai_search.py
Hybrid ranking: blends the Phase-1 filename score with three AI signals.

  1. CONTENT  — the query words appear INSIDE the file (PDF text, slides, code…)
                or in its AI tags.  (SQLite FTS5 over extracted text, BM25-ranked)
  2. MEANING  — the document is ABOUT the query even with different words.
                (BGE text embeddings, cosine similarity)
  3. VISUAL   — the image / video LOOKS LIKE the query.
                (CLIP image-text embeddings, cosine similarity)

AI similarity scores are turned into a z-score: "how many standard deviations
above the average file is this match?". A real cat photo stands out from the
crowd (z ≈ 4–6); a random photo doesn't (z ≈ 0). This adapts automatically to
each query and to each user's collection, instead of relying on a fixed cut-off.
"""

import re
import logging
from datetime import datetime

from config import get_db, FILE_TYPE_ICONS
from media_meta import format_size

log = logging.getLogger("orion.aisearch")

# ── Tunables ──────────────────────────────────────────────────────────────────
W_CONTENT_ALL   = 35     # every query word found inside the file
W_CONTENT_ONE   = 22     # single-word query found inside the file (weaker evidence)
W_CONTENT_SOME  = 14     # some (not all) query words inside the file
W_TAG           = 30     # a query word is one of the file's AI tags
W_TAG_PHRASE    = 42     # the whole query is one of the file's AI tags ("football match")

# Calibrated on a real 1.4M-file PC (Oct 2026):
#  CLIP ViT-L/14: true matches stand 3–4 std-devs above the crowd (cos ≈ 0.21–0.30).
CLIP_FLOOR, CLIP_Z_MIN, CLIP_Z_TOP = 0.19, 2.6, 4.0
#  BGE-small: true "this document is about X" matches have cos ≈ 0.70–0.85, while
#  unrelated files still reach 0.55–0.65 — so an absolute floor works far better
#  than z-scores here. Score rises from TEXT_FLOOR to TEXT_TOP.
TEXT_FLOOR, TEXT_TOP, TEXT_Z_MIN = 0.66, 0.80, 2.5
AI_MIN, AI_MAX = 42, 96                 # an AI-only match scores within this band
SMALL_COLLECTION = 40                   # below this, z-scores are unreliable

_WORD = re.compile(r"[\w]+", re.UNICODE)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _clip_score(sim: float, mean: float, std: float, n: int) -> float | None:
    if sim < CLIP_FLOOR:
        return None
    if n >= SMALL_COLLECTION:
        z = (sim - mean) / std
        if z < CLIP_Z_MIN:
            return None
        t = _clamp01((z - CLIP_Z_MIN) / (CLIP_Z_TOP - CLIP_Z_MIN))
    else:                                           # tiny collection: stricter absolute scale
        strict = CLIP_FLOOR + 0.06
        if sim < strict:
            return None
        t = _clamp01((sim - strict) / 0.08)
    return AI_MIN + t * (AI_MAX - AI_MIN)


def _text_score(sim: float, mean: float, std: float, n: int) -> float | None:
    if sim < TEXT_FLOOR:
        return None
    if n >= SMALL_COLLECTION and (sim - mean) / std < TEXT_Z_MIN:
        return None
    t = _clamp01((sim - TEXT_FLOOR) / (TEXT_TOP - TEXT_FLOOR))
    return AI_MIN + t * (AI_MAX - AI_MIN)


# ── Signal collectors ─────────────────────────────────────────────────────────
def _fts_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        w = "".join(_WORD.findall(t))
        if len(w) > 1:
            out.append(w)
    return out


def _content_hits(conn, tokens: list[str], sig: dict):
    words = _fts_tokens(tokens)
    if not words:
        return
    sql = ("SELECT rowid, snippet(content_fts, 1, '[[', ']]', ' … ', 16) AS snip "
           "FROM content_fts WHERE content_fts MATCH ? "
           "ORDER BY bm25(content_fts, 3.0, 1.0) LIMIT 300")
    try:
        rows = conn.execute(sql, [" ".join(f'"{w}"' for w in words)]).fetchall()
        full = W_CONTENT_ALL if len(words) > 1 else W_CONTENT_ONE
        n = max(len(rows), 1)
        for i, r in enumerate(rows):
            s = sig.setdefault(r[0], {})
            s["content"] = full - 8 * (i / n)
            s["snippet"] = r[1]
        if len(words) > 1:
            rows = conn.execute(sql, [" OR ".join(f'"{w}"' for w in words)]).fetchall()
            n = max(len(rows), 1)
            for i, r in enumerate(rows):
                s = sig.setdefault(r[0], {})
                if "content" not in s:
                    s["content"] = W_CONTENT_SOME - 6 * (i / n)
                    s["snippet"] = r[1]
    except Exception as e:
        log.debug("content FTS failed: %s", e)


def _semantic_hits(sem_query: str, filters: dict, sig: dict):
    import ai_engine as eng
    if not eng.is_loaded() or not sem_query:
        return
    ftype = filters.get("type")
    want_visual = ftype in (None, "image", "video")
    want_text = ftype in (None, "document", "code", "audio", "archive")

    if want_visual and len(eng.clip_space):
        hits, mean, std = eng.clip_space.search(eng.encode_clip_text(sem_query), k=200, blend=True)
        n = len(eng.clip_space)
        for fid, sim in hits:
            sc = _clip_score(sim, mean, std, n)
            if sc is not None:
                s = sig.setdefault(fid, {})
                if sc > s.get("ai", 0):
                    s.update(ai=sc, ai_kind="visual", sim=round(sim, 3))

    if want_text and len(eng.text_space):
        hits, mean, std = eng.text_space.search(eng.encode_text_query(sem_query), k=200)
        n = len(eng.text_space)
        for fid, sim in hits:
            sc = _text_score(sim, mean, std, n)
            if sc is not None:
                s = sig.setdefault(fid, {})
                if sc > s.get("ai", 0):
                    s.update(ai=sc, ai_kind="meaning", sim=round(sim, 3))


def _row_to_result(r) -> dict:
    modified_dt = datetime.fromtimestamp(r["modified"]) if r["modified"] else None
    path = str(r["path"])
    return {
        "id":             r["id"],
        "path":           path,
        "filename":       r["filename"],
        "extension":      r["extension"],
        "drive":          r["drive"],
        "file_type":      r["file_type"],
        "icon":           FILE_TYPE_ICONS.get(r["file_type"], "📄"),
        "size":           r["size"],
        "size_label":     format_size(r["size"]),
        "modified":       r["modified"],
        "modified_label": modified_dt.strftime("%d %b %Y, %H:%M") if modified_dt else "",
        "score":          0,
        "folder":         path.rsplit("\\", 1)[0] if "\\" in path else path,
        "ai_description": None,
    }


def _fetch_rows(conn, ids: list[int], filters: dict) -> list:
    from search import _build_sql_filters
    where, params = _build_sql_filters(filters)
    extra = where.replace("WHERE ", "AND ", 1) if where else ""
    out = []
    for i in range(0, len(ids), 800):
        chunk = ids[i:i + 800]
        marks = ",".join("?" * len(chunk))
        out += conn.execute(
            f"SELECT f.id, f.path, f.filename, f.extension, f.drive, f.size, f.modified, f.file_type "
            f"FROM files f WHERE f.id IN ({marks}) {extra}", chunk + params
        ).fetchall()
    return out


def _fetch_ai_items(conn, ids: list[int]) -> dict:
    out = {}
    for i in range(0, len(ids), 800):
        chunk = ids[i:i + 800]
        marks = ",".join("?" * len(chunk))
        for r in conn.execute(
            f"SELECT file_id, tags, title, info FROM ai_items WHERE file_id IN ({marks})", chunk
        ):
            out[r[0]] = (r[1], r[2], r[3])
    return out


# ── Main entry point (called from search.search) ──────────────────────────────
def augment(results: list[dict], query: str, clean_query: str,
            tokens: list[str], filters: dict) -> list[dict]:
    if not tokens:
        return results
    sem_query = _YEAR.sub(" ", clean_query).strip() or clean_query
    by_id = {r["id"]: r for r in results if r.get("id")}
    sig: dict[int, dict] = {}

    conn = get_db()
    try:
        _content_hits(conn, tokens, sig)
        try:
            _semantic_hits(sem_query, filters, sig)
        except Exception as e:
            log.warning("semantic search failed: %s", e)

        new_ids = [fid for fid in sig if fid not in by_id]
        if new_ids:
            from search import _score_result
            for row in _fetch_rows(conn, new_ids, filters):
                res = _row_to_result(row)
                res["score"] = _score_result(dict(row), tokens, filters.get("extension"))
                results.append(res)
                by_id[res["id"]] = res

        ai_items = _fetch_ai_items(conn, list(by_id.keys()))
    finally:
        conn.close()

    token_set = {t.lower() for t in tokens}
    phrase = sem_query.lower().strip()
    for fid, r in by_id.items():
        s = sig.get(fid, {})
        tags_str, title, info = ai_items.get(fid, (None, None, None))
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else []
        reasons = []
        lexical = r.get("score", 0) or 0
        fname = (r.get("filename") or "").lower()
        if any(t in fname for t in token_set):
            reasons.append("name")

        content = s.get("content", 0)
        tag_low = {t.lower() for t in tags}
        if tags and phrase in tag_low:
            content = max(content, W_TAG_PHRASE)
            reasons.append("tag")
        elif tags and token_set & tag_low:
            content = max(content, W_TAG)
            reasons.append("tag")
        elif content:
            reasons.append("content")
        lexical = min(100.0, lexical + content)

        ai = s.get("ai", 0)
        if ai:
            reasons.append(s.get("ai_kind", "ai"))

        final = max(lexical, ai) + 0.25 * min(lexical, ai)
        r["score"] = int(min(100, round(final)))
        r["ai_score"] = int(round(ai)) if ai else None
        r["match"] = reasons
        r["tags"] = tags
        if s.get("snippet"):
            r["snippet"] = s["snippet"]
        if title:
            r["ai_title"] = title
        if info:
            r["ai_info"] = info
    return results


# ── "Find similar" ────────────────────────────────────────────────────────────
def find_similar(path: str, limit: int = 60) -> dict:
    import ai_engine as eng
    if not eng.is_loaded():
        return {"error": "AI is still loading", "results": []}
    conn = get_db()
    try:
        row = conn.execute("SELECT id, file_type FROM files WHERE path=?", (path,)).fetchone()
        if not row:
            return {"error": "File not in index", "results": []}
        fid = row["id"]
        space_name, vec = "clip", eng.clip_space.vector_for(fid)
        if vec is None:
            space_name, vec = "text", eng.text_space.vector_for(fid)
        if vec is None:
            return {"error": "The AI hasn't processed this file yet", "results": []}

        hits, mean, std = eng.space(space_name).search(vec, k=limit + 1)
        hits = [(h, s) for h, s in hits if h != fid][:limit]
        rows = {r["id"]: r for r in _fetch_rows(conn, [h for h, _ in hits], {})}
        ai_items = _fetch_ai_items(conn, list(rows.keys()))
    finally:
        conn.close()

    out = []
    for h, sim in hits:
        if h not in rows:
            continue
        res = _row_to_result(rows[h])
        res["score"] = int(round(max(0.0, min(1.0, sim)) * 100))
        res["ai_score"] = res["score"]
        res["match"] = ["visual" if space_name == "clip" else "meaning"]
        tags_str = ai_items.get(h, (None,))[0]
        res["tags"] = [t.strip() for t in tags_str.split(",")] if tags_str else []
        out.append(res)
    return {"space": space_name, "results": out}


def file_ai_info(path: str) -> dict:
    """AI facts about one file (for the preview panel)."""
    conn = get_db()
    try:
        r = conn.execute(
            "SELECT a.kind, a.status, a.tags, a.title, a.info, a.processed_at, "
            "       substr(c.body, 1, 600) AS excerpt "
            "FROM files f JOIN ai_items a ON a.file_id = f.id "
            "LEFT JOIN content_fts c ON c.rowid = f.id WHERE f.path = ?", (path,)
        ).fetchone()
        if not r:
            return {"processed": False}
        return {
            "processed": True, "kind": r["kind"], "status": r["status"],
            "tags": [t.strip() for t in (r["tags"] or "").split(",") if t.strip()],
            "title": r["title"], "info": r["info"], "excerpt": r["excerpt"],
            "processed_at": r["processed_at"],
        }
    finally:
        conn.close()
