# CLAUDE.md

Working notes for Claude Code on this repo. Update freely as the workflow evolves.

## What this project is

`discogs_alert` polls the Discogs marketplace for releases on a user's wantlist
and sends a notification (ntfy / Pushbullet / Telegram / Gmail) when a matching
listing appears. Runs locally as a long-lived process, as a `cron` / `launchd`
single shot, as a macOS menu-bar app, or as a self-contained `.app` bundle.
Packaged for PyPI and DockerHub.

Entry points:
- CLI: `python -m discogs_alert` → `discogs_alert/__main__.py:main` runs
  `asyncio.run(_run(...))` which drives `discogs_alert.loop.loop` on a fixed
  interval (`asyncio.sleep`, not `schedule`).
- Menu-bar: `python -m discogs_alert.menubar` → `MenubarApp` (rumps) wrapping a
  `MenubarController` that owns the worker thread.
- `.app` bundle: built via `make app` / `make dmg`; Sparkle auto-update.

Configuration lives in `~/.discogs_alert/config.toml` (TOML, pydantic-validated)
with `DA_*` env-var overrides on top. The CLI is intentionally tiny: `--config`,
`--once`, `--verbose`, `--log-level`, `--validate-config`, `--print-config`,
`--version`.

## How the user works

- **Many small PRs, squash-merged into `main`.** Each PR is a single concern.
  PR title becomes the squash commit title and ends with ` (#NN)`.
- **Direct-to-`main` is fine for the user (admin bypass on branch protection).**
  Bots can't push direct — they have to PR + you merge.
- **CI is the source of truth — merge autonomously.** The user does not want
  to manually review every PR. Workflow:
  1. Open the PR. Wait for the GitHub Actions checks (`ruff`, `tox`,
     `lfs-warning`).
  2. If CI passes, **squash-merge it yourself** with
     `gh pr merge <PR> --squash --delete-branch`.
  3. If CI fails, push a fix to the same branch; don't open a follow-up PR.
  4. **Retarget downstream PRs *before* merging their base** if you ever stack.
     Squash-merge with `--delete-branch` deletes the head ref synchronously,
     auto-closing dependent PRs whose base was that ref. Use
     `gh pr edit <child> --base main` first.
- **Local checks before push** are wired up via pre-commit
  (`.pre-commit-config.yaml`): ruff + offline pytest. CI runs the full
  tox matrix + coverage gate.

When asked to "make a PR", default to: branch off `main`, single concern,
descriptive title in the past-tense / imperative style the user uses (e.g.
`Add ntfy.sh built-in alerter`, `Drop schedule for a plain sleep loop`).

## Releases

Releases are **automated on tag push**. There is a saved memory note
at `~/.claude/projects/.../memory/release_process.md` with the exact recipe.
Short version when the user says "release X.Y.Z":

1. Bump `version` in `pyproject.toml` and `_FALLBACK_VERSION` in
   `discogs_alert/__init__.py` (both must match the tag).
2. `git commit -am "Bump version to X.Y.Z"`
3. `git tag vX.Y.Z`
4. `git push origin main --follow-tags`

CI on `macos-latest` then builds `.app` + `.dmg`, signs with EdDSA from the
`SPARKLE_PRIVATE_KEY` secret, uploads to a GitHub Release, publishes to PyPI
via trusted publishing, pushes Docker image, and **opens a PR** appending to
`docs/appcast.xml` (direct push to main is blocked by branch protection). The
maintainer one-click-merges that appcast PR; that's the only manual step.

See `docs/release.md` for the full reference.

## Before starting a session

1. **Always `git fetch origin main && git log main..origin/main --oneline` first.**
   This repo's `main` moves between sessions.
2. **Then `git pull --ff-only` on main** before branching.
3. Sanity-check `pyproject.toml`'s version, the deps, and recent commits.

## Repo layout

```
discogs_alert/
  __main__.py        # slim click CLI; loads config, asyncio.run-s the loop
  loop.py            # async per-iteration logic (asyncio.gather + semaphore)
  client.py          # httpx.AsyncClient (API) + curl_cffi AsyncSession (marketplace)
  scrape.py          # BeautifulSoup parsing of marketplace HTML
  entities.py        # pydantic v2 models for Release, Listing, etc.
  config.py          # pydantic schema + TOML loader for ~/.discogs_alert/config.toml
  state.py           # SQLite AlertStore (dedup)
  menubar.py         # rumps menu-bar app + MenubarController
  _sparkle.py        # PyObjC bridge for Sparkle auto-update (only active in .app)
  alert/
    base.py, ntfy.py, pushbullet.py, telegram.py, gmail.py
    __init__.py        # registry + entry-point discovery
    _response.py       # shared HTTP-error logging helper
  util/
    click.py           # NotRequiredIf / RequiredIf / EnumChoice helpers
    constants.py       # COUNTRIES, CURRENCY_CHOICES, currency symbols
    currency.py        # Frankfurter API + on-disk weekly cache + stale fallback
    rate_limit.py      # X-Discogs-Ratelimit-* tracking (sync + async)
    system.py          # time_cache decorator
    wantlist_directives.py  # parses `@max=…` / `@media=…` from Discogs list comments
  py.typed           # PEP 561 marker

docker/              # Dockerfile (poetry-based multi-stage) + launchd plist template
docs/                # release.md, appcast.xml (Sparkle feed served via Pages)
examples/            # config.example.toml
scripts/             # append_to_appcast.py (used by the release workflow)
tests/               # pytest + pytest-asyncio (auto mode); offline by default,
                     #   network tests gated with @pytest.mark.online + --online
.github/workflows/   # pr_checks.yml + release.yml (tag-triggered full release)
Makefile             # make app / dmg / sparkle / keys / sign / secrets
setup_app.py         # py2app config for the .app bundle
```

## Things to be careful about

- **Rate limits matter.** Patterns the user has been bitten by:
  - Discogs API (60/min for the user token) — `client.UserTokenClient` tracks
    `X-Discogs-Ratelimit-Remaining`. `RateLimitGuard` sleeps proactively and
    cooperatively (async lock).
  - Discogs marketplace (Cloudflare) — `AnonClient` uses `curl_cffi` with
    `impersonate="chrome124"` for TLS fingerprinting. The async loop caps
    parallelism via `asyncio.Semaphore(max_concurrency=6)`. The cheap
    `/marketplace/stats/{id}` gate skips the full scrape when nothing's listed.
  - Pushbullet — silently 401s when the account is dormant; open the app
    monthly. Telegram dedup historically broken; SQLite `AlertStore` fixed it.
- **Don't run the loop against live APIs while iterating.** Unit tests use
  fixtures (`tests/conftest.py` mocks `get_currency_rates`; HTML fixtures in
  `tests/data/`). When a manual smoke test is unavoidable, scope the wantlist
  small.
- **Plain `requests`/`httpx` don't work against marketplace pages** —
  Cloudflare returns a 403 "Just a moment…" challenge without TLS
  impersonation. Stick with `curl_cffi` for `AnonClient`. Use `httpx` for the
  typed API client (no Cloudflare there).
- **`.env` is gitignored** but contains real tokens. Never `cat` or echo it
  into commit messages, logs, or PR descriptions. The hook blocks `grep
  DA_DISCOGS_TOKEN .env` patterns; use `grep -l` to test presence or pipe via
  `set -a; source .env; set +a` to flow values into child processes without
  echoing.
- **GH Actions disallows `secrets.*` in `if:` conditions.** They'll silently
  fail to parse the workflow. Gate on `vars.*` or check existence inside a
  step.

## Concurrent agents

If you spawn a background agent to monitor PRs or do other long-running work:

- The agent operates in the same git working tree as the parent. Concurrent
  `git checkout` / `git push` from both sides will conflict. Stick the parent
  to a different branch.
- The agent should only touch branches in its explicit watch list. The parent
  should only push to branches it owns.
- If you suspect the agent is auto-closing PRs (auto-close cascade after a
  squash-merge with `--delete-branch`), check whether the PR had downstream
  PRs whose bases pointed at it. Recover by recreating via
  `gh pr create --base main --head <branch>`.

## Testing

- **Coverage matters.** Every PR that touches runtime code must add or update
  tests. CI gate: `--cov-fail-under=88`. Aim to keep it green or rising;
  today ~89%.
- `tox` runs the full matrix (Python 3.10–3.13). `pytest -m 'not online'`
  runs the offline suite locally in ~1s.
- `pytest-asyncio` is in `auto` mode (`asyncio_mode = "auto"` in pyproject) —
  any `async def test_*` runs in an event loop automatically.
- Some environments have a stale `pytest-lazyfixture` plugin that crashes
  pytest collection. The pre-commit and CLI invocations include
  `-p no:lazy-fixture` defensively.
- Network-gated tests use `@pytest.mark.online` and `--online`. Don't add
  online-only tests without that marker, and don't make them load-bearing.
- Prefer fixture-based tests over mocks where practical — saved marketplace
  HTML in `tests/data/` catches real Discogs HTML changes as test diffs.

## Style

- `ruff` configured in `pyproject.toml` (E, F, I, TID, W, line-length 120,
  ban relative imports). Auto-fixes via the pre-commit hook on commit.
- Imports use the `da_xxx` alias convention for in-package modules (e.g.
  `from discogs_alert import entities as da_entities`). Match it.

## When making changes

1. Keep the diff small and the PR scope tight.
2. If a change is user-visible (CLI flags, env vars, alerter behavior, config
   schema), update the README in the same PR. The "Adding more alerters"
   section of the README has the recipe for an in-tree new alerter — third-
   party / separate-package alerters are explicitly NOT a supported direction
   anymore (we rolled that back; the entry-point discovery mechanism remains
   internally because the in-tree built-ins use it).
3. If a change affects the runtime contract (new env var, new dependency,
   removed Python version), call it out in the PR body so it can land in
   the release notes later.
4. Version bumps go in the release commit (`Bump version to X.Y.Z`); they
   don't go in feature PRs.
