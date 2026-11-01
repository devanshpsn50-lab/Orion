"""
Orion 2 — torch_check.py  (used by the installer)

    python backend\torch_check.py        -> exit 0 if PyTorch imports and works
    python backend\torch_check.py gpu    -> exit 0 only if PyTorch can really compute on the NVIDIA GPU
"""
import sys


def main() -> int:
    want_gpu = len(sys.argv) > 1 and sys.argv[1].lower() == "gpu"
    try:
        import torch
        import torchvision  # noqa: F401  (must match torch)
        x = torch.ones(64, 64)
        (x @ x).sum().item()
        if want_gpu:
            if not torch.cuda.is_available():
                return 3
            g = torch.ones(256, 256, device="cuda", dtype=torch.float16)
            (g @ g).sum().item()
            torch.cuda.synchronize()
            print(f"         PyTorch {torch.__version__} on GPU: {torch.cuda.get_device_name(0)}")
        else:
            print(f"         PyTorch {torch.__version__} (CPU)")
        return 0
    except Exception as e:
        print(f"         PyTorch check failed: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
