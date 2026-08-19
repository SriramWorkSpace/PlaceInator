"""Splits resume and job-description text into typed, scorable units.

A chunk/requirement is deliberately "dumb": a kind, a section label, the text,
and (for resumes) the character span it came from. Section detection here is
heading-based, not semantic -- it only needs to be right often enough that the
matching engine has something typed to score, and the LaTeX tailoring engine
depends on the character spans being exact (see placeinator.latex).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from placeinator.db.enums import ChunkKind, RequirementKind
from placeinator.skills.taxonomy import get_taxonomy

# Section headings recognised in free-text and LaTeX resumes alike, mapped to
# the chunk kind their content should default to. Longest/most specific key
# checked first via the ordering below.
_SECTION_HEADINGS: dict[str, ChunkKind] = {
    "technical skills": ChunkKind.SKILL,
    "skills": ChunkKind.SKILL,
    "programming languages": ChunkKind.SKILL,
    "projects": ChunkKind.PROJECT_BULLET,
    "personal projects": ChunkKind.PROJECT_BULLET,
    "experience": ChunkKind.EXPERIENCE_BULLET,
    "work experience": ChunkKind.EXPERIENCE_BULLET,
    "professional experience": ChunkKind.EXPERIENCE_BULLET,
    "education": ChunkKind.EDUCATION,
    "certifications": ChunkKind.CERTIFICATION,
    "achievements": ChunkKind.ACHIEVEMENT,
    "awards": ChunkKind.ACHIEVEMENT,
    "summary": ChunkKind.SUMMARY,
    "objective": ChunkKind.SUMMARY,
}

# A line is a heading if it is short, has no terminal punctuation, and matches
# a known section name -- deliberately conservative so body text is never
# misread as a heading. Matches plain text ("Skills") and Markdown ("## Skills").
_HEADING_RE = re.compile(
    r"^\s*#{0,3}\s*([A-Za-z][A-Za-z /&]{2,40})\s*:?\s*$"
)

# A minimal LaTeX section-heading match: \section{Skills}, \section*{Skills},
# \subsection{...}. This is a heuristic for the matching engine's plain-text
# chunker only -- real LaTeX-structure-aware parsing (with byte-exact node
# spans for splicing) is placeinator.latex's job in M3, not this module.
_LATEX_HEADING_RE = re.compile(r"^\s*\\(?:sub)*section\*?\{([^}]{2,60})\}")

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•▪◦]|\\item\b)\s*")

# Lines that are pure LaTeX structure and carry no resume content of their
# own -- skipped rather than chunked as a bogus bullet.
_LATEX_NOISE_RE = re.compile(
    r"^\s*(?:\\documentclass|\\usepackage|\\begin\{|\\end\{|\\newcommand|"
    r"\\renewcommand|\\setlength|\\pagestyle|\\definecolor|%)"
)


@dataclass(frozen=True)
class TextChunk:
    kind: ChunkKind
    section: str | None
    text: str
    span_start: int
    span_end: int
    skill_ids: frozenset[str]


@dataclass(frozen=True)
class RequirementLine:
    kind: RequirementKind
    text: str
    skill_ids: frozenset[str]


def _match_heading(line: str) -> ChunkKind | None:
    m = _LATEX_HEADING_RE.match(line) or _HEADING_RE.match(line)
    if not m:
        return None
    return _SECTION_HEADINGS.get(m.group(1).strip().lower())


def chunk_resume_text(source_text: str) -> list[TextChunk]:
    """Split plain-text resume content into typed chunks with source spans.

    One chunk per non-empty line within a recognised section; the span is the
    exact character range of that line in ``source_text``, which is what lets
    placeinator.latex splice by offset rather than by regenerating content.
    Lines before the first recognised heading are treated as SUMMARY, since
    that is almost always the header/objective block.
    """
    taxonomy = get_taxonomy()
    chunks: list[TextChunk] = []
    current_kind = ChunkKind.SUMMARY
    current_section: str | None = None

    offset = 0
    for raw_line in source_text.splitlines(keepends=True):
        line = raw_line.rstrip("\n\r")
        start = offset
        offset += len(raw_line)

        stripped = line.strip()
        if not stripped or _LATEX_NOISE_RE.match(line):
            continue

        heading_kind = _match_heading(line)
        if heading_kind is not None:
            current_kind = heading_kind
            current_section = stripped.rstrip(":").strip()
            continue

        text = _BULLET_PREFIX_RE.sub("", stripped).strip()
        if not text:
            continue

        chunks.append(
            TextChunk(
                kind=current_kind,
                section=current_section,
                text=text,
                span_start=start,
                span_end=start + len(raw_line.rstrip("\n\r")),
                skill_ids=frozenset(taxonomy.extract(text)),
            )
        )
    return chunks


# Phrases that mark a JD line as a hard requirement rather than merely
# preferred/nice-to-have. Checked before the generic requirement patterns.
_PREFERRED_MARKERS = ("preferred", "nice to have", "plus", "bonus", "good to have")
_REQUIREMENT_MARKERS = ("required", "must have", "must:", "requirements")
_RESPONSIBILITY_MARKERS = ("responsibilities", "you will", "role:", "what you'll do")
_QUALIFICATION_MARKERS = ("qualifications", "education:", "degree", "years of experience")


def _classify_jd_line(line: str) -> RequirementKind:
    lowered = line.lower()
    if any(marker in lowered for marker in _PREFERRED_MARKERS):
        return RequirementKind.PREFERRED_SKILL
    if any(marker in lowered for marker in _QUALIFICATION_MARKERS):
        return RequirementKind.QUALIFICATION
    if any(marker in lowered for marker in _RESPONSIBILITY_MARKERS):
        return RequirementKind.RESPONSIBILITY
    if any(marker in lowered for marker in _REQUIREMENT_MARKERS):
        return RequirementKind.REQUIRED_SKILL
    return RequirementKind.RESPONSIBILITY


def chunk_job_description(description: str) -> list[RequirementLine]:
    """Split a job description into typed requirement lines.

    Classification is keyword-based (see ADR 0002 -- deterministic only, no
    LLM): a line's kind follows from markers like "preferred" or "must have"
    on that line, defaulting to RESPONSIBILITY when nothing else matches. This
    trades recall for predictability, which matters more when the result
    drives a hard filter than when it drives a ranking nudge.
    """
    taxonomy = get_taxonomy()
    lines: list[RequirementLine] = []
    for raw_line in description.splitlines():
        text = _BULLET_PREFIX_RE.sub("", raw_line.strip()).strip()
        if not text or _HEADING_RE.match(raw_line):
            continue
        lines.append(
            RequirementLine(
                kind=_classify_jd_line(text),
                text=text,
                skill_ids=frozenset(taxonomy.extract(text)),
            )
        )
    return lines
