"""Skill taxonomy is the semantic backbone of matching with no LLM in the loop
(ADR 0002) -- these pin its contract, not just its current content."""

from __future__ import annotations

import pytest

from placeinator.skills.taxonomy import Skill, Taxonomy, get_taxonomy


def test_taxonomy_loads_and_has_real_coverage():
    taxonomy = get_taxonomy()
    assert len(taxonomy) > 50


def test_common_aliases_normalize_to_the_same_canonical_id():
    taxonomy = get_taxonomy()
    for alias in ("javascript", "JS", "  js  ", "ECMAScript"):
        assert taxonomy.normalize(alias) == "javascript"


def test_unrecognised_surface_form_returns_none():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("cobol-77-enterprise-edition") is None


def test_extract_prefers_the_longer_alias():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("Built services with Spring Boot and deployed to AWS")
    assert "spring-boot" in found
    # "spring" alone must not also fire as a separate id once "spring boot"
    # (mapping to the same canonical id) has already matched.
    assert "spring" not in found
    assert "aws" in found


def test_extract_is_case_and_punctuation_insensitive():
    taxonomy = get_taxonomy()
    assert "nodejs" in taxonomy.extract("Experience with NODE.JS and Express")


def test_duplicate_skill_id_is_rejected():
    with pytest.raises(ValueError, match="duplicate skill id"):
        Taxonomy(
            [
                Skill(id="x", category="language", aliases=("x", "xx")),
                Skill(id="x", category="language", aliases=("xxx",)),
            ]
        )


def test_conflicting_alias_ownership_is_rejected():
    with pytest.raises(ValueError, match="claimed by both"):
        Taxonomy(
            [
                Skill(id="a", category="language", aliases=("shared",)),
                Skill(id="b", category="language", aliases=("shared",)),
            ]
        )
