"""
Orion — pdf_helper.py
Small standalone process that reads PDFs for the AI worker.

PyMuPDF (MuPDF) is a C library: it is not thread-safe and a badly broken PDF can
crash the whole Python process. So Orion never opens PDFs inside the main server.
Instead it starts a few of these helpers and talks to them over stdin/stdout:

    request  (one JSON line):  {"path": "...", "max_chars": 20000}
    response (one JSON line):  @@ORION@@{"title": ..., "text": ..., "pages": N, "cover": "<png base64>"}

If a PDF kills this helper, Orion simply marks that one file as failed and starts
a fresh helper.
"""

import sys
import json
import base64
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PREFIX = b"@@ORION@@"


def _reply(out, obj):
    out.write(PREFIX + json.dumps(obj, ensure_ascii=True).encode("ascii") + b"\n")
    out.flush()


def main():
    # Keep a private handle to the real stdout for replies, and point fd 1 at
    # stderr so stray C-library prints can never corrupt the protocol.
    out = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

    import fitz  # PyMuPDF
    try:
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass
    from ai_extract import pdf_extract_direct

    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = pdf_extract_direct(req["path"], int(req.get("max_chars", 20000))) or {}
            if len(res.get("text", "")) < 200:          # scanned PDF → send first page picture
                try:
                    with fitz.open(req["path"]) as d:
                        if not d.needs_pass and d.page_count:
                            pix = d[0].get_pixmap(dpi=60)
                            res["cover"] = base64.b64encode(pix.tobytes("png")).decode("ascii")
                except Exception:
                    pass
            _reply(out, res)
        except Exception as e:
            _reply(out, {"error": str(e)[:200]})


if __name__ == "__main__":
    main()
