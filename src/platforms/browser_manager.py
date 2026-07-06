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

# Login detection: URL patterns that indicate a NOT-logged-in state.
# Includes login pages, 2FA/code-entry pages, and challenge screens.
_LOGIN_PATTERNS: dict[str, list[str]] = {
    "threads": ["threads.com/login", "threads.net/login", "accounts/login", "auth_platform/", "/challenge/", "/checkpoint/"],
    "facebook": ["facebook.com/login", "facebook.com/checkpoint", "auth_platform/", "/challenge/"],
    "instagram": ["accounts/login", "auth_platform/", "/challenge/", "/checkpoint/"],
}

# Session cookies that confirm a successful login (name, domain substring)
_SESSION_COOKIES: dict[str, list[tuple[str, str]]] = {
    # Threads auth goes through Instagram; either cookie suffices
    "threads": [("sessionid", "threads.com"), ("sessionid", "threads.net"), ("sessionid", "instagram.com")],
    "facebook": [("c_user", "facebook.com")],
    "instagram": [("sessionid", "instagram.com")],
}


class BrowserManager:
    """Manage a shared Playwright browser with per-platform contexts and session persistence."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._lock = threading.RLock()
        self._browser_tid: Optional[int] = None  # thread that created the browser
        self._latest_screenshot: Optional[bytes] = None  # PIP preview buffer

    def set_headless(self, headless: bool) -> None:
        """Change headless mode. Takes effect on next patrol start."""
        if self._headless == headless:
            return
        self._headless = headless
        logger.info("Browser headless mode changed to %s (takes effect on next patrol start)", headless)

    def _session_path(self, platform: str) -> Path:
        return Path(BROWSER_DATA_DIR) / f"{platform}_session.json"

    def _ensure_browser(self) -> None:
        """Start Playwright browser if not running. Must be called with lock held.

        Playwright objects are bound to the thread that created them (greenlet).
        If called from a different thread, the old browser is torn down and
        recreated in the current thread.
        """
        current_tid = threading.get_ident()
        if self._browser is not None and self._browser_tid != current_tid:
            logger.info("Browser created in thread %s but called from %s, recreating",
                        self._browser_tid, current_tid)
            self._teardown_browser()

        if self._browser is not None:
            return
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            args=BROWSER_ARGS,
        )
        self._browser_tid = current_tid
        logger.info("Playwright Chromium browser started (headless=%s, thread=%s)",
                    self._headless, current_tid)

    def _teardown_browser(self) -> None:
        """Close browser and Playwright without acquiring the lock (caller holds it)."""
        for platform in list(self._contexts):
            try:
                self._contexts[platform].storage_state(
                    path=str(self._session_path(platform)))
            except Exception:
                pass
            try:
                self._contexts[platform].close()
            except Exception:
                pass
        self._contexts.clear()
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None
        self._browser_tid = None

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

        If the browser/context has crashed, it will be torn down and recreated
        once before raising.

        Usage::

            with bm.locked_page("threads") as page:
                page.goto(url)
                # ... all Playwright calls are serialized
        """
        self._lock.acquire()
        try:
            page = self._get_or_create_page(platform)
            yield page
        finally:
            self._lock.release()

    def _get_or_create_page(self, platform: str, _retry: bool = True) -> Page:
        """Get a page for the platform, recovering from a crashed browser once.

        Must be called with ``self._lock`` held.
        """
        try:
            self._ensure_browser()
            if platform not in self._contexts:
                session_path = self._session_path(platform)
                ctx = self._browser.new_context(**self._new_context_kwargs(session_path))
                stealth_sync(ctx)
                self._contexts[platform] = ctx
            ctx = self._contexts[platform]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            # Quick liveness check — accessing a property on a dead context throws
            _ = page.url
            return page
        except Exception:
            if not _retry:
                raise
            logger.warning("Browser context appears crashed for %s — recreating", platform)
            self._teardown_browser()
            return self._get_or_create_page(platform, _retry=False)

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
            page.goto(url, wait_until="load")
            logger.info("Interactive login opened for %s — waiting for user", platform)

            login_patterns = _LOGIN_PATTERNS.get(platform, [])
            deadline = time.time() + timeout
            poll_count = 0
            url_off_login_since: Optional[float] = None  # tracks when URL first left login page

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

                poll_count += 1
                if poll_count % 5 == 1:  # Log every ~10 seconds
                    logger.debug("[%s] login poll #%d — url=%s", platform, poll_count, current_url[:120])

                still_on_login = any(pat in current_url for pat in login_patterns)
                has_session_cookie = self._check_login_cookies(ctx, platform)

                # Primary: session cookie confirms login (works for SPAs
                # where URL stays on /login, and Threads→IG auth flows)
                if has_session_cookie:
                    logger.info("[%s] Login detected via cookies (url=%s)", platform, current_url[:80])
                    time.sleep(2)
                    self._save_login_session(ctx, session_path)
                    self._reload_context(platform)
                    return True

                # Secondary: URL left login page — wait for cookie confirmation.
                # Prevents false positive on consent/captcha/error pages.
                if not still_on_login and login_patterns:
                    if url_off_login_since is None:
                        url_off_login_since = time.time()
                        logger.debug("[%s] URL left login page, waiting for session cookie…", platform)
                    elif time.time() - url_off_login_since > 15:
                        # URL stable off login for 15s without cookie — accept
                        # (handles platforms with unknown cookie names)
                        logger.warning("[%s] URL off login 15s without session cookie, accepting (url=%s)", platform, current_url[:80])
                        time.sleep(2)
                        self._save_login_session(ctx, session_path)
                        self._reload_context(platform)
                        return True
                else:
                    # URL went back to login page (e.g. after consent screen) — reset
                    url_off_login_since = None

                time.sleep(2)

            logger.warning("Login timed out for %s after %ds (last url=%s)", platform, timeout, current_url[:120])
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

    @staticmethod
    def _save_login_session(ctx: BrowserContext, session_path: Path) -> None:
        """Save browser context state to disk after successful login."""
        ctx.storage_state(path=str(session_path))
        try:
            os.chmod(str(session_path), 0o600)
        except OSError:
            pass
        logger.info("Login session saved to %s", session_path.name)

    @staticmethod
    def _check_login_cookies(ctx: BrowserContext, platform: str) -> bool:
        """Check if session cookies from a successful login are present."""
        targets = _SESSION_COOKIES.get(platform, [])
        if not targets:
            return False
        try:
            cookies = ctx.cookies()
            for name, domain in targets:
                if any(c["name"] == name and domain in c.get("domain", "") for c in cookies):
                    return True
        except Exception:
            pass
        return False

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

    def set_screenshot(self, data: bytes) -> None:
        """Store a screenshot for PIP preview (called from patrol thread)."""
        self._latest_screenshot = data

    def get_screenshot(self) -> Optional[bytes]:
        """Get the latest screenshot bytes (called from GUI thread)."""
        return self._latest_screenshot

    def clear_screenshot(self) -> None:
        """Clear the screenshot buffer."""
        self._latest_screenshot = None

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

    def close(self, timeout: float = 5) -> None:
        """Save all sessions and shut down Playwright.

        Uses a lock timeout to avoid deadlock when patrol thread holds the lock
        during app shutdown.  If the lock cannot be acquired, teardown is
        skipped — daemon threads are killed on process exit anyway.
        """
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            logger.warning("BrowserManager.close() could not acquire lock "
                           "(patrol thread likely active); skipping teardown — "
                           "daemon threads will be killed on process exit")
            return
        try:
            self._teardown_browser()
            logger.info("BrowserManager closed")
        finally:
            self._lock.release()
