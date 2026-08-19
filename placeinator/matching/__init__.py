"""The neural matching engine -- the piece everything else depends on.

Scores a resume against a job description across five components (overall,
skills, projects, experience, role), each in [0,1] and each stored with the
evidence that produced it. The weighted total is the semantic score.

Deterministic and explainable by construction: with no LLM in the pipeline there
is no black box to hide behind. Every score writes a ``MatchResult.explanation``
recording each component's value, weight, and top contributing chunk pairs --
one record that powers notification reasons, resume recommendation, and the
tailoring change log alike.

``vectors.py`` is the *only* place that encodes or decodes embeddings (float32
little-endian, C-contiguous, L2-normalized) and the only writer of
``embedding_model`` / ``embedding_dim``.

Entry points: ``embed_chunks``, ``score_match``.
"""
