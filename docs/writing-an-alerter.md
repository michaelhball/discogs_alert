# Writing a discogs_alert alerter (plugin)

If `discogs_alert` doesn't ship with the notification service you want to use,
you can ship an alerter as a separate Python package — no fork, no PR into
this repo. `discogs_alert` discovers alerters at runtime via Python entry
points; once your package is `pip install`'d alongside `discogs_alert`, your
alerter shows up automatically in `--alerter-type` (or in the eventual
config-file `[alerter]` block).

This doc covers:

1. The alerter contract.
2. How to register your alerter via an entry point.
3. A working template you can copy and rename.

## The alerter contract

Subclass `discogs_alert.alert.base.Alerter` and implement `send_alert`:

```python
from discogs_alert.alert.base import Alerter


class MyAlerter(Alerter):
    def __init__(self, *, my_token: str, my_chat: str):
        self.my_token = my_token
        self.my_chat = my_chat

    def send_alert(self, message_title: str, message_body: str) -> bool:
        # Send the notification however your service expects. Return True if
        # delivery succeeded; False if it failed (so discogs_alert can retry
        # on the next loop iteration).
        ...
```

That's the whole contract. **`send_alert` is the only method** you need to
implement. It must:

- Be **synchronous** (the loop calls it inside an async coroutine but doesn't
  expect a coroutine back; if your delivery is HTTP, plain `requests` or
  `httpx`-sync is fine; if you need async, wrap it in `asyncio.run`).
- Return `True` on successful delivery, `False` otherwise. Returning `False`
  prevents the listing from being marked as alerted, so the loop will try
  again next iteration.
- Avoid raising. If something blows up, log it and return `False`.

Constructor kwargs are entirely up to you. They come from one of:

- the matching `--my-*` CLI flags you add (Phase A: not yet supported for
  plugins; you'll wire env vars in your alerter constructor for now), or
- env vars / config that your alerter reads itself.

## Registering via entry points

Add this to your package's `pyproject.toml`:

```toml
[project.entry-points."discogs_alert.alerters"]
MY_ALERTER = "my_pkg.alerter:MyAlerter"
```

(Or for a Poetry-managed package: `[tool.poetry.plugins."discogs_alert.alerters"]`.)

The entry-point **name** (`MY_ALERTER` above) is what the user passes to
`--alerter-type`; the **value** is the Python import path to your `Alerter`
subclass. Names are case-insensitive and are uppercased by `discogs_alert`.

Once your package is installed alongside `discogs_alert`:

```bash
$ pip install discogs_alert my-pkg
$ python -m discogs_alert --alerter-type=MY_ALERTER ...
```

…the alerter is selectable. No changes to `discogs_alert` itself.

## Configuration

Built-in alerters (Pushbullet, Telegram, ntfy) read their config from
`discogs_alert`'s own CLI flags / env vars / config file. **Plugin alerters
are responsible for their own config** — at minimum, define a constructor
that takes the kwargs you need, and read them from env vars in the calling
code (or in a small wrapper).

The simplest pattern: read env vars in your alerter's `__init__`:

```python
import os


class MyAlerter(Alerter):
    def __init__(self):
        self.token = os.environ["MY_ALERTER_TOKEN"]
        self.chat = os.environ.get("MY_ALERTER_CHAT")
        if not self.chat:
            raise ValueError("MY_ALERTER_CHAT must be set")
```

A future Phase B of the config-file refactor will give plugin alerters a way
to declare their own pydantic config block in the shared TOML file (and the
menu-bar app will let users edit it). For now, env vars are the simplest path.

## Starter template

`examples/discogs-alert-alerter-template/` in this repo contains a complete,
working "Hello world" alerter package — a `pyproject.toml` with the right
entry-point block, a working `Alerter` subclass that just logs, and a
unit-test scaffold that exercises `send_alert(title, body) -> bool`.

Copy the directory, rename, replace the print with your real delivery code,
and `pip install -e .` it next to `discogs_alert`.

## Testing your alerter

The `Alerter` base class is just a Python class — no special test fixtures
needed:

```python
def test_my_alerter_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(200))
    alerter = MyAlerter(my_token="t", my_chat="c")
    assert alerter.send_alert("title", "body") is True


def test_my_alerter_returns_false_on_5xx(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(503))
    alerter = MyAlerter(my_token="t", my_chat="c")
    assert alerter.send_alert("title", "body") is False
```

Don't hit the real upstream service in your CI; mock the HTTP layer.

## Built-in examples to read

- `discogs_alert/alert/ntfy.py` — simplest (no auth required by default).
- `discogs_alert/alert/pushbullet.py` — token-based auth, JSON body.
- `discogs_alert/alert/telegram.py` — token + chat ID.

All three are short (~40 lines each); copy whichever pattern fits your
target service.
