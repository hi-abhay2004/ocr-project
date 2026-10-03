"""
ai/annotations/_common.py's ruled_paper_line_ys() — flags printed
ruled-paper lines (several full-width horizontal lines in one block) so
underline.py/strikethrough.py can tell them apart from a genuine one-off
hand-drawn mark, which is geometrically identical at the level of a single
line. Count-based, not pitch-regularity-based — see the module-level
comment above the function for why an exact-pitch check turned out too
fragile against a real (imperfectly photographed) page.
"""

from ai.annotations._common import Line, ruled_paper_line_ys


def _full_width_line(y: int, width: int = 1000) -> Line:
    return Line(x1=10, y1=y, x2=width - 10, y2=y)


def test_several_full_width_lines_are_flagged_as_ruled_paper():
    lines = [_full_width_line(y) for y in (40, 100, 160, 220)]
    assert ruled_paper_line_ys(lines, block_width=1000) == {40, 100, 160, 220}


def test_a_single_full_width_line_is_not_enough_to_call_it_ruled_paper():
    # One long line could still be a genuine underline/divider drawn once
    # — it takes several of them in the same block to say "this is the
    # page's own print," not a one-off mark.
    lines = [_full_width_line(100)]
    assert ruled_paper_line_ys(lines, block_width=1000) == set()


def test_irregularly_spaced_full_width_lines_are_still_flagged():
    # A real photographed page can mix genuine notebook ruling with
    # unrelated printed furniture (e.g. a header box's own borders) in the
    # same block, at a totally different spacing — verified (2026-08-26)
    # against a real photo where exactly this broke an earlier version of
    # this function that additionally required one consistent pitch.
    # Enough full-width lines, regardless of exact spacing, is itself the
    # signal now.
    lines = [_full_width_line(y) for y in (40, 55, 300)]
    assert ruled_paper_line_ys(lines, block_width=1000) == {40, 55, 300}


def test_a_short_line_does_not_count_toward_or_get_caught_by_the_pattern():
    short = Line(x1=100, y1=280, x2=200, y2=280)
    lines = [_full_width_line(y) for y in (40, 100, 160)] + [short]
    ys = ruled_paper_line_ys(lines, block_width=1000)
    assert ys == {40, 100, 160}
    assert 280 not in ys


def test_a_single_full_width_line_pinned_to_a_blocks_own_edge_is_flagged_without_a_count():
    # Live finding (2026-10-03): a single-answer crop usually only shows
    # the ONE ruled line nearest its own top/bottom boundary, never
    # several — the count-based check above never fires in that context,
    # so a genuine ruled-paper boundary line was being accepted as a
    # confident hand-drawn STRIKE/UNDERLINE. Position alone (sitting right
    # at the crop's own edge) is enough to call this one suspect, with no
    # count needed — only checked when the caller passes block_height.
    near_top = _full_width_line(5)
    lines = [near_top]
    assert ruled_paper_line_ys(lines, block_width=1000, block_height=400) == {5}


def test_a_single_full_width_line_in_the_middle_of_a_block_is_not_flagged_by_position():
    # Contrast with the edge case above: a line sitting well inside the
    # block (not near either edge) gets no help from the position signal —
    # still needs the count-based pattern, same as before block_height
    # existed at all.
    middle = _full_width_line(200)
    lines = [middle]
    assert ruled_paper_line_ys(lines, block_width=1000, block_height=400) == set()
