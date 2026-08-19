"""Loads and queries taxonomy.json.

With no LLM in the pipeline (ADR 0002), this alias map is the semantic backbone
of skill matching, gap analysis, and job filtering -- so it is loaded once,
validated at load time, and exposed through a single normalizer rather than
scattered ad hoc string comparisons.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_TAXONOMY_PATH = Path(__file__).parent / "taxonomy.json"

# Collapses whitespace/punctuation variance ("Node.js", "node js", "NODE-JS")
# down to one comparable form before alias lookup.
_NORMALIZE_RE = re.compile(r"[^a-z0-9+#.]+")


def _normalize_surface_form(text: str) -> str:
    return _NORMALIZE_RE.sub(" ", text.lower()).strip()


@dataclass(frozen=True)
class Skill:
    id: str
    category: str
    aliases: tuple[str, ...]


class Taxonomy:
    """An alias -> canonical-id lookup, longest-alias-first for greedy matching."""

    def __init__(self, skills: list[Skill]) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            if skill.id in self._skills:
                raise ValueError(f"duplicate skill id in taxonomy: {skill.id!r}")
            self._skills[skill.id] = skill

        self._alias_to_id: dict[str, str] = {}
        for skill in skills:
            for alias in skill.aliases:
                normalized = _normalize_surface_form(alias)
                existing = self._alias_to_id.get(normalized)
                if existing and existing != skill.id:
                    raise ValueError(
                        f"alias {alias!r} claimed by both {existing!r} and {skill.id!r}"
                    )
                self._alias_to_id[normalized] = skill.id

        # Longest alias first, so "spring boot" matches before "spring" inside it.
        self._aliases_by_length = sorted(
            self._alias_to_id.keys(), key=len, reverse=True
        )

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def normalize(self, surface_form: str) -> str | None:
        """Exact-alias lookup. Returns the canonical id, or None if unrecognised."""
        return self._alias_to_id.get(_normalize_surface_form(surface_form))

    def extract(self, text: str) -> set[str]:
        """Find every taxonomy skill mentioned in free text.

        Greedy longest-match over whitespace-normalized text, so multi-word
        aliases ("spring boot") win over a shorter alias they contain
        ("spring"). This is intentionally simple string matching, not NLP --
        precision matters more than recall for a signal that drives hard
        filters downstream.
        """
        haystack = f" {_normalize_surface_form(text)} "
        found: set[str] = set()
        for alias in self._aliases_by_length:
            skill_id = self._alias_to_id[alias]
            if skill_id in found:
                continue
            if f" {alias} " in haystack:
                found.add(skill_id)
        return found


def _load_skills(path: Path) -> list[Skill]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Skill(id=entry["id"], category=entry["category"], aliases=tuple(entry["aliases"]))
        for entry in data["skills"]
    ]


@lru_cache(maxsize=1)
def get_taxonomy() -> Taxonomy:
    return Taxonomy(_load_skills(_TAXONOMY_PATH))
