# Mac menu-bar app proposal

A spec for what a non-technical-user-friendly version of `discogs_alert`
could look like, packaged as a Mac menu-bar app. This is a thinking-out-loud
doc; nothing here is committed work yet.

## Goal

Right now `discogs_alert` is a CLI for developers: edit env vars, write a
JSON file (or paste a Discogs list ID), run `python -m discogs_alert`, leave
a terminal open. A casual record collector can't reasonably set this up —
they'd need a Discogs token, a Pushbullet/Telegram account, comfort with the
command line, and tolerance for a black terminal window forever-open.

The menu-bar app should let a casual collector:

1. Install a `.app`, click it, sign in with Discogs (OAuth).
2. Pick a Discogs list to watch (or build one in the app).
3. Click "start" and forget about it. Notifications arrive when matches happen.
4. Click the menu-bar icon any time to see status (last poll, next poll,
   recent alerts, why a listing was filtered).

## Architectural shape

```
       ┌──────────────────────────────────────┐
       │  discogs_alert.app   (signed bundle) │
       │                                      │
       │  ┌────────────┐    ┌──────────────┐  │
       │  │ rumps menu │ ←→ │ asyncio core │  │
       │  └────────────┘    └──────┬───────┘  │
       │        │                  │          │
       │        │  prefs UI        │          │
       │        ▼                  ▼          │
       │  ┌────────────┐    ┌──────────────┐  │
       │  │ ~/Library/ │    │ AlertStore   │  │
       │  │ Application│    │ (sqlite)     │  │
       │  │ Support/   │    └──────────────┘  │
       │  │ discogs_…  │                      │
       │  └────────────┘                      │
       │                                      │
       │  Bundles: Python 3.12 + curl_cffi    │
       │           + discogs_alert_core       │
       └──────────────────────────────────────┘
```

The app is a thin shell around the existing `discogs_alert` library code.
Reuses `loop.py`, `client.py`, `state.py`, `alert/*` unchanged. The shell
adds a menu-bar UI, OAuth flows, settings panel, and a launchd agent for
background-running.

## Scope decisions

### UI framework: `rumps` (Python) vs SwiftUI

**Use `rumps`.** It's a small native-feeling menu-bar wrapper for Python.
The whole app stays in Python, packaging is `py2app`, no Xcode dance, no
Swift–Python bridge. A fully-Swift app would be nicer but doubles the code
and wouldn't add user-visible value for a menu-bar tool.

### Packaging: `py2app` → signed `.app`

`py2app` bundles a Python interpreter + dependencies + the rumps shell into
a relocatable `.app`. Signed with the user's Apple Developer cert (~$99/yr)
and notarized via `notarytool`. The `release.yml` workflow grows a third
job that builds, signs, and attaches the `.app.zip` to the GitHub Release.

### Discogs OAuth (replace user-token for the app)

The CLI takes a `DA_DISCOGS_TOKEN`. The app should do real OAuth so a
non-technical user never sees a token string. Discogs has OAuth 1.0a (yes,
in 2026 — they're slow). Implement a small OAuth flow:

1. Click "Connect to Discogs" → opens the browser.
2. User logs in to Discogs and authorises the app.
3. Discogs redirects to `localhost:NNNN/callback` (we run a one-shot HTTP
   listener for this).
4. Store the access-token + secret in macOS Keychain via `keyring`.

Keychain storage means the user doesn't have a `.env` file anywhere; macOS
asks "discogs_alert wants to use a password from your keychain" once.

### Alerter: native macOS notifications

Inside a Mac app there's no need for Pushbullet or Telegram — `osascript`
or `pyobjc-framework-UserNotifications` can pop a native notification. New
alerter type `MacOSAlerter` lives in the app shell, not the core library.

The Pushbullet/Telegram alerters stay available — power users may want to
keep getting alerts on their phone.

### Settings UI

A simple SwiftUI-styled preferences window (`rumps.Window` for the simple
form, or pyobjc for a real `NSPreferencePane`) with:

- Discogs list picker (autocompletes from the user's lists).
- Or: a release picker + per-release filters (price, condition, country).
- Min media/sleeve condition global default.
- Country whitelist/blacklist.
- Currency.
- Alert channel: macOS native / Pushbullet / Telegram (multi-select).

All saved to `~/Library/Application Support/discogs_alert/config.toml`.
The CLI continues to honour env vars; the app uses the config file. They
don't conflict.

### Launchd agent for background running

`com.discogsalert.daemon.plist` registered in `~/Library/LaunchAgents/`,
auto-starts on login, runs `discogs_alert.app` headless. The menu-bar
icon becomes the user's interface to the daemon (status, pause/resume,
recent alerts).

## Engineering prerequisites

This proposal *depends on* one redesign-proposal item: **#6 (core/CLI
split)**. The app needs to import `discogs_alert_core` directly without
dragging click + schedule + the CLI argv parsing.

Without that, the app would have to subprocess the CLI, which is gnarly.

## Rough phasing

1. **Phase 0 (prereq):** core/CLI split (~1 day).
2. **Phase 1: minimum viable menu-bar app (~3–5 days):**
   - rumps shell with one menu: status / start-stop / open-prefs / quit.
   - Loads token from env var (no OAuth yet) — same UX as the CLI but in a window.
   - macOS-native notifications.
   - py2app bundle.
3. **Phase 2: settings UI and Discogs OAuth (~3 days):**
   - Preferences window with all the CLI options.
   - OAuth replacing the env-var token.
   - Keychain-backed storage.
4. **Phase 3: signing + notarization + release-workflow integration (~1 day):**
   - Apple Developer cert.
   - `release.yml` builds, signs, notarizes, attaches to GitHub Release.
5. **Phase 4: nice-to-haves:**
   - Recent-alerts history view.
   - "Why was this skipped?" view per release (uses the
     `stats_skip_reason` data we already compute).
   - Drag-and-drop a Discogs URL onto the menu-bar icon to add to wantlist.

## What this is NOT

- A web app. Discogs's OAuth + the loop's shape don't suit serverless.
- A mobile app. iOS would mean App Store approval and a much bigger lift.
  Casual users on iOS get notifications via the existing Pushbullet
  integration.
- An enterprise tool. Single-user, single-machine, runs locally.

## Open questions (for when we actually start)

- Does Discogs allow OAuth callback to localhost? (Need to check; some OAuth
  providers reject `http://localhost`.) If not, we can ship a custom URL
  scheme handler.
- How big does the bundled `.app` end up? Python + curl_cffi + dependencies
  → maybe 80–120MB. Acceptable for a desktop app, painful if we ever want
  to App-Store it.
- Multi-account: should one Mac user be able to watch *two* Discogs accounts'
  lists (e.g. their personal + a partner's)? Probably yes — design the
  config file as a list of accounts, not a singleton.
