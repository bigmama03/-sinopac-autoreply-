"""Playwright-based Threads browser adapter."""

import logging
import random
import time
import urllib.parse
from typing import Optional

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from src.platforms.base import PlatformAdapter
from src.platforms.browser_manager import BrowserManager

PLATFORM = "threads"
THREADS_HOME_URL = "https://www.threads.com/"
SEARCH_URL = "https://www.threads.com/search?q={keyword}&serp_type=default"

# Selectors — update when threads.com DOM changes
# Threads uses div containers (not <article>); detect posts by their permalink links
SEL_POST_ARTICLE = "div[data-pressable-container='true'], article, div[role='article']"
SEL_POST_LINK = "a[href*='/post/']"
SEL_POST_LINK_ALT = "a[href*='threads.com/@'][href*='/post/']"
SEL_PROFILE_LINK = "a[href^='/@']"
SEL_PROFILE_LINK_ABS = "a[href*='threads.com/@']"
SEL_POST_BODY = "[data-pressable-container='true'] span[dir='auto']"
SEL_POST_BODY_ALT = "div[dir='auto'] span"
SEL_POST_BODY_FALLBACK = "span[dir='auto']"
SEL_REPLY_INPUT = "div[role='textbox'][contenteditable='true']"
SEL_REPLY_INPUT_ALT = "div[contenteditable='true'][aria-label*='Reply' i]"
SEL_REPLY_INPUT_FALLBACK = "div[contenteditable='true']"
SEL_LOGIN_INPUT = "input[name='login_identifier']"
SEL_LOGIN_PASSWORD = "input[type='password']"
SEL_LOGIN_FORM = "form"
SEL_LOGGED_IN_PROFILE = "a[href='/'][role='link'], a[href^='/@'][role='link']"
SEL_REPLY_AUTHOR_LINK = "a[href^='/@']"
SEL_REPLY_AUTHOR_LINK_ABS = "a[href*='threads.com/@']"
SEL_MORE_BUTTON = "svg[aria-label='More'], button[aria-label='More'], div[role='button'][aria-label='More']"
SEL_MENU_DELETE = "[role='menuitem']"
SEL_CONFIRM_DELETE = "button"
SEL_NOT_FOUND_TEXT = "text=/not available|unavailable|Sorry, this page isn't available|content isn't available/i"
SEL_SEARCH_EMPTY_TEXT = "text=/No results|Try searching for|couldn't find/i"
SEL_SUBMIT_BUTTON = "div[role='button']"

# Login/register modal overlay that appears for logged-out or partially-authed users
SEL_MODAL_CONTINUE_INSTAGRAM = "div[role='button']:has-text('使用 Instagram 帳號繼續'), button:has-text('使用 Instagram 帳號繼續')"
SEL_MODAL_CONTINUE_INSTAGRAM_EN = "div[role='button']:has-text('Continue with Instagram'), button:has-text('Continue with Instagram')"
SEL_MODAL_LOGIN_BUTTON = "div[role='button']:has-text('登入'), button:has-text('登入')"
SEL_MODAL_CLOSE = "div[role='dialog'] svg[aria-label='Close'], div[role='dialog'] button[aria-label='Close'], div[role='dialog'] [aria-label='關閉']"

BUTTON_TEXT_REPLY = "Reply"
BUTTON_TEXT_POST = "Post"
BUTTON_TEXT_DELETE = "Delete"

logger = logging.getLogger(__name__)


class ThreadsBrowserAdapter(PlatformAdapter):
    """Browser automation adapter for Threads using Playwright."""

    def __init__(self, browser_manager: BrowserManager, repo=None):
        self._bm = browser_manager
        self._repo = repo

    def check_connection(self) -> tuple[bool, str]:
        try:
            with self._bm.locked_page(PLATFORM) as page:
                if not self._safe_goto(page, THREADS_HOME_URL, timeout=10000):
                    return False, "無法開啟 Threads"
                self._sleep(1.0, 1.8)
                self._dismiss_login_modal(page)
                if self._is_login_page(page):
                    return False, "未登入 Threads"
                username = self._get_own_username(page)
                try:
                    self._bm.save_session(PLATFORM)
                except Exception:
                    pass
                if username:
                    return True, f"已連線: @{username}"
                return True, "已連線 Threads"
        except Exception:
            logger.exception("Threads check_connection failed")
            return False, "開啟 Threads 頁面失敗"

    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        try:
            with self._bm.locked_page(PLATFORM) as page:
                # Quick session check: navigate to home and verify logged-in
                if not self._safe_goto(page, THREADS_HOME_URL, timeout=10000):
                    logger.error("Threads fetch_posts: cannot open home page")
                    return []
                self._sleep(1.0, 1.5)
                self._dismiss_login_modal(page)
                if self._is_login_page(page):
                    logger.error("Threads session invalid (redirected to login: %s)", page.url[:120])
                    return []

                deduped: dict[str, dict] = {}
                for keyword in keywords:
                    kw = keyword.strip()
                    if not kw:
                        continue
                    search_url = SEARCH_URL.format(keyword=urllib.parse.quote(kw))
                    if not self._safe_goto(page, search_url, timeout=15000):
                        continue
                    # Dismiss login modal that may overlay search results
                    self._sleep(1.0, 2.0)
                    dismissed = self._dismiss_login_modal(page)
                    if dismissed:
                        # Modal dismissal may redirect to home; re-navigate to search
                        current = page.url
                        if kw not in current and "search" not in current:
                            logger.info("Modal dismissed but redirected to %s, re-navigating to search for keyword=%s", current[:80], kw)
                            if not self._safe_goto(page, search_url, timeout=15000):
                                continue
                            self._sleep(1.0, 2.0)
                        else:
                            logger.info("Modal dismissed for keyword=%s", kw)
                    self._capture_screenshot(page)
                    posts_ready = self._wait_for_posts(page, timeout=15000)
                    self._capture_screenshot(page)
                    # Debug: always log page state for search pages
                    try:
                        container_count = page.locator(SEL_POST_ARTICLE).count()
                        link_count = page.locator(f"{SEL_POST_LINK}, {SEL_POST_LINK_ALT}").count()
                        logger.info(
                            "Search page for keyword=%s: url=%s, containers=%d, post_links=%d, posts_ready=%s",
                            kw, page.url[:100], container_count, link_count, posts_ready,
                        )
                    except Exception:
                        pass
                    if not posts_ready:
                        if self._is_search_empty(page):
                            logger.info("Threads search empty for keyword=%s", kw)
                        elif self._is_login_page(page):
                            logger.error("Threads session expired during search (url=%s)", page.url[:120])
                            return []
                        else:
                            try:
                                body_text = page.locator("body").inner_text(timeout=3000)[:300]
                                logger.warning(
                                    "Threads search did not load for keyword=%s (body_preview=%s)",
                                    kw, body_text[:200],
                                )
                            except Exception:
                                logger.warning("Threads search did not load for keyword=%s (url=%s)", kw, page.url[:120])
                        continue
                    scroll_count = 6
                    if self._repo is not None:
                        try:
                            v = int(self._repo.get_setting("search_scroll_count", "6"))
                            if v >= 1:
                                scroll_count = v
                        except (ValueError, TypeError):
                            pass
                    for _ in range(scroll_count):
                        try:
                            page.evaluate("window.scrollBy(0, 800)")
                        except Exception:
                            break
                        time.sleep(random.uniform(0.8, 1.5))
                    extracted = self._extract_posts(page)
                    logger.info("Extracted %d posts for keyword=%s", len(extracted), kw)
                    for post in extracted:
                        pid = post.get("platform_post_id")
                        if pid and pid not in deduped:
                            deduped[pid] = post
                    time.sleep(random.uniform(1.0, 3.0))
                return list(deduped.values())
        except Exception:
            logger.exception("Threads fetch_posts failed")
            return []

    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        try:
            with self._bm.locked_page(PLATFORM) as page:
                # post_id is the full post URL
                if not self._safe_goto(page, post_id, timeout=10000):
                    return False, None, "無法開啟 Threads 貼文"
                self._dismiss_login_modal(page)
                input_loc = self._find_first_visible(
                    page, (SEL_REPLY_INPUT, SEL_REPLY_INPUT_ALT, SEL_REPLY_INPUT_FALLBACK), timeout=10000,
                )
                if input_loc is None:
                    return False, None, "找不到回覆輸入框"
                try:
                    input_loc.click(timeout=5000)
                    time.sleep(random.uniform(0.3, 0.8))
                    page.keyboard.type(message, delay=50)
                except Exception:
                    logger.exception("Failed to type Threads reply")
                    return False, None, "輸入回覆失敗"
                submit = self._find_submit_button(page)
                if submit is None:
                    return False, None, "找不到送出按鈕"
                try:
                    submit.click(timeout=5000)
                except Exception:
                    logger.exception("Failed to click submit")
                    return False, None, "送出回覆失敗"
                time.sleep(random.uniform(1.5, 3.0))
                reply_id = self._extract_new_reply_permalink(page, message)
                try:
                    self._bm.save_session(PLATFORM)
                except Exception:
                    pass
                return True, reply_id, None
        except Exception:
            logger.exception("Threads reply_to_post failed")
            return False, None, "開啟 Threads 頁面失敗"

    def check_already_replied(self, post_id: str) -> bool:
        try:
            with self._bm.locked_page(PLATFORM) as page:
                if not self._safe_goto(page, post_id, timeout=10000):
                    return False
                own = self._get_own_username(page)
                if not own:
                    return False
                for _ in range(4):
                    try:
                        page.evaluate("window.scrollBy(0, 900)")
                    except Exception:
                        return False
                    time.sleep(random.uniform(0.8, 1.4))
                authors = page.locator(f"{SEL_REPLY_AUTHOR_LINK}, {SEL_REPLY_AUTHOR_LINK_ABS}")
                count = min(authors.count(), 80)
                for i in range(count):
                    username = self._extract_username_from_locator(authors.nth(i))
                    if username and username.lower() == own.lower():
                        return True
                return False
        except Exception:
            logger.exception("Threads check_already_replied failed")
            return False

    def check_reply_visible(self, reply_id: str) -> bool | None:
        try:
            with self._bm.locked_page(PLATFORM) as page:
                if not self._safe_goto(page, reply_id, timeout=10000):
                    return None
                time.sleep(random.uniform(0.8, 1.5))
                if page.locator(SEL_NOT_FOUND_TEXT).count() > 0:
                    return False
                if page.locator(SEL_POST_ARTICLE).count() > 0:
                    return True
                return False
        except Exception:
            logger.exception("Threads check_reply_visible failed")
            return None

    def delete_reply(self, reply_id: str) -> tuple[bool, str]:
        try:
            with self._bm.locked_page(PLATFORM) as page:
                if not self._safe_goto(page, reply_id, timeout=10000):
                    return False, "無法開啟回覆頁面"
                more = self._find_first_visible(page, (SEL_MORE_BUTTON,), timeout=7000)
                if more is None:
                    more = self._find_button_by_text(page, "More")
                if more is None:
                    return False, "找不到更多選項按鈕"
                more.click(timeout=5000)
                time.sleep(random.uniform(0.4, 0.9))
                delete_item = self._find_menu_item_by_text(page, BUTTON_TEXT_DELETE)
                if delete_item is None:
                    return False, "找不到刪除選項"
                delete_item.click(timeout=5000)
                time.sleep(random.uniform(0.4, 0.8))
                confirm = self._find_confirm_delete_button(page)
                if confirm is None:
                    return False, "找不到刪除確認按鈕"
                confirm.click(timeout=5000)
                time.sleep(random.uniform(1.0, 2.0))
                try:
                    self._bm.save_session(PLATFORM)
                except Exception:
                    pass
                return True, "deleted"
        except Exception:
            logger.exception("Threads delete_reply failed")
            return False, "刪除操作失敗"

    # ── Private helpers (receive page as parameter, no lock needed) ──

    def _dismiss_login_modal(self, page: Page) -> bool:
        """Detect and dismiss the Threads login/register modal overlay.

        Returns True if a modal was found and dismissed, False otherwise.
        The modal shows "透過 Threads 暢所欲言" with a
        "使用 Instagram 帳號繼續 <username>" button.
        """
        # Primary: detect modal by title text and iterate actual button elements.
        # This is the most reliable approach — text/CSS selectors may find the
        # text but clicking a <span> inside the button doesn't trigger the action.
        for modal_title in ("透過 Threads 暢所欲言", "Say more on Threads", "Log in to Threads"):
            try:
                title_loc = page.get_by_text(modal_title)
                if not title_loc.is_visible(timeout=1500):
                    continue
                logger.info("Threads modal detected: '%s'", modal_title)
                buttons = page.locator("div[role='button'], button").all()
                for btn in buttons[:15]:
                    try:
                        btn_text = btn.inner_text(timeout=1000).strip()
                        if "instagram" in btn_text.lower() or "繼續" in btn_text or "continue" in btn_text.lower():
                            logger.info("Clicking modal button: '%s'", btn_text[:60])
                            btn.click(timeout=5000)
                            time.sleep(random.uniform(2.5, 4.0))
                            try:
                                page.wait_for_load_state("domcontentloaded", timeout=10000)
                            except Exception:
                                pass
                            logger.info("Modal dismissed (url=%s)", page.url[:120])
                            try:
                                self._bm.save_session(PLATFORM)
                            except Exception:
                                pass
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

        # Fallback: try get_by_role for the "Continue with Instagram" button
        for label in ("使用 Instagram 帳號繼續", "Continue with Instagram"):
            try:
                btn = page.get_by_role("button", name=label).first
                if btn.is_visible(timeout=1000):
                    logger.info("Threads modal button found by role: '%s'", label)
                    btn.click(timeout=5000)
                    time.sleep(random.uniform(2.5, 4.0))
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    try:
                        self._bm.save_session(PLATFORM)
                    except Exception:
                        pass
                    return True
            except Exception:
                pass

        # Last resort: close modal via X button
        try:
            close_btn = page.locator(SEL_MODAL_CLOSE).first
            if close_btn.is_visible(timeout=1000):
                logger.info("Threads modal detected, closing via X button")
                close_btn.click(timeout=3000)
                time.sleep(random.uniform(0.5, 1.0))
                return True
        except Exception:
            pass

        return False

    def _safe_goto(self, page: Page, url: str, wait_until: str = "domcontentloaded", timeout: int = 15000) -> bool:
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except Exception:
            logger.exception("Failed to navigate to %s", url)
            return False

    def _wait_for_posts(self, page: Page, timeout: int = 10000) -> bool:
        # Try container selectors first, then fall back to post link detection
        for selector in (SEL_POST_ARTICLE, SEL_POST_LINK, SEL_POST_LINK_ALT):
            try:
                page.wait_for_selector(selector, timeout=timeout)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue
        return False

    def _is_search_empty(self, page: Page) -> bool:
        try:
            return page.locator(SEL_SEARCH_EMPTY_TEXT).count() > 0
        except Exception:
            return False

    def _extract_posts(self, page: Page) -> list[dict]:
        posts: list[dict] = []

        # Strategy 1: find post containers (article, div[data-pressable-container], etc.)
        try:
            articles = page.locator(SEL_POST_ARTICLE)
            count = min(articles.count(), 60)
        except Exception:
            count = 0
        for i in range(count):
            try:
                article = articles.nth(i)
                post_url = self._extract_post_url(article)
                if not post_url:
                    continue
                posts.append({
                    "platform_post_id": post_url,
                    "post_url": post_url,
                    "author_username": self._extract_post_author(article),
                    "post_content": self._extract_post_content(article),
                })
            except Exception:
                logger.debug("Failed to extract article at index=%d", i, exc_info=True)

        if posts:
            return posts

        # Strategy 2: no container matched — extract posts by finding permalink links
        # and walking up to their closest ancestor that contains post content
        logger.debug("No post containers found, trying link-based extraction")
        seen_urls: set[str] = set()
        try:
            links = page.locator(f"{SEL_POST_LINK}, {SEL_POST_LINK_ALT}")
            link_count = min(links.count(), 60)
        except Exception:
            return posts
        for i in range(link_count):
            try:
                link = links.nth(i)
                href = link.get_attribute("href", timeout=2000)
                post_url = self._normalize_url(href)
                if not post_url or post_url in seen_urls:
                    continue
                seen_urls.add(post_url)
                # Walk up to find a container with text content
                # Try the link's closest ancestor with post-like content
                container = link.locator("xpath=ancestor::div[.//a[contains(@href,'/@')]]").first
                author = ""
                content = ""
                try:
                    author = self._extract_post_author(container)
                except Exception:
                    pass
                try:
                    content = self._extract_post_content(container)
                except Exception:
                    pass
                posts.append({
                    "platform_post_id": post_url,
                    "post_url": post_url,
                    "author_username": author,
                    "post_content": content,
                })
            except Exception:
                logger.debug("Failed to extract link-based post at index=%d", i, exc_info=True)

        logger.info("Link-based extraction found %d posts", len(posts))
        return posts

    def _extract_post_url(self, article: Locator) -> str:
        for sel in (SEL_POST_LINK, SEL_POST_LINK_ALT):
            try:
                href = article.locator(sel).first.get_attribute("href", timeout=2000)
                url = self._normalize_url(href)
                if url:
                    return url
            except Exception:
                pass
        return ""

    def _extract_post_author(self, article: Locator) -> str:
        for sel in (SEL_PROFILE_LINK, SEL_PROFILE_LINK_ABS):
            try:
                username = self._extract_username_from_locator(article.locator(sel).first)
                if username:
                    return username
            except Exception:
                pass
        return ""

    def _extract_post_content(self, article: Locator) -> str:
        for sel in (SEL_POST_BODY, SEL_POST_BODY_ALT, SEL_POST_BODY_FALLBACK):
            try:
                texts = article.locator(sel).all_inner_texts()
                content = " ".join(t.strip() for t in texts if t.strip())
                if content:
                    return content
            except Exception:
                pass
        try:
            return article.inner_text(timeout=2000).strip()
        except Exception:
            return ""

    def _is_login_page(self, page: Page) -> bool:
        url = page.url.lower()
        if "login" in url:
            return True
        for sel in (SEL_LOGIN_INPUT, SEL_LOGIN_PASSWORD):
            try:
                if page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
        return False

    def _get_own_username(self, page: Page) -> str:
        for sel in (SEL_LOGGED_IN_PROFILE, SEL_PROFILE_LINK):
            try:
                loc = page.locator(sel)
                for i in range(min(loc.count(), 30)):
                    username = self._extract_username_from_locator(loc.nth(i))
                    if username and username.lower() not in {"threads", "home"}:
                        return username
            except Exception:
                pass
        return ""

    def _extract_username_from_locator(self, locator: Locator) -> str:
        try:
            href = locator.get_attribute("href", timeout=2000) or ""
        except Exception:
            href = ""
        u = self._parse_username(href)
        if u:
            return u
        try:
            text = (locator.inner_text(timeout=2000) or "").strip()
        except Exception:
            text = ""
        u = self._parse_username(text)
        if u:
            return u
        if text and " " not in text:
            return text.lstrip("@")
        return ""

    def _parse_username(self, value: str) -> str:
        if not value:
            return ""
        if "/@" in value:
            segment = value.split("/@", 1)[1]
            return segment.split("/", 1)[0].split("?", 1)[0].strip("@")
        if value.startswith("@"):
            return value[1:].split()[0].strip("/")
        return ""

    def _normalize_url(self, href: Optional[str]) -> str:
        if not href:
            return ""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"https://www.threads.com{href}"
        return ""

    def _find_first_visible(self, page: Page, selectors: tuple[str, ...], timeout: int = 5000) -> Optional[Locator]:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=timeout)
                return loc
            except Exception:
                pass
        return None

    def _find_submit_button(self, page: Page) -> Optional[Locator]:
        for text in (BUTTON_TEXT_REPLY, BUTTON_TEXT_POST):
            btn = self._find_button_by_text(page, text)
            if btn:
                return btn
        try:
            loc = page.locator(SEL_SUBMIT_BUTTON)
            for i in range(min(loc.count(), 30)):
                t = (loc.nth(i).inner_text(timeout=1000) or "").strip().lower()
                if t in {BUTTON_TEXT_REPLY.lower(), BUTTON_TEXT_POST.lower()}:
                    return loc.nth(i)
        except Exception:
            pass
        return None

    def _find_button_by_text(self, page: Page, text: str) -> Optional[Locator]:
        for loc in (page.get_by_role("button", name=text), page.get_by_text(text, exact=True)):
            try:
                first = loc.first
                first.wait_for(state="visible", timeout=3000)
                return first
            except Exception:
                pass
        return None

    def _extract_new_reply_permalink(self, page: Page, message: str) -> Optional[str]:
        normalized = " ".join(message.split()).strip()
        try:
            articles = page.locator(SEL_POST_ARTICLE)
            for i in range(min(articles.count(), 20)):
                article = articles.nth(i)
                text = " ".join(article.all_inner_texts()).strip()
                if normalized and normalized not in text:
                    continue
                url = self._extract_post_url(article)
                if url:
                    return url
        except Exception:
            pass
        return None

    def _find_menu_item_by_text(self, page: Page, text: str) -> Optional[Locator]:
        try:
            items = page.locator(SEL_MENU_DELETE)
            for i in range(min(items.count(), 20)):
                t = (items.nth(i).inner_text(timeout=1000) or "").strip().lower()
                if text.lower() in t:
                    return items.nth(i)
        except Exception:
            pass
        return self._find_button_by_text(page, text)

    def _find_confirm_delete_button(self, page: Page) -> Optional[Locator]:
        btn = self._find_button_by_text(page, BUTTON_TEXT_DELETE)
        if btn:
            return btn
        try:
            buttons = page.locator(SEL_CONFIRM_DELETE)
            for i in range(min(buttons.count(), 20)):
                t = (buttons.nth(i).inner_text(timeout=1000) or "").strip().lower()
                if t == BUTTON_TEXT_DELETE.lower():
                    return buttons.nth(i)
        except Exception:
            pass
        return None

    def _capture_screenshot(self, page: Page) -> None:
        """Take a screenshot and store it in BrowserManager for PIP preview."""
        try:
            self._bm.set_screenshot(page.screenshot(type="jpeg", quality=60))
        except Exception:
            pass

    def _sleep(self, lo: float, hi: float) -> None:
        time.sleep(random.uniform(lo, hi))
