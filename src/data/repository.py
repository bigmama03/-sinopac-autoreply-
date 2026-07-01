"""Data access layer for all database operations."""

import json
from typing import Optional
from datetime import datetime

from src.data.database import Database
from src.data.models import (
    Template, DetectedPost, ReplyLog, PlatformConfig, Keyword, AuditLog,
    PatrolSession,
)


class Repository:
    """Centralized data access for all tables."""

    def __init__(self, db: Database):
        self.db = db

    # ── Templates ────────────────────────────────────────────

    def insert_template(self, t: Template) -> int:
        cursor = self.db.execute(
            """INSERT INTO templates (template_code, category, content, platforms, keywords, priority, is_active, approved_by, approved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (t.template_code, t.category, t.content, t.platforms,
             t.keywords, t.priority, int(t.is_active), t.approved_by, t.approved_at),
        )
        self.db.commit()
        return cursor.lastrowid

    def get_all_templates(self, active_only: bool = True) -> list[Template]:
        sql = "SELECT * FROM templates"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY priority DESC, id ASC"
        rows = self.db.execute(sql).fetchall()
        return [self._row_to_template(r) for r in rows]

    def get_templates_by_category(self, category: str) -> list[Template]:
        rows = self.db.execute(
            "SELECT * FROM templates WHERE category = ? AND is_active = 1 ORDER BY priority DESC",
            (category,),
        ).fetchall()
        return [self._row_to_template(r) for r in rows]

    def get_template_by_id(self, template_id: int) -> Optional[Template]:
        row = self.db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
        return self._row_to_template(row) if row else None

    def delete_template(self, template_id: int):
        self.db.execute("UPDATE templates SET is_active = 0, updated_at = datetime('now', 'localtime') WHERE id = ?", (template_id,))
        self.db.commit()

    def count_templates(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM templates WHERE is_active = 1").fetchone()
        return row[0]

    def clear_all_templates(self):
        self.db.execute("UPDATE templates SET is_active = 0, updated_at = datetime('now', 'localtime')")
        self.db.commit()

    def _row_to_template(self, row) -> Template:
        return Template(
            id=row["id"], template_code=row["template_code"],
            category=row["category"], content=row["content"],
            platforms=row["platforms"], keywords=row["keywords"],
            priority=row["priority"], is_active=bool(row["is_active"]),
            approved_by=row["approved_by"], approved_at=row["approved_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # ── Detected Posts ───────────────────────────────────────

    def insert_detected_post(self, p: DetectedPost) -> Optional[int]:
        """Insert a detected post. Returns None if duplicate (UNIQUE constraint)."""
        import sqlite3
        try:
            cursor = self.db.execute(
                """INSERT INTO detected_posts
                   (platform, platform_post_id, post_url, author_username, post_content,
                    matched_keywords, relevance_score, recommended_template_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p.platform, p.platform_post_id, p.post_url, p.author_username,
                 p.post_content, p.matched_keywords, p.relevance_score,
                 p.recommended_template_id, p.status),
            )
            self.db.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate post (UNIQUE constraint on platform + platform_post_id)
            return None

    def get_pending_posts(self) -> list[DetectedPost]:
        rows = self.db.execute(
            "SELECT * FROM detected_posts WHERE status = 'pending' ORDER BY relevance_score DESC, detected_at ASC"
        ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def get_posts_by_status(self, status: str, limit: int = 100) -> list[DetectedPost]:
        rows = self.db.execute(
            "SELECT * FROM detected_posts WHERE status = ? ORDER BY detected_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def update_post_status(self, post_id: int, status: str):
        self.db.execute(
            "UPDATE detected_posts SET status = ?, reviewed_at = datetime('now', 'localtime') WHERE id = ?",
            (status, post_id),
        )
        self.db.commit()

    def batch_update_post_status(self, post_ids: list[int], status: str) -> int:
        """Update status for multiple pending posts at once. Returns count updated.

        Only updates posts still in 'pending' status to prevent overwriting
        posts concurrently approved/replied by another operation.
        """
        if not post_ids:
            return 0
        placeholders = ",".join("?" for _ in post_ids)
        cursor = self.db.execute(
            f"UPDATE detected_posts SET status = ?, reviewed_at = datetime('now', 'localtime') "
            f"WHERE id IN ({placeholders}) AND status = 'pending'",
            (status, *post_ids),
        )
        self.db.commit()
        return cursor.rowcount

    def delete_detected_posts(self, post_ids: list[int]) -> int:
        """Delete detected posts and their associated reply logs. Returns count deleted."""
        if not post_ids:
            return 0
        placeholders = ",".join("?" for _ in post_ids)
        try:
            self.db.execute(
                f"DELETE FROM reply_log WHERE detected_post_id IN ({placeholders})",
                tuple(post_ids),
            )
            cursor = self.db.execute(
                f"DELETE FROM detected_posts WHERE id IN ({placeholders})",
                tuple(post_ids),
            )
            self.db.commit()
            return cursor.rowcount
        except Exception:
            self.db.conn.rollback()
            raise

    def is_post_already_detected(self, platform: str, platform_post_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM detected_posts WHERE platform = ? AND platform_post_id = ?",
            (platform, platform_post_id),
        ).fetchone()
        return row is not None

    def count_posts_by_status(self, status: str) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM detected_posts WHERE status = ?", (status,)
        ).fetchone()
        return row[0]

    def _row_to_post(self, row) -> DetectedPost:
        return DetectedPost(
            id=row["id"], platform=row["platform"],
            platform_post_id=row["platform_post_id"],
            post_url=row["post_url"], author_username=row["author_username"],
            post_content=row["post_content"], matched_keywords=row["matched_keywords"],
            relevance_score=row["relevance_score"],
            recommended_template_id=row["recommended_template_id"],
            status=row["status"], detected_at=row["detected_at"],
            reviewed_at=row["reviewed_at"],
        )

    # ── Reply Log (immutable — INSERT only) ──────────────────

    def insert_reply_log(self, r: ReplyLog) -> int:
        cursor = self.db.execute(
            """INSERT INTO reply_log
               (detected_post_id, template_id, platform, reply_content, reply_mode,
                platform_reply_id, status, error_message, retry_count, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r.detected_post_id, r.template_id, r.platform, r.reply_content,
             r.reply_mode, r.platform_reply_id, r.status, r.error_message,
             r.retry_count, r.sent_at),
        )
        self.db.commit()
        return cursor.lastrowid

    def update_reply_status(self, reply_id: int, status: str,
                            platform_reply_id: Optional[str] = None,
                            error_message: Optional[str] = None):
        """Update reply status after send attempt. Only updates status fields."""
        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "sent" else None
        self.db.execute(
            """UPDATE reply_log SET status = ?, platform_reply_id = COALESCE(?, platform_reply_id),
               error_message = COALESCE(?, error_message),
               sent_at = COALESCE(?, sent_at),
               retry_count = retry_count + CASE WHEN ? = 'retrying' THEN 1 ELSE 0 END
               WHERE id = ?""",
            (status, platform_reply_id, error_message, sent_at, status, reply_id),
        )
        self.db.commit()

    def get_reply_history(self, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            """SELECT r.*, d.post_content, d.author_username, d.post_url, t.template_code
               FROM reply_log r
               JOIN detected_posts d ON r.detected_post_id = d.id
               JOIN templates t ON r.template_id = t.id
               ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_replies_today(self, platform: str) -> int:
        row = self.db.execute(
            """SELECT COUNT(*) FROM reply_log
               WHERE platform = ? AND status = 'sent'
               AND date(sent_at) = date('now', 'localtime')""",
            (platform,),
        ).fetchone()
        return row[0]

    def count_pending_replies(self) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM reply_log WHERE status = 'pending'",
        ).fetchone()
        return row[0]

    def get_reply_stats(
        self,
        period: str = "day",
        platform: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Get reply counts grouped by time period and platform.

        Args:
            period: "day", "week", or "month"
            platform: None for all platforms, or "threads"/"facebook"/"instagram"
            start_date: inclusive start date "YYYY-MM-DD" (default: 7 days ago)
            end_date: inclusive end date "YYYY-MM-DD" (default: today)

        Returns:
            List of {"label": str, "count": int, "platform": str}
        """
        group_exprs = {
            "day": "date(sent_at)",
            "week": "strftime('%Y-W%W', sent_at)",
            "month": "strftime('%Y-%m', sent_at)",
        }
        allowed_platforms = {"threads", "facebook", "instagram"}

        if period not in group_exprs:
            raise ValueError(f"Unsupported period: {period}")
        if platform is not None and platform not in allowed_platforms:
            raise ValueError(f"Unsupported platform: {platform}")

        group_expr = group_exprs[period]

        sql = f"""SELECT {group_expr} AS label, platform, COUNT(*) AS count
                  FROM reply_log
                  WHERE status = 'sent' AND sent_at IS NOT NULL"""
        params: list[str] = []

        if start_date:
            sql += " AND date(sent_at) >= ?"
            params.append(start_date)
        else:
            sql += " AND date(sent_at) >= date('now', 'localtime', '-6 days')"

        if end_date:
            sql += " AND date(sent_at) <= ?"
            params.append(end_date)

        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += f" GROUP BY {group_expr}, platform ORDER BY label ASC"

        rows = self.db.execute(sql, tuple(params)).fetchall()
        return [{"label": r["label"], "count": r["count"], "platform": r["platform"]} for r in rows]

    # ── Platform Config ──────────────────────────────────────

    def get_platform_config(self, platform: str) -> Optional[PlatformConfig]:
        row = self.db.execute(
            "SELECT * FROM platform_config WHERE platform = ?", (platform,)
        ).fetchone()
        if not row:
            return None
        return PlatformConfig(
            id=row["id"], platform=row["platform"],
            is_enabled=bool(row["is_enabled"]),
            access_token=row["access_token"], page_id=row["page_id"],
            ig_user_id=row["ig_user_id"], threads_user_id=row["threads_user_id"],
            app_id=row["app_id"], app_secret=row["app_secret"],
            token_expires_at=row["token_expires_at"],
            last_connected_at=row["last_connected_at"],
            config_json=row["config_json"], updated_at=row["updated_at"],
        )

    _ALLOWED_PLATFORM_CONFIG_COLS = frozenset({
        "is_enabled", "access_token", "page_id", "ig_user_id",
        "threads_user_id", "app_id", "app_secret", "token_expires_at",
        "last_connected_at", "config_json",
    })

    def update_platform_config(self, platform: str, **kwargs):
        # Whitelist column names to prevent SQL injection
        invalid_keys = set(kwargs.keys()) - self._ALLOWED_PLATFORM_CONFIG_COLS
        if invalid_keys:
            raise ValueError(f"Invalid column names: {invalid_keys}")
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values())
        vals.append(platform)
        self.db.execute(
            f"UPDATE platform_config SET {sets}, updated_at = datetime('now', 'localtime') WHERE platform = ?",
            tuple(vals),
        )
        self.db.commit()

    # ── Keywords ─────────────────────────────────────────────

    def get_all_keywords(self, active_only: bool = True) -> list[Keyword]:
        sql = "SELECT * FROM keywords"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY weight DESC"
        rows = self.db.execute(sql).fetchall()
        return [
            Keyword(id=r["id"], keyword=r["keyword"], category=r["category"],
                    weight=r["weight"], is_active=bool(r["is_active"]),
                    created_at=r["created_at"])
            for r in rows
        ]

    def upsert_keyword(self, keyword: str, category: str, weight: float):
        self.db.execute(
            """INSERT INTO keywords (keyword, category, weight)
               VALUES (?, ?, ?)
               ON CONFLICT(keyword) DO UPDATE SET category = ?, weight = ?, is_active = 1""",
            (keyword, category, weight, category, weight),
        )
        self.db.commit()

    def delete_keyword(self, keyword_id: int):
        self.db.execute("UPDATE keywords SET is_active = 0 WHERE id = ?", (keyword_id,))
        self.db.commit()

    # ── App Settings ─────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.db.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = datetime('now', 'localtime')""",
            (key, value, value),
        )
        self.db.commit()

    # ── Audit Log (immutable — INSERT only) ──────────────────

    def log_audit(self, action: str, details: Optional[dict] = None):
        details_json = json.dumps(details, ensure_ascii=False) if details else None
        self.db.execute(
            "INSERT INTO audit_log (action, details) VALUES (?, ?)",
            (action, details_json),
        )
        self.db.commit()

    def get_audit_logs(self, limit: int = 200, action_filter: Optional[str] = None) -> list[AuditLog]:
        if action_filter:
            rows = self.db.execute(
                "SELECT * FROM audit_log WHERE action LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{action_filter}%", limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            AuditLog(id=r["id"], action=r["action"], details=r["details"], timestamp=r["timestamp"])
            for r in rows
        ]

    def get_reply_logs_filtered(
        self,
        platform: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        show_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get reply logs with filtering for the replies UI."""
        sql = """SELECT r.id, r.platform, r.reply_content, r.reply_mode, r.status,
                        r.platform_reply_id, r.error_message, r.retry_count,
                        r.sent_at, r.created_at, r.deleted_at,
                        d.platform_post_id, d.post_url, d.author_username, d.post_content,
                        t.template_code, t.category
                 FROM reply_log r
                 LEFT JOIN detected_posts d ON r.detected_post_id = d.id
                 LEFT JOIN templates t ON r.template_id = t.id
                 WHERE 1=1"""
        params: list = []
        if not show_deleted:
            sql += " AND r.deleted_at IS NULL"
        if status:
            sql += " AND r.status = ?"
            params.append(status)
        if platform:
            sql += " AND r.platform = ?"
            params.append(platform)
        if search:
            sql += " AND (r.reply_content LIKE ? OR d.post_content LIKE ? OR d.author_username LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])
        sql += " ORDER BY r.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.db.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count_reply_logs_filtered(
        self,
        platform: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        show_deleted: bool = False,
    ) -> int:
        sql = """SELECT COUNT(*) FROM reply_log r
                 LEFT JOIN detected_posts d ON r.detected_post_id = d.id
                 WHERE 1=1"""
        params: list = []
        if not show_deleted:
            sql += " AND r.deleted_at IS NULL"
        if status:
            sql += " AND r.status = ?"
            params.append(status)
        if platform:
            sql += " AND r.platform = ?"
            params.append(platform)
        if search:
            sql += " AND (r.reply_content LIKE ? OR d.post_content LIKE ? OR d.author_username LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])
        row = self.db.execute(sql, params).fetchone()
        return row[0]

    def cancel_pending_reply(self, reply_id: int) -> Optional[int]:
        """Cancel a pending/retrying reply. Returns detected_post_id or None."""
        row = self.db.execute(
            "SELECT detected_post_id FROM reply_log WHERE id = ? AND status IN ('pending', 'retrying')",
            (reply_id,),
        ).fetchone()
        if not row:
            return None
        self.db.execute(
            "UPDATE reply_log SET status = 'cancelled' WHERE id = ?",
            (reply_id,),
        )
        self.db.commit()
        return row["detected_post_id"]

    def mark_reply_deleted(self, reply_id: int):
        """Mark a reply as deleted (soft-delete)."""
        self.db.execute(
            "UPDATE reply_log SET deleted_at = datetime('now', 'localtime') WHERE id = ?",
            (reply_id,),
        )
        self.db.commit()

    def get_all_reply_logs(self, limit: int = 10000) -> list[dict]:
        """Get all reply logs for CSV export."""
        rows = self.db.execute(
            """SELECT r.id, r.platform, r.reply_content, r.reply_mode, r.status,
                      r.error_message, r.retry_count, r.sent_at, r.created_at,
                      d.platform_post_id, d.post_url, d.author_username, d.post_content,
                      t.template_code, t.category
               FROM reply_log r
               LEFT JOIN detected_posts d ON r.detected_post_id = d.id
               LEFT JOIN templates t ON r.template_id = t.id
               ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sent_replies_for_check(self, limit: int = 50) -> list[dict]:
        """Get recent sent replies with platform_reply_id for shadowban check."""
        rows = self.db.execute(
            """SELECT r.id, r.platform, r.platform_reply_id, r.detected_post_id,
                      d.platform_post_id
               FROM reply_log r
               JOIN detected_posts d ON r.detected_post_id = d.id
               WHERE r.status = 'sent' AND r.platform_reply_id IS NOT NULL
                 AND r.platform_reply_id != ''
                 AND r.deleted_at IS NULL
               ORDER BY r.sent_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── FB Monitor Targets ───────────────────────────────────

    def get_fb_monitor_targets(self, active_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM fb_monitor_targets"
        if active_only:
            sql += " WHERE is_active = 1"
        rows = self.db.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def add_fb_monitor_target(self, target_type: str, target_id: str, target_name: str = ""):
        self.db.execute(
            """INSERT INTO fb_monitor_targets (target_type, target_id, target_name)
               VALUES (?, ?, ?)
               ON CONFLICT(target_id) DO UPDATE SET target_name = ?, is_active = 1""",
            (target_type, target_id, target_name, target_name),
        )
        self.db.commit()

    def remove_fb_monitor_target(self, target_id: str):
        self.db.execute("UPDATE fb_monitor_targets SET is_active = 0 WHERE target_id = ?", (target_id,))
        self.db.commit()

    # ── Patrol Sessions ──────────────────────────────────────

    def start_patrol_session(self, platforms: list[str]) -> int:
        """Create a new patrol session. Returns the session id."""
        cursor = self.db.execute(
            "INSERT INTO patrol_sessions (platforms) VALUES (?)",
            (json.dumps(platforms, ensure_ascii=False),),
        )
        self.db.commit()
        return cursor.lastrowid

    def stop_patrol_session(self, session_id: int):
        """Mark a patrol session as stopped and snapshot counts."""
        self.db.execute(
            """UPDATE patrol_sessions
               SET stopped_at = datetime('now', 'localtime'), status = 'stopped'
               WHERE id = ?""",
            (session_id,),
        )
        self.db.commit()

    def update_patrol_session_counts(self, session_id: int,
                                     detected_delta: int = 0,
                                     replied_delta: int = 0,
                                     skipped_delta: int = 0):
        """Increment counters on the active patrol session (only if still running)."""
        self.db.execute(
            """UPDATE patrol_sessions
               SET total_detected = total_detected + ?,
                   total_replied = total_replied + ?,
                   total_skipped = total_skipped + ?
               WHERE id = ? AND status = 'running'""",
            (detected_delta, replied_delta, skipped_delta, session_id),
        )
        self.db.commit()

    def cleanup_stale_sessions(self):
        """Mark any leftover 'running' sessions as 'error' (e.g. after a crash)."""
        self.db.execute(
            """UPDATE patrol_sessions
               SET status = 'error', stopped_at = datetime('now', 'localtime')
               WHERE status = 'running'""",
        )
        self.db.commit()

    def get_patrol_sessions(self, limit: int = 20) -> list[PatrolSession]:
        """Get recent patrol sessions, newest first."""
        rows = self.db.execute(
            "SELECT * FROM patrol_sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            PatrolSession(
                id=r["id"], started_at=r["started_at"], stopped_at=r["stopped_at"],
                platforms=r["platforms"] or "", total_detected=r["total_detected"],
                total_replied=r["total_replied"], total_skipped=r["total_skipped"],
                status=r["status"],
            )
            for r in rows
        ]

    def get_active_patrol_session(self) -> Optional[PatrolSession]:
        """Get the currently running session, if any."""
        row = self.db.execute(
            "SELECT * FROM patrol_sessions WHERE status = 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return PatrolSession(
            id=row["id"], started_at=row["started_at"], stopped_at=row["stopped_at"],
            platforms=row["platforms"] or "", total_detected=row["total_detected"],
            total_replied=row["total_replied"], total_skipped=row["total_skipped"],
            status=row["status"],
        )
