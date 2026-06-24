"""Compliance enforcement — template-only replies, duplicate prevention, audit."""

import csv
import logging
from datetime import datetime
from typing import Optional

from src.data.repository import Repository

logger = logging.getLogger(__name__)


class ComplianceGate:
    """Enforces compliance rules before any reply is sent."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def can_reply(self, platform: str, platform_post_id: str) -> tuple[bool, str]:
        """Check all compliance rules. Returns (allowed, reason)."""

        # Rule 1: Duplicate check — never reply to the same post twice
        if self.repo.is_post_already_detected(platform, platform_post_id):
            existing = self.repo.db.execute(
                """SELECT dp.id, rl.status FROM detected_posts dp
                   LEFT JOIN reply_log rl ON rl.detected_post_id = dp.id
                   WHERE dp.platform = ? AND dp.platform_post_id = ?
                   AND rl.status = 'sent'""",
                (platform, platform_post_id),
            ).fetchone()
            if existing:
                return False, "已回覆過此貼文"

        # Rule 2: Daily limit check
        daily_limit_key = f"daily_limit_{platform}"
        limit_str = self.repo.get_setting(daily_limit_key, "40")
        try:
            daily_limit = int(limit_str)
        except ValueError:
            daily_limit = 40

        today_count = self.repo.count_replies_today(platform)
        if today_count >= daily_limit:
            return False, f"已達每日上限 ({today_count}/{daily_limit})"

        # Rule 3: Business hours check
        start_str = self.repo.get_setting("business_hours_start", "09:00")
        end_str = self.repo.get_setting("business_hours_end", "18:00")
        now = datetime.now()
        try:
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            start_time = now.replace(hour=start_h, minute=start_m, second=0)
            end_time = now.replace(hour=end_h, minute=end_m, second=0)
            if not (start_time <= now <= end_time):
                return False, f"非營業時間 ({start_str}-{end_str})"
        except (ValueError, TypeError):
            pass  # If parsing fails, skip this check

        return True, ""

    def check_template_valid(self, post_id: int, template_id: int) -> tuple[bool, Optional[str]]:
        """Check if template is valid for reply."""
        template = self.repo.get_template_by_id(template_id)
        if not template:
            return False, "文案不存在"
        if not template.is_active:
            return False, "文案已停用"

        existing = self.repo.db.execute(
            "SELECT 1 FROM reply_log WHERE detected_post_id = ? AND status = 'sent'",
            (post_id,)
        ).fetchone()
        if existing:
            return False, "此貼文已回覆過"

        return True, None

    def check_warmup(self, platform: str) -> float:
        """Return the warmup ratio (0.0-1.0) for reply limiting during warmup period.
        Returns 1.0 if warmup is complete.
        """
        warmup_days = int(self.repo.get_setting("warmup_days", "3"))
        warmup_ratio = float(self.repo.get_setting("warmup_ratio", "0.3"))

        row = self.repo.db.execute(
            """SELECT MIN(sent_at) FROM reply_log
               WHERE platform = ? AND status = 'sent'""",
            (platform,),
        ).fetchone()

        if not row or not row[0]:
            return warmup_ratio

        try:
            first_reply = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            days_active = (datetime.now() - first_reply).days
            if days_active < warmup_days:
                progress = days_active / warmup_days
                return warmup_ratio + (1.0 - warmup_ratio) * progress
        except (ValueError, TypeError):
            pass

        return 1.0

    def export_audit_csv(self, file_path: str, limit: int = 10000) -> int:
        """Export audit logs to CSV for compliance review."""
        logs = self.repo.get_audit_logs(limit=limit)
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "時間", "動作", "詳細資訊"])
            for log in logs:
                writer.writerow([log.id, log.timestamp, log.action, log.details])
        return len(logs)

    def export_reply_history_csv(self, file_path: str, limit: int = 10000) -> int:
        """Export reply history for compliance review."""
        rows = self.repo.get_reply_history(limit=limit)
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "平台", "貼文作者", "貼文內容", "回覆文案編號",
                "回覆內容", "回覆模式", "狀態", "送出時間", "建立時間",
            ])
            for r in rows:
                writer.writerow([
                    r.get("id"), r.get("platform"), r.get("author_username"),
                    r.get("post_content", "")[:100], r.get("template_code"),
                    r.get("reply_content", "")[:100], r.get("reply_mode"),
                    r.get("status"), r.get("sent_at"), r.get("created_at"),
                ])
        return len(rows)
