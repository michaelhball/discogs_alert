# Discogs Alert

<p align="center">
    <a href="https://github.com/michaelhball/discogs_alert/blob/main/LICENSE">
        <img alt="GitHub" src="https://img.shields.io/badge/License-MIT-yellow.svg">
    </a>
    <a href="https://pypi.org/project/discogs_alert">
        <img alt="GitHub" src="https://img.shields.io/pypi/v/discogs_alert">
    </a>
    <a href="https://pypi.org/project/discogs_alert">
        <img alt="GitHub" src="https://img.shields.io/pypi/pyversions/tox.svg">
    </a>
    <a href="https://github.com/michaelhball/discogs_alert/actions/workflows/pr_checks.yml">
        <img alt="GitHub" src="https://github.com/michaelhball/discogs_alert/actions/workflows/pr_checks.yml/badge.svg">
    </a>
</p>

<h3 align="center">
<p>Customised, real-time alerting for your hard-to-find wantlist items.
</h3>

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
discogs-alert enables you to configure ~real-time alerts that notify you the moment a hard-to-find release goes on sale. The project is designed to require as little effort as possible: you customise your preference once, upfront, and then sit back and wait for a notification.

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
discogs-alert enables both global and fine-grained customisation of your preferences (including price thresholds, minimum seller rating, minimum media / sleeve conditions, and countries from which you either do or don't want to receive alerts). You'll only ever get notified if a record goes on sale that really matches what you're looking for.

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
If you have suggestions or ideas, please reach out! So far I've bought more than 50 records thanks to `discogs_alert` and I'd love to make it useful as possible for others.

## Requirements

- Python >= 3.10

## Installation & Setup

Four install paths, pick one:

### Python (via pip)

```
pip install discogs-alert
```

### macOS `.app` (drag-install, no Python required)

Download the latest `.dmg` from [Releases](https://github.com/michaelhball/discogs_alert/releases), open it, drag `discogs_alert.app` into `/Applications`. The app self-updates via Sparkle whenever a new version is published.

> On first launch, macOS Gatekeeper may say "discogs_alert can't be opened because Apple cannot check it for malicious software." Right-click the app → Open → confirm; you only have to do this once.

### Docker

```bash
docker pull miggleball/discogs_alert:latest
docker run -d --env-file .env miggleball/discogs_alert:latest
```

The container runs `python -m discogs_alert` as its entrypoint; pass your config via env vars (`DA_DISCOGS_TOKEN`, `DA_LIST_ID`, …) in your `.env` file.

### From source

```bash
git clone https://github.com/michaelhball/discogs_alert
cd discogs_alert
pip install -e .
```

For development you'll also want `pip install -e '.[menubar]'` if you're on a Mac and want the menu-bar app, plus `poetry install` to get the dev deps (`pytest`, `ruff`, `tox`, etc.).

## Setup

Before you can use this project, there are a few more things that need to be setup.

### Discogs access token

A Discogs access token allows `discogs_alert` to send requests to the discogs API on your behalf, and in particular it increases the rate at which you're allowed to make requests. This token can only be used to access the music database features of the Discogs API, not the marketplace, so there is no risk that you're accidentally granting control over the buying or selling of records. You can find more information [here](https://www.discogs.com/developers/#page:authentication).

To create an access token, go to your Discogs settings and click on the [Developer](https://www.discogs.com/settings/developers) tab. There is a button on this page to generate a new token. For now, just copy this token to your computer.

### Creating your wantlist

There are two different ways you can create a wantlist: 1) by connecting to one of your existing Discogs lists, or 2) by creating a local JSON file. The first option is easier, faster, and fits within your regular Discogs workflow. Both options support the same per-release filters (price threshold, media / sleeve condition); see below for the syntax in each case.

#### Discogs List

Using one of your existing Discogs [lists](https://www.discogs.com/lists) only requires that you specify the ID of the list at runtime, the process for which is outlined in the [usage](#usage) section below. Ideally you should set up a list specifically for this purpose, as you'll be notified the moment any of the releases in your list go on sale. This approach makes it incredibly easy to add new releases to your wantlist: simply add a release to the specified list and `discogs_alert` will automatically identify this and add that release to those it's searching for on the next iteration.

##### Per-release filters in list comments

You can put `@key=value` directives in a list item's _comment_ field to set per-release filters. Any other text in the comment is ignored. Recognised keys:

- `@max=N` (or `@price=N`) — maximum total price (in your `--currency`).
- `@media=...` — minimum media condition (e.g. `VG+`, `NM`, `M-`, `VERY_GOOD_PLUS`).
- `@sleeve=...` — minimum sleeve condition (same vocabulary).

Examples (each one is a valid comment on a list item):

```
@max=500
Hot one! @max=300 @media=NM
@media=VG+ @sleeve=NM @max=80
```

Unknown keys are ignored; malformed values are dropped with a warning so a typo on one item won't break the rest of the loop.

#### Local JSON

Here is an example `wantlist.json` file:
```yaml
[
  {
    "id": 1061046,
    "display_title": "Deep² — Sphere",
    "min_media_condition": "VERY_GOOD"
  },
  {
    "id": 2247646,
    "display_title": "Charanjit Singh — Ten Ragas to a Disco Beat",
    "price_threshold": 500 
  }
]
```
The wantlist is a list of objects, each object representing a release. The only essential attributes are the `id` field, which can be found on each release's Discogs page, and the `display_title`, which is the name you give the release s.t. you will recognise it when you're notified.

There are a number of optional attributes that can be included for each release. The combination of all attributes applied to a given release are used as a filter, so you will only be notified if all conditions are met for a given listing item. In the above case, the user is looking for any `VERY_GOOD` or higher copies of the `Deep²` release, with no maximum price (e.g. an example scenario here is that there are currently no copies on the market, and the user wants to be notified as soon as one goes on sale). For the `Charanjit Singh` release, the user is looking for any copies on sale for less than `€500`. NB: the currency is determined later, at runtime. This is outlined in the [usage](#usage) section below.

Remember that all criteria for restricting your alerts also have global values, the setting of which is discussed in [usage](#usage)). This means that if you want the same filters for most releases you do _not_ need to specify them for every single release in your `wantlist.json`. You can set the values once globally (when you run the program), and then set only those per-release values that differ from the global settings. Any filters specified in your `wantlist.json` will override the global values.

The possible optional filters are as follows:
* `price_threshold`: maximum allowable price (_excluding_ shipping)
* `min_media_condition`: minimum allowable media condition (one of `'POOR'`, `'FAIR'`, `'GOOD'`, `'GOOD_PLUS'`,
`'VERY_GOOD'`, `'VERY_GOOD_PLUS'`, `'NEAR_MINT'`, or `'MINT'`)
* `min_sleeve_condition`: minimum allowable sleeve condition (one of `'POOR'`, `'FAIR'`, `'GOOD'`, `'GOOD_PLUS'`,
`'VERY_GOOD'`, `'VERY_GOOD_PLUS'`, `'NEAR_MINT'`, or `'MINT'`)

### Alerting

`discogs_alert` ships with three built-in alerters. Pick the one whose setup matches what you have on your phone — they all do the same job (one notification per matching listing). **ntfy.sh is the recommended default** because it has the least setup and no account dependencies.

Configuration goes in `~/.discogs_alert/config.toml` (see [`examples/config.example.toml`](examples/config.example.toml) for the full schema). The `[alerter]` section selects which one and provides its credentials.

#### ntfy.sh (recommended — no account, no token)

[ntfy.sh](https://ntfy.sh/) is the easiest alerter to set up. Pick a random hard-to-guess topic name (anyone with the topic name can read your notifications) and subscribe to that topic from the [iOS](https://apps.apple.com/us/app/ntfy/id1625396347), [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy), [desktop](https://docs.ntfy.sh/subscribe/desktop/), or [web](https://ntfy.sh/app) app. Then in your `config.toml`:

```toml
[alerter]
type = "NTFY"
[alerter.ntfy]
topic = "your-secret-topic-here"
```

For privacy / reliability you can self-host ntfy: add `server = "https://ntfy.example.com"` (and optionally `token = "..."` if your server requires auth).

#### Pushbullet

Create an account at [pushbullet.com](https://www.pushbullet.com/) and install the app on the device(s) where you want notifications. Then create an access token from your [settings](https://www.pushbullet.com/#settings) page. Configure:

```toml
[alerter]
type = "PUSHBULLET"
[alerter.pushbullet]
token = "..."
```

> ⚠️ **Open the Pushbullet app at least once a month.** If you don't, Pushbullet's API silently 401s requests because it considers the account dormant — your alerts will go nowhere with no error visible from `discogs_alert`'s side.

#### Telegram

To use Telegram you first need to create a custom bot. Easiest path is via `@BotFather`:

1. Open Telegram on your phone, search for **@BotFather**, send `/start` then `/newbot`. Pick a name + username. BotFather replies with **a bot token** (looks like `123456789:ABC-…`).
2. Search for **your new bot** (by the username you chose) and send it `/start` (any message works).
3. In a browser, open `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`. Find the `"chat":{"id": …}` field — that number is your **chat_id**.

Then configure:

```toml
[alerter]
type = "TELEGRAM"
[alerter.telegram]
token = "..."
chat_id = "..."
```

#### Gmail

Sends each alert as a plain-text email via Gmail SMTP. Setup:

1. Make sure 2-Step Verification is on for your Google account (<https://myaccount.google.com/security>). Gmail SMTP requires it.
2. Generate an app password at <https://myaccount.google.com/apppasswords> — give it a name like `discogs_alert`, copy the 16-character value.

Then configure:

```toml
[alerter]
type = "GMAIL"
[alerter.gmail]
user = "you@gmail.com"           # also the From: address
app_password = "xxxx xxxx xxxx xxxx"
to = "you@gmail.com"             # where alerts get delivered
```

> ⚠️ **App password, not your regular Gmail password.** Gmail stopped accepting the latter for SMTP in 2022.

#### Adding more alerters

New alerters go in-tree as a PR: subclass `discogs_alert.alert.base.Alerter`, implement `send_alert(title, body) -> bool`, drop a file under `discogs_alert/alert/`, register it in both `_BUILTIN_ALERTERS` (in `alert/__init__.py`) and `[tool.poetry.plugins."discogs_alert.alerters"]` (in `pyproject.toml`). The built-in alerters are short — copy the closest one to whatever you're shipping (e.g. start from `ntfy.py` for a plain HTTP POST, or `gmail.py` for SMTP).

## Usage

`discogs_alert` can be run as a Python process or as a Docker container. Either way, the service polls your wantlist on a schedule, checks each release on the Discogs marketplace, and sends you a notification if any release (satisfying your filters) is for sale. Leave it running to be most effective.

Configuration lives in `~/.discogs_alert/config.toml` (or wherever `--config` points). See [`examples/config.example.toml`](examples/config.example.toml) for the full schema. Any field can be overridden by a `DA_*` environment variable — handy for Docker / launchd / CI without committing secrets.

#### Python

```bash
$ cp examples/config.example.toml ~/.discogs_alert/config.toml
$ $EDITOR ~/.discogs_alert/config.toml   # fill in your token, list_id, alerter
$ python -m discogs_alert
```

A few CLI helpers exist for debugging:

* `-c`/`--config <path>` — point at a non-default config file.
* `-O`/`--once` — run the loop once and exit (use with cron / launchd / systemd-timer).
* `-V`/`--verbose` — DEBUG-level logs.
* `-l`/`--log-level=<DEBUG|INFO|WARNING|ERROR>` — explicit log-level override.
* `--validate-config` — load the config, print a one-line summary, exit.
* `--print-config` — load the config, dump the resolved values as JSON, exit.
* `--version`

Run `python -m discogs_alert --help` for the full list.

#### Docker

```bash
$ docker run -d --env-file .env miggleball/discogs_alert:latest
```

Your `.env` file should set the required `DA_*` variables. Minimal example:

```bash
DA_DISCOGS_TOKEN=<discogs_access_token>
DA_LIST_ID=<discogs_list_id>
DA_ALERTER_TYPE=NTFY
DA_NTFY_TOPIC=<your-ntfy-topic>
```

The `-d` flag detaches the container so it runs in the background.

### Extras

You can add to or change your wantlist (Discogs list or local JSON) while the service is running; updates are picked up on the next iteration.

Each matching listing produces one notification — title is the release's display title, body is the listing URL. Deduplication is local: `discogs_alert` records every successful alert in `~/.discogs_alert/state.db` (configurable via `runtime.state_path` in `config.toml`) and won't re-alert across iterations.

The full set of knobs lives in [`examples/config.example.toml`](examples/config.example.toml) — global filters (seller rating, media / sleeve condition, country whitelist / blacklist), runtime tuning (`max_concurrency`, `prune_after_days`, `stats_gate`), and per-alerter config. Per-release overrides go in your wantlist JSON or as `@key=value` directives in Discogs list comments (see above).

#### Full Example

A realistic `~/.discogs_alert/config.toml` for a user driven by a Discogs list, who wants verbose logs, no minimum seller rating, a global minimum media condition of `VERY_GOOD`, and who doesn't want to consider sellers from the UK or US:

```toml
discogs_token = "<discogs_access_token>"

[wantlist]
list_id = <list_id>

[seller]
min_rating = 0   # turn off the seller-rating gate

[record]
min_media_condition = "VERY_GOOD"

[country_filters]
blacklist = ["UK", "US"]

[alerter]
type = "NTFY"
[alerter.ntfy]
topic = "<your-secret-topic>"

[runtime]
verbose = true
```

#### Running as a `cron` job

For low-effort always-on use, run `discogs_alert` as a `cron` job — set up your `config.toml` once and let cron schedule the iterations. Run `crontab -e` and add:

```bash
*/10 * * * * source ~/.bash_profile; python -m discogs_alert --once >> <path_to_log_file>.log 2>&1
```

`discogs_alert` runs every 10 minutes and logs to the specified file. `tail -f <path_to_log_file>.log` to follow.

See [here](https://www.hostinger.com/tutorials/cron-job) for more on cron / `crontab`.

#### Running as a macOS `launchd` daemon

On macOS, the cleanest "always-on" path is a `launchd` agent — survives logout, doesn't need a terminal open, integrates with macOS power management. A starter template lives at `docker/launchd/com.discogsalert.plist.template`. Replace the placeholder paths, drop the file at `~/Library/LaunchAgents/com.discogsalert.plist`, and `launchctl load` it. See the comments in the template for the exact recipe.

`launchd` timers pause while the Mac sleeps; for true 24/7 monitoring, run `discogs_alert` on an always-on box (Raspberry Pi, NAS, home server) instead.

#### macOS menu-bar app

For a lightweight GUI with status, "check now", and quick links to your config + state files, install the menu-bar extra and launch the app:

```bash
$ pip install 'discogs_alert[menubar]'
$ python -m discogs_alert.menubar
```

The menu-bar app is **not** the always-on path — closing it stops the loop. Use it interactively while at your Mac; pair it with `launchd` (above) for 24/7 monitoring.

#### Building a standalone `.app` / `.dmg`

If you'd rather drag-install a `.app` than `pip install` the package, the project ships a [`Makefile`](Makefile) that wraps `py2app` and `hdiutil`:

```bash
$ make app    # build dist/discogs_alert.app
$ make dmg    # build dist/discogs_alert-X.Y.Z.dmg (the user-facing artifact)
```

The build uses a clean throwaway venv at `.build-venv/` so unrelated packages on your outer Python don't pollute the bundle. End users only need to drag the `.app` from the DMG into `/Applications` — no Python install required.

> **Code signing**: the `.app` is unsigned by default. macOS Gatekeeper will prompt the user to right-click → Open on first launch. Code signing requires an Apple Developer ID ($99/yr); see [Apple's notarization docs](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) for the recipe.


## Contributing

1. Fork (https://github.com/michaelhball/discogs_alert/fork)
2. Create your feature branch (git checkout -b feature/fooBar)
3. Commit your changes (git commit -am 'Add some fooBar')
4. Push to the branch (git push origin feature/fooBar)
5. Create a new Pull Request

### Setting up the dev environment

Ideally, you should work inside a virtual environment set up for this project. Once that's the case, simply run the following two commands to install all dependencies:

* `$ pip install --user poetry`
* `$ poetry install` 

And that's it! Until you want to propose your changes as a new PR. When that's the case you need to run the tests to make sure nothing has broken, which you can do simply by running `$ tox` in the project's root directory. 

### Cutting a release

Tag-triggered: bump `version` in `pyproject.toml` + `_FALLBACK_VERSION` in `discogs_alert/__init__.py`, commit, tag `vX.Y.Z`, push with `--follow-tags`. CI builds + signs + publishes everything (PyPI, DockerHub, GitHub Release with `.app` + DMG, Sparkle appcast PR). See [`docs/release.md`](docs/release.md) for the full recipe.

## Author

[**mhsb**](https://github.com/michaelhball)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Housekeeping

<div>vinyl icon made by <a href="https://www.flaticon.com/authors/those-icons" title="Those Icons">Those Icons</a> on <a href="https://www.flaticon.com/" title="Flaticon">www.flaticon.com</a></div>
