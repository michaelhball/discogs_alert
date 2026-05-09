"""Tests for the per-release directive parser used in Discogs list comments."""

import pytest

from discogs_alert.entities import CONDITION, Release
from discogs_alert.util.wantlist_directives import apply_directives, parse_directives


# -- parse_directives --------------------------------------------------------


@pytest.mark.parametrize("comment", [None, "", "   ", "no directives here"])
def test_parse_directives_returns_empty_for_no_match(comment):
    assert parse_directives(comment) == {}


def test_parse_directives_extracts_price():
    assert parse_directives("@max=500") == {"price_threshold": 500}


@pytest.mark.parametrize("alias", ["max", "price", "price_threshold"])
def test_parse_directives_accepts_price_aliases(alias):
    assert parse_directives(f"@{alias}=42") == {"price_threshold": 42}


@pytest.mark.parametrize(
    "value,expected",
    [
        ("VG", CONDITION.VERY_GOOD),
        ("VG+", CONDITION.VERY_GOOD_PLUS),
        ("NM", CONDITION.NEAR_MINT),
        ("M-", CONDITION.NEAR_MINT),
        ("M", CONDITION.MINT),
        ("G+", CONDITION.GOOD_PLUS),
        ("VERY_GOOD", CONDITION.VERY_GOOD),
        ("near_mint", CONDITION.NEAR_MINT),
        ("nm", CONDITION.NEAR_MINT),
    ],
)
def test_parse_directives_media_aliases(value, expected):
    assert parse_directives(f"@media={value}") == {"min_media_condition": expected}


def test_parse_directives_sleeve():
    assert parse_directives("@sleeve=NM") == {"min_sleeve_condition": CONDITION.NEAR_MINT}


def test_parse_directives_combined():
    out = parse_directives("@max=300 @media=VG+ @sleeve=NM")
    assert out == {
        "price_threshold": 300,
        "min_media_condition": CONDITION.VERY_GOOD_PLUS,
        "min_sleeve_condition": CONDITION.NEAR_MINT,
    }


def test_parse_directives_mixed_with_freeform_text():
    """Comments are free-text; directives can be sprinkled inside it."""

    out = parse_directives("Hot one! @max=200 — known to surface around €180. @media=NM")
    assert out == {"price_threshold": 200, "min_media_condition": CONDITION.NEAR_MINT}


def test_parse_directives_unknown_key_logs_and_skips(caplog):
    out = parse_directives("@bogus=42 @max=500")
    assert out == {"price_threshold": 500}


def test_parse_directives_malformed_price_dropped(caplog):
    out = parse_directives("@max=cheese @media=NM")
    assert out == {"min_media_condition": CONDITION.NEAR_MINT}
    assert any("malformed" in m for m in caplog.messages)


def test_parse_directives_unrecognised_condition_dropped(caplog):
    out = parse_directives("@media=fantastic")
    assert out == {}
    assert any("unrecognised" in m for m in caplog.messages)


def test_parse_directives_keys_are_case_insensitive():
    """User typing on a phone shouldn't be punished for caps."""

    assert parse_directives("@MAX=500 @MEDIA=NM @SLEEVE=VG") == {
        "price_threshold": 500,
        "min_media_condition": CONDITION.NEAR_MINT,
        "min_sleeve_condition": CONDITION.VERY_GOOD,
    }


def test_parse_directives_never_raises_on_garbage():
    """Whatever the comment looks like, parse_directives must return a dict."""

    for garbage in ["@@@", "@=", "@key=", "@=value", "👀", "@key=val with spaces"]:
        out = parse_directives(garbage)
        assert isinstance(out, dict)


# -- apply_directives --------------------------------------------------------


def test_apply_directives_sets_unset_fields():
    release = Release(id=1, display_title="X", comment="@max=500 @media=NM")
    apply_directives(release)
    assert release.price_threshold == 500
    assert release.min_media_condition == CONDITION.NEAR_MINT


def test_apply_directives_does_not_override_existing_fields():
    """If the JSON / API already supplied a field, don't let a comment win."""

    release = Release(
        id=1,
        display_title="X",
        comment="@max=500",
        price_threshold=999,  # explicit
    )
    apply_directives(release)
    assert release.price_threshold == 999


def test_apply_directives_returns_release_for_chaining():
    release = Release(id=1, display_title="X", comment="@max=10")
    assert apply_directives(release) is release


def test_apply_directives_handles_no_comment():
    release = Release(id=1, display_title="X", comment=None)
    apply_directives(release)
    assert release.price_threshold is None
    assert release.min_media_condition is None
