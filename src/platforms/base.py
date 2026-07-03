"""Abstract base class for platform adapters."""

from abc import ABC, abstractmethod
from typing import Optional


class PlatformAdapter(ABC):
    """Interface that all platform adapters must implement."""

    @abstractmethod
    def check_connection(self) -> tuple[bool, str]:
        """Test API connection. Returns (success, message)."""
        ...

    @abstractmethod
    def fetch_posts(self, keywords: list[str], since_id: Optional[str] = None) -> list[dict]:
        """Fetch posts matching keywords.
        Returns list of dicts with keys:
            platform_post_id, post_url, author_username, post_content
        """
        ...

    @abstractmethod
    def reply_to_post(self, post_id: str, message: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Reply to a post.
        Returns (success, platform_reply_id, error_message).
        """
        ...

    @abstractmethod
    def check_already_replied(self, post_id: str) -> bool:
        """Check if we already replied to this post."""
        ...

    def fetch_post_comments(self, post_url: str) -> list[dict]:
        """Fetch comments on a specific post.
        Returns list of dicts with keys:
            platform_post_id, post_url, author_username, post_content
        Default: empty list (not supported).
        """
        return []

    def check_reply_visible(self, reply_id: str) -> bool | None:
        """Check if a sent reply is still visible. Returns None if check is unsupported."""
        return None

    def delete_reply(self, reply_id: str) -> tuple[bool, str]:
        """Delete a reply from the platform.
        Returns (success, error_message).
        """
        return False, "此平台不支援刪除回覆"
