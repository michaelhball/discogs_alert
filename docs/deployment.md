# Running discogs_alert as an always-on service

How the maintainer's own instance runs, written down so it can be rebuilt from
scratch. It is a macOS `launchd` user agent that fires the CLI in `--once` mode
every 10 minutes from a dedicated `uv`-built virtualenv. Nothing stays resident
between runs; `launchd` owns the schedule.

The same shape works on Linux with a systemd timer or `cron` (see the README);
only the scheduler differs.

## Layout

```
~/.discogs_alert/
  config.toml        # the only config; mode 600 (holds the Discogs token)
  state.db           # SQLite dedup store (table `sent_alerts`); never delete casually
  venv/              # uv-built virtualenv with discogs_alert installed
  DEPLOYMENT.md      # optional: machine-specific notes (alerter topic, VPN quirks, …)
~/Library/LaunchAgents/com.discogsalert.plist   # the launchd agent
~/Library/Logs/discogs_alert.log                # stdout+stderr of every run, appended
```

## One-time setup

```bash
# 1. Python environment (uv; plain `python -m venv` + pip works too)
uv venv --python 3.13 ~/.discogs_alert/venv
uv pip install --python ~/.discogs_alert/venv/bin/python discogs-alert       # from PyPI
#   …or from a checkout:  uv pip install --python ~/.discogs_alert/venv/bin/python /path/to/discogs_alert

# 2. Config
mkdir -p ~/.discogs_alert
cp examples/config.example.toml ~/.discogs_alert/config.toml
$EDITOR ~/.discogs_alert/config.toml          # token, list_id, alerter, filters
chmod 600 ~/.discogs_alert/config.toml
~/.discogs_alert/venv/bin/python -m discogs_alert --validate-config

# 3. First run by hand. NOTE: with an empty state.db this alerts on EVERY listing
#    that currently matches your filters — expect a burst. Consider a tight
#    price threshold or a small list for the very first run.
~/.discogs_alert/venv/bin/python -m discogs_alert --once --verbose

# 4. launchd agent
sed -e "s#/REPLACE_WITH/path/to/python#$HOME/.discogs_alert/venv/bin/python#" \
    -e "s#/REPLACE_WITH/Users/YOU/.discogs_alert/config.toml#$HOME/.discogs_alert/config.toml#" \
    -e "s#/REPLACE_WITH/Users/YOU/Library/Logs/discogs_alert.log#$HOME/Library/Logs/discogs_alert.log#g" \
    docker/launchd/com.discogsalert.plist.template > ~/Library/LaunchAgents/com.discogsalert.plist
plutil -lint ~/Library/LaunchAgents/com.discogsalert.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.discogsalert.plist
```

`RunAtLoad` is on in the template, so bootstrapping runs one iteration
immediately and then every `StartInterval` (600 s) after that.

## What one run does

Each fire is a fresh process: load `config.toml` (plus any `DA_*` env
overrides), fetch the Discogs list, hit `/marketplace/stats` for every release
(cheap gate), scrape the marketplace page for the ones with listings, apply the
filters, send an alert for each matching listing not already in `state.db`,
record it, exit. Failed sends are *not* recorded, so they retry next run.

## Day-to-day

```bash
~/.discogs_alert/venv/bin/discogs_alert --status                            # HEALTHY / STALE / UNHEALTHY + last summary; exit 0/1/2
launchctl print gui/$UID/com.discogsalert | grep -E "state|last exit|runs"   # loaded? last exit code?
tail -f ~/Library/Logs/discogs_alert.log                                     # follow
~/.discogs_alert/venv/bin/python -m discogs_alert --once --verbose           # manual iteration
sqlite3 ~/.discogs_alert/state.db "select count(*) from sent_alerts;"        # alerts ever sent
```

Config edits need no restart: every run re-reads the file.

## Upgrading

```bash
uv pip install --python ~/.discogs_alert/venv/bin/python --upgrade discogs-alert   # or a checkout path
launchctl bootout gui/$UID/com.discogsalert
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.discogsalert.plist
launchctl print gui/$UID/com.discogsalert | grep -E "state|last exit"
```

`bootout` kills an in-flight iteration; that is harmless (the next fire redoes it).

## Stopping / removing

```bash
launchctl bootout gui/$UID/com.discogsalert          # until next login
rm ~/Library/LaunchAgents/com.discogsalert.plist      # permanently
```

## Known limits

- `launchd` timers pause while the Mac sleeps; runs resume on wake. For true
  24/7 coverage use an always-on box (Raspberry Pi, NAS) with cron/systemd.
- Some VPNs break TLS 1.3 handshakes to particular hosts (seen with `ntfy.sh`
  through ExpressVPN: most sends died with `SSL: UNEXPECTED_EOF_WHILE_READING`).
  If alert sends fail intermittently while everything else works, try another
  server for the alerter (e.g. a different public ntfy instance) or exclude the
  host from the VPN.
- The launchd `StandardOutPath` file grows without rotation. Prefer, in
  `config.toml`:

  ```toml
  [runtime]
  log_file = "/Users/me/Library/Logs/discogs_alert.log"   # rotated at 10 MiB, 5 backups
  log_stderr = false                                        # don't also spray every line to launchd's capture
  ```

  and point the plist's `StandardOutPath` / `StandardErrorPath` at a separate
  `discogs_alert.crash.log`, which then only ever sees interpreter-level
  failures (import errors, tracebacks before logging is configured). Without
  `log_stderr = false` that file would silently receive a second, unrotated
  copy of the whole log.
