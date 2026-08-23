"""The one place that encodes, decodes, and computes embeddings.

Encoding contract (see ORM comments on ResumeChunk.embedding /
JobRequirement.embedding): float32, little-endian, C-contiguous, L2-normalized.
Every write also stamps ``embedding_model`` / ``embedding_dim`` next to the
bytes, so a model change leaves stale rows detectable and re-embeddable instead
of silently deserialising into meaningless numbers.

Uses fastembed (ONNX Runtime) rather than sentence-transformers -- see
ADR 0005. PyTorch must never enter this module's dependency chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from placeinator.settings import get_settings

# 384-dim, ~64 MB (the quantized ONNX weights fastembed actually downloads --
# measured directly off disk, not the ~130 MB figure ADR 0005 estimated
# before this was checked). Changing EMBEDDING_MODEL_NAME invalidates every
# stored embedding; any row whose embedding_model no longer matches it is
# stale.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
_DTYPE = np.float32

# Measured directly (model_optimized.onnx under Settings.models_dir), not
# assumed from ADR 0005's "~130 MB" estimate -- that figure was double the
# real quantized weights' size. Used only to estimate download progress (see
# get_model_download_status); approximate by nature, not a correctness
# dependency of anything else in this module.
_APPROX_MODEL_SIZE_BYTES = 64 * 1024 * 1024


class ModelDownloadError(RuntimeError):
    """The embedding model couldn't be downloaded or loaded -- almost always
    a network failure on first run, since every run after that reads from
    the local cache. Wraps whatever fastembed/huggingface_hub/onnxruntime
    happens to raise into one clear, catchable type, so callers (and the
    global FastAPI exception handler in placeinator/app.py) don't need to
    know those libraries' own exception hierarchies."""


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    # Loaded lazily and cached: importing fastembed is cheap, but constructing
    # the model reads ~64 MB from disk (downloading it on first run), which
    # must not happen at process import time.
    #
    # cache_dir is pinned to Settings.models_dir explicitly. fastembed's own
    # default is an OS temp directory, which would let a dev checkout and a
    # packaged install resolve the model to two different places -- the same
    # inconsistency the models/ directory removal fixed elsewhere.
    settings = get_settings()
    try:
        return TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=str(settings.models_dir))
    except Exception as exc:
        raise ModelDownloadError(
            f"could not load the embedding model ({EMBEDDING_MODEL_NAME}): {exc}"
        ) from exc


def warm_up_model() -> None:
    """Public entry point for triggering the model load/download without
    needing anything embedded yet -- placeinator/app.py's startup warm-up
    calls this rather than reaching into the private, lazily-cached
    _model() directly."""
    _model()


@dataclass(frozen=True)
class ModelDownloadStatus:
    ready: bool
    downloading: bool
    # 0..1. Meaningless once ready (always 1.0); approximate while
    # downloading, since it's based on bytes written to disk, not the
    # ONNX session initialization that follows the download itself.
    approx_progress: float


def get_model_download_status() -> ModelDownloadStatus:
    """Polls actual bytes on disk under Settings.models_dir against the
    known approximate model size, rather than hooking huggingface_hub's
    internal tqdm_class mechanism for byte-exact progress -- that would mean
    depending on kwargs correctly forwarding through three layers of
    fastembed/huggingface_hub internals (TextEmbedding.__init__ ->
    download_model -> download_files_from_huggingface -> snapshot_download),
    none of which is a documented, stable contract. Slower to update, but
    doesn't depend on anything that could silently break on a library
    upgrade.

    ``cache_info().currsize`` alone can't answer "ready": it only reflects
    whether *this process* has called ``_model()``, not whether a prior run
    already wrote the model to disk. A plain restart would otherwise report
    "downloading" for however long it takes the background warm-up
    (placeinator/app.py's lifespan) to catch up -- misleading, since loading
    an already-cached model from disk is fast and nothing like a fresh
    network download.
    """
    if _model.cache_info().currsize > 0:
        return ModelDownloadStatus(ready=True, downloading=False, approx_progress=1.0)

    settings = get_settings()
    if not settings.models_dir.exists():
        return ModelDownloadStatus(ready=False, downloading=False, approx_progress=0.0)

    total_bytes = sum(f.stat().st_size for f in settings.models_dir.rglob("*") if f.is_file())
    if total_bytes == 0:
        return ModelDownloadStatus(ready=False, downloading=False, approx_progress=0.0)

    progress = min(total_bytes / _APPROX_MODEL_SIZE_BYTES, 1.0)
    if progress >= 0.98:
        # Close enough to the full known size that this is almost certainly
        # a complete download from a prior run, not one in progress.
        return ModelDownloadStatus(ready=True, downloading=False, approx_progress=1.0)

    return ModelDownloadStatus(ready=False, downloading=True, approx_progress=progress)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of strings. Returns an (n, EMBEDDING_DIM) float32 array."""
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=_DTYPE)

    vectors = np.array(list(_model().embed(texts)), dtype=_DTYPE)
    return _l2_normalize(vectors)


def embed_text(text: str) -> np.ndarray:
    """Embed a single string. Returns a (EMBEDDING_DIM,) float32 vector."""
    return embed_texts([text])[0]


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    # A zero vector (empty/whitespace-only input) would divide by zero; leave
    # it as the zero vector rather than producing NaN.
    norms[norms == 0] = 1.0
    return vectors / norms


def encode_vector(vector: np.ndarray) -> bytes:
    """Serialize a vector for storage. Pair with decode_vector."""
    return np.ascontiguousarray(vector, dtype=_DTYPE).tobytes()


def decode_vector(data: bytes) -> np.ndarray:
    """Deserialize a vector stored by encode_vector."""
    return np.frombuffer(data, dtype=_DTYPE)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors, assumed already L2-normalized."""
    return float(np.dot(a, b))


def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity between two batches of normalized vectors.

    ``a`` is (m, d), ``b`` is (n, d); returns (m, n). This is the single NumPy
    matmul the latency budget in docs/architecture.md depends on -- ranking 500
    cached jobs must stay a matrix multiply, never a Python loop.
    """
    return a @ b.T
