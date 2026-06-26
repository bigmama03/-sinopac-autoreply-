"""Playwright-based Instagram browser adapter."""

import logging
import random
import re
import time
import urllib.parse
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.platforms.base import PlatformAdapter
from src.platforms.browser_manager import BrowserManager

INSTAGRAM_HOME_URL = "https://www.instagram.com/"
INSTAGRAM_TAG_URL_TEMPLATE = "https://www.instagram.com/explore/tags/{keyword}/"
INSTAGRAM_POST_URL_TEMPLATE = "https://www.instagram.com/p/{shortcode}/"
INSTAGRAM_LOGIN_PATH = "/accounts/login/"

COOKIE_BUTTON_TEXT_ACCEPT_ALL = "button:has-text('Accept all')"
COOKIE_BUTTON_TEXT_ALLOW_ALL = "button:has-text('Allow all cookies')"
COOKIE_BUTTON_TEXT_ACCEPT_OPTIONAL = "button:has-text('Allow essential and optional cookies')"
COOKIE_BUTTON_TEXT_ONLY_ESSENTIAL = "button:has-text('Allow essential cookies')"
COOKIE_BUTTON_ARIA_ACCEPT = "button[aria-label*='Allow' i]"
COOKIE_BUTTON_SELECTORS = (
    COOKIE_BUTTON_TEXT_ACCEPT_ALL,
    COOKIE_BUTTON_TEXT_ALLOW_ALL,
    COOKIE_BUTTON_TEXT_ACCEPT_OPTIONAL,
    COOKIE_BUTTON_TEXT_ONLY_ESSENTIAL,
    COOKIE_BUTTON_ARIA_ACCEPT,
)

PROFILE_LINK_SELECTOR = "a[href^='/'][href$='/']"
PROFILE_LINK_CURRENT_SELECTOR = "a[href='/accounts/edit/']"
PROFILE_IMAGE_ALT_SELECTOR = "img[alt*='profile picture' i]"
NAV_SELECTOR = "nav"
HEADER_SELECTOR = "header"
SIDEBAR_SELECTOR = "section main"

TAG_GRID_ARTICLE_SELECTOR = "article"
TAG_GRID_LINK_SELECTOR = "article a[href^='/p/']"
TAG_GRID_SECTION_SELECTOR = "main section"
POST_DIALOG_SELECTOR = "div[role='dialog']"
POST_ARTICLE_SELECTOR = "main article"

POST_HEADER_AUTHOR_SELECTOR = "header a[href^='/']"
POST_CAPTION_CONTAINER_SELECTOR = "ul li, article h1, article span, article div[dir='auto']"
POST_CAPTION_AUTHOR_LINK_SELECTOR = "a[href^='/']"
POST_COMMENT_BOX_SELECTOR = "form textarea[placeholder]"
POST_COMMENT_TEXTAREA_SELECTOR = "textarea[aria-label*='comment' i]"
POST_COMMENT_EDITABLE_SELECTOR = "div[contenteditable='true'][role='textbox']"
POST_COMMENT_INPUT_SELECTORS = (
    POST_COMMENT_TEXTAREA_SELECTOR,
    POST_COMMENT_BOX_SELECTOR,
    POST_COMMENT_EDITABLE_SELECTOR,
)
POST_SUBMIT_BUTTON_TEXT_POST = "form button:has-text('Post')"
POST_SUBMIT_BUTTON_TEXT_PUBLISH = "form button:has-text('發佈')"
POST_SUBMIT_BUTTON_TEXT_SEND = "form button:has-text('送出')"
POST_SUBMIT_BUTTON_SELECTORS = (
    POST_SUBMIT_BUTTON_TEXT_POST,
    POST_SUBMIT_BUTTON_TEXT_PUBLISH,
    POST_SUBMIT_BUTTON_TEXT_SEND,
)

COMMENTS_LIST_ITEM_SELECTOR = "ul ul li"
COMMENTS_AUTHOR_LINK_SELECTOR = "a[href^='/']"
COMMENTS_LOAD_MORE_BUTTON_SELECTOR = "button:has-text('Load more comments')"
COMMENTS_VIEW_REPLIES_BUTTON_SELECTOR = "button:has-text('View all comments')"
COMMENTS_EXPAND_BUTTON_SELECTOR = "button:has-text('View more comments')"
COMMENTS_EXPAND_SELECTORS = (
    COMMENTS_LOAD_MORE_BUTTON_SELECTOR,
    COMMENTS_VIEW_REPLIES_BUTTON_SELECTOR,
    COMMENTS_EXPAND_BUTTON_SELECTOR,
)

SHORTCODE_URL_PATTERN = re.compile(r"/p/([^/?#]+)/")

MAX_POSTS_PER_KEYWORD = 10
COMMENT_LOAD_MORE_CLICKS = 5

logger = logging.getLogger(__name__)


class InstagramBrowserAdapter(PlatformAdapter):
    """Browser automation adapter for Instagram using Playwright."""

    def __init__(self, browser_manager: BrowserManager):
        self._bm = browser_manager
        self._platform = "instagram"
        self._username: str | None = None

    def check_connection(self) -> tuple[bool, str]:
        try:
            with self._bm.locked_page(self._platform) as page:
                if not self._safe_goto(page, INSTAGRAM_HOME_URL):
                    return False, "Failed to open Instagram"

                self._dismiss_cookie_dialog(page)
                self._wait_for_page_settle(page, timeout_ms=10000)

                if self._is_login_page(page):
                    return False, "Not logged in"

                username = self._extract_logged_in_username(page)
                self._username = username or None

                try:
                    self._bm.save_session(self._platform)
                except Exception:
                    logger.error("Failed to save Instagram session", exc_info=True)

                if username:
                    return True, f"Connected as {username}"
                return True, "Connected"
        except Exception as exc:
            logger.error("Instagram check_connection failed", exc_info=True)
            return False, str(exc)

    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        del since_id

        try:
            with self._bm.locked_page(self._platform) as page:
                deduped: dict[str, dict] = {}
                normalized_keywords = [keyword.strip().lstrip("#") for keyword in keywords if keyword and keyword.strip()]

                try:
                    self._dismiss_cookie_dialog(page)
                except Exception:
                    logger.error("Failed during Instagram cookie dismissal", exc_info=True)

                for index, keyword in enumerate(normalized_keywords):
                    try:
                        tag_url = INSTAGRAM_TAG_URL_TEMPLATE.format(keyword=urllib.parse.quote(keyword))
                        if not self._safe_goto(page, tag_url):
                            logger.error("Failed to open Instagram tag page for keyword=%s", keyword)
                            continue

                        self._dismiss_cookie_dialog(page)
                        if not self._wait_for_media_grid(page):
                            logger.error("Instagram media grid not found for keyword=%s", keyword)
                            continue

                        post_urls = self._collect_recent_post_urls(page, MAX_POSTS_PER_KEYWORD)
                        logger.debug("Collected %s Instagram posts for keyword=%s", len(post_urls), keyword)

                        for post_url in post_urls:
                            try:
                                post_data = self._extract_post_data(page, post_url, keyword)
                                if not post_data:
                                    continue

                                platform_post_id = post_data.get("platform_post_id")
                                if platform_post_id and platform_post_id not in deduped:
                                    deduped[platform_post_id] = post_data
                            except Exception:
                                logger.error(
                                    "Failed processing Instagram post url=%s keyword=%s",
                                    post_url,
                                    keyword,
                                    exc_info=True,
                                )
                            self._sleep(1.0, 3.0)
                    except Exception:
                        logger.error("Unrecoverable Instagram fetch error for keyword=%s", keyword, exc_info=True)
                        return []

                    if index < len(normalized_keywords) - 1:
                        self._sleep(2.0, 4.0)

                return list(deduped.values())
        except Exception:
            logger.exception("Instagram fetch_posts failed")
            return []

    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        try:
            with self._bm.locked_page(self._platform) as page:
                post_url = INSTAGRAM_POST_URL_TEMPLATE.format(shortcode=post_id)
                if not self._safe_goto(page, post_url):
                    return False, None, "Failed to open Instagram post"

                self._dismiss_cookie_dialog(page)
                self._wait_for_page_settle(page)

                comment_input = self._find_first_locator(page, POST_COMMENT_INPUT_SELECTORS)
                if comment_input is None:
                    return False, None, "Instagram comment input not found"

                try:
                    comment_input.click(timeout=5000)
                except Exception:
                    logger.error("Failed to focus Instagram comment input", exc_info=True)
                    return False, None, "Failed to focus Instagram comment input"

                if not self._type_like_human(page, message):
                    return False, None, "Failed to type Instagram comment"

                submitted = self._click_submit_button(page)
                if not submitted:
                    try:
                        page.keyboard.press("Enter")
                        submitted = True
                    except Exception:
                        logger.error("Failed to submit Instagram comment via Enter", exc_info=True)
                        submitted = False

                if not submitted:
                    return False, None, "Failed to submit Instagram comment"

                self._sleep(2.0, 3.0)
                return True, None, None
        except Exception as exc:
            logger.error("Instagram reply_to_post failed for post_id=%s", post_id, exc_info=True)
            return False, None, str(exc)

    def check_already_replied(self, post_id: str) -> bool:
        try:
            with self._bm.locked_page(self._platform) as page:
                post_url = INSTAGRAM_POST_URL_TEMPLATE.format(shortcode=post_id)
                if not self._safe_goto(page, post_url):
                    return False

                self._dismiss_cookie_dialog(page)
                self._wait_for_page_settle(page)

                if not self._username:
                    self._username = self._extract_logged_in_username(page) or None
                if not self._username:
                    return False

                self._expand_comments(page)
                comments = self._extract_comments(page)
                own_username = self._username.lower()

                for comment in comments:
                    author = (comment.get("author") or "").lower()
                    text = (comment.get("text") or "").lower()
                    if author == own_username or f"{own_username} " in text or text.startswith(own_username):
                        return True
                return False
        except Exception:
            logger.error("Instagram check_already_replied failed for post_id=%s", post_id, exc_info=True)
            return False

    # Instagram reply_to_post() returns None as reply_id because IG comments
    # don't have stable permalinks. check_reply_visible and delete_reply
    # therefore use the base class defaults (return None / "unsupported").

    def _sleep(self, min_seconds: float, max_seconds: float) -> None:
        time.sleep(random.uniform(min_seconds, max_seconds))

    def _safe_goto(
        self,
        page: Page,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 15000,
    ) -> bool:
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            logger.error("Timeout navigating to Instagram URL: %s", url)
            return False
        except Exception:
            logger.error("Failed navigating to Instagram URL: %s", url, exc_info=True)
            return False

    def _wait_for_page_settle(self, page: Page, timeout_ms: int = 10000) -> bool:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            logger.debug("Instagram domcontentloaded wait did not complete", exc_info=True)

        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return True
        except Exception:
            logger.debug("Instagram networkidle wait did not complete", exc_info=True)
            return False

    def _dismiss_cookie_dialog(self, page: Page) -> None:
        for selector in COOKIE_BUTTON_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1500):
                    locator.click(timeout=3000)
                    self._sleep(0.8, 1.2)
                    logger.debug("Dismissed Instagram cookie dialog using selector=%s", selector)
                    return
            except Exception:
                logger.debug("Cookie selector not actionable: %s", selector, exc_info=True)

    def _is_login_page(self, page: Page) -> bool:
        try:
            return INSTAGRAM_LOGIN_PATH in page.url
        except Exception:
            logger.error("Failed reading Instagram page URL", exc_info=True)
            return False

    def _extract_logged_in_username(self, page: Page) -> str:
        script = """
        ({ profileLinkSelector, profileCurrentSelector, profileImageAltSelector, navSelector, headerSelector, sidebarSelector }) => {
            const roots = [
                document.querySelector(navSelector),
                document.querySelector(headerSelector),
                document.querySelector(sidebarSelector),
                document,
            ].filter(Boolean);

            const extractFromHref = (href) => {
                if (!href) return '';
                const match = href.match(/^\\/([A-Za-z0-9._]+)\\/$/);
                if (!match) return '';
                const candidate = match[1];
                if ([
                    'explore',
                    'accounts',
                    'reels',
                    'direct',
                    'stories',
                    'challenge'
                ].includes(candidate)) {
                    return '';
                }
                return candidate;
            };

            for (const root of roots) {
                const currentProfile = root.querySelector(profileCurrentSelector);
                if (currentProfile) {
                    const alt = currentProfile.querySelector(profileImageAltSelector)?.getAttribute('alt') || '';
                    const altMatch = alt.match(/([A-Za-z0-9._]+)'s profile picture/i);
                    if (altMatch) return altMatch[1];
                }

                const links = root.querySelectorAll(profileLinkSelector);
                for (const link of links) {
                    const candidate = extractFromHref(link.getAttribute('href') || '');
                    if (candidate) return candidate;
                }
            }
            return '';
        }
        """
        try:
            username = page.evaluate(
                script,
                {
                    "profileLinkSelector": PROFILE_LINK_SELECTOR,
                    "profileCurrentSelector": PROFILE_LINK_CURRENT_SELECTOR,
                    "profileImageAltSelector": PROFILE_IMAGE_ALT_SELECTOR,
                    "navSelector": NAV_SELECTOR,
                    "headerSelector": HEADER_SELECTOR,
                    "sidebarSelector": SIDEBAR_SELECTOR,
                },
            )
        except Exception:
            logger.error("Failed extracting Instagram logged-in username", exc_info=True)
            return ""

        if not isinstance(username, str):
            return ""
        return username.strip().lstrip("@")

    def _wait_for_media_grid(self, page: Page) -> bool:
        try:
            page.wait_for_selector(TAG_GRID_ARTICLE_SELECTOR, timeout=10000)
            return True
        except PlaywrightTimeoutError:
            logger.error("Timed out waiting for Instagram article grid")
        except Exception:
            logger.error("Failed waiting for Instagram article grid", exc_info=True)

        try:
            page.wait_for_selector(TAG_GRID_SECTION_SELECTOR, timeout=5000)
            return True
        except PlaywrightTimeoutError:
            logger.error("Timed out waiting for Instagram section grid")
            return False
        except Exception:
            logger.error("Failed waiting for Instagram section grid", exc_info=True)
            return False

    def _collect_recent_post_urls(self, page: Page, limit: int) -> list[str]:
        script = """
        ({ linkSelector, limit }) => {
            const links = Array.from(document.querySelectorAll(linkSelector));
            const results = [];
            const seen = new Set();

            for (const link of links) {
                const href = link.getAttribute('href') || '';
                if (!href.startsWith('/p/')) continue;
                if (seen.has(href)) continue;
                seen.add(href);
                results.push(new URL(href, window.location.origin).toString());
                if (results.length >= limit) break;
            }
            return results;
        }
        """
        try:
            result = page.evaluate(
                script,
                {"linkSelector": TAG_GRID_LINK_SELECTOR, "limit": limit},
            )
        except Exception:
            logger.error("Failed collecting Instagram post URLs from tag grid", exc_info=True)
            return []

        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, str)]

    def _extract_post_data(self, page: Page, post_url: str, keyword: str) -> Optional[dict]:
        if not self._safe_goto(page, post_url):
            return None

        self._wait_for_page_settle(page)
        try:
            page.wait_for_selector(POST_ARTICLE_SELECTOR, timeout=5000)
        except Exception:
            try:
                page.wait_for_selector(POST_DIALOG_SELECTOR, timeout=3000)
            except Exception:
                logger.debug("Instagram post content selectors did not explicitly appear", exc_info=True)

        shortcode = self._extract_shortcode_from_url(page.url)
        if not shortcode:
            shortcode = self._extract_shortcode_from_url(post_url)
        if not shortcode:
            logger.error("Could not extract Instagram shortcode from url=%s", post_url)
            return None

        author_username = self._extract_post_author(page)
        post_content = self._extract_post_caption(page)

        return {
            "platform": "instagram",
            "platform_post_id": shortcode,
            "post_url": INSTAGRAM_POST_URL_TEMPLATE.format(shortcode=shortcode),
            "author_username": author_username,
            "post_content": post_content,
            "keyword_matched": keyword,
        }

    def _extract_shortcode_from_url(self, url: str) -> str:
        if not url:
            return ""
        match = SHORTCODE_URL_PATTERN.search(url)
        if not match:
            return ""
        return match.group(1).strip()

    def _extract_post_author(self, page: Page) -> str:
        script = """
        ({ selector }) => {
            const links = Array.from(document.querySelectorAll(selector));
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const text = (link.textContent || '').trim();
                const match = href.match(/^\\/([A-Za-z0-9._]+)\\/$/);
                if (!match) continue;
                const candidate = match[1];
                if (candidate === 'p') continue;
                if (text && text.replace(/^@/, '') === candidate) return candidate;
                if (candidate) return candidate;
            }
            return '';
        }
        """
        try:
            author = page.evaluate(script, {"selector": POST_HEADER_AUTHOR_SELECTOR})
        except Exception:
            logger.error("Failed extracting Instagram post author", exc_info=True)
            return ""

        if not isinstance(author, str):
            return ""
        return author.strip().lstrip("@")

    def _extract_post_caption(self, page: Page) -> str:
        script = """
        ({ selector, authorLinkSelector }) => {
            const items = Array.from(document.querySelectorAll(selector));
            for (const item of items) {
                const text = (item.innerText || item.textContent || '').trim();
                if (!text) continue;

                const headerLink = item.querySelector(authorLinkSelector);
                const authorText = (headerLink?.textContent || '').trim();
                if (authorText && text.startsWith(authorText)) {
                    return text.slice(authorText.length).trim();
                }

                if (text.length > 1) return text;
            }
            return '';
        }
        """
        try:
            caption = page.evaluate(
                script,
                {
                    "selector": POST_CAPTION_CONTAINER_SELECTOR,
                    "authorLinkSelector": POST_CAPTION_AUTHOR_LINK_SELECTOR,
                },
            )
        except Exception:
            logger.error("Failed extracting Instagram caption", exc_info=True)
            return ""

        if not isinstance(caption, str):
            return ""
        return re.sub(r"\s+", " ", caption).strip()

    def _find_first_locator(self, page: Page, selectors: tuple[str, ...]):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=2000):
                    return locator
            except Exception:
                logger.debug("Instagram locator not found for selector=%s", selector, exc_info=True)
        return None

    def _type_like_human(self, page: Page, message: str) -> bool:
        try:
            for char in message:
                page.keyboard.type(char, delay=int(random.uniform(0.05, 0.15) * 1000))
            return True
        except Exception:
            logger.error("Failed typing Instagram comment message", exc_info=True)
            return False

    def _click_submit_button(self, page: Page) -> bool:
        for selector in POST_SUBMIT_BUTTON_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1500) and locator.is_enabled():
                    locator.click(timeout=3000)
                    return True
            except Exception:
                logger.debug("Instagram submit button not actionable for selector=%s", selector, exc_info=True)
        return False

    def _expand_comments(self, page: Page) -> None:
        for _ in range(COMMENT_LOAD_MORE_CLICKS):
            clicked = False
            for selector in COMMENTS_EXPAND_SELECTORS:
                try:
                    locator = page.locator(selector).first
                    if locator.is_visible(timeout=1500):
                        locator.click(timeout=3000)
                        self._sleep(1.0, 1.5)
                        clicked = True
                        break
                except Exception:
                    logger.debug("Instagram comments expand button not actionable: %s", selector, exc_info=True)
            if not clicked:
                return

    def _extract_comments(self, page: Page) -> list[dict]:
        script = """
        ({ itemSelector, authorLinkSelector }) => {
            const items = Array.from(document.querySelectorAll(itemSelector));
            const results = [];

            for (const item of items) {
                const link = item.querySelector(authorLinkSelector);
                const authorHref = link?.getAttribute('href') || '';
                const authorMatch = authorHref.match(/^\\/([A-Za-z0-9._]+)\\/$/);
                const author = authorMatch ? authorMatch[1] : ((link?.textContent || '').trim());
                const text = (item.innerText || item.textContent || '').trim();
                if (!author && !text) continue;
                results.push({ author, text });
            }

            return results;
        }
        """
        try:
            result = page.evaluate(
                script,
                {
                    "itemSelector": COMMENTS_LIST_ITEM_SELECTOR,
                    "authorLinkSelector": COMMENTS_AUTHOR_LINK_SELECTOR,
                },
            )
        except Exception:
            logger.error("Failed extracting Instagram comments", exc_info=True)
            return []

        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]
