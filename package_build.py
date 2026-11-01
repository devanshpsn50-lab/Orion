"""Build the Orion distribution zip."""
import os, zipfile, shutil

PROJECT = os.path.dirname(os.path.abspath(__file__))
OUT_ZIP  = os.path.join(PROJECT, 'installer', 'orion.zip')

EXCLUDE_DIRS  = {'.git', '.vs', '__pycache__', 'node_modules', 'installer', 'data', '.agents'}
EXCLUDE_FILES = {'.gitignore', 'package.bat', 'package_build.py'}
EXCLUDE_EXTS  = {'.pyc', '.pyo', '.log', '.db'}

os.makedirs(os.path.join(PROJECT, 'installer'), exist_ok=True)
if os.path.exists(OUT_ZIP):
    os.remove(OUT_ZIP)

with zipfile.ZipFile(OUT_ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(PROJECT):
        # Prune excluded dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if fname in EXCLUDE_FILES:
                continue
            if os.path.splitext(fname)[1].lower() in EXCLUDE_EXTS:
                continue
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, PROJECT)
            zf.write(full, rel)
            print(f'  + {rel}')

size_mb = os.path.getsize(OUT_ZIP) / 1024 / 1024
print(f'\nDone! installer/orion.zip ({size_mb:.1f} MB)')
print(f'Distribute the "installer/" folder — it contains:')
print(f'  - Install Orion.bat')
print(f'  - orion.zip')
