"""Playwright browser lifecycle and session management."""

import contextlib
import logging
import os
import threading
import time
from pathlib import Path
from typing import Generator, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from playwright_stealth import Stealth

_stealth = Stealth()
stealth_sync = _stealth.apply_stealth_sync

from config import BROWSER_DATA_DIR

logger = logging.getLogger(__name__)

BROWSER_ARGS = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Login detection: URL patterns that indicate a NOT-logged-in state
_LOGIN_PATTERNS: dict[str, list[str]] = {
    "threads": ["login.threads.net", "/login"],
    "facebook": ["/login", "facebook.com/login"],
    "instagram": ["accounts/login"],
}


class BrowserManager:
    """Manage a shared Playwright browser with per-platform contexts and session persistence."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._lock = threading.RLock()

    def _session_path(self, platform: str) -> Path:
        return Path(BROWSER_DATA_DIR) / f"{platform}_session.json"

    def _ensure_browser(self) -> None:
        """Start Playwright browser if not running. Must be called with lock held."""
        if self._browser is not None:
            return
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            args=BROWSER_ARGS,
        )
        logger.info("Playwright Chromium browser started (headless=%s)", self._headless)

    def _new_context_kwargs(self, session_path: Optional[Path] = None) -> dict:
        """Build kwargs for browser.new_context()."""
        kwargs = {
            "user_agent": USER_AGENT,
            "viewport": DEFAULT_VIEWPORT,
            "locale": "zh-TW",
            "timezone_id": "Asia/Taipei",
        }
        if session_path and session_path.exists():
            kwargs["storage_state"] = str(session_path)
        return kwargs

    def ensure_browser(self) -> None:
        """Ensure the shared headless browser is running."""
        with self._lock:
            self._ensure_browser()

    def get_context(self, platform: str) -> BrowserContext:
        """Get or create a browser context for the given platform."""
        with self._lock:
            self._ensure_browser()
            if platform in self._contexts:
                return self._contexts[platform]

            session_path = self._session_path(platform)
            ctx = self._browser.new_context(**self._new_context_kwargs(session_path))
            stealth_sync(ctx)
            self._contexts[platform] = ctx
            logger.debug("Created browser context for %s (session=%s)", platform, session_path.exists())
            return ctx

    @contextlib.contextmanager
    def locked_page(self, platform: str) -> Generator[Page, None, None]:
        """Context manager that acquires the lock, returns a page, and holds
        the lock until the block exits. This guarantees exclusive access to the
        shared page for the entire duration of a browser operation.

        Usage::

            with bm.locked_page("threads") as page:
                page.goto(url)
                # ... all Playwright calls are serialized
        """
        self._lock.acquire()
        try:
            self._ensure_browser()
            if platform not in self._contexts:
                session_path = self._session_path(platform)
                ctx = self._browser.new_context(**self._new_context_kwargs(session_path))
                stealth_sync(ctx)
                self._contexts[platform] = ctx
            ctx = self._contexts[platform]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            yield page
        finally:
            self._lock.release()

    def save_session(self, platform: str) -> None:
        """Persist context storage state (cookies/localStorage) to disk."""
        with self._lock:
            ctx = self._contexts.get(platform)
            if ctx:
                path = str(self._session_path(platform))
                ctx.storage_state(path=path)
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
                logger.debug("Saved browser session for %s", platform)

    def has_session(self, platform: str) -> bool:
        """Check if a saved session file exists on disk."""
        return self._session_path(platform).exists()

    def delete_session(self, platform: str) -> None:
        """Delete saved session file (logout)."""
        path = self._session_path(platform)
        if path.exists():
            path.unlink()
            logger.info("Deleted browser session for %s", platform)

    def login_interactive(self, platform: str, url: str, timeout: int = 300) -> bool:
        """Open a headed browser for the user to log in manually.

        Uses a SEPARATE Playwright instance so it doesn't interfere with the
        headless patrol browser. Returns True if login was detected.
        """
        session_path = self._session_path(platform)
        pw: Optional[Playwright] = None
        browser: Optional[Browser] = None

        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=False, args=BROWSER_ARGS)
            ctx = browser.new_context(**self._new_context_kwargs())
            stealth_sync(ctx)

            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
            logger.info("Interactive login opened for %s — waiting for user", platform)

            login_patterns = _LOGIN_PATTERNS.get(platform, [])
            deadline = time.time() + timeout

            while time.time() < deadline:
                # Check if user closed the browser
                if not browser.is_connected():
                    logger.info("User closed login browser for %s", platform)
                    return False

                try:
                    current_url = page.url
                except Exception:
                    # Page/browser was closed
                    return False

                # Login detected: URL no longer contains login patterns
                still_on_login = any(pat in current_url for pat in login_patterns)
                if not still_on_login and login_patterns:
                    # Give the page a moment to settle after redirect
                    time.sleep(2)
                    ctx.storage_state(path=str(session_path))
                    try:
                        os.chmod(str(session_path), 0o600)
                    except OSError:
                        pass
                    logger.info("Login successful for %s, session saved", platform)

                    # Reload main patrol context if it exists
                    self._reload_context(platform)
                    return True

                time.sleep(2)

            logger.warning("Login timed out for %s after %ds", platform, timeout)
            return False

        except Exception:
            logger.exception("Interactive login failed for %s", platform)
            return False
        finally:
            try:
                if browser and browser.is_connected():
                    browser.close()
            except Exception:
                pass
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass

    def _reload_context(self, platform: str) -> None:
        """Close and recreate a platform context to pick up a new session file."""
        with self._lock:
            if platform in self._contexts:
                try:
                    self._contexts[platform].close()
                except Exception:
                    pass
                del self._contexts[platform]
            # Next get_context() call will reload from the saved session

    def close_context(self, platform: str) -> None:
        """Save session and close a specific platform context."""
        with self._lock:
            ctx = self._contexts.pop(platform, None)
            if ctx:
                try:
                    ctx.storage_state(path=str(self._session_path(platform)))
                except Exception:
                    pass
                ctx.close()
                logger.debug("Closed context for %s", platform)

    def close(self) -> None:
        """Save all sessions and shut down Playwright."""
        with self._lock:
            for platform in list(self._contexts):
                try:
                    self._contexts[platform].storage_state(
                        path=str(self._session_path(platform))
                    )
                except Exception:
                    pass
                try:
                    self._contexts[platform].close()
                except Exception:
                    pass
            self._contexts.clear()

            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._pw:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None

            logger.info("BrowserManager closed")
