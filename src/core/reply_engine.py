"""Reply dispatch engine — orchestrates the full reply flow."""

import json
import logging
import random
import time
from typing import TYPE_CHECKING

from src.data.models import DetectedPost, ReplyLog
from src.data.repository import Repository
from src.core.keyword_matcher import KeywordMatcher
from src.core.compliance import ComplianceGate
from src.core.template_manager import TemplateManager
from src.platforms.base import PlatformAdapter

if TYPE_CHECKING:
    from src.core.ollama_judge import OllamaJudge

logger = logging.getLogger(__name__)


class ReplyEngine:
    """Orchestrates detection -> matching -> compliance -> reply flow."""

    def __init__(self, repo: Repository, matcher: KeywordMatcher,
                 compliance: ComplianceGate, template_manager: TemplateManager,
                 ollama_judge: "OllamaJudge | None" = None):
        self.repo = repo
        self.matcher = matcher
        self.compliance = compliance
        self.template_manager = template_manager
        self.ollama_judge = ollama_judge
        self.adapters: dict[str, PlatformAdapter] = {}
        self._last_reply_time: dict[str, float] = {}
        self._scheduled_send_time: dict[int, float] = {}  # reply_id -> monotonic time to send

    def _safe_int(self, setting_key: str, default: int) -> int:
        try:
            return int(self.repo.get_setting(setting_key, str(default)))
        except (ValueError, TypeError):
            return default

    def register_adapter(self, platform: str, adapter: PlatformAdapter):
        self.adapters[platform] = adapter

    def process_fetched_posts(self, platform: str, raw_posts: list[dict]) -> int:
        """Process raw posts from a platform adapter. Returns number of new relevant posts."""
        new_count = 0
        templates = self.template_manager.get_all()

        skipped_empty = 0
        skipped_dup = 0
        skipped_irrelevant = 0
        for raw in raw_posts:
            post_id = raw.get("platform_post_id", "")
            content = raw.get("post_content", "")

            if not post_id or not content:
                skipped_empty += 1
                continue

            if self.repo.is_post_already_detected(platform, post_id):
                skipped_dup += 1
                continue

            result = self.matcher.match(content)
            if not result.is_relevant:
                skipped_irrelevant += 1
                if skipped_irrelevant <= 3:
                    logger.debug("Irrelevant post (score=%.1f): %s", result.score, content[:80])
                continue

            recommended = self.matcher.recommend_templates(result, templates, platform, top_n=1)
            rec_id = recommended[0].id if recommended else None

            mode = self.repo.get_setting("reply_mode", "semi_auto")
            if result.has_negative:
                status = "pending"
            elif mode == "full_auto":
                status = self._ollama_evaluate(content, result)
            else:
                status = "pending"

            post = DetectedPost(
                platform=platform,
                platform_post_id=post_id,
                post_url=raw.get("post_url", ""),
                author_username=raw.get("author_username", ""),
                post_content=content,
                matched_keywords=json.dumps(result.matched_keywords, ensure_ascii=False),
                relevance_score=result.score,
                recommended_template_id=rec_id,
                status=status,
            )

            inserted_id = self.repo.insert_detected_post(post)
            if inserted_id:
                new_count += 1
                logger.info("Detected on %s: score=%.1f, keywords=%s, status=%s",
                            platform, result.score, result.matched_keywords, status)

                if status == "approved" and rec_id:
                    self._queue_auto_reply(inserted_id, rec_id, platform, recommended[0].content)

        if raw_posts:
            logger.info(
                "process_fetched_posts(%s): total=%d, empty=%d, dup=%d, irrelevant=%d, new=%d",
                platform, len(raw_posts), skipped_empty, skipped_dup, skipped_irrelevant, new_count,
            )
        return new_count

    def _ollama_evaluate(self, content: str, result) -> str:
        """Use Ollama to evaluate if post should be replied to in full_auto mode."""
        ollama_enabled = self.repo.get_setting("ollama_enabled", "0") == "1"
        if not ollama_enabled or not self.ollama_judge:
            return "approved"

        try:
            should, reason = self.ollama_judge.should_reply(content, result.matched_keywords)
            self.repo.log_audit("OLLAMA_JUDGE", {
                "should_reply": should,
                "reason": reason,
                "content_preview": content[:100],
            })
            if should:
                logger.info("Ollama approved: %s", reason)
                return "approved"
            else:
                logger.info("Ollama rejected: %s", reason)
                return "skipped"
        except Exception as e:
            logger.error("Ollama evaluation failed: %s", e)
            return "approved"

    def _queue_auto_reply(self, post_id: int, template_id: int,
                          platform: str, content: str):
        reply = ReplyLog(
            detected_post_id=post_id,
            template_id=template_id,
            platform=platform,
            reply_content=content,
            reply_mode="full_auto",
            status="pending",
        )
        self.repo.insert_reply_log(reply)
        self.repo.log_audit("AUTO_REPLY_QUEUED", {
            "post_id": post_id, "template_id": template_id, "platform": platform,
        })

    def send_pending_replies(self) -> int:
        """Send all pending replies. Returns number sent."""
        sent_count = 0

        rows = self.repo.db.execute(
            """SELECT rl.*, dp.platform_post_id
               FROM reply_log rl
               JOIN detected_posts dp ON rl.detected_post_id = dp.id
               WHERE rl.status IN ('pending', 'retrying')
               ORDER BY rl.created_at ASC"""
        ).fetchall()

        # Prune stale scheduled entries for replies no longer pending
        active_ids = {row["id"] for row in rows}
        stale_ids = [rid for rid in self._scheduled_send_time if rid not in active_ids]
        for rid in stale_ids:
            self._scheduled_send_time.pop(rid, None)

        for row in rows:
            reply_id = row["id"]
            platform = row["platform"]
            platform_post_id = row["platform_post_id"]
            reply_content = row["reply_content"]

            adapter = self.adapters.get(platform)
            if not adapter:
                logger.debug("Skipping reply %d: no adapter for platform %s", reply_id, platform)
                continue

            # Compliance check
            allowed, reason = self.compliance.can_reply(platform, platform_post_id)
            if not allowed:
                logger.info("Reply blocked: %s", reason)
                self.repo.update_reply_status(reply_id, "failed", error_message=reason)
                continue

            # Reply interval check
            last_time = self._last_reply_time.get(platform)
            if last_time:
                min_interval = self._safe_int("reply_interval_min_sec", 120)
                elapsed = time.monotonic() - last_time
                if elapsed < min_interval:
                    continue

            # Non-blocking random delay for human-like behavior
            if reply_id not in self._scheduled_send_time:
                min_delay = self._safe_int("reply_delay_min_sec", 180)
                max_delay = self._safe_int("reply_delay_max_sec", 900)
                delay = random.randint(min(min_delay, max_delay), max(min_delay, max_delay))
                self._scheduled_send_time[reply_id] = time.monotonic() + delay
                logger.info("Reply %d scheduled in %ds", reply_id, delay)
                continue

            if time.monotonic() < self._scheduled_send_time[reply_id]:
                remaining = int(self._scheduled_send_time[reply_id] - time.monotonic())
                logger.debug("Reply %d: %ds remaining", reply_id, remaining)
                continue

            # Delay elapsed, clean up
            self._scheduled_send_time.pop(reply_id, None)

            # Check if already replied (API-level)
            try:
                if adapter.check_already_replied(platform_post_id):
                    self.repo.update_reply_status(reply_id, "sent", error_message="已由其他裝置回覆")
                    self.repo.update_post_status(row["detected_post_id"], "replied")
                    continue
            except Exception as e:
                logger.warning("check_already_replied failed: %s", e)

            # Send reply
            success, platform_reply_id, error = adapter.reply_to_post(platform_post_id, reply_content)

            if success:
                self.repo.update_reply_status(reply_id, "sent", platform_reply_id=platform_reply_id)
                self.repo.update_post_status(row["detected_post_id"], "replied")
                self._last_reply_time[platform] = time.monotonic()
                sent_count += 1

                self.repo.log_audit("REPLY_SENT", {
                    "reply_id": reply_id, "platform": platform,
                    "post_id": platform_post_id,
                })
                logger.info("Reply sent on %s: %s", platform, platform_reply_id)
            else:
                retry_count = row["retry_count"]
                if retry_count < 3:
                    self.repo.update_reply_status(reply_id, "retrying", error_message=error)
                    logger.warning("Reply failed (%d/3): %s", retry_count + 1, error)
                else:
                    self.repo.update_reply_status(reply_id, "failed", error_message=error)
                    self.repo.update_post_status(row["detected_post_id"], "failed")
                    logger.error("Reply permanently failed: %s", error)

        return sent_count
