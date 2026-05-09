"""macOS menu-bar app for ``discogs_alert``.

Wraps the async loop in a ``rumps.App`` shell, so the user can see status,
trigger a one-shot check, and open their config / state files from a menu
in the system status bar instead of a terminal.

This module is **macOS-only** because ``rumps`` imports AppKit. It's
intentionally an optional install — ``pip install discogs_alert[menubar]``
pulls in ``rumps``; without that, importing this module raises a clear
error rather than failing somewhere deeper.

For "always-on" notifications when the Mac is asleep or you're away from
the computer, the menu-bar app is **not** the right tool — see
``docs/launchd.md`` for the recommended cron-style alternative that uses
the same ``config.toml`` and runs as a system daemon.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from discogs_alert import (
    client as da_client,
    config as da_config,
    entities as da_entities,
    loop as da_loop,
    state as da_state,
)
from discogs_alert.util import constants as dac

logger = logging.getLogger(__name__)


# rumps is a hard requirement for actually running the app, but we want
# importing this module on a non-Mac box (e.g. for testing or for simply
# running `python -c "import discogs_alert"`) to not blow up. The import is
# delayed until `_require_rumps()` is called.
try:
    import rumps  # type: ignore
except ImportError:  # pragma: no cover — exercised on Linux CI
    rumps = None


class MenubarController:
    """The data-and-behaviour part of the menu-bar app.

    Decoupled from ``rumps`` so the loop wiring, status string formatting,
    and config-reading paths can be unit-tested without an AppKit display.
    The real ``rumps.App`` (in ``MenubarApp`` below) just calls into this.
    """

    def __init__(self, cfg: da_config.Config):
        self.cfg = cfg
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        # Reference to the worker thread's asyncio event loop, set when the
        # worker starts. Used by `check_now()` to wake the sleep that's
        # gating the next iteration.
        self._asyncio_loop: Optional[asyncio.AbstractEventLoop] = None
        self._tick_event: Optional[asyncio.Event] = None
        # Latest status, updated after every iteration.
        self.last_check_at: Optional[datetime] = None
        self.last_alerts_24h: int = 0
        self.last_alerts_total: int = 0
        self.last_error: Optional[str] = None

    # ---- status formatting --------------------------------------------

    def status_title(self) -> str:
        """One-line summary used as the menu-bar title."""

        if self.last_error is not None:
            return "🎵 ⚠️"
        if self.last_check_at is None:
            return "🎵"
        return "🎵"

    def last_check_str(self) -> str:
        if self.last_check_at is None:
            return "Last check: never"
        return f"Last check: {self.last_check_at.strftime('%H:%M:%S')}"

    def alerts_str(self) -> str:
        return f"Alerts (24h): {self.last_alerts_24h} / total: {self.last_alerts_total}"

    def error_str(self) -> Optional[str]:
        return None if self.last_error is None else f"⚠️ {self.last_error}"

    # ---- loop integration ---------------------------------------------

    def _build_loop_kwargs(self) -> dict:
        """Translate the pydantic Config into the kwargs that ``loop.loop`` accepts.

        Mirrors the shape ``__main__.main`` uses. Kept here (not on the
        Config class) so changes to ``loop.loop``'s signature don't bleed
        into the schema.
        """

        cfg = self.cfg
        alerter_kwargs: dict = {}
        if cfg.alerter.type.upper() == "PUSHBULLET":
            alerter_kwargs = {"pushbullet_token": cfg.alerter.pushbullet.token}
        elif cfg.alerter.type.upper() == "TELEGRAM":
            alerter_kwargs = {
                "telegram_token": cfg.alerter.telegram.token,
                "telegram_chat_id": cfg.alerter.telegram.chat_id,
            }
        elif cfg.alerter.type.upper() == "NTFY":
            alerter_kwargs = {
                "ntfy_topic": cfg.alerter.ntfy.topic,
                "ntfy_server": cfg.alerter.ntfy.server,
                "ntfy_token": cfg.alerter.ntfy.token,
            }
        return dict(
            discogs_token=cfg.discogs_token,
            list_id=cfg.wantlist.list_id,
            wantlist_path=cfg.wantlist.path,
            user_agent=cfg.user_agent,
            country=cfg.country,
            currency=cfg.currency,
            seller_filters=da_entities.SellerFilters(
                min_seller_rating=cfg.seller.min_rating,
                min_seller_sales=cfg.seller.min_sales,
            ),
            record_filters=da_entities.RecordFilters(
                min_media_condition=da_entities.CONDITION[cfg.record.min_media_condition],
                min_sleeve_condition=da_entities.CONDITION[cfg.record.min_sleeve_condition],
            ),
            country_whitelist=set(dac.COUNTRIES[c] for c in cfg.country_filters.whitelist),
            country_blacklist=set(dac.COUNTRIES[c] for c in cfg.country_filters.blacklist),
            alerter_type=cfg.alerter.type.upper(),
            alerter_kwargs=alerter_kwargs,
            state_path=cfg.runtime.state_path,
            use_stats_gate=cfg.runtime.stats_gate,
            max_concurrency=cfg.runtime.max_concurrency,
            prune_after_days=cfg.runtime.prune_after_days,
            verbose=cfg.runtime.verbose,
        )

    async def _run_one_iteration(  # pragma: no cover — needs a real Discogs token + network
        self,
        user_token_client: da_client.UserTokenClient,
        anon_client: da_client.AnonClient,
    ) -> None:
        await da_loop.loop(
            **self._build_loop_kwargs(),
            user_token_client=user_token_client,
            client_anon=anon_client,
        )
        with self._lock:
            self.last_check_at = datetime.now()
            self.last_error = None
            try:
                with da_state.AlertStore(self.cfg.runtime.state_path) as store:
                    s = store.stats()
                self.last_alerts_24h = s["last_24h"]
                self.last_alerts_total = s["total"]
            except Exception:
                logger.exception("failed to read alert store stats")

    async def _loop_forever(self) -> None:  # pragma: no cover — runs in the worker thread, needs network
        """The async main loop the worker thread runs.

        Two ways out of the inter-iteration sleep:
        1. The interval expires (normal cadence).
        2. ``self._tick_event`` fires — set via ``check_now()`` from the
           AppKit thread when the user clicks "Check now".
        """

        interval_seconds = max(1, int(3600 / self.cfg.frequency))
        # Save loop + event so the AppKit thread can poke us mid-sleep.
        self._asyncio_loop = asyncio.get_running_loop()
        self._tick_event = asyncio.Event()
        user_token_client = da_client.UserTokenClient(
            self.cfg.user_agent, self.cfg.discogs_token
        )
        anon_client = da_client.AnonClient(self.cfg.user_agent)
        try:
            while not self._stop_event.is_set():
                try:
                    await self._run_one_iteration(user_token_client, anon_client)
                except Exception as exc:
                    logger.exception("iteration failed")
                    with self._lock:
                        self.last_error = repr(exc)
                # Sleep until either the interval expires or someone sets
                # the tick event from another thread (e.g. "Check now").
                try:
                    await asyncio.wait_for(self._tick_event.wait(), timeout=interval_seconds)
                except asyncio.TimeoutError:
                    pass
                self._tick_event.clear()
        finally:
            await anon_client.aclose()
            await user_token_client.aclose()

    def check_now(self) -> bool:
        """Threadsafe: poke the worker thread to skip the rest of its sleep
        and run another iteration immediately. Returns True if the poke was
        scheduled, False if the worker isn't running yet.

        Called from the AppKit (rumps) thread. Delegates to the worker's
        event loop via ``call_soon_threadsafe`` to set the asyncio.Event the
        sleep is waiting on.
        """

        if self._asyncio_loop is None or self._tick_event is None:
            return False
        # `call_soon_threadsafe` is the only safe way to interact with an
        # asyncio loop from another thread.
        self._asyncio_loop.call_soon_threadsafe(self._tick_event.set)
        return True

    def start(self) -> None:
        """Spawn the worker thread that drives the async loop."""

        if self._loop_thread is not None:
            return
        self._loop_thread = threading.Thread(
            target=lambda: asyncio.run(self._loop_forever()),
            name="discogs-alert-loop",
            daemon=True,
        )
        self._loop_thread.start()

    def stop(self) -> None:
        self._stop_event.set()


# ---- the actual rumps app ---------------------------------------------------


def _require_rumps():
    if rumps is None:
        raise RuntimeError(
            "discogs_alert.menubar requires `rumps`. Install it with "
            "`pip install discogs_alert[menubar]`."
        )


class MenubarApp:  # pragma: no cover — wired up to AppKit at runtime, not unit-tested
    """The thin ``rumps.App`` that surfaces ``MenubarController`` state."""

    def __init__(self, cfg: da_config.Config):
        _require_rumps()
        self.controller = MenubarController(cfg)
        self.app = rumps.App("discogs_alert", title=self.controller.status_title())
        self.app.menu = [
            rumps.MenuItem(self.controller.last_check_str(), key=""),
            rumps.MenuItem(self.controller.alerts_str(), key=""),
            None,
            rumps.MenuItem("Check now", callback=self._on_check_now),
            None,
            rumps.MenuItem("Open config file…", callback=self._on_open_config),
            rumps.MenuItem("Reveal state DB…", callback=self._on_reveal_state),
        ]
        # Refresh the menu titles every few seconds so stats stay current.
        rumps.Timer(self._refresh_menu, interval=5).start()

    def _refresh_menu(self, _timer):
        self.app.title = self.controller.status_title()
        self.app.menu[self.controller.last_check_str()]
        # rumps menu items are keyed by their original title — easier to
        # rebuild than rename. The 5s tick is cheap enough.
        try:
            self.app.menu.clear()
        except Exception:
            return
        items = [
            rumps.MenuItem(self.controller.last_check_str(), key=""),
            rumps.MenuItem(self.controller.alerts_str(), key=""),
        ]
        if (err := self.controller.error_str()) is not None:
            items.append(rumps.MenuItem(err, key=""))
        items += [
            None,
            rumps.MenuItem("Check now", callback=self._on_check_now),
            None,
            rumps.MenuItem("Open config file…", callback=self._on_open_config),
            rumps.MenuItem("Reveal state DB…", callback=self._on_reveal_state),
        ]
        for it in items:
            self.app.menu.add(it)

    def _on_check_now(self, _sender):
        if self.controller.check_now():
            rumps.notification("discogs_alert", "", "Checking now…")
        else:
            # Worker thread hasn't started its asyncio loop yet — happens
            # only in the brief window between app launch and the first
            # iteration kicking off.
            rumps.notification(
                "discogs_alert", "", "Worker not ready yet; try again in a moment"
            )

    def _on_open_config(self, _sender):
        path = da_config.DEFAULT_CONFIG_PATH
        if not path.exists():
            rumps.notification(
                "discogs_alert", "Config file not found", str(path)
            )
            return
        rumps.macos.open_file(str(path))

    def _on_reveal_state(self, _sender):
        path = (
            Path(self.controller.cfg.runtime.state_path)
            if self.controller.cfg.runtime.state_path
            else da_state.DEFAULT_STATE_PATH
        )
        if path.exists():
            rumps.macos.open_file(str(path.parent))

    def run(self) -> None:
        self.controller.start()
        self.app.run()


# ---- entry point -----------------------------------------------------------


def main() -> None:
    """Console-script entry point.

    Loads the config from the default path (or ``DA_CONFIG_PATH`` env var),
    starts the controller's worker thread, then hands off to rumps.

    First-launch UX: if no config exists yet, fall back to a tiny
    "configure me" rumps app that points the user at where to put the
    config file and offers to open the parent directory. Better than
    crashing with a pydantic stack trace.
    """

    import os

    from pydantic import ValidationError

    logging.basicConfig(level=logging.INFO)

    config_path = os.environ.get("DA_CONFIG_PATH")
    resolved = Path(config_path) if config_path else da_config.DEFAULT_CONFIG_PATH

    try:
        cfg = da_config.load_config(path=resolved)
    except ValidationError as exc:
        _run_first_launch_app(resolved, exc)
        return

    logging.getLogger().setLevel(cfg.runtime.log_level.upper())
    MenubarApp(cfg).run()


def _run_first_launch_app(config_path: Path, exc) -> None:  # pragma: no cover
    """Tiny rumps app shown when the config file is missing or invalid.

    Saves the user from a crash on first launch. Shows the expected config
    path and an "Open folder…" button so they know where to drop a
    ``config.toml``. Logs the underlying validation error to stderr so
    advanced users can see exactly what's missing.
    """

    _require_rumps()
    logger.warning("Config not loadable, entering first-launch mode: %s", exc)

    app = rumps.App("discogs_alert", title="🎵 ⚙️")
    app.menu = [
        rumps.MenuItem(f"Configure: {config_path}", key=""),
        None,
        rumps.MenuItem(
            "Open config folder…",
            callback=lambda _s: rumps.macos.open_file(str(config_path.parent)),
        ),
        rumps.MenuItem(
            "Show example config…",
            callback=lambda _s: rumps.notification(
                "discogs_alert",
                "Example config",
                "See examples/config.example.toml in the source repo.",
            ),
        ),
    ]
    # Make sure the parent directory exists so the user has somewhere to
    # save the file from their editor.
    config_path.parent.mkdir(parents=True, exist_ok=True)
    app.run()


if __name__ == "__main__":
    main()
