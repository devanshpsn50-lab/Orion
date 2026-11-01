"""
Orion — ai_extract.py
Reads the *contents* of files so the AI can understand what they are about.

  PDF / EPUB          → title, author, table of contents, first pages + pages sampled across the book
  DOCX / PPTX / XLSX  → body text, slide text, cell values
  ODT / RTF / TXT / MD / CSV / HTML / code → raw text
  Audio               → music tags (title, artist, album, genre, year)
  ZIP / TAR           → list of file names inside

Every extractor is defensive: a broken/encrypted file just returns None.
"""

import os
import re
import zipfile
import tarfile
import logging

log = logging.getLogger("orion.extract")

_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")
_RTF_CTRL = re.compile(r"\\[a-zA-Z]+-?\d* ?|[{}]|\\'[0-9a-f]{2}")

PLAIN_TEXT_EXTS = {
    "txt", "md", "csv", "log", "tex", "rst", "json", "xml", "yaml", "yml", "toml",
    "ini", "cfg", "sql", "py", "js", "ts", "java", "cpp", "c", "h", "hpp", "cs",
    "go", "rs", "php", "rb", "sh", "bat", "ps1", "kt", "swift", "m", "r", "lua",
    "dart", "scala", "ipynb", "css", "jsx", "tsx", "vue", "svelte",
}
HTML_EXTS = {"html", "htm", "xhtml"}


def _clean(s: str) -> str:
    return _WS.sub(" ", s or "").strip()


def _cap(parts: list[str], max_chars: int) -> str:
    out, total = [], 0
    for p in parts:
        p = _clean(p)
        if not p:
            continue
        if total + len(p) > max_chars:
            out.append(p[: max(0, max_chars - total)])
            break
        out.append(p)
        total += len(p) + 1
    return " ".join(out)


# ── PDF ───────────────────────────────────────────────────────────────────────
# PyMuPDF is NOT thread-safe and can crash the process on a corrupt PDF, so the
# server never calls it directly: PDFs go to a small pool of pdf_helper.py
# processes. If a helper dies or hangs, only that one file fails.
import sys as _sys
import json as _json
import queue as _queue
import threading as _threading
import subprocess as _subprocess

_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_helper.py")
_PREFIX = b"@@ORION@@"
PDF_TIMEOUT = 90          # seconds per PDF before the helper is killed


def _python_exe() -> str:
    exe = _sys.executable or "python"
    # pythonw.exe works fine with pipes, but prefer python.exe if it sits next to it
    if exe.lower().endswith("pythonw.exe"):
        alt = exe[:-11] + "python.exe"
        if os.path.exists(alt):
            return alt
    return exe


class _PdfHelper:
    def __init__(self):
        self.proc = None
        self.lines: _queue.Queue = _queue.Queue()

    def _start(self):
        flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
        self.proc = _subprocess.Popen(
            [_python_exe(), "-u", _HELPER],
            stdin=_subprocess.PIPE, stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL,
            creationflags=flags,
        )
        self.lines = _queue.Queue()
        proc, q = self.proc, self.lines

        def _reader():
            try:
                for ln in proc.stdout:
                    if ln.startswith(_PREFIX):
                        q.put(ln[len(_PREFIX):])
            except Exception:
                pass
            q.put(None)                                       # EOF → helper died
        _threading.Thread(target=_reader, daemon=True, name="orion-pdf-reader").start()

    def kill(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def run(self, path: str, max_chars: int, timeout: float) -> dict | None:
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        try:
            self.proc.stdin.write(_json.dumps({"path": path, "max_chars": max_chars}).encode("utf-8") + b"\n")
            self.proc.stdin.flush()
            ln = self.lines.get(timeout=timeout)
        except _queue.Empty:
            log.warning("PDF took over %ds (cloud file?), will retry later: %s", int(timeout), path)
            self.kill()
            return {"_timeout": True}
        except Exception:
            self.kill()
            return None
        if ln is None:
            log.warning("PDF crashed the reader, skipping: %s", path)
            self.kill()
            return None
        res = _json.loads(ln)
        return None if res.get("error") else res


_pool: _queue.Queue | None = None
_pool_lock = _threading.Lock()
PDF_HELPERS = 5


def _pdf(path: str, max_chars: int, patient: bool = False) -> dict | None:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = _queue.Queue()
            for _ in range(PDF_HELPERS):
                _pool.put(_PdfHelper())
    # Online-only files (Google Drive / OneDrive) are downloaded on open, so big
    # books can be slow. First pass: short timeout so the scan never stalls.
    # "patient" = the second attempt at the end of the scan, allowed 15 minutes.
    timeout = 900 if patient else PDF_TIMEOUT
    helper = _pool.get()
    try:
        return helper.run(path, max_chars, timeout)
    finally:
        _pool.put(helper)


def shutdown_pdf_helpers():
    if _pool is None:
        return
    while not _pool.empty():
        try:
            _pool.get_nowait().kill()
        except Exception:
            break


def pdf_extract_direct(path: str, max_chars: int) -> dict | None:
    """Runs INSIDE pdf_helper.py only (never in the server process)."""
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            return None
        meta = doc.metadata or {}
        title = _clean(meta.get("title", ""))
        header = [title, meta.get("author", ""), meta.get("subject", ""), meta.get("keywords", "")]

        # Table of contents is gold for books: chapter names describe the whole book
        toc = [t[1] for t in (doc.get_toc(simple=True) or [])[:200]]

        n = doc.page_count
        pages: list[str] = []
        for i in range(min(n, 8)):                       # first pages (title, preface, contents)
            pages.append(doc[i].get_text("text"))
        if n > 8:                                        # sample across the rest of the book
            samples = min(20, n - 8)
            step = (n - 8) / samples
            for k in range(samples):
                pg = int(8 + k * step)
                pages.append(doc[pg].get_text("text")[:1200])

        text = _cap(header + (["Contents:"] + toc if toc else []) + pages, max_chars)
        return {"title": title, "text": text, "pages": n}
    finally:
        doc.close()


# ── EPUB / ODT (zip containers of XML/HTML) ───────────────────────────────────
def _epub(path: str, max_chars: int) -> dict | None:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")))
        title = ""
        for n in z.namelist():
            if n.lower().endswith(".opf"):
                m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", z.read(n).decode("utf-8", "ignore"), re.S)
                if m:
                    title = _clean(_TAG.sub(" ", m.group(1)))
                break
        parts, total = [title], 0
        for n in names:
            t = _TAG.sub(" ", z.read(n).decode("utf-8", "ignore"))
            parts.append(t[:4000])
            total += len(t)
            if total > max_chars * 2:
                break
        return {"title": title, "text": _cap(parts, max_chars)}


def _odt(path: str, max_chars: int) -> dict | None:
    with zipfile.ZipFile(path) as z:
        xml = z.read("content.xml").decode("utf-8", "ignore")
    return {"title": "", "text": _cap([_TAG.sub(" ", xml)], max_chars)}


# ── Office ────────────────────────────────────────────────────────────────────
def _docx(path: str, max_chars: int) -> dict | None:
    import docx
    d = docx.Document(path)
    title = _clean(d.core_properties.title or "")
    parts = [title, d.core_properties.subject or "", d.core_properties.keywords or ""]
    total = 0
    for p in d.paragraphs:
        parts.append(p.text)
        total += len(p.text)
        if total > max_chars:
            break
    if total < max_chars:
        for tbl in d.tables[:10]:
            for row in tbl.rows[:50]:
                parts.append(" | ".join(c.text for c in row.cells))
    return {"title": title, "text": _cap(parts, max_chars)}


def _pptx(path: str, max_chars: int) -> dict | None:
    from pptx import Presentation
    prs = Presentation(path)
    title = _clean(prs.core_properties.title or "")
    parts = [title]
    for slide in prs.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                parts.append(shape.text_frame.text)
        if sum(len(p) for p in parts) > max_chars:
            break
    return {"title": title, "text": _cap(parts, max_chars), "pages": len(prs.slides)}


def _xlsx(path: str, max_chars: int) -> dict | None:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        parts = []
        for ws in wb.worksheets[:5]:
            parts.append(f"Sheet {ws.title}:")
            cells = 0
            for row in ws.iter_rows(max_row=200, values_only=True):
                vals = [str(v) for v in row if v not in (None, "")]
                if vals:
                    parts.append(" | ".join(vals))
                    cells += len(vals)
                if cells > 600:
                    break
        return {"title": "", "text": _cap(parts, max_chars)}
    finally:
        wb.close()


def _rtf(path: str, max_chars: int) -> dict | None:
    with open(path, "rb") as f:
        raw = f.read(max_chars * 4).decode("latin-1", "ignore")
    return {"title": "", "text": _cap([_RTF_CTRL.sub(" ", raw)], max_chars)}


# ── Plain text / code / HTML ──────────────────────────────────────────────────
def _plain(path: str, max_chars: int, html: bool = False) -> dict | None:
    with open(path, "rb") as f:
        raw = f.read(max_chars * 2)
    if raw[:4096].count(b"\x00") > 8:          # binary disguised as text
        return None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    if html:
        m = re.search(r"<title[^>]*>(.*?)</title>", txt, re.S | re.I)
        title = _clean(m.group(1)) if m else ""
        txt = _TAG.sub(" ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I))
        return {"title": title, "text": _cap([title, txt], max_chars)}
    return {"title": "", "text": _cap([txt], max_chars)}


# ── Audio tags ────────────────────────────────────────────────────────────────
def _audio(path: str, max_chars: int) -> dict | None:
    import mutagen
    a = mutagen.File(path, easy=True)
    if a is None:
        return None
    parts = []
    title = ""
    for key in ("title", "artist", "albumartist", "album", "genre", "date", "composer", "comment"):
        v = a.get(key)
        if v:
            v = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            parts.append(f"{key}: {v}")
            if key == "title":
                title = v
    if not parts:
        return None
    return {"title": title, "text": _cap(parts, max_chars)}


# ── Archives ──────────────────────────────────────────────────────────────────
def _archive(path: str, ext: str, max_chars: int) -> dict | None:
    names: list[str] = []
    if ext == "zip":
        with zipfile.ZipFile(path) as z:
            names = z.namelist()[:400]
    elif ext in ("tar", "gz", "bz2", "xz"):
        try:
            with tarfile.open(path) as t:
                names = [m.name for m in t.getmembers()[:400]]
        except tarfile.ReadError:
            return None
    else:
        return None                      # rar / 7z need extra libraries
    if not names:
        return None
    readable = [os.path.basename(n.rstrip("/")).replace("_", " ").replace("-", " ") for n in names]
    return {"title": "", "text": _cap(["Archive containing:"] + readable, max_chars)}


# ── Dispatcher ────────────────────────────────────────────────────────────────
TEXT_KINDS = {"document", "code", "audio", "archive"}


def extract(path: str, ext: str, file_type: str, max_chars: int = 20000, patient: bool = False) -> dict | None:
    """Return {'title', 'text', ...} describing the file's contents, or None.
    A slow PDF returns {'_timeout': True} so the caller can retry it later."""
    ext = (ext or "").lower()
    try:
        if ext == "pdf":
            return _pdf(path, max_chars, patient)
        if ext == "epub":
            return _epub(path, max_chars)
        if ext in ("odt", "odp", "ods"):
            return _odt(path, max_chars)
        if ext == "docx":
            return _docx(path, max_chars)
        if ext == "pptx":
            return _pptx(path, max_chars)
        if ext in ("xlsx", "xlsm"):
            if os.path.getsize(path) > 40 * 1024 * 1024:
                return None
            return _xlsx(path, max_chars)
        if ext == "rtf":
            return _rtf(path, max_chars)
        if ext in HTML_EXTS:
            return _plain(path, max_chars, html=True)
        if ext in PLAIN_TEXT_EXTS:
            return _plain(path, max_chars)
        if file_type == "audio":
            return _audio(path, max_chars)
        if file_type == "archive":
            return _archive(path, ext, max_chars)
    except Exception as e:                # corrupt, locked, encrypted, permission…
        log.debug("extract failed for %s: %s", path, e)
    return None


def can_extract(ext: str, file_type: str) -> bool:
    ext = (ext or "").lower()
    return (
        ext in {"pdf", "epub", "odt", "odp", "ods", "docx", "pptx", "xlsx", "xlsm", "rtf"}
        or ext in HTML_EXTS or ext in PLAIN_TEXT_EXTS
        or file_type == "audio"
        or (file_type == "archive" and ext in ("zip", "tar", "gz", "bz2", "xz"))
    )
