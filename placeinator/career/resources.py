"""Curated learning resources for taxonomy skill ids (spec §4's "Suggested
learning direction/resources").

Deterministic and hand-verified: every URL in resources.json was confirmed
real (fetched and inspected) before being added, never recalled from
training data -- the same discipline already applied to robots.txt
behavior, pylatexenc's API, and every external claim this project has made.

Partial coverage is the expected, supported state -- the same honest gap
placeinator/skills/taxonomy.json itself carries (26 curated resources for
133 skills; new skill ids are added without a matching resource entry as a
matter of course). A skill with no entry here simply has none; get()
returning None is not an error case to work around, it's the correct
answer for "no verified resource exists yet".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_RESOURCES_PATH = Path(__file__).parents[1] / "skills" / "resources.json"


@dataclass(frozen=True)
class Resource:
    title: str
    url: str


class ResourceLibrary:
    def __init__(self, entries: dict[str, Resource]) -> None:
        self._entries = entries

    def get(self, skill_id: str) -> Resource | None:
        return self._entries.get(skill_id)


def _load_resources(path: Path) -> dict[str, Resource]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        skill_id: Resource(title=entry["title"], url=entry["url"])
        for skill_id, entry in data["resources"].items()
    }


@lru_cache(maxsize=1)
def get_resource_library() -> ResourceLibrary:
    return ResourceLibrary(_load_resources(_RESOURCES_PATH))
