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

from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from placeinator.settings import get_settings

# 384-dim, ~130 MB. Changing this value invalidates every stored embedding; any
# row whose embedding_model no longer matches EMBEDDING_MODEL_NAME is stale.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
_DTYPE = np.float32


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    # Loaded lazily and cached: importing fastembed is cheap, but constructing
    # the model reads ~130 MB from disk (downloading it on first run), which
    # must not happen at process import time.
    #
    # cache_dir is pinned to Settings.models_dir explicitly. fastembed's own
    # default is an OS temp directory, which would let a dev checkout and a
    # packaged install resolve the model to two different places -- the same
    # inconsistency the models/ directory removal fixed elsewhere.
    settings = get_settings()
    return TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=str(settings.models_dir))


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
