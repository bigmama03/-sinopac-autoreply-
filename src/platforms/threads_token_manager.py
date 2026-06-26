"""Threads OAuth token lifecycle: exchange short-lived → long-lived, auto-refresh."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

THREADS_API_BASE = "https://graph.threads.net"


def exchange_for_long_lived_token(
    short_lived_token: str, app_secret: str,
) -> tuple[str, datetime]:
    """Exchange a short-lived token (1h) for a long-lived token (60 days).

    Returns (long_lived_token, expires_at).
    Raises ValueError on failure.
    """
    try:
        resp = requests.get(
            f"{THREADS_API_BASE}/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": app_secret,
                "access_token": short_lived_token,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise ValueError(f"Token 交換網路錯誤: {e}") from e

    if resp.status_code != 200:
        error = _extract_error(resp)
        raise ValueError(f"Token 交換失敗: {error}")

    data = resp.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 5184000)  # default 60 days

    if not token:
        raise ValueError("Token 交換失敗: 未回傳 access_token")

    expires_at = datetime.now() + timedelta(seconds=expires_in)
    logger.info("Threads token exchanged, expires at %s", expires_at.isoformat())
    return token, expires_at


def refresh_long_lived_token(current_token: str) -> tuple[str, datetime]:
    """Refresh a long-lived token. Token must be valid and at least 24h before expiry.

    Returns (new_token, new_expires_at).
    Raises ValueError on failure.
    """
    try:
        resp = requests.get(
            f"{THREADS_API_BASE}/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": current_token,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise ValueError(f"Token 刷新網路錯誤: {e}") from e

    if resp.status_code != 200:
        error = _extract_error(resp)
        raise ValueError(f"Token 刷新失敗: {error}")

    data = resp.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 5184000)

    if not token:
        raise ValueError("Token 刷新失敗: 未回傳 access_token")

    expires_at = datetime.now() + timedelta(seconds=expires_in)
    logger.info("Threads token refreshed, expires at %s", expires_at.isoformat())
    return token, expires_at


def check_token_expiry(expires_at_str: Optional[str]) -> dict:
    """Check token expiry status.

    Returns dict with keys: is_valid, days_remaining, status_text, needs_refresh.
    """
    if not expires_at_str:
        return {
            "is_valid": None,
            "days_remaining": None,
            "status_text": "未知（無到期資訊）",
            "needs_refresh": False,
        }

    try:
        # Normalize timezone-aware strings to naive local time
        raw = expires_at_str.replace("Z", "+00:00")
        expires_at = datetime.fromisoformat(raw)
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone().replace(tzinfo=None)
    except (ValueError, TypeError):
        return {
            "is_valid": None,
            "days_remaining": None,
            "status_text": "無法解析到期時間",
            "needs_refresh": False,
        }

    remaining = expires_at - datetime.now()
    days = remaining.days

    if days < 0:
        return {
            "is_valid": False,
            "days_remaining": days,
            "status_text": f"已過期 {abs(days)} 天",
            "needs_refresh": False,
        }
    elif days <= 7:
        return {
            "is_valid": True,
            "days_remaining": days,
            "status_text": f"即將到期（剩餘 {days} 天）",
            "needs_refresh": True,
        }
    else:
        return {
            "is_valid": True,
            "days_remaining": days,
            "status_text": f"有效（剩餘 {days} 天，到期 {expires_at.strftime('%Y-%m-%d')}）",
            "needs_refresh": False,
        }


def _extract_error(resp: requests.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", resp.text[:200])
        return str(err)[:200]
    except (ValueError, KeyError):
        return resp.text[:200]
