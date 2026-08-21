"""Byte-exact LaTeX structure parsing for JD-based resume tailoring
(specification section 5).

``parse_latex`` partitions ``Resume.source_text`` into a flat, ordered list of
non-overlapping spans that together cover the whole string: preamble, header,
and section/bullet-list wrapper text are **fixed** (never reordered); each
top-level ``\\section{...}`` is a movable unit; each ``\\item`` within a
directly-nested ``itemize``/``enumerate`` is a movable unit within its own
list. Concatenating every span in its *original* order therefore reproduces
the source byte-for-byte by construction -- that identity is the round-trip
acceptance gate this module exists to make trivially true rather than
something to separately get right.

This is deliberately **not** a tree walk. Two things ruled that out, both
confirmed against the real library rather than assumed:

* pylatexenc's node tree doesn't nest a section's body under its heading --
  ``\\section{Skills}`` is one flat macro node, and everything that follows it
  is a *sibling* in the parent's node list, not a child.
* A ``\\newcommand``-defined macro -- the shape most real resume templates
  actually use, e.g. ``\\resumeItem{...}`` -- doesn't get its argument
  captured as a child node at all. pylatexenc only associates arguments for
  macros it has a signature for, so an unrecognized macro parses as a
  zero-arg macro with its following ``{...}`` group left as an unrelated
  sibling.

So unit boundaries are computed directly from cut points -- section-macro and
item-macro *positions* -- never from how pylatexenc chose to nest anything.
A section or list environment that uses non-standard bullet macros still
round-trips correctly; it just isn't split any finer than "one movable
block", which is an honest scope limit (see this package's ``__init__``),
not a bug.
"""

from __future__ import annotations

from dataclasses import dataclass

from pylatexenc.latexwalker import (
    LatexEnvironmentNode,
    LatexMacroNode,
    LatexNode,
    LatexWalker,
    LatexWalkerParseError,
)

from placeinator.matching.chunking import LATEX_HEADING_RE

_LIST_ENVIRONMENTS = frozenset({"itemize", "enumerate"})
_SECTION_MACRO = "section"
_DOCUMENT_ENV = "document"


class LatexParseError(ValueError):
    """The source doesn't parse as LaTeX, or has no
    ``\\begin{document}...\\end{document}`` to tailor. Mirrors
    ``UnsupportedFormatError``/``EmptyDocumentError`` in
    ``placeinator.resumes.parsing``."""


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"end {self.end} before start {self.start}")


@dataclass(frozen=True)
class Bullet:
    """One ``\\item``, from its marker through (but not including) the next
    ``\\item`` or the end of its enclosing list. Never includes the
    ``\\begin``/``\\end`` wrapper -- that belongs to the containing
    ``BulletGroup`` instead, so it always survives a reorder untouched."""

    span: Span


@dataclass(frozen=True)
class BulletGroup:
    """One ``itemize``/``enumerate`` environment. Reordering only ever
    happens *within* one group -- a bullet from one job entry never moves
    into another's list, since the two are usually unrelated content."""

    open_span: Span  # "\begin{itemize}" plus any text before the first \item
    bullets: tuple[Bullet, ...]
    close_span: Span  # "\end{itemize}"


@dataclass(frozen=True)
class FixedRegion:
    """Connective text within a section body that is never reordered: a
    subheading line, prose between two bullet lists, or an entire section's
    body when it has no recognized list at all."""

    span: Span


Region = FixedRegion | BulletGroup


@dataclass(frozen=True)
class Section:
    heading: str
    heading_span: Span
    regions: tuple[Region, ...]  # contiguous, covers [heading_span.end, section_end)


@dataclass(frozen=True)
class ParsedResume:
    source: str
    preamble_span: Span  # [0, ...) through "\begin{document}"
    header_span: Span  # content before the first \section (name, contact info)
    sections: tuple[Section, ...]
    trailing_span: Span  # "\end{document}" through EOF

    def text(self, span: Span) -> str:
        return self.source[span.start : span.end]


def parse_latex(source: str) -> ParsedResume:
    try:
        walker = LatexWalker(source, tolerant_parsing=False)
        nodelist, _pos, _length = walker.get_latex_nodes(pos=0)
    except LatexWalkerParseError as exc:
        raise LatexParseError(f"could not parse LaTeX source: {exc}") from exc

    doc_env = next(
        (
            n
            for n in nodelist
            if isinstance(n, LatexEnvironmentNode) and n.environmentname == _DOCUMENT_ENV
        ),
        None,
    )
    if doc_env is None:
        raise LatexParseError(r"no \begin{document}...\end{document} found")

    body_start, body_end = _environment_body_bounds(doc_env)
    preamble_span = Span(0, body_start)
    trailing_span = Span(body_end, len(source))

    body_nodes: list[LatexNode] = doc_env.nodelist
    section_indices = [
        i
        for i, n in enumerate(body_nodes)
        if isinstance(n, LatexMacroNode) and n.macroname == _SECTION_MACRO
    ]

    if not section_indices:
        # No recognized \section at all: nothing is movable, but the resume
        # still round-trips -- the whole body is the "header".
        return ParsedResume(
            source=source,
            preamble_span=preamble_span,
            header_span=Span(body_start, body_end),
            sections=(),
            trailing_span=trailing_span,
        )

    header_span = Span(body_start, body_nodes[section_indices[0]].pos)

    sections: list[Section] = []
    for k, idx in enumerate(section_indices):
        heading_node = body_nodes[idx]
        heading_span = Span(heading_node.pos, heading_node.pos + heading_node.len)
        heading_text = _extract_heading_text(source, heading_span)

        next_idx = section_indices[k + 1] if k + 1 < len(section_indices) else len(body_nodes)
        section_end = body_nodes[next_idx].pos if next_idx < len(body_nodes) else body_end
        region_nodes = body_nodes[idx + 1 : next_idx]
        regions = _build_regions(heading_span.end, section_end, region_nodes)

        sections.append(
            Section(heading=heading_text, heading_span=heading_span, regions=tuple(regions))
        )

    return ParsedResume(
        source=source,
        preamble_span=preamble_span,
        header_span=header_span,
        sections=tuple(sections),
        trailing_span=trailing_span,
    )


def _environment_body_bounds(env: LatexEnvironmentNode) -> tuple[int, int]:
    """The span strictly between ``\\begin{name}`` and ``\\end{name}`` --
    computed from the marker text's own length rather than the node's first/
    last child, so it is correct even for an empty environment."""
    begin_len = len(f"\\begin{{{env.environmentname}}}")
    end_len = len(f"\\end{{{env.environmentname}}}")
    return env.pos + begin_len, env.pos + env.len - end_len


def _extract_heading_text(source: str, heading_span: Span) -> str:
    """Reuses the chunker's own heading regex against the macro's raw text,
    rather than pylatexenc's parsed argument structure -- one fewer thing to
    get right about how pylatexenc represents a recognized macro's args, and
    it's already the pattern the rest of the app trusts for this."""
    match = LATEX_HEADING_RE.match(source[heading_span.start : heading_span.end])
    return match.group(1).strip() if match else source[heading_span.start : heading_span.end]


def _build_regions(start: int, end: int, nodes: list[LatexNode]) -> list[Region]:
    regions: list[Region] = []
    cursor = start
    for node in nodes:
        if isinstance(node, LatexEnvironmentNode) and node.environmentname in _LIST_ENVIRONMENTS:
            if node.pos > cursor:
                regions.append(FixedRegion(Span(cursor, node.pos)))
            regions.append(_build_bullet_group(node))
            cursor = node.pos + node.len
    if cursor < end:
        regions.append(FixedRegion(Span(cursor, end)))
    return regions


def _build_bullet_group(env: LatexEnvironmentNode) -> BulletGroup:
    _body_start, body_end = _environment_body_bounds(env)
    env_end = env.pos + env.len

    item_indices = [
        i
        for i, c in enumerate(env.nodelist)
        if isinstance(c, LatexMacroNode) and c.macroname == "item"
    ]
    if not item_indices:
        # A list with no recognized \item (e.g. only custom \resumeItem{...}
        # macros) has nothing to reorder -- the whole thing, wrapper
        # included, is one fixed block.
        return BulletGroup(
            open_span=Span(env.pos, env_end), bullets=(), close_span=Span(env_end, env_end)
        )

    open_span = Span(env.pos, env.nodelist[item_indices[0]].pos)
    bullets = []
    for k, idx in enumerate(item_indices):
        item_node = env.nodelist[idx]
        next_start = (
            env.nodelist[item_indices[k + 1]].pos if k + 1 < len(item_indices) else body_end
        )
        bullets.append(Bullet(Span(item_node.pos, next_start)))
    close_span = Span(body_end, env_end)

    return BulletGroup(open_span=open_span, bullets=tuple(bullets), close_span=close_span)


def bullet_id(bullet: Bullet) -> int:
    """A bullet's identity for the caller's purposes: its own span start.
    Stable across calls for the same source text, unique by construction
    (spans never overlap), and needs no index bookkeeping on the caller's
    side the way a (section, group, bullet) index triple would."""
    return bullet.span.start


def emit_latex(
    parsed: ParsedResume,
    *,
    section_order: list[int] | None = None,
    bullet_orders: dict[int, dict[int, list[int]]] | None = None,
    excluded_bullet_ids: frozenset[int] = frozenset(),
) -> str:
    """Re-serializes ``parsed`` by concatenating spans in the requested
    order. With no arguments this reproduces ``parsed.source`` exactly --
    the round-trip acceptance gate.

    ``section_order`` is a permutation of ``range(len(parsed.sections))``.
    ``bullet_orders[section_index][group_index]`` is a permutation of that
    bullet group's own indices. ``excluded_bullet_ids`` holds ``bullet_id()``
    values to omit entirely -- the only way content is ever dropped, and only
    when the caller passes it explicitly (see ``placeinator.latex.tailoring``:
    never automatic).
    """
    if section_order is None:
        section_order = list(range(len(parsed.sections)))
    bullet_orders = bullet_orders or {}

    parts = [parsed.text(parsed.preamble_span), parsed.text(parsed.header_span)]

    for section_index in section_order:
        section = parsed.sections[section_index]
        parts.append(parsed.text(section.heading_span))
        group_index = 0
        for region in section.regions:
            if isinstance(region, FixedRegion):
                parts.append(parsed.text(region.span))
                continue
            parts.append(parsed.text(region.open_span))
            order = bullet_orders.get(section_index, {}).get(
                group_index, list(range(len(region.bullets)))
            )
            for bullet_index in order:
                bullet = region.bullets[bullet_index]
                if bullet_id(bullet) in excluded_bullet_ids:
                    continue
                parts.append(parsed.text(bullet.span))
            parts.append(parsed.text(region.close_span))
            group_index += 1

    parts.append(parsed.text(parsed.trailing_span))
    return "".join(parts)
