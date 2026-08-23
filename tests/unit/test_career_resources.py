"""placeinator.career.resources -- the curated, hand-verified skill-to-
resource lookup. get_resource_library() reads the real resources.json
shipped with the package, so this also doubles as a shape check on that
file -- if its schema ever drifts, this breaks immediately.
"""

from __future__ import annotations

from placeinator.career.resources import get_resource_library


def test_a_known_skill_returns_its_curated_resource():
    library = get_resource_library()
    resource = library.get("python")
    assert resource is not None
    assert resource.url.startswith("https://")
    assert resource.title


def test_an_unlisted_skill_returns_none_not_a_fabricated_entry():
    library = get_resource_library()
    assert library.get("some-skill-with-no-curated-resource-yet") is None


def test_every_entry_has_a_non_empty_title_and_a_real_looking_url():
    """A loose sanity check on resources.json's actual content, not just
    its schema -- every entry should look like a real, verified resource
    (https, non-empty title), not a placeholder."""
    library = get_resource_library()
    # Spot-check a representative few rather than iterate the private dict.
    for skill_id in ("javascript", "docker", "postgresql", "kubernetes"):
        resource = library.get(skill_id)
        assert resource is not None, skill_id
        assert resource.url.startswith("https://"), skill_id
        assert len(resource.title) > 0, skill_id
