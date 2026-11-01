"""
Orion — ai_engine.py
The "brain": loads two neural networks onto the GPU and does vector search.

  1. CLIP (OpenAI, ViT-L/14)  — understands IMAGES and VIDEO FRAMES.
     It maps pictures and text into the same 768-number "meaning space",
     so the text "cat" lands right next to photos of cats.

  2. BGE-small (BAAI)         — understands DOCUMENT TEXT.
     It maps passages of text into a 384-number meaning space, so the query
     "linear algebra" lands next to a book about "matrices, vector spaces,
     eigenvalues" even if the words differ.

Every file's vector is kept in GPU memory, so comparing a query against tens of
thousands of files is a single matrix multiplication (a few milliseconds).
"""

import logging
import threading
import time

import numpy as np

log = logging.getLogger("orion.ai")

CLIP_MODELS = ["ViT-L/14", "ViT-B/32"]          # preferred first, fallback second
TEXT_MODEL  = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_lock         = threading.Lock()
_torch        = None
_device       = "cpu"
_clip_model   = None
_clip_pre     = None
_clip_tok     = None
_clip_name    = None
_text_model   = None
_tag_names: list[str] = []
_tag_matrix   = None          # torch [T, D]
_load_error   = None


# ═════════════════════════════════════════════════════════════════════════════
#  Model loading
# ═════════════════════════════════════════════════════════════════════════════
def available() -> bool:
    """True if torch can be imported (AI features possible)."""
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def device() -> str:
    return _device


def clip_name() -> str | None:
    return _clip_name


def load_error() -> str | None:
    return _load_error


def is_loaded() -> bool:
    return _clip_model is not None and _text_model is not None


def load_models() -> bool:
    """Load CLIP + text model once. Safe to call repeatedly from any thread."""
    global _torch, _device, _clip_model, _clip_pre, _clip_tok, _clip_name
    global _text_model, _load_error
    with _lock:
        if is_loaded():
            return True
        try:
            import torch
            _torch = torch
            _device = "cuda" if torch.cuda.is_available() else "cpu"

            if _clip_model is None:
                import clip
                # Without an NVIDIA GPU the big ViT-L/14 is ~10x too slow, so prefer ViT-B/32
                order = CLIP_MODELS if _device == "cuda" else list(reversed(CLIP_MODELS))
                for name in order:
                    try:
                        t = time.time()
                        m, pre = clip.load(name, device=_device)
                        m.eval()
                        _clip_model, _clip_pre, _clip_tok, _clip_name = m, pre, clip.tokenize, name
                        log.info("CLIP %s loaded on %s in %.1fs", name, _device, time.time() - t)
                        break
                    except Exception as e:
                        log.warning("CLIP %s failed to load: %s", name, e)
                if _clip_model is None:
                    raise RuntimeError("No CLIP model could be loaded")

            if _text_model is None:
                from sentence_transformers import SentenceTransformer
                t = time.time()
                tm = SentenceTransformer(TEXT_MODEL, device=_device)
                tm.max_seq_length = 512
                if _device == "cuda":
                    tm.half()
                _text_model = tm
                log.info("Text model %s loaded in %.1fs", TEXT_MODEL, time.time() - t)

            _build_tag_matrix()
            _load_error = None
            return True
        except Exception as e:
            _load_error = str(e)
            log.exception("AI model loading failed: %s", e)
            return False


def _build_tag_matrix():
    """Pre-compute CLIP text vectors for every tag (prompt-ensembled)."""
    global _tag_names, _tag_matrix
    from ai_tags import TAGS, PROMPT_TEMPLATES
    torch = _torch
    names = list(TAGS.keys())
    vecs = []
    with torch.inference_mode():
        for tmpl in PROMPT_TEMPLATES:
            toks = _clip_tok([tmpl.format(n) for n in names], truncate=True).to(_device)
            v = _clip_model.encode_text(toks).float()
            vecs.append(v / v.norm(dim=-1, keepdim=True))
        m = torch.stack(vecs).mean(0)
        m = m / m.norm(dim=-1, keepdim=True)
    _tag_names, _tag_matrix = names, m
    log.info("Built tag matrix: %d tags", len(names))


# ═════════════════════════════════════════════════════════════════════════════
#  Encoding
# ═════════════════════════════════════════════════════════════════════════════
def preprocess_image(img):
    """PIL image → CLIP input tensor (CPU). Safe to call from worker threads."""
    return _clip_pre(img)


def encode_image_tensors(tensors: list) -> np.ndarray:
    """Batch of preprocessed image tensors → normalized float16 vectors [N, D]."""
    torch = _torch
    with torch.inference_mode():
        x = torch.stack(tensors).to(_device)
        if _device == "cuda":
            x = x.half()
        v = _clip_model.encode_image(x).float()
        v = v / v.norm(dim=-1, keepdim=True)
    return v.cpu().numpy().astype(np.float16)


def encode_clip_text(query: str) -> np.ndarray:
    """Query text → CLIP vector, averaged over a few phrasings for robustness."""
    torch = _torch
    phrasings = [query, f"a photo of {query}.", f"an image showing {query}."]
    with torch.inference_mode():
        toks = _clip_tok(phrasings, truncate=True).to(_device)
        v = _clip_model.encode_text(toks).float()
        v = v / v.norm(dim=-1, keepdim=True)
        v = v.mean(0)
        v = v / v.norm()
    return v.cpu().numpy().astype(np.float16)


def tags_for_vector(vec: np.ndarray, max_tags: int = 4) -> list[tuple[str, float]]:
    """Zero-shot tagging: which vocabulary tags best describe this image vector?"""
    torch = _torch
    v = torch.from_numpy(vec.astype(np.float32)).to(_device)
    logits = 100.0 * (_tag_matrix @ v)               # CLIP's learned temperature ≈ 100
    probs = logits.softmax(dim=0)
    top = torch.topk(probs, k=min(10, len(_tag_names)))
    out = []
    for p, i in zip(top.values.tolist(), top.indices.tolist()):
        if p >= 0.10 or (not out and p >= 0.04):
            out.append((_tag_names[i], round(p, 3)))
        if len(out) >= max_tags:
            break
    return out


def encode_documents(texts: list[str], batch_size: int = 32) -> np.ndarray:
    v = _text_model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
    return v.astype(np.float16)


def encode_text_query(query: str) -> np.ndarray:
    v = _text_model.encode([BGE_QUERY_PREFIX + query], normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)[0]
    return v.astype(np.float16)


# ═════════════════════════════════════════════════════════════════════════════
#  In-memory vector store (lives on the GPU)
# ═════════════════════════════════════════════════════════════════════════════
class VectorSpace:
    """
    Holds every vector of one kind ('clip' or 'text') as one big matrix.
    Several rows may belong to the same file (e.g. multiple document chunks);
    search returns the best row per file.
    """

    def __init__(self, name: str):
        self.name = name
        self._ids = np.zeros(0, dtype=np.int64)
        self._mat = None                       # torch [N, D] on device
        self._pending_ids: list[np.ndarray] = []
        self._pending_vecs: list[np.ndarray] = []
        self._lock = threading.Lock()

    def __len__(self):
        return len(self._ids) + sum(len(p) for p in self._pending_ids)

    def file_count(self) -> int:
        with self._lock:
            self._flush()
            return int(len(np.unique(self._ids))) if len(self._ids) else 0

    def add(self, file_ids, vecs: np.ndarray):
        if len(file_ids) == 0:
            return
        with self._lock:
            self._pending_ids.append(np.asarray(file_ids, dtype=np.int64))
            self._pending_vecs.append(np.asarray(vecs, dtype=np.float16))

    def clear(self):
        with self._lock:
            self._ids = np.zeros(0, dtype=np.int64)
            self._mat = None
            self._pending_ids.clear()
            self._pending_vecs.clear()

    def _flush(self):
        if not self._pending_ids:
            return
        torch = _torch
        new_ids = np.concatenate(self._pending_ids)
        new_vecs = torch.from_numpy(np.concatenate(self._pending_vecs)).to(_device)
        if _device != "cuda":
            new_vecs = new_vecs.float()
        self._ids = np.concatenate([self._ids, new_ids])
        self._mat = new_vecs if self._mat is None else torch.cat([self._mat, new_vecs])
        self._pending_ids.clear()
        self._pending_vecs.clear()

    def vector_for(self, file_id: int) -> np.ndarray | None:
        with self._lock:
            self._flush()
            rows = np.where(self._ids == file_id)[0]
            if not len(rows):
                return None
            v = self._mat[rows].float().mean(0)
            v = v / v.norm()
            return v.cpu().numpy().astype(np.float16)

    def _multi_rows(self) -> dict[int, np.ndarray]:
        """file_id → row indices, only for files with more than one row (cached)."""
        if getattr(self, "_multi_n", -1) != len(self._ids):
            uniq, inv, counts = np.unique(self._ids, return_inverse=True, return_counts=True)
            multi = {}
            sel = np.where(counts[inv] > 1)[0]
            for row in sel.tolist():
                multi.setdefault(int(self._ids[row]), []).append(row)
            self._multi = {k: np.asarray(v) for k, v in multi.items()}
            self._multi_n = len(self._ids)
        return self._multi

    def search(self, qvec: np.ndarray, k: int = 300, blend: bool = False
               ) -> tuple[list[tuple[int, float]], float, float]:
        """
        Returns ([(file_id, similarity)], mean, std).
        mean/std of similarity over ALL rows lets the caller turn a raw cosine
        score into a "how unusual is this match" z-score.
        blend=True (videos): a file with several rows scores (best + average) / 2,
        so one lucky frame can't make a random video look like a match.
        """
        torch = _torch
        with self._lock:
            self._flush()
            if self._mat is None or len(self._ids) == 0:
                return [], 0.0, 1.0
            q = torch.from_numpy(qvec).to(_device).to(self._mat.dtype)
            sims = (self._mat @ q).float()
            mean = float(sims.mean())
            std = float(sims.std()) if len(sims) > 1 else 1.0
            kk = min(len(sims), k * 4)
            top = torch.topk(sims, kk)
            vals = top.values.cpu().numpy()
            rows = top.indices.cpu().numpy()
            ids = self._ids[rows]
            multi = self._multi_rows() if blend else {}
            all_sims = sims.cpu().numpy() if multi else None
        best: dict[int, float] = {}
        for fid, s in zip(ids.tolist(), vals.tolist()):
            if fid not in best:
                if fid in multi:
                    s = 0.5 * (s + float(all_sims[multi[fid]].mean()))
                best[fid] = s
                if len(best) >= k:
                    break
        out = sorted(best.items(), key=lambda x: -x[1]) if multi else list(best.items())
        return out, mean, max(std, 1e-6)


clip_space = VectorSpace("clip")
text_space = VectorSpace("text")


def space(name: str) -> VectorSpace:
    return clip_space if name == "clip" else text_space


def load_vectors_from_db():
    """Load every stored vector for the current models into GPU memory."""
    from config import get_db
    clip_space.clear()
    text_space.clear()
    conn = get_db()
    try:
        for sp, model in (("clip", _clip_name), ("text", TEXT_MODEL)):
            ids, vecs = [], []
            for row in conn.execute(
                "SELECT file_id, vec FROM ai_vectors WHERE space=? AND model=?", (sp, model)
            ):
                ids.append(row[0])
                vecs.append(np.frombuffer(row[1], dtype=np.float16))
                if len(ids) >= 20000:
                    space(sp).add(ids, np.stack(vecs))
                    ids, vecs = [], []
            if ids:
                space(sp).add(ids, np.stack(vecs))
        log.info("Loaded vectors: clip=%d rows, text=%d rows", len(clip_space), len(text_space))
    finally:
        conn.close()
