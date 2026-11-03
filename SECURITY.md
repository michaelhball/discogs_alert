# Security

Report a vulnerability privately through the "Report a vulnerability" button on this repository's Security tab, or by email to michael.h.s.ball@gmail.com. Do not open a public issue for it.

You can expect an acknowledgement within a week. Fixes ship as a normal release, and the release notes name the advisory.

Only the latest release is supported.

## What the project handles

- Your Discogs token and alerter tokens live in `~/.discogs_alert/config.toml` (keep it readable by you only: `chmod 600`) or in `DA_*` environment variables. Logs and `--print-config` mask them.
- The program talks to `api.discogs.com`, `www.discogs.com`, `api.frankfurter.dev` and the alerter you configured, and nothing else.
- The macOS app installs updates only when their Sparkle signature matches the public key built into the app.
