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
from placeinator.matching.vectors import cosine_similarity_matrix, embed_texts

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
    return ComponentScore(value=max(0.0, similarity), weight=COMPONENT_WEIGHTS["overall"])


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

    value = float(np.clip(best_scores.mean(), 0.0, 1.0))

    ranked = sorted(
        zip(requirements, best_bullet_idx, best_scores, strict=True),
        key=lambda t: t[2],
        reverse=True,
    )
    evidence = [
        Evidence(
            resume_text=bullets[int(bullet_idx)].text,
            requirement_text=req.text,
            similarity=float(sim),
        )
        for req, bullet_idx, sim in ranked[:_TOP_K_EVIDENCE]
    ]
    return ComponentScore(value=value, weight=weight, evidence=evidence)


def _score_role(resume_target_role: str | None, jd_title: str) -> ComponentScore:
    if not resume_target_role or not jd_title:
        return ComponentScore(value=0.5, weight=COMPONENT_WEIGHTS["role"])
    vectors = embed_texts([resume_target_role, jd_title])
    similarity = float(np.dot(vectors[0], vectors[1]))
    return ComponentScore(value=max(0.0, similarity), weight=COMPONENT_WEIGHTS["role"])


def score_match(
    *,
    resume_chunks: list[TextChunk],
    requirements: list[RequirementLine],
    resume_target_role: str | None,
    jd_title: str,
) -> MatchExplanation:
    """Score one resume against one job description.

    Embeds every chunk and requirement exactly once, then reuses those vectors
    across all five components -- the expensive part is the embedding calls,
    not the similarity math.
    """
    resume_texts = [c.text for c in resume_chunks]
    requirement_texts = [r.text for r in requirements]

    resume_vectors = embed_texts(resume_texts)
    requirement_vectors = embed_texts(requirement_texts)

    project_bullets = [c for c in resume_chunks if c.kind == ChunkKind.PROJECT_BULLET]
    project_vectors = embed_texts([c.text for c in project_bullets])

    experience_bullets = [c for c in resume_chunks if c.kind == ChunkKind.EXPERIENCE_BULLET]
    experience_vectors = embed_texts([c.text for c in experience_bullets])

    responsibilities = [r for r in requirements if r.kind == RequirementKind.RESPONSIBILITY]
    responsibility_vectors = embed_texts([r.text for r in responsibilities])

    components = {
        "overall": _score_overall(resume_vectors, requirement_vectors),
        "skills": _score_skills(resume_chunks, requirements),
        "projects": _score_bullets_against_requirements(
            project_bullets, project_vectors, responsibilities, responsibility_vectors,
            COMPONENT_WEIGHTS["projects"],
        ),
        "experience": _score_bullets_against_requirements(
            experience_bullets, experience_vectors, responsibilities, responsibility_vectors,
            COMPONENT_WEIGHTS["experience"],
        ),
        "role": _score_role(resume_target_role, jd_title),
    }

    semantic_score = components["overall"].value
    return MatchExplanation(components=components, semantic_score=semantic_score)
