"""Build the Orion 2 (AI) distribution zip -> "Orion 2 installer\\orion2.zip".

Separate from package_build.py (Orion 1), which is left untouched.
"""
import os
import zipfile

PROJECT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROJECT, "Orion 2 installer")
OUT_ZIP = os.path.join(OUT_DIR, "orion2.zip")

EXCLUDE_DIRS  = {".git", ".vs", "__pycache__", "node_modules", "installer",
                 "Orion 2 installer", "data", ".agents"}
EXCLUDE_FILES = {".gitignore", "package.bat", "package_build.py", "package_build_v2.py"}
EXCLUDE_EXTS  = {".pyc", ".pyo", ".log", ".db", ".db-wal", ".db-shm"}

REQUIRED = [
    "orion.bat", "requirements.txt", "requirements-ai.txt",
    os.path.join("backend", "main.py"), os.path.join("backend", "ai_engine.py"),
    os.path.join("backend", "ai_download.py"), os.path.join("backend", "pdf_helper.py"),
    os.path.join("backend", "clip", "clip.py"), os.path.join("frontend", "ai.js"),
    os.path.join("assets", "orion_icon.ico"),
]

os.makedirs(OUT_DIR, exist_ok=True)
missing = [r for r in REQUIRED if not os.path.exists(os.path.join(PROJECT, r))]
if missing:
    raise SystemExit(f"Missing required files: {missing}")

if os.path.exists(OUT_ZIP):
    os.remove(OUT_ZIP)

count = 0
with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if fname in EXCLUDE_FILES or os.path.splitext(fname)[1].lower() in EXCLUDE_EXTS:
                continue
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, PROJECT)
            zf.write(full, rel)
            count += 1
            print(f"  + {rel}")

print(f"\nDone! {count} files -> Orion 2 installer\\orion2.zip "
      f"({os.path.getsize(OUT_ZIP) / 1024 / 1024:.1f} MB)")
