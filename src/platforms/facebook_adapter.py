"""Facebook Graph API adapter — monitor groups/pages + reply."""

import logging
from typing import Optional

import requests

from src.platforms.base import PlatformAdapter
from src.platforms.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

FB_API_BASE = "https://graph.facebook.com/v25.0"


class FacebookAdapter(PlatformAdapter):
    """Facebook Graph API integration for page comment monitoring and reply."""

    def __init__(self, page_id: str, access_token: str,
                 app_id: str, rate_limiter: RateLimiter):
        self.page_id = page_id
        self.access_token = access_token
        self.app_id = app_id
        self.rate_limiter = rate_limiter
        self.session = requests.Session()

    def _params(self, extra: Optional[dict] = None) -> dict:
        params = {"access_token": self.access_token}
        if extra:
            params.update(extra)
        return params

    def check_connection(self) -> tuple[bool, str]:
        try:
            resp = self.session.get(
                f"{FB_API_BASE}/{self.page_id}",
                params=self._params({"fields": "id,name"}),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, f"已連線: {data.get('name', 'unknown')}"
            return False, f"API 錯誤: {resp.status_code} {resp.text[:100]}"
        except requests.RequestException as e:
            return False, f"連線失敗: {e}"

    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        """Fetch recent posts from monitored pages/groups and filter by keywords."""
        all_posts = []

        # Monitor the page's own feed for comments with keywords
        if not self.rate_limiter.acquire():
            logger.warning("Facebook rate limit reached")
            return []

        try:
            resp = self.session.get(
                f"{FB_API_BASE}/{self.page_id}/feed",
                params=self._params({
                    "fields": "id,message,created_time,comments{id,message,from,created_time}",
                    "limit": "25",
                }),
                timeout=15,
            )

            if resp.status_code != 200:
                self._check_token_expiry(resp)
                logger.error("Facebook feed fetch failed: %s", resp.text[:200])
                return []

            data = resp.json()
            for post in data.get("data", []):
                comments = post.get("comments", {}).get("data", [])
                for comment in comments:
                    comment_text = comment.get("message", "")
                    # Check if comment matches any keyword
                    if any(kw.lower() in comment_text.lower() for kw in keywords):
                        from_user = comment.get("from", {})
                        all_posts.append({
                            "platform_post_id": comment.get("id", ""),
                            "post_url": f"https://www.facebook.com/{comment.get('id', '')}",
                            "author_username": from_user.get("name", ""),
                            "post_content": comment_text,
                        })

        except requests.RequestException as e:
            logger.error("Facebook feed error: %s", e)

        return all_posts

    def fetch_from_target(self, target_id: str, keywords: list[str]) -> list[dict]:
        """Fetch posts from a specific group/page and filter by keywords."""
        posts = []

        if not self.rate_limiter.acquire():
            return []

        try:
            resp = self.session.get(
                f"{FB_API_BASE}/{target_id}/feed",
                params=self._params({
                    "fields": "id,message,from,created_time,permalink_url",
                    "limit": "25",
                }),
                timeout=15,
            )

            if resp.status_code != 200:
                self._check_token_expiry(resp)
                logger.error("Facebook target %s fetch failed: %s", target_id, resp.text[:200])
                return []

            data = resp.json()
            for post in data.get("data", []):
                post_text = post.get("message", "")
                if any(kw.lower() in post_text.lower() for kw in keywords):
                    from_user = post.get("from", {})
                    posts.append({
                        "platform_post_id": post.get("id", ""),
                        "post_url": post.get("permalink_url", ""),
                        "author_username": from_user.get("name", ""),
                        "post_content": post_text,
                    })

        except requests.RequestException as e:
            logger.error("Facebook target %s error: %s", target_id, e)

        return posts

    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Reply to a post/comment on Facebook."""
        if not self.rate_limiter.acquire():
            return False, None, "已達 API 呼叫上限"

        try:
            resp = self.session.post(
                f"{FB_API_BASE}/{post_id}/comments",
                data={"message": message, "access_token": self.access_token},
                timeout=15,
            )

            if resp.status_code == 200:
                reply_id = resp.json().get("id", "")
                logger.info("Facebook reply sent: %s → %s", post_id, reply_id)
                return True, reply_id, None
            else:
                self._check_token_expiry(resp)
                try:
                    error = resp.json().get("error", {}).get("message", resp.text[:200])
                except (ValueError, KeyError):
                    error = resp.text[:200]
                return False, None, f"回覆失敗: {error}"

        except requests.RequestException as e:
            return False, None, f"網路錯誤: {e}"

    def check_reply_visible(self, reply_id: str) -> bool | None:
        """Check if a Facebook comment is still visible."""
        try:
            resp = self.session.get(
                f"{FB_API_BASE}/{reply_id}",
                params=self._params({"fields": "id,message"}),
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
        """Delete a Facebook comment."""
        try:
            resp = self.session.delete(
                f"{FB_API_BASE}/{reply_id}",
                params={"access_token": self.access_token},
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Facebook comment deleted: %s", reply_id)
                return True, ""
            if resp.status_code in (404, 400):
                logger.info("Facebook comment already gone: %s", reply_id)
                return True, ""
            try:
                error = resp.json().get("error", {}).get("message", resp.text[:200])
            except (ValueError, KeyError):
                error = resp.text[:200]
            return False, f"刪除失敗: {error}"
        except requests.RequestException as e:
            return False, f"網路錯誤: {e}"

    def _check_token_expiry(self, resp: requests.Response):
        """Log a warning if the API returns 401/403 (likely token expired)."""
        if resp.status_code in (401, 403):
            logger.warning("Facebook API returned %d — access token may be expired or revoked. "
                           "Response: %s", resp.status_code, resp.text[:200])

    def check_already_replied(self, post_id: str) -> bool:
        """Check if our page already replied to this post/comment."""
        try:
            resp = self.session.get(
                f"{FB_API_BASE}/{post_id}/comments",
                params=self._params({"fields": "from{id}"}),
                timeout=10,
            )
            if resp.status_code != 200:
                return False

            data = resp.json()
            for comment in data.get("data", []):
                from_id = comment.get("from", {}).get("id", "")
                if from_id == self.page_id:
                    return True
            return False
        except requests.RequestException:
            return False
