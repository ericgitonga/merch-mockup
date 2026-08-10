"""Slug-based filename generation (`app._slugify`)."""

from app import _slugify


def test_lowercases_and_joins_spaces_with_underscores():
    assert _slugify("Flagrant Ant") == "flagrant_ant"


def test_strips_surrounding_whitespace():
    assert _slugify("  Flagrant  ") == "flagrant"


def test_collapses_internal_whitespace_runs():
    assert _slugify("Flagrant   Ant\tHere") == "flagrant_ant_here"


def test_drops_characters_outside_the_allowed_set():
    assert _slugify("Flagrant! Ant? #1") == "flagrant_ant_1"


def test_keeps_existing_hyphens_and_underscores():
    assert _slugify("already-slugged_text") == "already-slugged_text"


def test_empty_or_whitespace_only_input_yields_empty_slug():
    assert _slugify("") == ""
    assert _slugify("   ") == ""
