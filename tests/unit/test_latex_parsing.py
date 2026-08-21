"""placeinator.latex.parsing -- the round-trip acceptance gate and the
structural rules the splice design depends on.

The gate (parse then emit with no reordering reproduces the input
byte-for-byte) is true by construction here, since emit_latex concatenates a
contiguous, non-overlapping partition of the source (see parsing.py's module
docstring) -- these tests pin that property against real resume LaTeX, not
synthetic strings, the same discipline that caught the robots.txt bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from placeinator.latex.parsing import (
    BulletGroup,
    FixedRegion,
    LatexParseError,
    bullet_id,
    emit_latex,
    parse_latex,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "resumes"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "filename",
    ["sde_resume.tex", "multi_entry_experience.tex", "custom_macro_template.tex"],
)
def test_identity_emit_reproduces_the_source_byte_for_byte(filename: str):
    source = _read(filename)
    parsed = parse_latex(source)

    assert emit_latex(parsed) == source


def test_reversing_a_bullet_group_still_reproduces_every_byte():
    """Not just identity -- concatenation must account for every byte of the
    source under a real permutation too, not only the trivial no-op case."""
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience = next(s for s in parsed.sections if s.heading == "Experience")
    group = next(r for r in experience.regions if isinstance(r, BulletGroup))
    reversed_order = list(range(len(group.bullets)))[::-1]
    section_index = parsed.sections.index(experience)

    reordered = emit_latex(parsed, bullet_orders={section_index: {0: reversed_order}})

    assert len(reordered) == len(source)
    assert sorted(reordered) == sorted(source)
    assert reordered != source  # the reorder actually did something


def test_reordered_output_still_parses_as_valid_latex():
    """Splicing must not corrupt LaTeX structure -- the reordered text is fed
    right back through the parser."""
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience_idx = next(i for i, s in enumerate(parsed.sections) if s.heading == "Experience")
    group = next(r for r in parsed.sections[experience_idx].regions if isinstance(r, BulletGroup))

    reordered = emit_latex(
        parsed, bullet_orders={experience_idx: {0: list(range(len(group.bullets)))[::-1]}}
    )

    reparsed = parse_latex(reordered)
    assert [s.heading for s in reparsed.sections] == [s.heading for s in parsed.sections]


def test_excluding_a_bullet_omits_only_that_bullet():
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience = next(s for s in parsed.sections if s.heading == "Experience")
    group = next(r for r in experience.regions if isinstance(r, BulletGroup))
    dropped = group.bullets[0]

    result = emit_latex(parsed, excluded_bullet_ids=frozenset({bullet_id(dropped)}))

    assert parsed.text(dropped.span) not in result
    assert parsed.text(group.bullets[1].span) in result
    # Still valid LaTeX with one fewer item.
    reparsed = parse_latex(result)
    reparsed_experience = next(s for s in reparsed.sections if s.heading == "Experience")
    reparsed_group = next(r for r in reparsed_experience.regions if isinstance(r, BulletGroup))
    assert len(reparsed_group.bullets) == len(group.bullets) - 1


# -- structure -------------------------------------------------------------- #


def test_sections_are_found_in_document_order():
    parsed = parse_latex(_read("sde_resume.tex"))
    assert [s.heading for s in parsed.sections] == ["Skills", "Experience", "Projects"]


def test_starred_sections_are_recognized_the_same_as_unstarred():
    parsed = parse_latex(_read("multi_entry_experience.tex"))
    assert [s.heading for s in parsed.sections] == ["Experience"]


def test_a_section_can_hold_multiple_independent_bullet_groups():
    """Two job entries under one \\section{Experience} -- each with its own
    itemize -- must never mix bullets across entries."""
    parsed = parse_latex(_read("multi_entry_experience.tex"))
    experience = parsed.sections[0]
    groups = [r for r in experience.regions if isinstance(r, BulletGroup)]

    assert len(groups) == 2
    assert [len(g.bullets) for g in groups] == [2, 1]
    assert "Built APIs" in parsed.text(groups[0].bullets[0].span)
    assert "Wrote tests" in parsed.text(groups[1].bullets[0].span)


def test_connective_text_between_bullet_groups_is_preserved_as_fixed():
    parsed = parse_latex(_read("multi_entry_experience.tex"))
    experience = parsed.sections[0]
    fixed = [r for r in experience.regions if isinstance(r, FixedRegion)]

    assert any("Globex" in parsed.text(r.span) for r in fixed)


def test_a_list_with_only_custom_bullet_macros_has_no_recognized_items():
    """A \\newcommand-defined \\resumeItem{...} macro's argument isn't
    captured as a child of the macro by pylatexenc (it has no signature for
    it), so this template's list has zero recognized \\item nodes -- the
    whole thing must degrade to one immutable block, not crash and not
    silently invent bullet boundaries that were never there."""
    parsed = parse_latex(_read("custom_macro_template.tex"))
    experience = parsed.sections[0]
    groups = [r for r in experience.regions if isinstance(r, BulletGroup)]

    assert len(groups) == 1
    assert groups[0].bullets == ()
    # But the content is still there, verbatim, just not bullet-splittable.
    assert "resumeItem" in parsed.text(groups[0].open_span)


def test_header_content_before_the_first_section_is_preserved():
    parsed = parse_latex(_read("sde_resume.tex"))
    assert "Jane Doe" in parsed.text(parsed.header_span)


def test_no_sections_at_all_still_round_trips():
    source = "\\documentclass{article}\n\\begin{document}\nJust some text.\n\\end{document}\n"
    parsed = parse_latex(source)

    assert parsed.sections == ()
    assert emit_latex(parsed) == source


def test_malformed_latex_raises_a_clear_error_not_a_crash():
    broken = (
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Skills\nmissing brace\n\\end{document}\n"
    )

    with pytest.raises(LatexParseError):
        parse_latex(broken)


def test_missing_document_environment_raises_a_clear_error():
    no_doc = "\\documentclass{article}\n\\section{Skills}\nNo document environment.\n"

    with pytest.raises(LatexParseError, match="begin.document"):
        parse_latex(no_doc)
