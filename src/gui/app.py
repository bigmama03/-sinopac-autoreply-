"""Main application window with sidebar navigation."""

import logging
import queue
import customtkinter as ctk

from src.data.database import Database
from src.data.repository import Repository
from src.core.template_manager import TemplateManager
from src.core.keyword_matcher import KeywordMatcher
from src.core.reply_engine import ReplyEngine
from src.core.compliance import ComplianceGate
from src.core.ollama_judge import OllamaJudge
from src.core.scheduler import PatrolScheduler
from src.platforms.rate_limiter import PlatformRateLimiters
from src.platforms.browser_manager import BrowserManager
from config import APP_NAME_ZH, APP_VERSION, NEGATIVE_KEYWORDS

logger = logging.getLogger(__name__)

try:
    from plyer import notification as _plyer_notification
except ImportError:
    _plyer_notification = None


class App(ctk.CTk):
    """Root application window."""

    def __init__(self, db: Database):
        super().__init__()

        self.db = db
        self.repo = Repository(db)
        self.repo.cleanup_stale_sessions()
        self.template_manager = TemplateManager(self.repo)

        # Build core engine components
        keywords = self.repo.get_all_keywords(active_only=True)
        self.keyword_matcher = KeywordMatcher(keywords, NEGATIVE_KEYWORDS)
        self.compliance = ComplianceGate(self.repo)
        self.ollama_judge = self._create_ollama_judge()

        _patrol_log_cb = lambda level, msg: self.run_in_gui(
            lambda l=level, m=msg: self._on_patrol_log(l, m)
        )
        self.reply_engine = ReplyEngine(
            self.repo, self.keyword_matcher, self.compliance, self.template_manager,
            ollama_judge=self.ollama_judge,
            on_log=_patrol_log_cb,
        )
        self.rate_limiters = PlatformRateLimiters()
        browser_visible = self.repo.get_setting("browser_visible", "0") == "1"
        self.browser_manager = BrowserManager(headless=not browser_visible)
        self.scheduler = PatrolScheduler(
            self.repo, self.reply_engine, self.rate_limiters,
            browser_manager=self.browser_manager,
            on_new_posts=lambda count: self.run_in_gui(
                lambda c=count: self._on_new_posts(c)
            ),
            on_shadowban=lambda plat, cnt: self.run_in_gui(
                lambda p=plat, c=cnt: self._on_shadowban(p, c)
            ),
            on_patrol_log=_patrol_log_cb,
        )

        # Thread-safe message queue for background → GUI communication
        self.msg_queue: queue.Queue = queue.Queue(maxsize=500)
        self._patrol_log_buffer: list[tuple[str, str]] = []  # buffer before monitor frame exists
        self._shutting_down = False  # Flag for daemon threads to check

        # Window setup
        self.title(f"{APP_NAME_ZH} v{APP_VERSION}")
        self.geometry("1100x700")
        self.minsize(900, 600)
        # Restore persisted appearance mode
        saved_appearance = self.repo.get_setting("appearance_mode", "dark")
        ctk.set_appearance_mode(saved_appearance)
        ctk.set_default_color_theme("blue")

        # Layout: sidebar + content
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()

        # Show dashboard by default
        self._show_frame("dashboard")

        # Start polling the message queue + badge refresh
        self._poll_queue()
        self._update_sidebar_badges()
        self._badge_refresh_loop()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(9, weight=1)  # Push bottom items down

        # Title
        title_label = ctk.CTkLabel(
            sidebar, text="永豐金證券\n社群自動回覆",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Navigation buttons
        nav_items = [
            ("總覽儀表板", "dashboard"),
            ("海巡監測", "monitor"),
            ("審核佇列", "review"),
            ("回覆紀錄", "replies"),
            ("文案管理", "templates"),
            ("關鍵字管理", "keywords"),
            ("稽核日誌", "logs"),
            ("設定", "settings"),
        ]

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_badges: dict[str, ctk.CTkLabel] = {}
        for i, (label, name) in enumerate(nav_items):
            row_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
            row_frame.grid(row=i + 1, column=0, padx=10, pady=2, sticky="ew")
            row_frame.grid_columnconfigure(0, weight=1)

            btn = ctk.CTkButton(
                row_frame, text=label, height=40,
                fg_color="transparent", text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="w",
                command=lambda n=name: self._show_frame(n),
            )
            btn.grid(row=0, column=0, sticky="ew")
            self._nav_buttons[name] = btn

            # Badge placeholders for review queue and replies
            if name in ("review", "replies"):
                badge_color = "#F44336" if name == "review" else "#FF9800"
                badge = ctk.CTkLabel(
                    row_frame, text="", width=28, height=20,
                    corner_radius=10, font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=badge_color, text_color="#FFFFFF",
                )
                badge.grid(row=0, column=1, padx=(0, 8))
                badge.grid_remove()  # Hidden by default
                self._nav_badges[name] = badge

        # Appearance toggle
        self._appearance_menu = ctk.CTkOptionMenu(
            sidebar, values=["Dark", "Light", "System"],
            width=100, height=28, font=ctk.CTkFont(size=11),
            command=self._on_appearance_change,
        )
        # Restore appearance menu to match saved setting
        mode_display = {"dark": "Dark", "light": "Light", "system": "System"}
        saved_mode = self.repo.get_setting("appearance_mode", "dark")
        self._appearance_menu.set(mode_display.get(saved_mode, "Dark"))
        self._appearance_menu.grid(row=10, column=0, padx=20, pady=(5, 5))

        # Version at bottom
        ver_label = ctk.CTkLabel(
            sidebar, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11), text_color="gray50",
        )
        ver_label.grid(row=11, column=0, padx=20, pady=(0, 10))

    def _build_content_area(self):
        """Create the content container and all page frames."""
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.content_container.grid_columnconfigure(0, weight=1)
        self.content_container.grid_rowconfigure(0, weight=1)

        # Lazy-loaded frames
        self._frames: dict[str, ctk.CTkFrame] = {}

    def _get_frame(self, name: str) -> ctk.CTkFrame:
        """Lazy-load and return a frame by name."""
        if name not in self._frames:
            frame = self._create_frame(name)
            frame.grid(row=0, column=0, sticky="nsew")
            self._frames[name] = frame
        return self._frames[name]

    def _create_frame(self, name: str) -> ctk.CTkFrame:
        """Create a frame instance by name."""
        if name == "dashboard":
            from src.gui.frames.dashboard_frame import DashboardFrame
            return DashboardFrame(self.content_container, self)
        elif name == "monitor":
            from src.gui.frames.monitor_frame import MonitorFrame
            return MonitorFrame(self.content_container, self)
        elif name == "review":
            from src.gui.frames.review_frame import ReviewFrame
            return ReviewFrame(self.content_container, self)
        elif name == "replies":
            from src.gui.frames.replies_frame import RepliesFrame
            return RepliesFrame(self.content_container, self)
        elif name == "templates":
            from src.gui.frames.templates_frame import TemplatesFrame
            return TemplatesFrame(self.content_container, self)
        elif name == "keywords":
            from src.gui.frames.keywords_frame import KeywordsFrame
            return KeywordsFrame(self.content_container, self)
        elif name == "logs":
            from src.gui.frames.logs_frame import LogsFrame
            return LogsFrame(self.content_container, self)
        elif name == "settings":
            from src.gui.frames.settings_frame import SettingsFrame
            return SettingsFrame(self.content_container, self)
        else:
            # Fallback placeholder
            f = ctk.CTkFrame(self.content_container)
            ctk.CTkLabel(f, text=f"Page: {name}").pack(pady=20)
            return f

    def _show_frame(self, name: str):
        """Switch visible content frame and highlight nav button."""
        frame = self._get_frame(name)

        # Hide all other frames
        for f in self._frames.values():
            f.grid_remove()
        frame.grid()

        # Refresh frame data if it has a refresh method
        if hasattr(frame, "refresh"):
            frame.refresh()

        # Highlight active nav button
        for btn_name, btn in self._nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

    def _poll_queue(self):
        """Process messages from background threads."""
        if self._shutting_down:
            return
        try:
            while True:
                callback = self.msg_queue.get_nowait()
                try:
                    callback()
                except Exception as e:
                    logger.error("GUI callback error: %s", e)
        except queue.Empty:
            pass
        self.after(200, self._poll_queue)

    def run_in_gui(self, callback):
        """Schedule a callback to run on the GUI thread."""
        if self._shutting_down:
            return
        try:
            self.msg_queue.put_nowait(callback)
        except queue.Full:
            pass  # drop callback if queue is full

    def _update_sidebar_badges(self):
        """Update the pending count badges on review and replies nav items."""
        # Review queue badge
        review_badge = self._nav_badges.get("review")
        if review_badge:
            count = self.repo.count_posts_by_status("pending")
            if count > 0:
                review_badge.configure(text=str(count) if count < 100 else "99+")
                review_badge.grid()
            else:
                review_badge.grid_remove()

        # Pending replies badge
        replies_badge = self._nav_badges.get("replies")
        if replies_badge:
            pending_replies = self.repo.count_pending_replies()
            if pending_replies > 0:
                replies_badge.configure(text=str(pending_replies) if pending_replies < 100 else "99+")
                replies_badge.grid()
            else:
                replies_badge.grid_remove()

    def _badge_refresh_loop(self):
        """Periodically refresh sidebar badges."""
        try:
            self._update_sidebar_badges()
        except Exception:
            pass
        self._badge_after_id = self.after(5000, self._badge_refresh_loop)

    def _on_appearance_change(self, value: str):
        mode_map = {"Dark": "dark", "Light": "light", "System": "system"}
        mode = mode_map.get(value, "dark")
        ctk.set_appearance_mode(mode)
        self.repo.set_setting("appearance_mode", mode)

    def _create_ollama_judge(self) -> OllamaJudge:
        """Build an Ollama judge instance from current repository settings."""
        ollama_url = self.repo.get_setting("ollama_url", "http://localhost:11434")
        ollama_model = self.repo.get_setting("ollama_model", "llama3.2")
        return OllamaJudge(url=ollama_url, model=ollama_model)

    def reload_ollama_judge(self):
        """Refresh the injected Ollama judge after settings changes."""
        self.ollama_judge = self._create_ollama_judge()
        self.reply_engine.ollama_judge = self.ollama_judge

    def _on_patrol_log(self, level: str, message: str):
        """Forward patrol log to monitor frame, buffering if not yet created."""
        if "monitor" not in self._frames:
            self._patrol_log_buffer.append((level, message))
            if len(self._patrol_log_buffer) > 200:
                self._patrol_log_buffer = self._patrol_log_buffer[-200:]
            return
        frame = self._frames["monitor"]
        if hasattr(frame, "append_patrol_log"):
            frame.append_patrol_log(level, message)

    def _on_new_posts(self, count: int):
        """Called when new posts are detected by patrol."""
        # Refresh current frame if it's dashboard, monitor, or review
        for name in ("dashboard", "monitor", "review"):
            if name in self._frames:
                frame = self._frames[name]
                if hasattr(frame, "refresh"):
                    frame.refresh()

        self._update_sidebar_badges()

        # Desktop notification in semi_auto mode
        mode = self.repo.get_setting("reply_mode", "semi_auto")
        if mode == "semi_auto":
            self._send_notification(
                title="新的待審核貼文",
                message=f"偵測到 {count} 則新的相關貼文，請前往審核佇列處理",
            )

    def _on_shadowban(self, platform: str, hidden_count: int):
        """Called when potential shadowban is detected."""
        self._send_notification(
            title=f"Shadowban 警告 — {platform.capitalize()}",
            message=f"偵測到 {hidden_count} 則回覆可能被隱藏，建議暫停 {platform.capitalize()} 的海巡",
        )
        # Refresh dashboard to show updated status
        if "dashboard" in self._frames:
            frame = self._frames["dashboard"]
            if hasattr(frame, "refresh"):
                frame.refresh()

    def _send_notification(self, title: str, message: str):
        """Send a desktop notification via plyer."""
        if not _plyer_notification:
            logger.debug("plyer not available, skipping notification")
            return
        try:
            _plyer_notification.notify(
                title=title,
                message=message,
                app_name=APP_NAME_ZH,
                timeout=10,
            )
        except Exception as e:
            logger.warning("Desktop notification failed: %s", e)

    def destroy(self):
        self._shutting_down = True
        if hasattr(self, "_badge_after_id"):
            self.after_cancel(self._badge_after_id)
        self.scheduler.stop()
        self.browser_manager.close()
        self.db.close()
        super().destroy()
