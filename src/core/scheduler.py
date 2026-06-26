"""APScheduler-based polling orchestrator for patrol + reply."""

import logging
from typing import Optional, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.data.repository import Repository
from src.core.reply_engine import ReplyEngine
from src.platforms.rate_limiter import PlatformRateLimiters

logger = logging.getLogger(__name__)


class PatrolScheduler:
    """Manages background polling jobs for all platforms."""

    def __init__(self, repo: Repository, reply_engine: ReplyEngine,
                 rate_limiters: PlatformRateLimiters,
                 browser_manager=None,
                 on_new_posts: Optional[Callable[[int], None]] = None,
                 on_shadowban: Optional[Callable[[str, int], None]] = None,
                 on_patrol_log: Optional[Callable[[str, str], None]] = None):
        self.repo = repo
        self.reply_engine = reply_engine
        self.limiters = rate_limiters
        self.on_new_posts = on_new_posts
        self.on_shadowban = on_shadowban
        self.on_patrol_log = on_patrol_log

        self._scheduler: Optional[BackgroundScheduler] = None
        self._running = False
        self._session_id: Optional[int] = None
        self.active_platforms: Optional[list[str]] = None
        self._browser_manager = browser_manager

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, platforms: Optional[list[str]] = None):
        if self._running:
            return

        # Early reject empty selection
        if platforms is not None and len(platforms) == 0:
            logger.warning("No platforms selected")
            return

        # Register platform adapters on the injected reply engine.
        # Build into a temp dict first; only replace on success.
        old_adapters = dict(self.reply_engine.adapters)
        self.reply_engine.adapters.clear()
        try:
            self._register_adapters(platforms)
        except Exception:
            # Rollback on unexpected failure
            self.reply_engine.adapters.update(old_adapters)
            raise
        self.active_platforms = list(self.reply_engine.adapters.keys())

        if not self.reply_engine.adapters:
            logger.warning("No platform adapters configured")
            return

        self._scheduler = BackgroundScheduler(daemon=True)

        # Patrol jobs — recurring + immediate first run
        for plat, default_sec in [("threads", 300), ("facebook", 120), ("instagram", 300)]:
            if plat not in self.reply_engine.adapters:
                continue
            interval = self._safe_int(f"polling_interval_{plat}_sec", default_sec)
            self._scheduler.add_job(
                self._patrol, IntervalTrigger(seconds=interval),
                args=[plat], id=f"patrol_{plat}", replace_existing=True,
            )
            # Run first patrol immediately (within 2 seconds)
            self._scheduler.add_job(
                self._patrol, DateTrigger(),
                args=[plat], id=f"patrol_{plat}_init",
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

        # Create session before starting scheduler so _session_id is set
        # when the immediate DateTrigger patrol jobs fire.
        platforms = list(self.reply_engine.adapters.keys())
        self._session_id = self.repo.start_patrol_session(platforms)

        self._scheduler.start()
        self._running = True

        self._emit_log("success", f"海巡已啟動，平台: {', '.join(p.capitalize() for p in platforms)}")
        self.repo.log_audit("PATROL_STARTED", {
            "platforms": platforms,
            "session_id": self._session_id,
        })
        logger.info("Patrol started (session %d): %s", self._session_id, platforms)

    def stop(self):
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=True)
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

    def _emit_log(self, level: str, message: str):
        """Emit a patrol log message to the GUI callback."""
        if self.on_patrol_log:
            self.on_patrol_log(level, message)

    def _safe_int(self, setting_key: str, default: int) -> int:
        try:
            return int(self.repo.get_setting(setting_key, str(default)))
        except (ValueError, TypeError):
            return default

    def _register_adapters(self, platforms: Optional[list[str]] = None):
        platform_filter = set(platforms) if platforms is not None else None

        if self._browser_manager is None:
            raise RuntimeError("BrowserManager not injected — cannot register adapters")

        for plat in ('threads', 'facebook', 'instagram'):
            if platform_filter is not None and plat not in platform_filter:
                continue

            config = self.repo.get_platform_config(plat)
            if not config or not config.is_enabled:
                continue

            if not self._browser_manager.has_session(plat):
                self._emit_log('warning', f'[{plat}] 尚未登入，請至設定頁面登入')
                continue

            try:
                if plat == 'threads':
                    from src.platforms.threads_browser import ThreadsBrowserAdapter
                    self.reply_engine.register_adapter(plat, ThreadsBrowserAdapter(self._browser_manager))
                elif plat == 'facebook':
                    from src.platforms.facebook_browser import FacebookBrowserAdapter
                    self.reply_engine.register_adapter(plat, FacebookBrowserAdapter(self._browser_manager))
                elif plat == 'instagram':
                    from src.platforms.instagram_browser import InstagramBrowserAdapter
                    self.reply_engine.register_adapter(plat, InstagramBrowserAdapter(self._browser_manager))
            except Exception as e:
                self._emit_log('error', f'[{plat}] 建立瀏覽器 adapter 失敗: {e}')
                logger.exception('Failed to create browser adapter for %s', plat)

    def _patrol(self, platform: str):
        try:
            adapter = self.reply_engine.adapters.get(platform)
            if not adapter:
                self._emit_log("warning", f"[{platform}] 無可用的 adapter")
                return

            keywords = [kw.keyword for kw in self.repo.get_all_keywords(active_only=True)]
            if not keywords:
                self._emit_log("warning", f"[{platform}] 無啟用中的關鍵字，跳過海巡")
                return

            self._emit_log("info", f"[{platform}] 開始海巡，共 {len(keywords)} 個關鍵字: {', '.join(keywords[:10])}{'...' if len(keywords) > 10 else ''}")

            new_count = 0

            # For Facebook, also patrol monitored targets
            if platform == "facebook" and hasattr(adapter, "fetch_from_target"):
                targets = self.repo.get_fb_monitor_targets(active_only=True)
                if targets:
                    self._emit_log("info", f"[facebook] 監控目標: {len(targets)} 個")
                    for target in targets:
                        raw = adapter.fetch_from_target(target["target_id"], keywords)
                        count = self.reply_engine.process_fetched_posts(platform, raw)
                        new_count += count
                        self._emit_log("info", f"[facebook] 目標 {target['target_id']}: 取得 {len(raw)} 篇，新增 {count} 篇")

            raw_posts = adapter.fetch_posts(keywords)
            if not raw_posts and new_count == 0:
                # Check if empty result is due to session issue (adapter logs error)
                if not self._browser_manager.has_session(platform):
                    self._emit_log("error", f"[{platform}] 瀏覽器 session 不存在，請至設定頁面重新登入")
                    return

            processed = self.reply_engine.process_fetched_posts(platform, raw_posts)
            new_count += processed

            self._emit_log("info", f"[{platform}] 搜尋到 {len(raw_posts)} 篇貼文，新增相關 {processed} 篇")

            if new_count > 0:
                if self._session_id:
                    self.repo.update_patrol_session_counts(
                        self._session_id, detected_delta=new_count,
                    )
                if self.on_new_posts:
                    self.on_new_posts(new_count)
                self._emit_log("success", f"[{platform}] 本次海巡偵測到 {new_count} 篇新貼文")
            else:
                self._emit_log("info", f"[{platform}] 本次海巡無新貼文")

            logger.info("Patrol %s: %d new relevant posts", platform, new_count)
        except Exception as e:
            self._emit_log("error", f"[{platform}] 海巡錯誤: {e}")
            logger.exception("Patrol %s error: %s", platform, e)

    def _send_replies(self):
        try:
            sent = self.reply_engine.send_pending_replies()
            if sent > 0:
                if self._session_id:
                    self.repo.update_patrol_session_counts(
                        self._session_id, replied_delta=sent,
                    )
                self._emit_log("success", f"已發送 {sent} 則回覆")
                logger.info("Sent %d replies", sent)
        except Exception as e:
            self._emit_log("error", f"回覆發送錯誤: {e}")
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
