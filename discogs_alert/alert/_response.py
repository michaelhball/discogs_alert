"""Shared HTTP-response handling for alerters.

Different alerter providers respond with different error shapes, but the
*meaning* of those shapes is broadly consistent:

- 2xx → success.
- 401 / 403 / 410 → authentication is dead (revoked token, dormant account,
  service-side ban). Retrying won't help; logging at ERROR is the right level.
- 429 → rate limited. The provider may include a `Retry-After` header. We log
  the requested cool-off so the user can diagnose noisy logs.
- Anything else → transient failure; the loop's natural cadence retries.

In all non-2xx cases the alerter returns False so the listing isn't
mark-as-seen'd; next loop iteration retries (assuming the issue clears).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Status codes that mean "your auth is dead, don't bother trying again until
# the user does something" — log loudly so the cause is obvious.
_DEAD_AUTH_STATUSES = (401, 403, 410)


def parse_retry_after_seconds(headers: Mapping[str, Any]) -> float | None:
    """Parse a `Retry-After` HTTP header value into seconds.

    The header can be either a number-of-seconds (integer or float) or an
    HTTP-date. We only handle the seconds form — the date form is rare in
    practice for the alerters we talk to, and would require dragging in a
    parser. Returns None for missing or unparseable values.
    """

    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def log_alerter_failure(
    provider: str,
    status_code: int,
    body: bytes | str,
    headers: Mapping[str, Any] | None = None,
) -> None:
    """Log an alerter HTTP failure at the right level for the response shape.

    Authentication-dead (401/403/410) → ERROR with a hint. Rate-limited (429)
    → WARNING with the parsed Retry-After (if present). Other non-2xx →
    ERROR.
    """

    body_preview = body[:200] if isinstance(body, (bytes, str)) else repr(body)[:200]
    if status_code in _DEAD_AUTH_STATUSES:
        logger.error(
            "%s notification failed (HTTP %s — auth dead, retrying won't help): %s",
            provider,
            status_code,
            body_preview,
        )
        return
    if status_code == 429:
        retry_after = parse_retry_after_seconds(headers or {})
        retry_msg = f" — Retry-After: {retry_after}s" if retry_after is not None else ""
        logger.warning(
            "%s notification rate-limited (HTTP 429%s): %s",
            provider,
            retry_msg,
            body_preview,
        )
        return
    logger.error("%s notification failed (HTTP %s): %s", provider, status_code, body_preview)
