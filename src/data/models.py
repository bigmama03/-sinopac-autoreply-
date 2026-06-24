"""Data models for the application."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Template:
    id: Optional[int] = None
    template_code: str = ""
    category: str = ""
    content: str = ""
    platforms: str = "threads;fb;ig"
    keywords: Optional[str] = None  # JSON array
    priority: int = 0
    is_active: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class DetectedPost:
    id: Optional[int] = None
    platform: str = ""
    platform_post_id: str = ""
    post_url: Optional[str] = None
    author_username: Optional[str] = None
    post_content: str = ""
    matched_keywords: Optional[str] = None  # JSON array
    relevance_score: float = 0.0
    recommended_template_id: Optional[int] = None
    status: str = "pending"  # pending|approved|rejected|replied|failed|skipped
    detected_at: Optional[str] = None
    reviewed_at: Optional[str] = None


@dataclass
class ReplyLog:
    id: Optional[int] = None
    detected_post_id: int = 0
    template_id: int = 0
    platform: str = ""
    reply_content: str = ""
    reply_mode: str = "semi_auto"  # semi_auto|full_auto
    platform_reply_id: Optional[str] = None
    status: str = "pending"  # pending|sent|failed|retrying
    error_message: Optional[str] = None
    retry_count: int = 0
    sent_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class PlatformConfig:
    id: Optional[int] = None
    platform: str = ""
    is_enabled: bool = False
    access_token: Optional[str] = None  # Encrypted
    page_id: Optional[str] = None
    ig_user_id: Optional[str] = None
    threads_user_id: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None  # Encrypted
    token_expires_at: Optional[str] = None
    last_connected_at: Optional[str] = None
    config_json: Optional[str] = None  # Additional config
    updated_at: Optional[str] = None


@dataclass
class Keyword:
    id: Optional[int] = None
    keyword: str = ""
    category: Optional[str] = None
    weight: float = 1.0
    is_active: bool = True
    created_at: Optional[str] = None


@dataclass
class AuditLog:
    id: Optional[int] = None
    action: str = ""
    details: Optional[str] = None  # JSON
    timestamp: Optional[str] = None


@dataclass
class PatrolSession:
    id: Optional[int] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    platforms: str = ""  # JSON array
    total_detected: int = 0
    total_replied: int = 0
    total_skipped: int = 0
    status: str = "running"  # running|stopped|error
