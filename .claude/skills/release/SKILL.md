---
name: release
description: Cut a discogs_alert release end to end — bump the version on main, tag it, let the tag-triggered GitHub Actions workflow build/publish, merge the appcast PR, then upgrade the always-on launchd instance to the published build and verify it. Defaults to a patch bump; asks before any minor/major bump.
argument-hint: "[X.Y.Z]"
---

# /release — cut and deploy a release

Usage: `/release` (next patch, e.g. 0.1.0 → 0.1.1) or `/release 0.1.3`.
Argument given: `$ARGUMENTS`

The mechanics are already automated by `.github/workflows/release.yml` (tag
push → sdist/wheel → PyPI, GitHub Release, Docker image, macOS .app + DMG,
appcast PR). This skill drives that pipeline and then upgrades the running
service described in `docs/deployment.md`. Read `docs/release.md` if anything
below is surprising.

## 0. Version policy — read before doing anything

- **Default is the smallest possible bump: patch** (`X.Y.Z` → `X.Y.(Z+1)`).
- If the requested version (or the one you would pick) is a **minor or major
  bump** relative to the current version, **stop and ask the user to confirm
  with AskUserQuestion**, even if they typed that version themselves. Offer the
  patch version as the recommended alternative. Do not tag until they confirm.
- Never release a version that is not strictly greater than the current one,
  and never re-tag an existing tag.

## 1. Preflight (all read-only)

```bash
git fetch origin main --tags
git status --porcelain            # must be empty apart from untracked files
git log --oneline main..origin/main   # must be empty after `git pull --ff-only` on main
gh pr list --state open           # note anything still open; don't release over a half-merged change
current="$(grep -E '^version = ' pyproject.toml | cut -d'"' -f2)"
grep -E '^_FALLBACK_VERSION = ' discogs_alert/__init__.py   # must equal $current
gh run list --workflow=release.yml --limit 3       # is a previous release still running/failed?
```

Decide the target version per section 0. Check it doesn't already exist:
`git tag -l vX.Y.Z` must print nothing and `gh release view vX.Y.Z` must fail.

Summarise to the user in one line what will be released (current → target,
and the list of commits since the last tag: `git log --oneline v$current..main`).

## 2. Version bump via PR

Branch protection blocks bots from pushing to `main` directly, so the bump
goes through a PR like every other change. Both files must change together;
the release workflow fails fast if the tag and `pyproject.toml` disagree.

```bash
git checkout -b release/vX.Y.Z origin/main
sed -i '' 's/^version = ".*"/version = "X.Y.Z"/' pyproject.toml
sed -i '' 's/^_FALLBACK_VERSION = ".*"/_FALLBACK_VERSION = "X.Y.Z"/' discogs_alert/__init__.py
git diff --stat            # exactly 2 files, 1 line each
git commit -am "Bump version to X.Y.Z"      # the pre-commit hooks must pass; if `poetry-check`
                                            # complains about a stale lock, run
                                            # `uvx --from poetry==1.8.4 poetry lock` first
git push -u origin release/vX.Y.Z
gh pr create --base main --title "Bump version to X.Y.Z" --body "Release prep for vX.Y.Z. Tag is pushed after this merges."
gh pr checks <N> --watch
gh pr merge <N> --squash --delete-branch    # only when every check passed
git checkout main && git pull --ff-only
```

## 3. Tag and push (this is the trigger)

Tag the squash-merge commit on `main`, never the branch commit:

```bash
git log --oneline -1                # must be "Bump version to X.Y.Z (#N)"
git tag vX.Y.Z
git push origin vX.Y.Z
```

## 4. Wait for the release workflow

```bash
gh run list --workflow=release.yml --limit 1        # grab the run id for the tag
gh run watch <run-id> --exit-status                 # blocks until done; ~5 min (macOS job is the slow one)
gh run view <run-id> --json jobs --jq '.jobs[] | "\(.name): \(.conclusion)"'
```

Jobs and what "done" means:

| job | must be | notes |
|---|---|---|
| Build distribution | success | |
| Publish to PyPI | success | `continue-on-error: true` — a failure does NOT fail the run. Check it explicitly. |
| Create GitHub Release | success | `gh release view vX.Y.Z` shows sdist + wheel |
| Publish Docker image | success or skipped | skipped when `vars.DOCKERHUB_USERNAME` is unset |
| Build macOS .app + .dmg, sign, append to appcast | success | uploads the DMG and opens the appcast PR |

Then wait for the wheel to be visible on PyPI (CDN lag of a minute or two):

```bash
until curl -fsS "https://pypi.org/pypi/discogs-alert/X.Y.Z/json" >/dev/null; do sleep 15; done
```

If "Publish to PyPI" failed, say so plainly and use the GitHub Release wheel in
step 6 instead (`gh release download vX.Y.Z -p '*.whl' -D /tmp/da-release`).

## 5. Merge the appcast PR

The macOS job opens a PR titled `Append vX.Y.Z to appcast`. Merging it is what
lets existing `.app` installs see the update.

```bash
gh pr list --search "Append vX.Y.Z to appcast" --json number --jq '.[0].number'
gh pr checks <M> --watch
gh pr merge <M> --squash --delete-branch
git pull --ff-only
```

## 6. Upgrade the always-on instance

Only if this machine runs the service (`launchctl print gui/$UID/com.discogsalert`
succeeds). Otherwise skip this section and say so.

```bash
uv pip install --python ~/.discogs_alert/venv/bin/python "discogs-alert==X.Y.Z"
#   fallback when PyPI publish failed:
#   uv pip install --python ~/.discogs_alert/venv/bin/python /tmp/da-release/discogs_alert-X.Y.Z-*.whl
~/.discogs_alert/venv/bin/python -m discogs_alert --version        # must print X.Y.Z
~/.discogs_alert/venv/bin/python -m discogs_alert --validate-config
launchctl bootout gui/$UID/com.discogsalert
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.discogsalert.plist
```

`RunAtLoad` fires an iteration immediately. Wait for it to finish and check it:

```bash
until grep -q "iteration finished" ~/Library/Logs/discogs_alert.log; do sleep 5; done   # or watch the tail of the log
launchctl print gui/$UID/com.discogsalert | grep -E "state =|last exit"    # last exit code = 0
grep -ciE "traceback|error" ~/Library/Logs/discogs_alert.log                # explain anything non-zero
```

Do not truncate the log; the user may want the previous runs.

## 7. Report

One short message: version released, links (`gh release view vX.Y.Z --web`
URL, PyPI URL), which jobs succeeded/skipped/failed, whether the local service
was upgraded and its first-run result, and anything left for the user.

## If something fails midway

- Bump PR red → fix on the same branch, don't open a second PR.
- Tag pushed but workflow failed before "Create GitHub Release" → fix `main`
  via a normal PR, then **delete the tag** (`git push --delete origin vX.Y.Z && git tag -d vX.Y.Z`)
  and re-run from step 3. Never reuse a tag that already produced a Release.
- Workflow succeeded but local upgrade failed → the release is still valid;
  reinstall the previous version (`uv pip install ... "discogs-alert==<previous>"`),
  restart the agent, and report the upgrade failure separately.
