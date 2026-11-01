"""
Orion 2 — ai_download.py
Run once by the installer: downloads the AI models (~1 GB) so the first launch
is fast and works offline. Safe to run again (already-downloaded models are reused).

    python backend\ai_download.py
"""
import os
import sys

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # use the bundled `clip`


def main() -> int:
    try:
        import torch
    except Exception as e:
        print(f"   [ERROR] PyTorch is not installed correctly: {e}")
        return 1

    gpu = torch.cuda.is_available()
    if gpu:
        print(f"   GPU found: {torch.cuda.get_device_name(0)}  -> using the large, accurate image model")
    else:
        print("   No NVIDIA GPU found -> using the smaller, faster image model (CPU mode)")

    ok = True
    import clip
    name = "ViT-L/14" if gpu else "ViT-B/32"
    size = "~890 MB" if gpu else "~340 MB"
    print(f"\n   [1/2] Image model CLIP {name} ({size})...")
    try:
        clip.load(name, device="cpu")
        print("         OK")
    except Exception as e:
        ok = False
        print(f"         [FAILED] {e}")

    print("\n   [2/2] Text model BGE-small (~130 MB)...")
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
        print("         OK")
    except Exception as e:
        ok = False
        print(f"         [FAILED] {e}")

    if not ok:
        print("\n   Some models did not download. Orion will try again automatically")
        print("   the first time it starts (internet needed).")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
