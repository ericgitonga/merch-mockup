"""Colour config table lookups (`app.TEXT_COLOURS`, `app.SHIRT_COLOURS`,
`app._resolve_colours`, `app._hex_to_rgb`)."""

import pytest

from app import SHIRT_COLOURS, TEXT_COLOURS, _hex_to_rgb, _resolve_colours


@pytest.mark.parametrize("name, entry", TEXT_COLOURS.items())
def test_text_colour_entries_are_valid_rgb_triples(name, entry):
    for channel in ("rgb", "shadow"):
        triple = entry[channel]
        assert len(triple) == 3
        assert all(0 <= c <= 255 for c in triple), (name, channel, triple)


@pytest.mark.parametrize("name, hex_code", SHIRT_COLOURS.items())
def test_shirt_colour_hex_codes_parse_to_valid_rgb(name, hex_code):
    assert hex_code.startswith("#")
    assert len(hex_code) == 7
    rgb = _hex_to_rgb(hex_code)
    assert len(rgb) == 3
    assert all(0 <= c <= 255 for c in rgb), (name, hex_code, rgb)


def test_resolve_colours_passes_through_known_names():
    assert _resolve_colours("Red", "Forest Green") == ("Red", "Forest Green")


def test_resolve_colours_falls_back_on_unknown_text_colour():
    text_colour, shirt_colour = _resolve_colours("Not A Colour", "Forest Green")
    assert text_colour == "White"
    assert shirt_colour == "Forest Green"


def test_resolve_colours_falls_back_on_unknown_shirt_colour():
    text_colour, shirt_colour = _resolve_colours("Red", "Not A Colour")
    assert text_colour == "Red"
    assert shirt_colour == next(iter(SHIRT_COLOURS))


def test_resolve_colours_falls_back_on_both_unknown():
    text_colour, shirt_colour = _resolve_colours("", "")
    assert text_colour == "White"
    assert shirt_colour == next(iter(SHIRT_COLOURS))
