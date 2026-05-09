# Holistic redesign proposal

A design doc for what `discogs_alert` could become if we rebuilt the
architecture with everything we know now. The current code (post stack #87–#99)
works well — this is exploratory, not a commitment to do any of it. **Each
section is independent**; we can pick one or two pieces to pursue and leave
the rest for later, or never.

## Recap: what the project is now

```
   ┌──────────────┐
   │  __main__.py │  click CLI, env-var driven, sets up loop_kwargs
   └──────┬───────┘
          │
   ┌──────▼───────┐
   │   schedule   │  every N minutes
   └──────┬───────┘
          │
   ┌──────▼─────────────────────────────────────────────────────┐
   │                       loop()                               │
   │                                                            │
   │  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
   │  │UserTokenClient─┐ │  AnonClient  │    │  AlertStore   │  │
   │  │ (api.discogs) │ │ (curl_cffi)  │    │   (sqlite)    │  │
   │  └─────────────┘ │ └──────────────┘    └───────────────┘  │
   │                  │        │                                │
   │  load_wantlist ──┘        │                                │
   │       │                   │                                │
   │       ▼                   ▼                                │
   │  for release in shuffled wantlist:                         │
   │    if stats says no listings → skip                        │
   │    else fetch marketplace HTML, parse, filter, alert       │
   │                                                            │
   └────────────────────────────────────────────────────────────┘
```

Per-iteration cost is dominated by the marketplace scrape (one HTTP request
per "interesting" release; cheap stats call to gate it). With curl_cffi this
is on the order of ~50ms each. Scheduling is naive — every release in the
wantlist is checked at the same cadence, regardless of whether it's a
once-in-a-decade ultra-rare or a routinely-listed common item.

## What I'd consider redesigning

### 1. Per-release adaptive scheduling

Today every release is polled at the same frequency (`--frequency`, default
60/hr). That's wasteful for releases with hundreds of listings continuously
available, and risks missing ultra-rare ones if the user's wantlist gets long.

**Proposal:** weight the schedule by the release's "scarcity score":
- `num_for_sale` from `/marketplace/stats` (cached) → cheaper.
- `lowest_price` vs `price_threshold` proximity.
- Time-since-last-listing (how often new listings appear).

Implementation: a per-release "next check at" timestamp stored in the
`AlertStore` SQLite, updated each iteration. The loop becomes "fetch all
releases whose next-check time has passed". Hot releases get checked every
minute; dormant ones every hour. Net rate-limit pressure goes down further
even on huge wantlists.

**Cost:** ~150 lines of new code + a small schema migration.
**Benefit:** maybe 5–10× more wantlist capacity for the same upstream load.

### 2. Async loop instead of `schedule` + `time.sleep`

`schedule` is a polling library that wakes up every second to see if anything
needs running. It works but it's wasteful and the loop is fully synchronous —
one slow Discogs API call blocks the whole iteration.

**Proposal:** async `httpx` + `asyncio.gather` with a small concurrency limit
(say 4 parallel marketplace requests, respecting Discogs rate limits). The
schedule itself becomes `asyncio.sleep(60 / frequency)`. The Discogs API
client and scraper become async. `curl_cffi` has async support already.

**Cost:** rewrite of `loop.py`, `client.py`, `state.py` to be async-aware
(SQLite is fine sync inside an executor). Maybe 200–300 lines of changes.
**Benefit:** the wall-clock cost of one loop iteration becomes
`max(per_release_cost)` instead of `sum(per_release_cost)`. For a wantlist
of 100 releases at ~50ms each, that's 50ms vs 5s — and a deeper pipeline
means the user can use higher frequency without piling on Discogs.

### 3. Replace `dacite` with `msgspec`

`dacite` is fine but slow and has surprising edge cases (the
`Listing(**dict)` bug in #86 came from it). `msgspec` is ~50× faster, does
runtime type validation, and has cleaner error messages. Drop-in replacement
for `entities.py`.

**Cost:** small refactor in `entities.py` and `client.py`.
**Benefit:** faster, fewer footguns, better error messages when Discogs changes
their JSON shape.

### 4. Replace `schedule` with native cron support

`schedule` is in-process — if the loop is killed, scheduling stops. The user
already has a way to run as cron (the README `--test` flag), so the
in-process scheduler is mostly redundant. The CLI could:

- Run once and exit (the current `--test` flag, but make it the default).
- Provide `discogs_alert install-cron <interval>` that writes the user's
  crontab entry for them.
- Drop the `schedule` dep entirely.

**Cost:** delete `schedule`, simplify `__main__.py`, add a tiny `install-cron`
helper. Maybe 50 lines net.
**Benefit:** less code to maintain; survives reboots / kills cleanly; one
fewer runtime dep.

### 5. Make `Alerter` pluggable via entry points

Right now adding a new alerter means editing `discogs_alert/alert/__init__.py`
to add to the `AlerterType` enum and the `get_alerter` factory. That's fine
for a handful but doesn't scale.

**Proposal:** declare alerters as Python entry points
(`discogs_alert.alerters` group). Adding `ntfy.sh` becomes a separate package
or a config file, not a core-codebase change. The user could pip-install
`discogs-alert-ntfy` and it'd be picked up automatically.

**Cost:** small refactor in `alert/__init__.py` (~30 lines), update README.
**Benefit:** community can contribute alerters without forking. The user has
mentioned wanting "many more alerting options eventually".

### 6. Monorepo split: `discogs_alert_core` + UI shell

The user wants a Mac menu-bar app for non-technical users. The cleanest way
to support both the CLI and a future GUI is to split:

- `discogs_alert_core`: the loop, clients, state, alerters. Pure library, no
  CLI. Importable from anywhere.
- `discogs_alert`: the CLI shell + scheduler around the core. Current behavior.
- `discogs_alert_menubar` (future): a [`rumps`](https://rumps.readthedocs.io/)
  or SwiftUI shell that calls `core` directly. Settings in a UI, no env vars.

**Cost:** moderate — restructure into a `src/` layout with two packages, but
no behavior changes. Maybe a day's work.
**Benefit:** the Mac app can ship without dragging click + schedule along, and
future shells (web, mobile, system tray on Linux) become trivial.

### 7. Replace `dataclasses` + `dacite` with `pydantic v2`

If we're already considering rewriting `entities.py` (see #3), `pydantic v2`
is faster than `msgspec` for our use case (mostly JSON I/O), better
ecosystem, and gives us free settings management for `__main__.py` (replace
40+ `click.option` decorators with one `BaseSettings` subclass).

**Cost:** larger refactor than `msgspec`, but consolidates entities and
settings into one well-trodden library.
**Benefit:** cleaner code, less boilerplate, validation messages ten times
better than click's.

### 8. End-to-end testing harness with VCR

We have great unit tests but no integration tests. Adding `vcrpy` (or
`pytest-recording`) lets us record one real Discogs interaction and replay
it deterministically forever. Combined with the existing
`tests/data/marketplace_listing_real.html` fixture, we'd cover the full
loop end-to-end without hitting Discogs from CI.

**Cost:** new dev dep, ~50 lines of test scaffolding, one careful capture
session.
**Benefit:** catch regressions across module boundaries (e.g. the bs4
`text=` deprecation) at unit-test speed.

### 9. Observability

Right now logs are info-level only and there's no surface for "how many
alerts last week / how often does Discogs throttle me / which releases are
generating false-positive alerts". A small metrics surface — even just
SQLite-backed counters that the CLI can dump — would help users tune their
filters and would give the (eventual) menubar app something to display.

**Cost:** small (existing `AlertStore` can hold this), maybe ~80 lines.
**Benefit:** opens the door for the menubar UI's "stats" panel.

## What I would NOT redesign

- **The scraper.** It works against current Discogs HTML and the synthetic +
  real fixtures catch regressions. Don't touch it without a real reason.
- **The local SQLite dedup (`state.py`).** It's small, simple, and exactly
  the right shape.
- **The `RateLimitGuard` + `/marketplace/stats` gate.** Both pull a lot of
  weight for very little code.

## Suggested ordering

If you want to do *any* of this, my recommended order:

1. **#5 (entry-point alerters)** — smallest, future-proofs the alerter
   ecosystem before we add 5 more alerters.
2. **#1 (adaptive scheduling)** — biggest user-facing benefit (more wantlist
   capacity), and the data is already in the local SQLite store.
3. **#4 (drop schedule)** — small win, makes long-running deployments more
   robust.
4. **#6 (core/CLI split)** — only if you actually decide to build the Mac app.
5. **Everything else (#2/#3/#7/#8/#9)** — nice-to-haves, do when something
   else needs them.

None of this is urgent. Current main is in great shape; this is "where to go
next when the urge strikes".
