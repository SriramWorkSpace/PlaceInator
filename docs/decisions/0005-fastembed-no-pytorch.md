# ADR 0005 — fastembed + ONNX Runtime, never PyTorch

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

The matching engine ([ADR 0002](./0002-deterministic-no-llm.md)) needs sentence
embeddings computed locally, on CPU, inside a desktop app with a strict footprint
budget.

The obvious choice, `sentence-transformers`, depends on PyTorch. PyTorch adds roughly
2 GB to the installed size and seconds to process import time — costs that dominate
this application's entire budget, for a model of only ~130 MB.

## Decision

Use **`fastembed`** (ONNX Runtime) with **`BAAI/bge-small-en-v1.5`** (384-dim).

- Optional cross-encoder reranking runs over the top ~25 candidates only, never the
  full set.
- Vector search is a single NumPy matmul over precomputed vectors. At this scale
  (hundreds to low thousands of jobs) a vector database would be overhead, not
  optimization.
- `placeinator/matching/vectors.py` is the **only** place that encodes or decodes
  embeddings: float32 little-endian, C-contiguous, L2-normalized.

**PyTorch must never be added to the dependency tree.**

## Verification

This was the project's largest technical assumption, so it was resolved against the
real package index before any code was written against it. On Python 3.13:

```
fastembed 0.8.0
  onnxruntime 1.29.0, numpy 2.5.2, tokenizers 0.23.1,
  huggingface_hub 1.28.0, py_rust_stemmers 0.1.8, mmh3 5.2.1
```

All wheels. No source builds. **No PyTorch anywhere in the tree.**

## Consequences

- Meets the latency budget: embedding a ~40-chunk resume in under 200 ms, ranking 500
  cached jobs in under 50 ms.
- Bundle stays in the low hundreds of MB rather than multiple GB.
- Models are downloaded on first run into `Settings.models_dir` (the per-user data
  directory), never into the repository — so a dev checkout and a packaged install
  resolve them identically. M6 owns the download-with-progress UX.
- **Embeddings must carry provenance.** Changing the model would leave stored vectors
  deserialising successfully into meaningless numbers, silently degrading match quality
  with no error. `ResumeChunk` and `JobRequirement` therefore store `embedding_model`
  and `embedding_dim` alongside the bytes, making stale rows detectable and
  re-embeddable.
- onnxruntime ships native libraries, which makes it the likeliest PyInstaller
  packaging problem. Proving the packaged build is scheduled for M0/M1, not M6.
