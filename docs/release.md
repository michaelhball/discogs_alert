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
   - The **public key** goes into `~/.discogs_alert_release/eddsa_pub.key`
     and is read by the build into the `.app`'s `Info.plist`.
   - The **private key** at `~/.discogs_alert_release/eddsa_priv.key`
     signs each DMG. **Back this up.** Lose it and you'll have to ship a
     new public key (which means existing installs can never auto-update).

3. **Set up GitHub Pages** for the appcast feed (one-time):
   - In the repo's settings, enable Pages from `main` / `docs/`.
   - The appcast lives at `docs/appcast.xml` and ends up served at
     `https://<owner>.github.io/<repo>/appcast.xml`.
   - That URL is what's baked into the bundle's `Info.plist` as
     `SUFeedURL`. Override at build time with `DA_APPCAST_URL=...`.

## Each release

```bash
# 1. Bump the version in pyproject.toml.
$EDITOR pyproject.toml          # bump [tool.poetry] version
$EDITOR discogs_alert/__init__.py  # bump _FALLBACK_VERSION to match

# 2. Tag the commit (Sparkle ignores the tag name itself but it's nice for git log).
git commit -am "Bump version to 0.1.1"
git tag v0.1.1
git push --tags

# 3. Build the .app and the .dmg.
make app
make dmg

# 4. Sign the DMG. `make sign` prints something like:
#       sparkle:edSignature="..." length="..."
#    Copy those two values; you'll paste them into the appcast below.
make sign

# 5. Upload the DMG to a GitHub Release for v0.1.1.
gh release create v0.1.1 dist/discogs_alert-0.1.1.dmg --notes "0.1.1 release notes…"

# 6. Edit docs/appcast.xml — add a new <item> at the top with:
#      - <enclosure url=…> pointing at the GitHub release URL
#      - sparkle:edSignature and length from step 4
#      - <pubDate> in RFC 822 format
#      - <description> with a short HTML changelog
#    Commit + push docs/appcast.xml; Pages picks it up within a minute.
$EDITOR docs/appcast.xml
git commit -am "Append v0.1.1 to appcast"
git push

# 7. Existing installs poll the appcast on launch + once a day. They'll
#    notice the new <item>, download the DMG, verify the EdDSA sig, and
#    prompt the user to update.
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
