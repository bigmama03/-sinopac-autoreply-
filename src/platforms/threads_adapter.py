"""Threads API adapter — keyword search + reply."""

import logging
import threading
from typing import Optional

import requests

from src.platforms.base import PlatformAdapter
from src.platforms.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

THREADS_API_BASE = "https://graph.threads.net/v1.0"


class ThreadsAdapter(PlatformAdapter):
    """Threads API integration for keyword search and reply."""

    def __init__(self, user_id: str, access_token: str,
                 search_limiter: RateLimiter, reply_limiter: RateLimiter):
        self.user_id = user_id
        self.access_token = access_token
        self.search_limiter = search_limiter
        self.reply_limiter = reply_limiter
        self._token_lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})

    def update_token(self, new_token: str):
        """Atomically update access token and session header."""
        with self._token_lock:
            self.access_token = new_token
            self.session.headers["Authorization"] = f"Bearer {new_token}"

    def check_connection(self) -> tuple[bool, str]:
        try:
            resp = self.session.get(
                f"{THREADS_API_BASE}/me",
                params={"fields": "id,username"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, f"已連線: @{data.get('username', 'unknown')}"
            return False, f"API 錯誤: {resp.status_code} {resp.text[:100]}"
        except requests.RequestException as e:
            return False, f"連線失敗: {e}"

    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        """Search Threads posts by keywords."""
        all_posts = []

        for keyword in keywords:
            if not self.search_limiter.acquire():
                logger.warning("Threads search rate limit reached")
                break

            try:
                params = {
                    "q": keyword,
                    "search_type": "TOP",
                    "fields": "id,text,username,permalink,timestamp",
                }
                resp = self.session.get(
                    f"{THREADS_API_BASE}/keyword_search",
                    params=params,
                    timeout=15,
                )

                if resp.status_code != 200:
                    logger.error("Threads search failed: %s %s", resp.status_code, resp.text[:200])
                    continue

                data = resp.json()
                for post in data.get("data", []):
                    all_posts.append({
                        "platform_post_id": post.get("id", ""),
                        "post_url": post.get("permalink", ""),
                        "author_username": post.get("username", ""),
                        "post_content": post.get("text", ""),
                    })

            except requests.RequestException as e:
                logger.error("Threads search error for '%s': %s", keyword, e)

        return all_posts

    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Reply to a Threads post (two-step: create container → publish)."""
        if not self.reply_limiter.acquire():
            return False, None, "已達每日回覆上限"

        try:
            # Step 1: Create reply container
            create_resp = self.session.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads",
                data={
                    "media_type": "TEXT",
                    "text": message,
                    "reply_to_id": post_id,
                },
                timeout=15,
            )

            if create_resp.status_code != 200:
                error = create_resp.json().get("error", {}).get("message", create_resp.text[:200])
                return False, None, f"建立回覆失敗: {error}"

            container_id = create_resp.json().get("id")
            if not container_id:
                return False, None, "建立回覆容器失敗：無回傳 ID"

            # Step 2: Publish the reply
            publish_resp = self.session.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads_publish",
                data={"creation_id": container_id},
                timeout=15,
            )

            if publish_resp.status_code != 200:
                error = publish_resp.json().get("error", {}).get("message", publish_resp.text[:200])
                return False, None, f"發佈回覆失敗: {error}"

            reply_id = publish_resp.json().get("id", "")
            logger.info("Threads reply sent: %s → %s", post_id, reply_id)
            return True, reply_id, None

        except requests.RequestException as e:
            return False, None, f"網路錯誤: {e}"

    def check_already_replied(self, post_id: str) -> bool:
        """Check if our account already replied to this post."""
        try:
            resp = self.session.get(
                f"{THREADS_API_BASE}/{post_id}/replies",
                params={"fields": "id,username"},
                timeout=10,
            )
            if resp.status_code != 200:
                return False

            data = resp.json()
            for reply in data.get("data", []):
                # Check if any reply is from our account
                if reply.get("username") == self._get_own_username():
                    return True
            return False
        except requests.RequestException:
            return False

    def check_reply_visible(self, reply_id: str) -> bool | None:
        """Check if a Threads reply is still visible."""
        try:
            resp = self.session.get(
                f"{THREADS_API_BASE}/{reply_id}",
                params={"fields": "id,text"},
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
        """Delete a Threads reply."""
        try:
            resp = self.session.delete(
                f"{THREADS_API_BASE}/{reply_id}",
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Threads reply deleted: %s", reply_id)
                return True, ""
            if resp.status_code in (404, 400):
                logger.info("Threads reply already gone: %s", reply_id)
                return True, ""
            try:
                error = resp.json().get("error", {}).get("message", resp.text[:200])
            except (ValueError, KeyError):
                error = resp.text[:200]
            return False, f"刪除失敗: {error}"
        except requests.RequestException as e:
            return False, f"網路錯誤: {e}"

    def _get_own_username(self) -> str:
        """Get our account username (cached)."""
        if not hasattr(self, "_username"):
            try:
                resp = self.session.get(
                    f"{THREADS_API_BASE}/me",
                    params={"fields": "username"},
                    timeout=10,
                )
                self._username = resp.json().get("username", "") if resp.status_code == 200 else ""
            except requests.RequestException:
                self._username = ""
        return self._username
