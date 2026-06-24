"""APScheduler-based polling orchestrator for patrol + reply."""

import logging
from typing import Optional, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.data.repository import Repository
from src.core.reply_engine import ReplyEngine
from src.platforms.rate_limiter import PlatformRateLimiters
from src.utils.crypto import decrypt_token

logger = logging.getLogger(__name__)


class PatrolScheduler:
    """Manages background polling jobs for all platforms."""

    def __init__(self, repo: Repository, reply_engine: ReplyEngine,
                 rate_limiters: PlatformRateLimiters,
                 on_new_posts: Optional[Callable[[int], None]] = None,
                 on_shadowban: Optional[Callable[[str, int], None]] = None):
        self.repo = repo
        self.reply_engine = reply_engine
        self.limiters = rate_limiters
        self.on_new_posts = on_new_posts
        self.on_shadowban = on_shadowban

        self._scheduler: Optional[BackgroundScheduler] = None
        self._running = False
        self._session_id: Optional[int] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return

        # Register platform adapters on the injected reply engine.
        self.reply_engine.adapters.clear()
        self._register_adapters()

        if not self.reply_engine.adapters:
            logger.warning("No platform adapters configured")
            return

        self._scheduler = BackgroundScheduler(daemon=True)

        # Patrol jobs
        if "threads" in self.reply_engine.adapters:
            interval = self._safe_int("polling_interval_threads_sec", 300)
            self._scheduler.add_job(
                self._patrol, IntervalTrigger(seconds=interval),
                args=["threads"], id="patrol_threads", replace_existing=True,
            )

        if "facebook" in self.reply_engine.adapters:
            interval = self._safe_int("polling_interval_facebook_sec", 120)
            self._scheduler.add_job(
                self._patrol, IntervalTrigger(seconds=interval),
                args=["facebook"], id="patrol_facebook", replace_existing=True,
            )

        if "instagram" in self.reply_engine.adapters:
            interval = self._safe_int("polling_interval_instagram_sec", 300)
            self._scheduler.add_job(
                self._patrol, IntervalTrigger(seconds=interval),
                args=["instagram"], id="patrol_instagram", replace_existing=True,
            )

        # Reply sender (every 30 seconds)
        self._scheduler.add_job(
            self._send_replies, IntervalTrigger(seconds=30),
            id="send_replies", replace_existing=True,
        )

        # Shadowban check (every 30 minutes)
        self._scheduler.add_job(
            self._check_shadowban, IntervalTrigger(minutes=30),
            id="shadowban_check", replace_existing=True,
        )

        self._scheduler.start()
        self._running = True

        platforms = list(self.reply_engine.adapters.keys())
        self._session_id = self.repo.start_patrol_session(platforms)
        self.repo.log_audit("PATROL_STARTED", {
            "platforms": platforms,
            "session_id": self._session_id,
        })
        logger.info("Patrol started (session %d): %s", self._session_id, platforms)

    def stop(self):
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            self._running = False

            if self._session_id:
                self.repo.stop_patrol_session(self._session_id)
                self.repo.log_audit("PATROL_STOPPED", {
                    "session_id": self._session_id,
                })
                logger.info("Patrol stopped (session %d)", self._session_id)
                self._session_id = None
            else:
                self.repo.log_audit("PATROL_STOPPED", {})
                logger.info("Patrol stopped")

    def _safe_int(self, setting_key: str, default: int) -> int:
        try:
            return int(self.repo.get_setting(setting_key, str(default)))
        except (ValueError, TypeError):
            return default

    def _register_adapters(self):
        # Threads
        t_config = self.repo.get_platform_config("threads")
        if t_config and t_config.is_enabled and t_config.access_token:
            try:
                token = decrypt_token(t_config.access_token)
                if token and t_config.threads_user_id:
                    from src.platforms.threads_adapter import ThreadsAdapter
                    self.reply_engine.register_adapter("threads", ThreadsAdapter(
                        user_id=t_config.threads_user_id,
                        access_token=token,
                        search_limiter=self.limiters.threads_search,
                        reply_limiter=self.limiters.threads_reply,
                    ))
            except ValueError as e:
                logger.error("Threads token decrypt failed: %s", e)

        # Facebook
        fb_config = self.repo.get_platform_config("facebook")
        if fb_config and fb_config.is_enabled and fb_config.access_token:
            try:
                token = decrypt_token(fb_config.access_token)
                if token and fb_config.page_id:
                    from src.platforms.facebook_adapter import FacebookAdapter
                    self.reply_engine.register_adapter("facebook", FacebookAdapter(
                        page_id=fb_config.page_id,
                        access_token=token,
                        app_id=fb_config.app_id or "",
                        rate_limiter=self.limiters.facebook,
                    ))
            except ValueError as e:
                logger.error("Facebook token decrypt failed: %s", e)

        # Instagram
        ig_config = self.repo.get_platform_config("instagram")
        if ig_config and ig_config.is_enabled and ig_config.access_token:
            try:
                token = decrypt_token(ig_config.access_token)
                if token and ig_config.ig_user_id:
                    from src.platforms.instagram_adapter import InstagramAdapter
                    self.reply_engine.register_adapter("instagram", InstagramAdapter(
                        ig_user_id=ig_config.ig_user_id,
                        access_token=token,
                        api_limiter=self.limiters.instagram_api,
                        hashtag_limiter=self.limiters.instagram_hashtag,
                    ))
            except ValueError as e:
                logger.error("Instagram token decrypt failed: %s", e)

    def _patrol(self, platform: str):
        try:
            adapter = self.reply_engine.adapters.get(platform)
            if not adapter:
                return

            keywords = [kw.keyword for kw in self.repo.get_all_keywords(active_only=True)]
            if not keywords:
                return

            new_count = 0

            # For Facebook, also patrol monitored targets
            if platform == "facebook":
                from src.platforms.facebook_adapter import FacebookAdapter
                if isinstance(adapter, FacebookAdapter):
                    for target in self.repo.get_fb_monitor_targets(active_only=True):
                        raw = adapter.fetch_from_target(target["target_id"], keywords)
                        new_count += self.reply_engine.process_fetched_posts(platform, raw)

            raw_posts = adapter.fetch_posts(keywords)
            new_count += self.reply_engine.process_fetched_posts(platform, raw_posts)

            if new_count > 0:
                if self._session_id:
                    self.repo.update_patrol_session_counts(
                        self._session_id, detected_delta=new_count,
                    )
                if self.on_new_posts:
                    self.on_new_posts(new_count)

            logger.info("Patrol %s: %d new relevant posts", platform, new_count)
        except Exception as e:
            logger.exception("Patrol %s error: %s", platform, e)

    def _send_replies(self):
        try:
            sent = self.reply_engine.send_pending_replies()
            if sent > 0:
                if self._session_id:
                    self.repo.update_patrol_session_counts(
                        self._session_id, replied_delta=sent,
                    )
                logger.info("Sent %d replies", sent)
        except Exception as e:
            logger.exception("Reply sender error: %s", e)

    def _check_shadowban(self):
        """Check if recent replies are still visible (shadowban detection)."""
        try:
            replies = self.repo.get_sent_replies_for_check(limit=20)
            hidden_counts: dict[str, int] = {}

            for reply in replies:
                platform = reply["platform"]
                platform_reply_id = reply["platform_reply_id"]

                adapter = self.reply_engine.adapters.get(platform)
                if not adapter:
                    continue

                visible = adapter.check_reply_visible(platform_reply_id)
                if visible is False:
                    hidden_counts[platform] = hidden_counts.get(platform, 0) + 1
                    logger.warning(
                        "Reply %s on %s may be hidden (shadowban)",
                        platform_reply_id, platform,
                    )

            for platform, count in hidden_counts.items():
                if count >= 3:
                    self.repo.log_audit("SHADOWBAN_DETECTED", {
                        "platform": platform,
                        "hidden_count": count,
                    })
                    logger.error(
                        "Possible shadowban on %s: %d replies hidden", platform, count,
                    )
                    if self.on_shadowban:
                        self.on_shadowban(platform, count)

        except Exception as e:
            logger.exception("Shadowban check error: %s", e)
