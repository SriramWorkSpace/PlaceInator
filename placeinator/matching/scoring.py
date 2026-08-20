"""Component scoring and the weighted-sum match score.

Every score is computed from named, evidence-bearing components (see
ComponentScore) rather than a single opaque number, because the explanation
those components form powers three separate spec features from one record:
notification reasons, resume recommendation, and the tailoring change log
(see docs/architecture.md#the-matching-engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from placeinator.db.enums import ChunkKind, RequirementKind
from placeinator.matching.chunking import RequirementLine, TextChunk
from placeinator.matching.vectors import EMBEDDING_DIM, cosine_similarity_matrix, embed_texts

# Tunable without a code change once config/scoring.toml lands in a later
# milestone; centralized here in the meantime so nothing hardcodes a weight
# inline.
COMPONENT_WEIGHTS: dict[str, float] = {
    "overall": 0.25,
    "skills": 0.30,
    "projects": 0.20,
    "experience": 0.15,
    "role": 0.10,
}

SCORING_VERSION = "1"


def _clamp_unit(value: float) -> float:
    """Every component value is contractually in [0, 1] -- MatchResult.explanation
    is user-facing and the weighted sum assumes it.

    Cosine similarity of two *near-identical* float32 vectors can land a few
    ULPs above 1.0 (e.g. 1.0000001192092896 for an exact role-title match),
    and whether it does depends on the CPU's vector instructions -- it stayed
    under 1.0 on the dev machine and crossed it on CI's runner. Clamping both
    ends, rather than only the lower one, makes the bound hold on every
    machine instead of most of them.
    """
    return min(1.0, max(0.0, value))

_TOP_K_EVIDENCE = 3


@dataclass(frozen=True)
class Evidence:
    resume_text: str
    requirement_text: str
    similarity: float


@dataclass(frozen=True)
class ComponentScore:
    value: float
    weight: float
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "weight": self.weight,
            "evidence": [
                {
                    "resume_text": e.resume_text,
                    "requirement_text": e.requirement_text,
                    "similarity": e.similarity,
                }
                for e in self.evidence
            ],
        }


@dataclass(frozen=True)
class MatchExplanation:
    components: dict[str, ComponentScore]
    semantic_score: float

    def to_dict(self) -> dict:
        return {name: c.to_dict() for name, c in self.components.items()}

    @property
    def personalized_score(self) -> float:
        """The weighted sum. Preference/filter signals are folded in by the
        caller (placeinator.jobs) on top of this -- this module only ever
        knows about resume/JD content, never about user preferences."""
        return sum(c.value * c.weight for c in self.components.values())


def _mean_pool(vectors: np.ndarray) -> np.ndarray:
    if len(vectors) == 0:
        return np.zeros(vectors.shape[-1] if vectors.ndim > 1 else 384, dtype=np.float32)
    pooled = vectors.mean(axis=0)
    norm = np.linalg.norm(pooled)
    return pooled / norm if norm > 0 else pooled


def _score_overall(resume_vectors: np.ndarray, jd_vectors: np.ndarray) -> ComponentScore:
    resume_mean = _mean_pool(resume_vectors)
    jd_mean = _mean_pool(jd_vectors)
    has_content = resume_vectors.size and jd_vectors.size
    similarity = float(np.dot(resume_mean, jd_mean)) if has_content else 0.0
    return ComponentScore(value=_clamp_unit(similarity), weight=COMPONENT_WEIGHTS["overall"])


def _score_skills(chunks: list[TextChunk], requirements: list[RequirementLine]) -> ComponentScore:
    resume_skills: set[str] = set()
    for chunk in chunks:
        resume_skills |= chunk.skill_ids

    required = [r for r in requirements if r.kind == RequirementKind.REQUIRED_SKILL]
    preferred = [r for r in requirements if r.kind == RequirementKind.PREFERRED_SKILL]
    jd_skills: set[str] = set()
    for r in required + preferred:
        jd_skills |= r.skill_ids

    if not jd_skills:
        # No skills detected in the JD: neither confirm nor penalize -- treat
        # as neutral rather than a false 0 or false 1.
        return ComponentScore(value=0.5, weight=COMPONENT_WEIGHTS["skills"])

    matched = resume_skills & jd_skills
    value = len(matched) / len(jd_skills)

    evidence = [
        Evidence(resume_text=skill_id, requirement_text=skill_id, similarity=1.0)
        for skill_id in sorted(matched)[:_TOP_K_EVIDENCE]
    ]
    return ComponentScore(value=value, weight=COMPONENT_WEIGHTS["skills"], evidence=evidence)


def _score_bullets_against_requirements(
    bullets: list[TextChunk],
    bullet_vectors: np.ndarray,
    requirements: list[RequirementLine],
    requirement_vectors: np.ndarray,
    weight: float,
) -> ComponentScore:
    """Shared shape for `projects` and `experience`: for each JD requirement,
    the best-matching bullet; the component value is the mean of those bests.
    """
    if not bullets or not requirements:
        return ComponentScore(value=0.0, weight=weight)

    sims = cosine_similarity_matrix(requirement_vectors, bullet_vectors)  # (n_req, n_bullets)
    best_bullet_idx = sims.argmax(axis=1)
    best_scores = sims[np.arange(len(requirements)), best_bullet_idx]

    value = _clamp_unit(float(best_scores.mean()))

    ranked = sorted(
        zip(requirements, best_bullet_idx, best_scores, strict=True),
        key=lambda t: t[2],
        reverse=True,
    )
    evidence = [
        Evidence(
            resume_text=bullets[int(bullet_idx)].text,
            requirement_text=req.text,
            similarity=_clamp_unit(float(sim)),
        )
        for req, bullet_idx, sim in ranked[:_TOP_K_EVIDENCE]
    ]
    return ComponentScore(value=value, weight=weight, evidence=evidence)


def _score_role(resume_target_role: str | None, jd_title: str) -> ComponentScore:
    if not resume_target_role or not jd_title:
        return ComponentScore(value=0.5, weight=COMPONENT_WEIGHTS["role"])
    vectors = embed_texts([resume_target_role, jd_title])
    similarity = float(np.dot(vectors[0], vectors[1]))
    return ComponentScore(value=_clamp_unit(similarity), weight=COMPONENT_WEIGHTS["role"])


def _rows_at(vectors: np.ndarray, indices: list[int]) -> np.ndarray:
    if not indices:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    return vectors[indices]


def score_match(
    *,
    resume_chunks: list[TextChunk],
    requirements: list[RequirementLine],
    resume_target_role: str | None,
    jd_title: str,
    resume_vectors: np.ndarray | None = None,
    requirement_vectors: np.ndarray | None = None,
) -> MatchExplanation:
    """Score one resume against one job description.

    Embedding is the expensive part; the similarity math is not. Two things
    keep it to a minimum:

    * ``resume_vectors`` / ``requirement_vectors`` may be supplied by the
      caller -- ``placeinator.matching.service`` passes the vectors already
      persisted on ``ResumeChunk.embedding`` / ``JobRequirement.embedding``,
      so ranking a whole job corpus embeds nothing at all. Omit them and this
      function embeds the text itself, so it stays usable on its own.
    * The project/experience/responsibility subsets are *indexed out* of those
      arrays rather than embedded again. Embedding is deterministic for the
      same text and model, so re-embedding a subset produced identical numbers
      at triple the cost.
    """
    if resume_vectors is None:
        resume_vectors = embed_texts([c.text for c in resume_chunks])
    if requirement_vectors is None:
        requirement_vectors = embed_texts([r.text for r in requirements])

    if len(resume_vectors) != len(resume_chunks) or len(requirement_vectors) != len(requirements):
        raise ValueError(
            "supplied vectors must align 1:1 with their chunks/requirements "
            f"(got {len(resume_vectors)}/{len(resume_chunks)} resume, "
            f"{len(requirement_vectors)}/{len(requirements)} requirement)"
        )

    project_idx = [i for i, c in enumerate(resume_chunks) if c.kind == ChunkKind.PROJECT_BULLET]
    experience_idx = [
        i for i, c in enumerate(resume_chunks) if c.kind == ChunkKind.EXPERIENCE_BULLET
    ]
    responsibility_idx = [
        i for i, r in enumerate(requirements) if r.kind == RequirementKind.RESPONSIBILITY
    ]

    responsibilities = [requirements[i] for i in responsibility_idx]
    responsibility_vectors = _rows_at(requirement_vectors, responsibility_idx)

    components = {
        "overall": _score_overall(resume_vectors, requirement_vectors),
        "skills": _score_skills(resume_chunks, requirements),
        "projects": _score_bullets_against_requirements(
            [resume_chunks[i] for i in project_idx],
            _rows_at(resume_vectors, project_idx),
            responsibilities, responsibility_vectors,
            COMPONENT_WEIGHTS["projects"],
        ),
        "experience": _score_bullets_against_requirements(
            [resume_chunks[i] for i in experience_idx],
            _rows_at(resume_vectors, experience_idx),
            responsibilities, responsibility_vectors,
            COMPONENT_WEIGHTS["experience"],
        ),
        "role": _score_role(resume_target_role, jd_title),
    }

    semantic_score = components["overall"].value
    return MatchExplanation(components=components, semantic_score=semantic_score)
