"""Instagram Graph API adapter — hashtag search + comment reply."""

import logging
from typing import Optional

import requests

from src.platforms.base import PlatformAdapter
from src.platforms.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

IG_API_BASE = "https://graph.facebook.com/v25.0"


class InstagramAdapter(PlatformAdapter):
    """Instagram Graph API integration for hashtag discovery and comment replies."""

    def __init__(self, ig_user_id: str, access_token: str,
                 api_limiter: RateLimiter, hashtag_limiter: RateLimiter):
        self.ig_user_id = ig_user_id
        self.access_token = access_token
        self.api_limiter = api_limiter
        self.hashtag_limiter = hashtag_limiter
        self.session = requests.Session()
        self._hashtag_id_cache: dict[str, str] = {}

    def _params(self, extra: Optional[dict] = None) -> dict:
        params = {"access_token": self.access_token}
        if extra:
            params.update(extra)
        return params

    def check_connection(self) -> tuple[bool, str]:
        try:
            resp = self.session.get(
                f"{IG_API_BASE}/{self.ig_user_id}",
                params=self._params({"fields": "id,username"}),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, f"已連線: @{data.get('username', 'unknown')}"
            return False, f"API 錯誤: {resp.status_code} {resp.text[:100]}"
        except requests.RequestException as e:
            return False, f"連線失敗: {e}"

    def _get_hashtag_id(self, hashtag: str) -> Optional[str]:
        """Look up hashtag ID. Uses cache to save API calls."""
        # Remove # prefix if present
        hashtag = hashtag.lstrip("#")

        if hashtag in self._hashtag_id_cache:
            return self._hashtag_id_cache[hashtag]

        if not self.hashtag_limiter.acquire():
            logger.warning("Instagram hashtag search limit reached (30/week)")
            return None

        if not self.api_limiter.acquire():
            logger.warning("Instagram API rate limit reached")
            return None

        try:
            resp = self.session.get(
                f"{IG_API_BASE}/ig_hashtag_search",
                params=self._params({"q": hashtag}),
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    hid = data[0].get("id", "")
                    self._hashtag_id_cache[hashtag] = hid
                    return hid
            else:
                self._check_token_expiry(resp)
                logger.error("IG hashtag search failed: %s", resp.text[:200])

        except requests.RequestException as e:
            logger.error("IG hashtag search error: %s", e)

        return None

    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        """Search Instagram posts by hashtags."""
        all_posts = []

        for keyword in keywords:
            hashtag_id = self._get_hashtag_id(keyword)
            if not hashtag_id:
                continue

            if not self.api_limiter.acquire():
                logger.warning("Instagram API rate limit reached")
                break

            try:
                resp = self.session.get(
                    f"{IG_API_BASE}/{hashtag_id}/recent_media",
                    params=self._params({
                        "user_id": self.ig_user_id,
                        "fields": "id,caption,permalink,comments_count,timestamp",
                    }),
                    timeout=15,
                )

                if resp.status_code != 200:
                    self._check_token_expiry(resp)
                    logger.error("IG recent_media failed: %s", resp.text[:200])
                    continue

                data = resp.json()
                for media in data.get("data", []):
                    all_posts.append({
                        "platform_post_id": media.get("id", ""),
                        "post_url": media.get("permalink", ""),
                        "author_username": "",  # Not available from hashtag search
                        "post_content": media.get("caption", ""),
                    })

            except requests.RequestException as e:
                logger.error("IG fetch error for hashtag '%s': %s", keyword, e)

        return all_posts

    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Comment on an Instagram media post."""
        if not self.api_limiter.acquire():
            return False, None, "已達 API 呼叫上限"

        try:
            resp = self.session.post(
                f"{IG_API_BASE}/{post_id}/comments",
                data={"message": message, "access_token": self.access_token},
                timeout=15,
            )

            if resp.status_code == 200:
                reply_id = resp.json().get("id", "")
                logger.info("Instagram comment sent: %s → %s", post_id, reply_id)
                return True, reply_id, None
            else:
                self._check_token_expiry(resp)
                try:
                    error = resp.json().get("error", {}).get("message", resp.text[:200])
                except (ValueError, KeyError):
                    error = resp.text[:200]
                return False, None, f"留言失敗: {error}"

        except requests.RequestException as e:
            return False, None, f"網路錯誤: {e}"

    def check_reply_visible(self, reply_id: str) -> bool | None:
        """Check if an Instagram comment is still visible."""
        try:
            if not self.api_limiter.acquire():
                return None
            resp = self.session.get(
                f"{IG_API_BASE}/{reply_id}",
                params=self._params({"fields": "id,text"}),
                timeout=10,
            )
            if resp.status_code == 200:
                return True
            if resp.status_code in (404, 400):
                return False
            return None
        except requests.RequestException:
            return None

    def delete_reply(self, reply_id: str) -> tuple[bool, str]:
        """Delete an Instagram comment."""
        try:
            resp = self.session.delete(
                f"{IG_API_BASE}/{reply_id}",
                params={"access_token": self.access_token},
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Instagram comment deleted: %s", reply_id)
                return True, ""
            if resp.status_code in (404, 400):
                logger.info("Instagram comment already gone: %s", reply_id)
                return True, ""
            try:
                error = resp.json().get("error", {}).get("message", resp.text[:200])
            except (ValueError, KeyError):
                error = resp.text[:200]
            return False, f"刪除失敗: {error}"
        except requests.RequestException as e:
            return False, f"網路錯誤: {e}"

    def check_already_replied(self, post_id: str) -> bool:
        """Check if we already commented on this media."""
        try:
            if not self.api_limiter.acquire():
                return False

            resp = self.session.get(
                f"{IG_API_BASE}/{post_id}/comments",
                params=self._params({"fields": "id,username"}),
                timeout=10,
            )
            if resp.status_code != 200:
                return False

            own_username = self._get_own_username()
            if not own_username:
                return False

            data = resp.json()
            for comment in data.get("data", []):
                if comment.get("username") == own_username:
                    return True
            return False
        except requests.RequestException:
            return False

    def _get_own_username(self) -> str:
        """Get our account username (cached). Only caches non-empty results."""
        if getattr(self, "_username", ""):
            return self._username
        try:
            resp = self.session.get(
                f"{IG_API_BASE}/{self.ig_user_id}",
                params=self._params({"fields": "username"}),
                timeout=10,
            )
            self._check_token_expiry(resp)
            if resp.status_code == 200:
                username = resp.json().get("username", "")
                if username:
                    self._username = username
                    return username
        except requests.RequestException:
            pass
        return ""

    def _check_token_expiry(self, resp: requests.Response):
        """Log a warning if the API returns 401/403 (likely token expired)."""
        if resp.status_code in (401, 403):
            logger.warning("Instagram API returned %d — access token may be expired or revoked. "
                           "Response: %s", resp.status_code, resp.text[:200])
