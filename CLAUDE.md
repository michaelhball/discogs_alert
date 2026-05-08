# CLAUDE.md

Working notes for Claude Code on this repo. Update freely as the workflow evolves.

## What this project is

`discogs_alert` polls the Discogs marketplace for releases on a user's wantlist
and sends a notification (Pushbullet / Telegram / …) when a matching listing
appears. Runs locally as a long-lived process or as a `cron`-triggered single
shot, packaged for PyPI and DockerHub.

Entry point: `python -m discogs_alert` → `discogs_alert/__main__.py:main`,
which schedules `discogs_alert.loop.loop` via the `schedule` library.

## How the user works

- **Many small PRs, squash-merged into `main`.** Each PR is a single concern.
  PR title becomes the squash commit title and ends with ` (#NN)`.
- **Direct-to-`main` is fine.** No long-lived feature branches; main is
  always-shippable-ish.
- **CI is the source of truth — merge autonomously.** The user does not want
  to manually review every PR. Workflow:
  1. Open the PR. Wait for the GitHub Actions checks (`ruff`, `tox`,
     `lfs-warning`) using `gh pr checks <PR>`.
  2. If CI passes and coverage isn't regressed, **squash-merge it yourself**
     with `gh pr merge <PR> --squash --delete-branch`.
  3. If CI fails, investigate, push a fix to the same branch, wait for CI
     again. Don't open follow-up PRs for CI fixes — keep the original PR in
     flight until green.
  4. After merging a base PR, update the next PR's base if it was stacked:
     `gh pr edit <PR> --base main`.
  5. End-to-end verification happens at release time, not per PR. The user
     trusts the test suite + CI between releases.
- **Releases are deliberate, not automatic.** Every so often we cut a release:
  1. Open a `Bump version (#NN)` PR that bumps `pyproject.toml`'s `version`.
  2. Merge it.
  3. Tag the merge commit `vX.Y.Z` (matching `pyproject.toml`).
  4. Publish to PyPI manually (`poetry build && poetry publish`) and push the
     Docker image to DockerHub (`miggleball/discogs_alert`). There is no
     GitHub Actions release workflow yet — see the open task to add one.
  5. Summarise the changes since the previous tag for the release notes (use
     `git log vPREV..HEAD --oneline`).
- **Versioning:** still `0.0.x`. Treat any user-facing breakage as worth a
  bump, but the user decides when to cut.

When asked to "make a PR", default to: branch off `main`, single concern,
descriptive title in the past-tense / imperative style the user uses
(e.g. `Replace exchangerate.host with frankfurter.app`,
`Gate marketplace scrapes on /marketplace/stats`).

## Before starting a session

1. **Always `git fetch origin main && git log main..origin/main --oneline` first.**
   This repo's `main` moves between sessions, often with PRs whose scope
   overlaps with whatever you're about to do. We learned this the hard way:
   in May 2026 the entire stack #82–#86 had to be rebased after the user
   merged 13 commits (releases v0.0.20/v0.0.21) that duplicated the early
   PRs' work.
2. **Then `git pull --ff-only` on main** before branching.
3. Sanity-check `pyproject.toml`'s version, the deps, and a quick read of
   recent commits — what's there might already do what you were about to do.

## Repo layout

```
discogs_alert/
  __main__.py        # click CLI, env-var-driven, schedules the loop
  loop.py            # the per-iteration logic
  client.py          # Discogs API + anonymous Selenium scraper
  scrape.py          # BeautifulSoup parsing of the marketplace HTML
  entities.py        # dataclasses for Release, Listing, conditions, etc.
  alert/
    base.py, pushbullet.py, telegram.py, __init__.py (AlerterType + factory)
  util/
    click.py         # NotRequiredIf / RequiredIf / EnumChoice click helpers
    constants.py     # COUNTRIES, CURRENCY_CHOICES, currency symbols
    currency.py      # rate fetching + conversion
    system.py        # time_cache decorator
tests/               # pytest, with `--online` flag to gate network tests
docker/              # Dockerfile + entrypoint
```

## Things to be careful about

- **Rate limits matter a lot.** The user has historically been bitten by:
  - Discogs API (60/min user-token) — `client.UserTokenClient` tracks
    `X-Discogs-Ratelimit-Remaining`; respect it with margin, don't wait
    until `==1`.
  - Discogs marketplace scraping — Cloudflare gets aggressive with repeated
    requests from one IP. Reducing request *volume* matters more than
    rotating user-agents. Prefer cheap API gates (e.g.
    `/marketplace/stats/{id}`) before a full page load.
  - Pushbullet — the v2 API has a low rate limit; `get_all_alerts`
    historically paginated the whole push history every iteration. Local
    dedup (SQLite) is the fix.
  - Currency provider — `freecurrencyapi` (currently on main) needs an API
    key (`DA_CURRENCY_TOKEN`); `Frankfurter` is free, key-less, ECB-backed.
- **Don't run the loop against live APIs while iterating.** Use unit tests
  with fixtures (`tests/conftest.py` already mocks `get_currency_rates`).
  When a manual smoke test is unavoidable, run with a 1-item wantlist, not
  the user's full list.
- **Plain `requests` does NOT work against Discogs marketplace pages.** A
  one-off probe in May 2026 with a realistic Chrome User-Agent returned a
  Cloudflare 403 "Just a moment…" challenge. Future scraper work needs
  `curl_cffi` (TLS-fingerprint impersonation) or Selenium / Playwright;
  `cloudscraper` is unmaintained. When changing the HTTP client, do
  exactly one probe to verify the new client bypasses Cloudflare, save the
  response HTML as a test fixture (`tests/data/marketplace_listing.html`),
  and never hit Discogs from CI.
- **Keep dependencies on a leash.** `selenium` + `webdriver-manager` churn
  their public API. If they break again, that's a hint to drop them.
- **`.env` is gitignored** but contains real tokens. Never `cat` or echo it
  into commit messages, logs, or PR descriptions.

## Concurrent agents

If you spawn a background agent to monitor PRs, be aware:

- The agent operates in the same git working tree as the parent. Concurrent
  `git checkout` / `git merge` / `git push` from both sides will conflict.
- The agent should only touch branches in its explicit watch list. The parent
  should only push to branches it owns. Don't share a branch.
- When the parent is doing a complex operation (e.g. a stack-wide rebase),
  pause the agent first via SendMessage with explicit "stand down" instructions.

## Testing

- **Coverage matters here.** Every PR that touches runtime code must add or
  update tests. The user explicitly wants CI to be trustworthy. Aim for >80%
  with a goal of ~90% by the end of the active stack.
- `tox` runs the full suite. `pytest` directly works too.
- Network-gated tests use `@pytest.mark.online` and `--online`. Don't add
  online-only tests without that marker, and don't make them load-bearing —
  the offline suite must catch regressions on its own.
- Some test files are empty stubs. Fill them out when touching the adjacent
  code; treat empty stubs as a debt, not a license.
- Prefer fixture-based tests over mocks where practical (e.g. saved
  marketplace HTML in `tests/data/`), so a real Discogs HTML change shows up
  as a test diff.

## Style

- `ruff` configured in `pyproject.toml` (E, F, I, TID, W, line-length 120,
  ban relative imports). The new `[tool.ruff.lint]` table layout is required
  on ruff 0.6+.
- `black` is configured for 120 cols; pre-commit hook in
  `.pre-commit-config.yaml`.
- Imports use the `da_xxx` alias convention for in-package modules
  (e.g. `from discogs_alert import entities as da_entities`). Match it.

## When making changes

1. Keep the diff small and the PR scope tight.
2. If a change is user-visible (CLI flags, env vars, alerter behavior),
   update the README in the same PR.
3. If a change affects the runtime contract (new env var, new dependency,
   removed Python version), call it out in the PR body so it can land in
   the release notes later.
4. Don't bump `pyproject.toml`'s version inside a feature PR — version
   bumps live in their own PR (see release flow above).
