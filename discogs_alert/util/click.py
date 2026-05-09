import enum
from typing import Any, List, Mapping, Optional, Tuple, Type

import click

# Click 8.3 changed `consume_value` to return the literal `Sentinel.UNSET` for
# unprovided options, instead of the option's default (typically `None`). We
# match against both so the same code works on click 8.0–8.2 and 8.3+.
try:
    from click.core import UNSET as _CLICK_UNSET  # type: ignore[attr-defined]

    _UNSET_VALUES: tuple = (None, _CLICK_UNSET)
except ImportError:  # pragma: no cover — pre-8.3 click
    _UNSET_VALUES = (None,)


def _is_unset(value: Any) -> bool:
    return value in _UNSET_VALUES


class NotRequiredIf(click.Option):
    """A class enabling click to specify arguments of which we require one or the other.
    https://stackoverflow.com/questions/11154946/require-either-of-two-arguments-using-argparse
    """

    def __init__(self, *args, **kwargs):
        self.not_required_if = kwargs.pop("not_required_if")
        assert self.not_required_if, "'not_required_if' parameter required"
        helper_text = f" NOTE: This argument is mutually exclusive with {self.not_required_if}"
        kwargs["help"] = (kwargs.get("help", "") + helper_text).strip()
        super().__init__(*args, **kwargs)

    def handle_parse_result(
        self, ctx: click.Context, opts: Mapping[str, Any], args: List[str]
    ) -> Tuple[Any, List[str]]:
        # Click stores option names in `opts` with underscores; users pass hyphens to
        # `not_required_if` to mirror the CLI flag style. Normalise to underscores so
        # the comparison actually fires.
        other_name = self.not_required_if.replace("-", "_")
        we_are_present = self.name in opts and not _is_unset(opts.get(self.name))
        other_present = other_name in opts and not _is_unset(opts.get(other_name))
        if other_present:
            if we_are_present:
                raise click.UsageError(
                    f"Illegal usage: `{self.name}` is mutually exclusive with `{self.not_required_if}`"
                )
            else:
                self.prompt = None

        return super().handle_parse_result(ctx, opts, args)


class RequiredIf(click.Option):
    """A class enabling Click to require a specific argument if some boolean condition is met. Both `required_if`
    and `required_if_str` must be specified for any Click option using RequiredIf, the former a callable that
    determines whether the option is required, and the latter a string used to explain the condition (see usage below).
    """

    def __init__(self, *args, **kwargs):
        self.required_if = kwargs.pop("required_if")
        self.required_if_str = kwargs.pop("required_if_str")
        assert (
            self.required_if is not None and self.required_if_str is not None
        ), "Both the `required_if` and the `required_if_str` parameters are required if using the `RequiredIf` class"

        kwargs["help"] = (
            kwargs.get("help", "") + f" NB: this argument is only required if `{self.required_if_str}`"
        ).strip()

        super().__init__(*args, **kwargs)

    def handle_parse_result(
        self, ctx: click.Context, opts: Mapping[str, Any], args: List[str]
    ) -> Tuple[Any, List[str]]:
        """If the `required_if` condition is met, check whether this option's value is set before proceeding."""

        value, _ = self.consume_value(ctx, opts)
        if self.required_if(ctx.params) and _is_unset(value):
            raise click.UsageError(f"Illegal usage: `{self.name}` is required when `{self.required_if_str}`")

        self.prompt = None
        return super().handle_parse_result(ctx, opts, args)


class EnumChoice(click.Choice):
    """Thanks to https://github.com/pallets/click/pull/2210 🙏"""

    def __init__(self, enum_type: Type[enum.Enum], case_sensitive: bool = True):
        super().__init__(choices=[element.name for element in enum_type], case_sensitive=case_sensitive)
        self.enum_type = enum_type

    def convert(self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]) -> Any:
        value = super().convert(value=value, param=param, ctx=ctx)
        if value is None:
            return None
        return self.enum_type[value]
