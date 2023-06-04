from typing import Any, List, Mapping, Tuple

import click


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
        we_are_present = self.name in opts
        other_present = self.not_required_if in opts
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
        super().__init__(*args, **kwargs)

    def handle_parse_result(
        self, ctx: click.Context, opts: Mapping[str, Any], args: List[str]
    ) -> Tuple[Any, List[str]]:
        """If the `required_if` condition is met, check whether this option's value is set before proceeding."""

        value, _ = self.consume_value(ctx, opts)
        if self.required_if(ctx.params) and value is None:
            raise click.UsageError(f"Illegal usage: `{self.name}` is required when `{self.required_if_str}`")

        self.prompt = None
        return super().handle_parse_result(ctx, opts, args)
