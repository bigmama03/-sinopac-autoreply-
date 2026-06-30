"""Monitor frame — shows detected posts from patrol."""

import io
import json
import webbrowser
from datetime import datetime
import customtkinter as ctk
from PIL import Image

from src.gui import theme as T
from src.gui.widgets.expandable_text import ExpandableText
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class MonitorFrame(ctk.CTkFrame):
    _STATUS_ZH = {
        "pending": "待處理", "replied": "已回覆", "approved": "已審核",
        "rejected": "已拒絕", "failed": "失敗", "skipped": "已跳過",
    }

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=3)
        self.grid_rowconfigure(5, weight=1)

        # Title + status
        header = T.page_header(self, "海巡監測")
        header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._status_label = ctk.CTkLabel(
            header, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_small(),
        )
        self._status_label.pack(side="left", padx=T.PAD_LG)

        self._patrol_indicator = ctk.CTkLabel(
            header, text="", text_color=T.TEAL_500,
            font=T.font_small(),
        )
        self._patrol_indicator.pack(side="right", padx=T.PAD_MD)

        # Filter row
        filter_row = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=T.RADIUS_MD,
                                  border_width=1, border_color=T.BORDER_SUBTLE)
        filter_row.grid(row=1, column=0, sticky="ew", pady=(0, T.PAD_SM))

        filter_inner = ctk.CTkFrame(filter_row, fg_color="transparent")
        filter_inner.pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM)

        ctk.CTkLabel(filter_inner, text="平台:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._platform_filter = ctk.CTkOptionMenu(
            filter_inner, values=["全部", "Threads", "Facebook", "Instagram"],
            width=110, command=lambda _: self._apply_filter(),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        self._platform_filter.pack(side="left", padx=(T.PAD_XS, T.PAD_MD))

        ctk.CTkLabel(filter_inner, text="狀態:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._status_filter = ctk.CTkOptionMenu(
            filter_inner, values=["全部", "待處理", "已回覆", "已跳過", "已審核", "已拒絕", "失敗"],
            width=110, command=lambda _: self._apply_filter(),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        self._status_filter.pack(side="left", padx=(T.PAD_XS, T.PAD_MD))

        ctk.CTkLabel(filter_inner, text="搜尋:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            filter_inner, textvariable=self._search_var, width=180,
            placeholder_text="搜尋貼文內容或作者...",
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._search_entry.pack(side="left", padx=T.PAD_XS)
        self._search_entry.bind("<Return>", lambda _: self._apply_filter())

        ctk.CTkButton(
            filter_inner, text="搜尋", width=50, height=28,
            **T.BTN_GHOST_ACCENT,
            command=self._apply_filter,
        ).pack(side="left", padx=T.PAD_XS)

        self._count_label = ctk.CTkLabel(
            filter_inner, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_caption(),
        )
        self._count_label.pack(side="right")

        # Batch action bar
        batch_row = ctk.CTkFrame(self, fg_color="transparent")
        batch_row.grid(row=2, column=0, sticky="ew", pady=(0, T.PAD_XS))

        self._select_all_var = ctk.StringVar(value="0")
        self._select_all_cb = ctk.CTkCheckBox(
            batch_row, text="全選", variable=self._select_all_var,
            onvalue="1", offvalue="0",
            command=self._toggle_select_all, width=60,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            checkmark_color=T.TEXT_INVERSE,
            text_color=T.TEXT_SECONDARY,
        )
        self._select_all_cb.pack(side="left")

        self._selected_label = ctk.CTkLabel(
            batch_row, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_caption(),
        )
        self._selected_label.pack(side="left", padx=T.PAD_SM)

        self._batch_delete_btn = ctk.CTkButton(
            batch_row, text="批次刪除", width=90, height=28,
            **T.BTN_DANGER,
            command=self._batch_delete,
        )
        self._batch_delete_btn.pack(side="left", padx=T.PAD_SM)

        self._batch_skip_btn = ctk.CTkButton(
            batch_row, text="批次跳過", width=90, height=28,
            **T.BTN_GHOST,
            command=self._batch_skip,
        )
        self._batch_skip_btn.pack(side="left")

        # Post list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        self._scroll_frame.grid(row=3, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._post_widgets: list[ctk.CTkFrame] = []
        self._all_posts = []
        self._filtered_posts = []
        self._page_size = 30
        self._displayed = 0
        self._check_vars: dict[int, ctk.StringVar] = {}

        # Bottom panel: browser preview (left) + patrol log (right)
        bottom_panel = ctk.CTkFrame(self, fg_color="transparent")
        bottom_panel.grid(row=4, column=0, rowspan=2, sticky="nsew", pady=(T.PAD_SM, 0))
        bottom_panel.grid_columnconfigure(1, weight=1)
        bottom_panel.grid_rowconfigure(1, weight=1)

        # Browser preview (left)
        preview_frame = T.card_frame(bottom_panel)
        preview_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, T.PAD_SM))

        ctk.CTkLabel(
            preview_frame, text="瀏覽器即時預覽",
            font=T.font_card_title(), text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        self._preview_width = 384
        self._preview_height = 240
        self._preview_label = ctk.CTkLabel(
            preview_frame, text="海巡未啟動",
            text_color=T.TEXT_TERTIARY,
            width=self._preview_width, height=self._preview_height,
        )
        self._preview_label.pack(padx=T.PAD_MD, pady=(0, T.PAD_SM))
        self._preview_image = None
        self._preview_after_id = None

        # Patrol log (right)
        log_frame = ctk.CTkFrame(bottom_panel, fg_color="transparent")
        log_frame.grid(row=0, column=1, rowspan=2, sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_XS))
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header, text="海巡活動日誌",
            font=T.font_card_title(), text_color=T.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        log_btn_frame = ctk.CTkFrame(log_header, fg_color="transparent")
        log_btn_frame.grid(row=0, column=1, sticky="e")

        self._log_follow = True
        self._follow_btn = ctk.CTkButton(
            log_btn_frame, text="暫停追蹤", width=80, height=24,
            font=T.font_caption(),
            **T.BTN_GHOST,
            command=self._toggle_log_follow,
        )
        self._follow_btn.pack(side="left", padx=(0, T.PAD_XS))

        ctk.CTkButton(
            log_btn_frame, text="清除", width=50, height=24,
            font=T.font_caption(),
            **T.BTN_GHOST,
            command=self._clear_patrol_log,
        ).pack(side="left")

        self._log_textbox = ctk.CTkTextbox(
            log_frame, height=150, font=T.font_mono(),
            state="disabled", wrap="word",
            fg_color=T.NAVY_900, text_color=T.TEXT_SECONDARY,
            border_width=1, border_color=T.BORDER_SUBTLE,
            corner_radius=T.RADIUS_MD,
        )
        self._log_textbox.grid(row=1, column=0, sticky="nsew")
        self._patrol_log_lines: list[str] = []
        self._max_log_lines = 200

    _STATUS_PRIORITY = {
        "pending": 0, "approved": 1, "failed": 2,
        "replied": 3, "skipped": 4, "rejected": 5,
    }

    def refresh(self):
        if hasattr(self.app, "_patrol_log_buffer") and self.app._patrol_log_buffer:
            for level, message in self.app._patrol_log_buffer:
                self.append_patrol_log(level, message)
            self.app._patrol_log_buffer.clear()

        if self.app.scheduler.is_running:
            self._patrol_indicator.configure(text="海巡中...")
            self._start_preview_polling()
        else:
            self._patrol_indicator.configure(text="")
            self._stop_preview_polling()

        self._all_posts = []
        for s in ("pending", "approved", "replied", "rejected", "failed", "skipped"):
            self._all_posts.extend(self.app.repo.get_posts_by_status(s, limit=100))

        self._all_posts.sort(key=lambda p: p.detected_at or "", reverse=True)
        self._all_posts.sort(key=lambda p: self._STATUS_PRIORITY.get(p.status, 9))

        self._apply_filter()

    def _apply_filter(self):
        platform_map = {
            "全部": None, "Threads": "threads",
            "Facebook": "facebook", "Instagram": "instagram",
        }
        status_map = {
            "全部": None, "待處理": "pending", "已回覆": "replied",
            "已跳過": "skipped", "已審核": "approved", "已拒絕": "rejected", "失敗": "failed",
        }

        plat = platform_map.get(self._platform_filter.get())
        status = status_map.get(self._status_filter.get())
        search = self._search_var.get().strip().lower()

        posts = self._all_posts
        if plat:
            posts = [p for p in posts if p.platform == plat]
        if status:
            posts = [p for p in posts if p.status == status]
        if search:
            posts = [
                p for p in posts
                if search in (p.post_content or "").lower()
                or search in (p.author_username or "").lower()
            ]

        self._filtered_posts = posts
        self._displayed = 0
        self._check_vars.clear()
        self._select_all_var.set("0")
        self._update_selected_count()

        for w in self._post_widgets:
            w.destroy()
        self._post_widgets.clear()

        total = len(self._all_posts)
        self._status_label.configure(text=f"共 {total} 筆")

        if not posts:
            self._count_label.configure(text=f"顯示 0 / 共 {total} 筆")
            empty_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            empty_frame.grid(row=0, column=0, pady=40)

            is_patrolling = self.app.scheduler.is_running
            has_filters = (
                self._platform_filter.get() != "全部"
                or self._status_filter.get() != "全部"
                or self._search_var.get().strip()
            )

            if has_filters and total > 0:
                empty_text = "沒有符合篩選條件的貼文\n\n試著調整篩選條件"
                btn_text = None
            elif is_patrolling:
                empty_text = "海巡進行中，尚未偵測到相關貼文\n\n系統正在搜尋中，請稍候..."
                btn_text = None
            else:
                empty_text = "尚無偵測到的貼文\n\n啟動海巡後，相關貼文會出現在這裡"
                btn_text = "前往總覽啟動海巡"

            ctk.CTkLabel(
                empty_frame, text=empty_text,
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
                justify="center",
            ).pack(pady=(0, T.PAD_MD))

            if btn_text:
                ctk.CTkButton(
                    empty_frame, text=btn_text,
                    width=160, height=32,
                    **T.BTN_GHOST_ACCENT,
                    command=lambda: self.app._show_frame("dashboard"),
                ).pack()
            self._post_widgets.append(empty_frame)
            return

        self._load_more()

    def _load_more(self):
        posts = self._filtered_posts
        start = self._displayed
        end = min(start + self._page_size, len(posts))

        if self._post_widgets and isinstance(self._post_widgets[-1], ctk.CTkButton):
            self._post_widgets[-1].destroy()
            self._post_widgets.pop()

        for i in range(start, end):
            card = self._create_post_card(posts[i], i)
            self._post_widgets.append(card)

        self._displayed = end
        total = len(self._all_posts)
        shown = len(posts)
        self._count_label.configure(text=f"顯示 {self._displayed}/{shown} 筆（共 {total} 筆）")

        if self._displayed < len(posts):
            remaining = len(posts) - self._displayed
            btn = ctk.CTkButton(
                self._scroll_frame,
                text=f"載入更多（剩餘 {remaining} 筆）",
                width=200, height=32,
                **T.BTN_GHOST,
                command=self._load_more,
            )
            btn.grid(row=self._displayed, column=0, pady=T.PAD_MD)
            self._post_widgets.append(btn)

    def _create_post_card(self, post, index: int) -> ctk.CTkFrame:
        card = T.card_frame(self._scroll_frame,
                            row=index, column=0, sticky="ew",
                            pady=T.PAD_XS, padx=2)
        card.grid_columnconfigure(1, weight=1)

        # Checkbox
        var = ctk.StringVar(value="0")
        self._check_vars[post.id] = var
        cb = ctk.CTkCheckBox(
            card, text="", variable=var, width=24,
            onvalue="1", offvalue="0",
            command=self._update_selected_count,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            checkmark_color=T.TEXT_INVERSE,
        )
        cb.grid(row=0, column=0, rowspan=3, padx=(T.PAD_SM, 0), pady=T.PAD_SM, sticky="n")

        # Header: platform + author + time + status
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        color = T.PLATFORM_COLORS.get(post.platform, T.TEXT_SECONDARY)
        ctk.CTkLabel(
            header, text=post.platform.upper(),
            font=T.font_badge(), text_color=color,
        ).pack(side="left")

        if post.author_username:
            ctk.CTkLabel(
                header, text=f"@{post.author_username}",
                font=T.font_small(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left", padx=T.PAD_SM)

        if post.detected_at:
            ctk.CTkLabel(
                header, text=post.detected_at[:16],
                font=T.font_caption(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left", padx=T.PAD_XS)

        # Status badge
        s_color = T.STATUS_COLORS.get(post.status, T.TEXT_TERTIARY)
        ctk.CTkLabel(
            header, text=self._STATUS_ZH.get(post.status, post.status),
            font=T.font_badge(), text_color=s_color,
        ).pack(side="right")

        # Score
        if post.relevance_score:
            score_color = T.TEAL_500 if post.relevance_score >= 4.0 else (
                T.WARNING if post.relevance_score >= 3.0 else T.TEXT_TERTIARY
            )
            ctk.CTkLabel(
                header, text=f"相關性 {post.relevance_score:.1f}",
                font=T.font_caption(), text_color=score_color,
            ).pack(side="right", padx=T.PAD_MD)

        # Content
        ExpandableText(
            card, text=post.post_content or "", max_preview=100,
            wraplength=700, font=T.font_body(),
        ).grid(row=1, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_XS, T.PAD_XS))

        # Footer: keywords + actions
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=2, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_SM))

        keywords = self._parse_keywords(post.matched_keywords)
        if keywords:
            kw_frame = ctk.CTkFrame(footer, fg_color="transparent")
            kw_frame.pack(side="left")
            ctk.CTkLabel(
                kw_frame, text="關鍵字:",
                font=T.font_caption(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left")
            for kw in keywords[:5]:
                ctk.CTkLabel(
                    kw_frame, text=kw,
                    font=T.font_caption(),
                    text_color=T.GOLD_500,
                    fg_color=T.NAVY_600,
                    corner_radius=T.RADIUS_SM,
                    padx=T.PAD_XS, pady=1,
                ).pack(side="left", padx=2)
            if len(keywords) > 5:
                ctk.CTkLabel(
                    kw_frame, text=f"+{len(keywords) - 5}",
                    font=T.font_caption(), text_color=T.TEXT_TERTIARY,
                ).pack(side="left", padx=2)

        if post.post_url:
            ctk.CTkButton(
                footer, text="查看原文", width=70, height=24,
                font=T.font_caption(),
                **T.BTN_GHOST,
                command=lambda url=post.post_url: webbrowser.open(url),
            ).pack(side="right")

        return card

    def _get_selected_ids(self) -> list[int]:
        return [pid for pid, var in self._check_vars.items() if var.get() == "1"]

    def _update_selected_count(self):
        count = len(self._get_selected_ids())
        if count:
            self._selected_label.configure(text=f"已選 {count} 筆")
        else:
            self._selected_label.configure(text="")

    def _toggle_select_all(self):
        val = self._select_all_var.get()
        for var in self._check_vars.values():
            var.set(val)
        self._update_selected_count()

    def _batch_delete(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        if CTkMessagebox:
            msg = CTkMessagebox(
                title="確認刪除",
                message=f"確定要刪除選取的 {len(ids)} 筆貼文？\n相關的回覆紀錄也會一併刪除。",
                icon="warning",
                option_1="取消", option_2="刪除",
            )
            if msg.get() != "刪除":
                return
        deleted = self.app.repo.delete_detected_posts(ids)
        self.app.repo.log_audit("BATCH_DELETE_POSTS", {"count": deleted, "post_ids": ids})
        show_toast(self, f"已刪除 {deleted} 筆貼文", "success")
        self.refresh()

    def _batch_skip(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        for pid in ids:
            self.app.repo.update_post_status(pid, "skipped")
        self.app.repo.log_audit("BATCH_SKIP_POSTS", {"count": len(ids)})
        show_toast(self, f"已跳過 {len(ids)} 筆貼文", "info")
        self.refresh()

    def _parse_keywords(self, raw) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(k) for k in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    # -- Patrol log panel --

    _LOG_LEVEL_PREFIX = {
        "info": "INFO",
        "success": "OK  ",
        "warning": "WARN",
        "error": "ERR ",
    }

    def append_patrol_log(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = self._LOG_LEVEL_PREFIX.get(level, "INFO")
        line = f"[{ts}] [{prefix}] {message}"

        self._patrol_log_lines.append(line)

        self._log_textbox.configure(state="normal")
        self._log_textbox.insert("end", line + "\n")

        if len(self._patrol_log_lines) > self._max_log_lines:
            overflow = len(self._patrol_log_lines) - self._max_log_lines
            self._patrol_log_lines = self._patrol_log_lines[-self._max_log_lines:]
            self._log_textbox.delete("1.0", f"{overflow + 1}.0")

        if self._log_follow:
            self._log_textbox.see("end")
        self._log_textbox.configure(state="disabled")

    def _toggle_log_follow(self):
        self._log_follow = not self._log_follow
        if self._log_follow:
            self._follow_btn.configure(text="暫停追蹤")
            self._log_textbox.configure(state="normal")
            self._log_textbox.see("end")
            self._log_textbox.configure(state="disabled")
        else:
            self._follow_btn.configure(text="繼續追蹤")

    def _clear_patrol_log(self):
        self._patrol_log_lines.clear()
        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")
        self._log_textbox.configure(state="disabled")

    # -- Browser PIP preview --

    def _start_preview_polling(self):
        if self._preview_after_id is not None:
            return
        self._poll_preview()

    def _stop_preview_polling(self):
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def _poll_preview(self):
        try:
            data = self.app.browser_manager.get_screenshot()
            if data:
                img = Image.open(io.BytesIO(data))
                img.thumbnail((self._preview_width, self._preview_height), Image.LANCZOS)
                ctk_img = ctk.CTkImage(
                    light_image=img, dark_image=img,
                    size=(img.width, img.height),
                )
                self._preview_label.configure(image=ctk_img, text="")
                self._preview_image = ctk_img
            elif self.app.scheduler.is_running:
                self._preview_label.configure(text="等待瀏覽器截圖...")
        except Exception:
            pass

        if self.app.scheduler.is_running:
            self._preview_after_id = self.after(1500, self._poll_preview)
        else:
            self._preview_after_id = None
            self._preview_label.configure(text="海巡未啟動")
            self._preview_image = None
            self.app.browser_manager.clear_screenshot()
