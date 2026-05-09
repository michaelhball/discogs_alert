# Cutting a macOS release (DMG + Sparkle auto-update)

End-to-end recipe for shipping a new version of the menu-bar `.app` so
existing installs upgrade themselves automatically.

## Prereqs (one-time setup)

1. **Download Sparkle**:
   ```bash
   make sparkle
   ```
   Drops `Sparkle.framework` and the signing tools into `vendor/`.

2. **Generate your EdDSA signing keypair**:
   ```bash
   make keys
   ```
   Sparkle 2 stores the private key in the macOS Keychain (account name
   `discogs_alert`); `make sign` finds it there automatically. The
   target also writes:
   - A **backup of the private key** at
     `~/.discogs_alert_release/eddsa_priv.key`. Back this up
     somewhere safe (1Password, encrypted USB, …) — losing both the
     keychain entry AND this file means existing installs can never
     auto-update.
   - The **public key** at `~/.discogs_alert_release/eddsa_pub.key`,
     which the build reads into the `.app`'s `Info.plist`.

   `make keys` is idempotent: re-running it on a machine with an
   existing key for the `discogs_alert` account just re-extracts the
   public key and refreshes the backup file.

3. **Set up GitHub Pages** for the appcast feed (one-time):
   - This repo already has Pages enabled on `main` / `docs/`. New
   forks need to do this once via GitHub settings (or
   `gh api repos/OWNER/REPO/pages -X POST --input -` with
   `{"source":{"branch":"main","path":"/docs"}}`).
   - The appcast at `docs/appcast.xml` ends up served at
     `https://<owner>.github.io/<repo>/appcast.xml`.
   - That URL is baked into the bundle's `Info.plist` as
     `SUFeedURL`. Override at build time with `DA_APPCAST_URL=…`.

4. **Push the signing keys to GitHub Actions secrets** (one-time):
   ```bash
   make secrets
   ```
   That just runs `gh secret set SPARKLE_PUBLIC_KEY < ~/…/eddsa_pub.key`
   and `gh secret set SPARKLE_PRIVATE_KEY < ~/…/eddsa_priv.key`. The
   release workflow reads both at runtime.

   *Re-running `make secrets` overwrites the secrets in place, so you
   can do this again any time (e.g. after rotating keys).*

## Each release (automated)

The release workflow at `.github/workflows/release.yml` builds, signs,
publishes, and updates the appcast on every `vX.Y.Z` tag push. You only
need to bump the version, commit, tag, push:

```bash
# 1. Bump the version in pyproject.toml AND discogs_alert/__init__.py.
#    Both must match the tag, or the `release` workflow's sanity-check
#    fails fast.
$EDITOR pyproject.toml             # bump [tool.poetry] version
$EDITOR discogs_alert/__init__.py  # bump _FALLBACK_VERSION to match

# 2. Commit, tag, push.
git commit -am "Bump version to 0.1.1"
git tag v0.1.1
git push origin main --tags

# That's it. CI (on macos-latest) takes ~5min and:
#   - builds dist/discogs_alert-0.1.1.dmg
#   - signs it with the EdDSA key from secrets
#   - creates a GitHub Release v0.1.1, uploads the DMG
#   - appends a new <item> to docs/appcast.xml
#   - commits + pushes the appcast change to main
#
# You can watch progress with `gh run watch`.

# 3. (Optional) Verify the published artifacts:
gh release view v0.1.1                # confirm the DMG is attached
curl -fsSI "$(gh release view v0.1.1 --json assets --jq '.assets[0].url')"
```

Existing `.app` installs poll the appcast on launch + once a day,
download the new DMG, verify the EdDSA signature, and prompt the user
to install. No more manual upgrade steps for users.

## Each release (manual fallback)

If the workflow is broken or you want to ship a hotfix from your own
machine, the `make` targets cover the same steps:

```bash
make app                                                    # → dist/discogs_alert.app
make dmg                                                    # → dist/discogs_alert-X.Y.Z.dmg
make sign                                                   # prints sparkle:edSignature="…" length="…"
gh release create vX.Y.Z dist/discogs_alert-X.Y.Z.dmg --generate-notes
python scripts/append_to_appcast.py \
    --version X.Y.Z \
    --signature 'sparkle:edSignature="…" length="…"' \
    --download-url "https://github.com/<owner>/<repo>/releases/download/vX.Y.Z/discogs_alert-X.Y.Z.dmg"
git commit -am "Append vX.Y.Z to appcast"
git push
```

## Sanity-checks

After a release:

- `curl -fsSL https://<owner>.github.io/<repo>/appcast.xml` returns the
  updated XML (Pages can take a minute to refresh).
- `curl -fsSLI <release URL>` returns 200; `Content-Length` matches the
  `length=` you put in the appcast.
- An old `.app` still in `/Applications` opens, sees the new version,
  and offers to upgrade. The "Update available" dialog is Sparkle's
  built-in UI — no work on our side.

## Code signing (optional)

The DMG is **unsigned by default**. macOS Gatekeeper will prompt the
user to right-click → Open on first launch. To clean that up:

1. Get an Apple Developer ID ($99/yr).
2. `codesign --deep --force --options runtime --sign "Developer ID Application: …" dist/discogs_alert.app`
3. `xcrun notarytool submit dist/discogs_alert-X.Y.Z.dmg --apple-id … --wait`
4. `xcrun stapler staple dist/discogs_alert-X.Y.Z.dmg`

Sparkle updates work fine without code signing — Sparkle's own EdDSA
signature is what guarantees update authenticity. Code signing is
purely about the first-launch UX.

## Things that go wrong

- **"discogs_alert can't be opened because Apple cannot check it for
  malicious software"** on first launch — Gatekeeper, not signed.
  Right-click → Open. Or sign / notarize as above.
- **Sparkle says "Update is improperly signed"** — your Info.plist has
  a different `SUPublicEDKey` than the private key that signed the
  release. Re-build the `.app` against the correct public key, or
  re-sign the DMG with the matching private key.
- **The appcast loads but Sparkle says "You're already up to date"** even
  though it shouldn't — the new release's `sparkle:version` isn't higher
  than what's installed. Check the `<sparkle:version>` value in the
  appcast item.
- **Sparkle fails silently with no UI** — check the bundle has Sparkle.framework
  inside `Contents/Frameworks/` (`make app` should report
  "Sparkle bundled"). If it doesn't, run `make sparkle` first.
