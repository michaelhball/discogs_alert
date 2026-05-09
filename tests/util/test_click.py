"""Tests for the small Click extensions in `discogs_alert.util.click`."""

import enum

import click
import pytest
from click.testing import CliRunner

from discogs_alert.util import click as da_click


class _Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


# -- NotRequiredIf ----------------------------------------------------------


def _build_either_app():
    @click.command()
    @click.option("--list-id", cls=da_click.NotRequiredIf, not_required_if="wantlist-path", default=None)
    @click.option("--wantlist-path", cls=da_click.NotRequiredIf, not_required_if="list-id", default=None)
    def app(list_id, wantlist_path):
        click.echo(f"list_id={list_id} wantlist_path={wantlist_path}")

    return app


def test_not_required_if_passes_with_only_first():
    runner = CliRunner()
    result = runner.invoke(_build_either_app(), ["--list-id", "42"])
    assert result.exit_code == 0
    assert "list_id=42" in result.output


def test_not_required_if_passes_with_only_second():
    runner = CliRunner()
    result = runner.invoke(_build_either_app(), ["--wantlist-path", "/tmp/wl.json"])
    assert result.exit_code == 0
    assert "wantlist_path=/tmp/wl.json" in result.output


def test_not_required_if_rejects_both():
    runner = CliRunner()
    result = runner.invoke(_build_either_app(), ["--list-id", "1", "--wantlist-path", "/tmp/wl.json"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_not_required_if_requires_init_arg():
    """The class refuses to be instantiated without `not_required_if`."""

    with pytest.raises((AssertionError, KeyError)):
        da_click.NotRequiredIf(["--foo"])  # missing kwarg


# -- RequiredIf -------------------------------------------------------------


def _build_required_if_app():
    @click.command()
    @click.option("--mode", type=str, default=None)
    @click.option(
        "--token",
        cls=da_click.RequiredIf,
        required_if=lambda ctx: ctx.get("mode") == "secret",
        required_if_str="mode=secret",
        default=None,
    )
    def app(mode, token):
        click.echo(f"mode={mode} token={token}")

    return app


def test_required_if_inactive_when_condition_false():
    runner = CliRunner()
    result = runner.invoke(_build_required_if_app(), ["--mode", "open"])
    assert result.exit_code == 0
    assert "mode=open token=None" in result.output


def test_required_if_active_when_condition_true_without_value():
    runner = CliRunner()
    result = runner.invoke(_build_required_if_app(), ["--mode", "secret"])
    assert result.exit_code != 0
    assert "is required when" in result.output


def test_required_if_passes_when_condition_true_with_value():
    runner = CliRunner()
    result = runner.invoke(_build_required_if_app(), ["--mode", "secret", "--token", "abc"])
    assert result.exit_code == 0
    assert "mode=secret token=abc" in result.output


def test_required_if_handles_click_83_unset_sentinel():
    """Click 8.3 changed `consume_value` to return `Sentinel.UNSET` for unprovided
    options instead of the option's `default`. The original RequiredIf code
    checked `value is None`, which silently no-op'd on click 8.3+. Captured here
    so the regression doesn't return.
    """

    runner = CliRunner()
    result = runner.invoke(_build_required_if_app(), ["--mode", "secret"])
    assert result.exit_code != 0
    assert "is required when" in result.output


# -- EnumChoice -------------------------------------------------------------


def test_enum_choice_converts_to_enum_member():
    @click.command()
    @click.option("--color", type=da_click.EnumChoice(_Color))
    def app(color):
        click.echo(repr(color))

    runner = CliRunner()
    result = runner.invoke(app, ["--color", "RED"])
    assert result.exit_code == 0
    assert "_Color.RED" in result.output


def test_enum_choice_rejects_unknown_member():
    @click.command()
    @click.option("--color", type=da_click.EnumChoice(_Color))
    def app(color):
        click.echo(repr(color))

    runner = CliRunner()
    result = runner.invoke(app, ["--color", "GREEN"])
    assert result.exit_code != 0


def test_enum_choice_passes_none_through():
    @click.command()
    @click.option("--color", type=da_click.EnumChoice(_Color), default=None)
    def app(color):
        click.echo(repr(color))

    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "None" in result.output
