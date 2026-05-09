# discogs-alert-alerter-template

A starter template for shipping a custom `discogs_alert` alerter as a
separate pip package.

## What this is

`discogs_alert` discovers alerters at runtime via the
`discogs_alert.alerters` entry-point group. To add a new notification
service (Discord, Slack, Apprise, email, your-self-hosted-thing, …) you
ship a separate package — no fork, no PR into the upstream repo.

This template is a complete, working "hello world" alerter:

- One file (`discogs_alert_example/alerter.py`) implementing the
  `Alerter` contract.
- A `pyproject.toml` with the entry-point already wired.
- A `tests/` directory with a working unit test.

## Using as a starting point

1. Copy this directory to a new location and rename:
   ```bash
   $ cp -r examples/discogs-alert-alerter-template ~/code/discogs-alert-discord
   $ cd ~/code/discogs-alert-discord
   ```
2. Rename the package directory and entry point:
   - `discogs_alert_example/` → e.g. `discogs_alert_discord/`
   - In `pyproject.toml`: change the `name`, the `packages` line, and the
     entry-point name + import path.
3. Replace the `print(...)` in `alerter.py` with your real delivery code.
4. `pip install -e .` next to `discogs_alert`.
5. Run with `python -m discogs_alert --alerter-type=DISCORD ...` (or
   whatever entry-point name you picked).

## The contract

`Alerter` subclasses must implement `send_alert(title: str, body: str) -> bool`.
Return `True` on successful delivery, `False` otherwise. See
[docs/writing-an-alerter.md](../../docs/writing-an-alerter.md) in the
upstream repo for the full guide.
