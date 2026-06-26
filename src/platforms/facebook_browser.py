"""Playwright-based Facebook browser adapter."""

import logging
import random
import re
import time
import urllib.parse
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.platforms.base import PlatformAdapter
from src.platforms.browser_manager import BrowserManager

# Feed / post containers.
POST_CONTAINER_SELECTOR_FEEDUNIT = "div[data-pagelet^='FeedUnit_']"
POST_CONTAINER_SELECTOR_FEED_CHILDREN = "div[role='feed'] > div"
POST_CONTAINER_SELECTOR_POST_MESSAGE = "div[data-testid='post_message']"
POST_CONTAINER_SELECTOR_ARTICLE = "article"
POST_CONTAINER_SELECTORS = (
    POST_CONTAINER_SELECTOR_FEEDUNIT,
    POST_CONTAINER_SELECTOR_FEED_CHILDREN,
    POST_CONTAINER_SELECTOR_POST_MESSAGE,
    POST_CONTAINER_SELECTOR_ARTICLE,
)

# Post content.
POST_CONTENT_SELECTOR_TESTID = "div[data-testid='post_message'] p"
POST_CONTENT_SELECTOR_AUTO_DIV = "div[dir='auto']"
POST_CONTENT_SELECTOR_AUTO_SPAN = "span[dir='auto']"
POST_CONTENT_SELECTORS = (
    POST_CONTENT_SELECTOR_TESTID,
    POST_CONTENT_SELECTOR_AUTO_DIV,
    POST_CONTENT_SELECTOR_AUTO_SPAN,
)

# Post link / ID extraction.
POST_LINK_SELECTOR_POSTS = "a[href*='/posts/']"
POST_LINK_SELECTOR_PERMALINK = "a[href*='/permalink/']"
POST_LINK_SELECTOR_STORY_FBID = "a[href*='story_fbid=']"
POST_LINK_SELECTOR_GROUP_POSTS = "a[href*='/groups/'][href*='/posts/']"
POST_LINK_SELECTORS = (
    POST_LINK_SELECTOR_GROUP_POSTS,
    POST_LINK_SELECTOR_POSTS,
    POST_LINK_SELECTOR_PERMALINK,
    POST_LINK_SELECTOR_STORY_FBID,
)

# Author.
AUTHOR_SELECTOR_USER = "a[role='link'][href*='/user/']"
AUTHOR_SELECTOR_H2 = "h2 a"
AUTHOR_SELECTOR_STRONG = "strong a"
AUTHOR_SELECTORS = (
    AUTHOR_SELECTOR_USER,
    AUTHOR_SELECTOR_H2,
    AUTHOR_SELECTOR_STRONG,
)

# Comment input.
COMMENT_INPUT_SELECTOR_ROLE = "div[contenteditable='true'][role='textbox']"
COMMENT_INPUT_SELECTOR_EDITABLE = "div[contenteditable='true']"
COMMENT_INPUT_SELECTOR_FORM = "form div[contenteditable]"
COMMENT_INPUT_SELECTOR_ARIA = "div[aria-label*='comment' i][contenteditable='true']"
COMMENT_INPUT_SELECTOR_TESTID = "div[data-testid='comment-composer-input']"
COMMENT_INPUT_SELECTORS = (
    COMMENT_INPUT_SELECTOR_ROLE,
    COMMENT_INPUT_SELECTOR_ARIA,
    COMMENT_INPUT_SELECTOR_FORM,
    COMMENT_INPUT_SELECTOR_TESTID,
    COMMENT_INPUT_SELECTOR_EDITABLE,
)

# Login check.
LOGIN_SELECTOR_EMAIL = "input[name='email']"
LOGIN_SELECTOR_BUTTON = "button[name='login']"
LOGIN_SELECTOR_FORM = "div[data-testid='royal_login_form']"
LOGIN_CHECK_SELECTORS = (
    LOGIN_SELECTOR_EMAIL,
    LOGIN_SELECTOR_BUTTON,
    LOGIN_SELECTOR_FORM,
)

# Comments section.
COMMENTS_SELECTOR_ARIA = "div[aria-label*='Comment' i]"
COMMENTS_SELECTOR_LIST = "ul[class*='commentList']"
COMMENTS_SELECTOR_ARTICLE = "div[role='article']"
COMMENTS_SECTION_SELECTORS = (
    COMMENTS_SELECTOR_ARIA,
    COMMENTS_SELECTOR_LIST,
    COMMENTS_SELECTOR_ARTICLE,
)

# Feed load wait.
MAIN_SELECTOR = "[role='main']"
PAGELET_SELECTOR = "[data-pagelet]"

logger = logging.getLogger(__name__)


class FacebookBrowserAdapter(PlatformAdapter):
    """Browser automation adapter for Facebook using Playwright."""

    def __init__(self, browser_manager: BrowserManager):
        self._bm = browser_manager

    def check_connection(self) -> tuple[bool, str]:
        """Check whether the current browser session is logged into Facebook."""
        try:
            with self._bm.locked_page("facebook") as page:
                if not self._safe_goto(page, "https://www.facebook.com", "domcontentloaded", 10000):
                    return False, "Failed to open Facebook"

                self._sleep(1.0, 2.0)
                if self._is_login_visible(page):
                    return False, "Not logged in to Facebook"

                username = self._extract_profile_name(page)
                try:
                    self._bm.save_session("facebook")
                except Exception:
                    logger.exception("Failed to save Facebook session after connection check")

                if username:
                    return True, f"Connected as {username}"
                return True, "Connected to Facebook"
        except Exception:
            logger.exception("Facebook check_connection failed")
            return False, "Failed to open Facebook browser page"

    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        """Search Facebook posts by keyword and return deduplicated matches."""
        del since_id

        try:
            with self._bm.locked_page("facebook") as page:
                deduped: dict[str, dict] = {}
                normalized_keywords = [keyword.strip() for keyword in keywords if keyword and keyword.strip()]

                for keyword in normalized_keywords:
                    search_url = (
                        "https://www.facebook.com/search/posts/?q="
                        f"{urllib.parse.quote(keyword)}"
                    )
                    if not self._safe_goto(page, search_url):
                        continue

                    if not self._wait_for_feed(page):
                        logger.warning("Facebook search results did not show a feed for keyword=%s", keyword)

                    self._sleep(1.5, 2.5)
                    self._scroll_page(page, scrolls=4)
                    posts = self._extract_posts_from_page(page, keyword=keyword)

                    for post in posts:
                        platform_post_id = post.get("platform_post_id")
                        if platform_post_id and platform_post_id not in deduped:
                            deduped[platform_post_id] = post

                    self._sleep(2.0, 4.0)

                return list(deduped.values())
        except Exception:
            logger.exception("Facebook fetch_posts failed")
            return []

    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Reply to a Facebook post by posting a browser comment."""
        try:
            with self._bm.locked_page("facebook") as page:
                post_urls = self._candidate_post_urls(post_id)
                if not post_urls:
                    return False, None, "Unable to construct Facebook post URL"

                loaded = False
                for url in post_urls:
                    if self._safe_goto(page, url):
                        loaded = True
                        break
                if not loaded:
                    return False, None, "Failed to open Facebook post"

                self._wait_for_feed(page)
                self._sleep(1.5, 2.5)

                input_locator = self._find_first_locator(page, COMMENT_INPUT_SELECTORS)
                if input_locator is None:
                    return False, None, "Facebook comment input not found"

                try:
                    input_locator.scroll_into_view_if_needed(timeout=5000)
                except Exception:
                    logger.exception("Failed to scroll comment input into view")

                try:
                    input_locator.click(timeout=5000)
                    self._sleep(1.0, 1.5)
                    input_locator.type(message, delay=random.randint(30, 80), timeout=10000)
                    self._sleep(1.0, 1.5)
                    input_locator.press("Enter", timeout=5000)
                except Exception:
                    logger.exception("Failed to submit Facebook comment")
                    return False, None, "Failed to type or submit Facebook comment"

                self._sleep(2.0, 3.0)

                if not self._comment_text_visible(page, message):
                    logger.warning("Submitted Facebook comment but could not confirm visible text for post_id=%s", post_id)

                reply_id = self._extract_reply_id(page, post_id)
                try:
                    self._bm.save_session("facebook")
                except Exception:
                    logger.exception("Failed to save Facebook session after reply")
                return True, reply_id, None
        except Exception:
            logger.exception("Facebook reply_to_post failed")
            return False, None, "Failed to open Facebook browser page"

    def check_already_replied(self, post_id: str) -> bool:
        """Check whether the logged-in account appears to have already commented on a post."""
        try:
            with self._bm.locked_page("facebook") as page:
                post_urls = self._candidate_post_urls(post_id)
                if not post_urls:
                    return False

                loaded = False
                for url in post_urls:
                    if self._safe_goto(page, url):
                        loaded = True
                        break
                if not loaded:
                    return False

                self._wait_for_feed(page)
                self._sleep(1.5, 2.5)
                self._scroll_page(page, scrolls=2)

                profile_name = self._extract_profile_name(page)
                if not profile_name:
                    return False

                comments_text = self._extract_comments_text(page)
                if not comments_text:
                    return False

                return profile_name.lower() in comments_text.lower()
        except Exception:
            logger.exception("Facebook check_already_replied failed")
            return False

    def fetch_from_target(self, target_id: str, keywords: list[str]) -> list[dict]:
        """Fetch Facebook posts from a group or profile/page target and filter by keyword."""
        try:
            with self._bm.locked_page("facebook") as page:
                normalized_keywords = [keyword.strip() for keyword in keywords if keyword and keyword.strip()]
                target_urls = [
                    f"https://www.facebook.com/groups/{target_id}",
                    f"https://www.facebook.com/{target_id}",
                ]

                best_posts: list[dict] = []
                for target_url in target_urls:
                    if not self._safe_goto(page, target_url):
                        continue

                    has_feed = self._wait_for_feed(page)
                    self._sleep(1.5, 2.5)
                    self._scroll_page(page, scrolls=4)
                    posts = self._extract_posts_from_page(page)

                    if posts:
                        best_posts = self._filter_posts_by_keywords(posts, normalized_keywords)
                        if best_posts or has_feed:
                            break

                    if has_feed:
                        logger.warning("Facebook target page loaded but no matching posts found at %s", target_url)
                    else:
                        logger.warning("Facebook target page did not expose a feed at %s", target_url)

                return best_posts
        except Exception:
            logger.exception("Facebook fetch_from_target failed")
            return []

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
            self._sleep(1.0, 2.0)
            return True
        except PlaywrightTimeoutError:
            logger.warning("Timeout navigating to Facebook URL: %s", url)
            return False
        except Exception:
            logger.exception("Failed navigating to Facebook URL: %s", url)
            return False

    def _wait_for_feed(self, page: Page) -> bool:
        try:
            page.wait_for_selector(MAIN_SELECTOR, timeout=10000)
            return True
        except PlaywrightTimeoutError:
            logger.warning("Timed out waiting for Facebook main content")
        except Exception:
            logger.exception("Failed waiting for Facebook main content")

        try:
            page.wait_for_selector(PAGELET_SELECTOR, timeout=5000)
            return True
        except PlaywrightTimeoutError:
            logger.warning("Timed out waiting for Facebook pagelet content")
            return False
        except Exception:
            logger.exception("Failed waiting for Facebook pagelet content")
            return False

    def _scroll_page(self, page: Page, scrolls: int = 4) -> None:
        for _ in range(scrolls):
            try:
                page.mouse.wheel(0, 800)
            except Exception:
                logger.exception("Failed to scroll Facebook page using mouse wheel")
                try:
                    page.evaluate("window.scrollBy(0, 800)")
                except Exception:
                    logger.exception("Failed to scroll Facebook page using window.scrollBy")
            self._sleep(1.5, 2.0)

    def _extract_posts_from_page(self, page: Page, keyword: Optional[str] = None) -> list[dict]:
        raw_posts = self._extract_post_candidates(page)
        posts: list[dict] = []

        for raw_post in raw_posts:
            platform_post_id = self._extract_post_id(raw_post.get("href", ""))
            post_url = self._normalize_post_url(raw_post.get("href", ""))
            post_content = (raw_post.get("content") or "").strip()
            author_username = (raw_post.get("author") or "").strip()

            if not platform_post_id or not post_url or not post_content:
                continue
            if keyword and keyword.lower() not in post_content.lower():
                continue

            posts.append(
                {
                    "platform": "facebook",
                    "platform_post_id": platform_post_id,
                    "post_url": post_url,
                    "author_username": author_username,
                    "post_content": post_content,
                    "created_at": None,
                    "raw_data": {
                        "matched_keyword": keyword,
                        "source_href": raw_post.get("href", ""),
                    },
                }
            )

        deduped: dict[str, dict] = {}
        for post in posts:
            deduped.setdefault(post["platform_post_id"], post)
        return list(deduped.values())

    def _extract_post_candidates(self, page: Page) -> list[dict]:
        script = """
        ({ containerSelectors, contentSelectors, linkSelectors, authorSelectors }) => {
            const results = [];
            const seen = new Set();

            const textFrom = (root, selectors) => {
                for (const selector of selectors) {
                    const nodes = Array.from(root.querySelectorAll(selector));
                    const text = nodes
                        .map((node) => (node.innerText || node.textContent || '').trim())
                        .filter(Boolean)
                        .join(' ')
                        .trim();
                    if (text) return text;
                }
                return '';
            };

            const hrefFrom = (root, selectors) => {
                for (const selector of selectors) {
                    const link = root.querySelector(selector);
                    if (link && link.href) return link.href;
                }
                return '';
            };

            for (const containerSelector of containerSelectors) {
                const nodes = document.querySelectorAll(containerSelector);
                for (const node of nodes) {
                    const href = hrefFrom(node, linkSelectors);
                    const content = textFrom(node, contentSelectors);
                    const author = textFrom(node, authorSelectors);
                    const key = `${href}||${content}`;
                    if (!href || !content || seen.has(key)) continue;
                    seen.add(key);
                    results.push({ href, content, author });
                }
            }

            return results;
        }
        """
        try:
            result = page.evaluate(
                script,
                {
                    "containerSelectors": list(POST_CONTAINER_SELECTORS),
                    "contentSelectors": list(POST_CONTENT_SELECTORS),
                    "linkSelectors": list(POST_LINK_SELECTORS),
                    "authorSelectors": list(AUTHOR_SELECTORS),
                },
            )
        except Exception:
            logger.exception("Failed extracting Facebook posts from DOM")
            return []

        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    def _filter_posts_by_keywords(self, posts: list[dict], keywords: list[str]) -> list[dict]:
        if not keywords:
            return posts

        filtered: list[dict] = []
        for post in posts:
            content = (post.get("post_content") or "").lower()
            matched_keyword = next((kw for kw in keywords if kw.lower() in content), None)
            if matched_keyword:
                raw_data = dict(post.get("raw_data") or {})
                raw_data["matched_keyword"] = matched_keyword
                cloned = dict(post)
                cloned["raw_data"] = raw_data
                filtered.append(cloned)
        return filtered

    def _is_login_visible(self, page: Page) -> bool:
        for selector in LOGIN_CHECK_SELECTORS:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=2000)
                if locator.is_visible():
                    return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                logger.exception("Failed checking Facebook login selector: %s", selector)
        return False

    def _extract_profile_name(self, page: Page) -> str:
        script = """
        () => {
            const candidates = [
                "a[aria-label*='Profile']",
                "a[href*='/me/']",
                "a[href*='profile.php']",
                "a[href^='https://www.facebook.com/'][role='link']",
                "svg[aria-label*='Your profile']"
            ];

            for (const selector of candidates) {
                const nodes = document.querySelectorAll(selector);
                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || node.getAttribute('aria-label') || '').trim();
                    if (text && text.length < 120) return text;
                    const parent = node.closest('a, div');
                    const parentText = (parent?.innerText || parent?.textContent || '').trim();
                    if (parentText && parentText.length < 120) return parentText;
                }
            }
            return '';
        }
        """
        try:
            name = page.evaluate(script)
        except Exception:
            logger.exception("Failed extracting Facebook profile name")
            return ""

        if not isinstance(name, str):
            return ""
        return re.sub(r"\s+", " ", name).strip()

    def _candidate_post_urls(self, post_id: str) -> list[str]:
        if not post_id:
            return []

        if post_id.startswith("http://") or post_id.startswith("https://"):
            return [post_id]

        post_id = post_id.strip()
        urls = [
            f"https://www.facebook.com/{post_id}",
            f"https://www.facebook.com/permalink.php?story_fbid={urllib.parse.quote(post_id)}&id={urllib.parse.quote(post_id)}",
        ]

        if "_" in post_id:
            owner_id, story_fbid = post_id.split("_", 1)
            urls.insert(
                0,
                "https://www.facebook.com/permalink.php?"
                f"story_fbid={urllib.parse.quote(story_fbid)}&id={urllib.parse.quote(owner_id)}",
            )
        return list(dict.fromkeys(urls))

    def _extract_post_id(self, url: str) -> str:
        if not url:
            return ""

        patterns = [
            r"/groups/[^/]+/posts/(\d+)",
            r"/posts/(\d+)",
            r"/permalink/(\d+)",
            r"story_fbid=(\d+).*?[?&]id=(\d+)",
            r"[?&]story_fbid=(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if not match:
                continue
            if len(match.groups()) >= 2:
                return f"{match.group(2)}_{match.group(1)}"
            return match.group(1)
        return ""

    def _normalize_post_url(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("/"):
            return urllib.parse.urljoin("https://www.facebook.com", url)
        return url

    def _find_first_locator(self, page: Page, selectors: tuple[str, ...]):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                locator.wait_for(state="visible", timeout=2000)
                if locator.is_visible():
                    return locator
            except PlaywrightTimeoutError:
                continue
            except Exception:
                logger.exception("Failed locating Facebook selector: %s", selector)
        return None

    def _comment_text_visible(self, page: Page, message: str) -> bool:
        escaped = re.escape(message.strip())
        if not escaped:
            return False
        try:
            locator = page.get_by_text(re.compile(escaped, re.IGNORECASE)).first
            locator.wait_for(state="visible", timeout=3000)
            return locator.is_visible()
        except PlaywrightTimeoutError:
            return False
        except Exception:
            logger.exception("Failed checking for visible Facebook comment text")
            return False

    def _extract_reply_id(self, page: Page, fallback_post_id: str) -> Optional[str]:
        """Extract a permalink URL for the posted comment.

        Returns a full URL (starting with http) so that check_reply_visible()
        can navigate to it. Falls back to None if no permalink is found.
        """
        script = """
        () => {
            const anchors = Array.from(document.querySelectorAll("a[href*='comment_id='], a[href*='/comment/']"));
            for (const anchor of anchors) {
                if (anchor.href) return anchor.href;
            }
            return '';
        }
        """
        try:
            href = page.evaluate(script)
        except Exception:
            logger.exception("Failed extracting Facebook reply id from DOM")
            return None

        if isinstance(href, str) and href.startswith("http"):
            # Return full permalink URL for later visibility checks
            return href

        return None

    def check_reply_visible(self, reply_id: str) -> bool | None:
        """Check if a Facebook comment is still visible.

        Only works when reply_id is a full URL containing comment_id.
        Numeric-only comment IDs cannot be navigated to directly.
        """
        if not reply_id or not reply_id.startswith("http"):
            return None  # Cannot check without a permalink
        try:
            with self._bm.locked_page("facebook") as page:
                if not self._safe_goto(page, reply_id):
                    return None
                self._wait_for_feed(page)
                self._sleep(1.0, 2.0)
                comments_text = self._extract_comments_text(page)
                return True if comments_text else False
        except Exception:
            logger.exception("Facebook check_reply_visible failed")
            return None

    def _extract_comments_text(self, page: Page) -> str:
        script = """
        (selectors) => {
            const chunks = [];
            for (const selector of selectors) {
                const nodes = document.querySelectorAll(selector);
                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').trim();
                    if (text) chunks.push(text);
                }
            }
            return chunks.join('\\n');
        }
        """
        try:
            comments_text = page.evaluate(script, list(COMMENTS_SECTION_SELECTORS))
        except Exception:
            logger.exception("Failed extracting Facebook comments text")
            return ""

        if not isinstance(comments_text, str):
            return ""
        return comments_text
