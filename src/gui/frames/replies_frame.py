"""Reply records frame — browse and manage sent replies."""

import threading
import webbrowser
import customtkinter as ctk

from src.gui import theme as T
from src.gui.widgets.expandable_text import ExpandableText
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class RepliesFrame(ctk.CTkFrame):
    _STATUS_ZH = {
        "pending": "待送出", "sending": "發送中", "sent": "已送出",
        "failed": "失敗", "retrying": "重試中",
        "cancelled": "已取消",
    }
    _STATUS_FILTER_MAP = {
        "全部": None, "待送出": "pending", "發送中": "sending",
        "已送出": "sent", "失敗": "failed", "重試中": "retrying",
        "已取消": "cancelled",
    }

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title row
        title_row = T.page_header(self, "回覆紀錄")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._sending_btn = ctk.CTkButton(
            title_row, text="暫停發送", width=100, height=30,
            **T.BTN_WARNING,
            command=self._toggle_sending,
        )
        self._sending_btn.pack(side="right")

        self._pending_count_label = ctk.CTkLabel(
            title_row, text="", text_color=T.WARNING,
            font=T.font_small(),
        )
        self._pending_count_label.pack(side="right", padx=T.PAD_MD)

        # Filter row
        filter_row = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=T.RADIUS_MD,
                                  border_width=1, border_color=T.BORDER_SUBTLE)
        filter_row.grid(row=1, column=0, sticky="ew", pady=(0, T.PAD_SM))

        filter_inner = ctk.CTkFrame(filter_row, fg_color="transparent")
        filter_inner.pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM)

        ctk.CTkLabel(filter_inner, text="狀態:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._status_filter = ctk.CTkOptionMenu(
            filter_inner, values=list(self._STATUS_FILTER_MAP.keys()),
            width=90, command=lambda _: self._apply_filter(),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        self._status_filter.pack(side="left", padx=(T.PAD_XS, T.PAD_MD))

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

        ctk.CTkLabel(filter_inner, text="搜尋:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            filter_inner, textvariable=self._search_var, width=200,
            placeholder_text="搜尋回覆內容、貼文或作者...",
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

        self._show_deleted_var = ctk.StringVar(value="0")
        ctk.CTkCheckBox(
            filter_inner, text="顯示已刪除", variable=self._show_deleted_var,
            onvalue="1", offvalue="0", width=100,
            command=self._apply_filter,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            checkmark_color=T.TEXT_INVERSE,
            text_color=T.TEXT_SECONDARY,
        ).pack(side="left", padx=T.PAD_LG)

        self._count_label = ctk.CTkLabel(
            filter_inner, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_caption(),
        )
        self._count_label.pack(side="right")

        # Reply list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._reply_widgets: list[ctk.CTkFrame] = []
        self._all_replies: list[dict] = []
        self._page_size = 30
        self._displayed = 0
        self._total_count = 0

    def refresh(self):
        self._apply_filter()

    def _get_platform_filter(self):
        m = {"全部": None, "Threads": "threads", "Facebook": "facebook", "Instagram": "instagram"}
        return m.get(self._platform_filter.get())

    def _get_status_filter(self):
        return self._STATUS_FILTER_MAP.get(self._status_filter.get())

    def _apply_filter(self):
        platform = self._get_platform_filter()
        search = self._search_var.get().strip() or None
        status = self._get_status_filter()
        show_deleted = self._show_deleted_var.get() == "1"

        self._total_count = self.app.repo.count_reply_logs_filtered(
            platform=platform, search=search, status=status, show_deleted=show_deleted,
        )
        self._all_replies = self.app.repo.get_reply_logs_filtered(
            platform=platform, search=search, status=status, show_deleted=show_deleted,
            limit=self._page_size, offset=0,
        )

        pending = self.app.repo.count_reply_logs_filtered(status="pending")
        retrying = self.app.repo.count_reply_logs_filtered(status="retrying")
        queue_count = pending + retrying
        if queue_count > 0:
            self._pending_count_label.configure(text=f"{queue_count} 則待送出")
        else:
            self._pending_count_label.configure(text="")
        self._update_sending_btn()
        self._displayed = 0

        for w in self._reply_widgets:
            w.destroy()
        self._reply_widgets.clear()

        if not self._all_replies:
            self._count_label.configure(text=f"共 {self._total_count} 筆")
            empty_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            empty_frame.grid(row=0, column=0, pady=40)
            ctk.CTkLabel(
                empty_frame,
                text="尚無回覆紀錄\n\n系統回覆貼文後，紀錄會出現在這裡\n你可以搜尋、篩選，並從平台刪除回覆",
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
                justify="center",
            ).pack(pady=(0, T.PAD_MD))
            ctk.CTkButton(
                empty_frame, text="前往審核佇列",
                width=140, height=32,
                **T.BTN_GHOST_ACCENT,
                command=lambda: self.app._show_frame("review"),
            ).pack()
            self._reply_widgets.append(empty_frame)
            return

        self._load_page(self._all_replies)

    def _load_page(self, replies: list[dict]):
        if self._reply_widgets and isinstance(self._reply_widgets[-1], ctk.CTkButton):
            self._reply_widgets[-1].destroy()
            self._reply_widgets.pop()

        for i, r in enumerate(replies):
            idx = self._displayed + i
            card = self._create_reply_card(r, idx)
            self._reply_widgets.append(card)

        self._displayed += len(replies)
        self._count_label.configure(text=f"顯示 {self._displayed} / 共 {self._total_count} 筆")

        if self._displayed < self._total_count:
            remaining = self._total_count - self._displayed
            btn = ctk.CTkButton(
                self._scroll_frame,
                text=f"載入更多（剩餘 {remaining} 筆）",
                width=200, height=32,
                **T.BTN_GHOST,
                command=self._load_more,
            )
            btn.grid(row=self._displayed, column=0, pady=T.PAD_MD)
            self._reply_widgets.append(btn)

    def _load_more(self):
        platform = self._get_platform_filter()
        search = self._search_var.get().strip() or None
        status = self._get_status_filter()
        show_deleted = self._show_deleted_var.get() == "1"

        more = self.app.repo.get_reply_logs_filtered(
            platform=platform, search=search, status=status, show_deleted=show_deleted,
            limit=self._page_size, offset=self._displayed,
        )
        if more:
            self._load_page(more)

    def _create_reply_card(self, reply: dict, index: int) -> ctk.CTkFrame:
        card = T.card_frame(self._scroll_frame,
                            row=index, column=0, sticky="ew",
                            pady=T.PAD_XS, padx=2)
        card.grid_columnconfigure(0, weight=1)

        is_deleted = reply.get("deleted_at") is not None

        # Header: platform + author + time + status
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        plat = reply.get("platform", "")
        color = T.PLATFORM_COLORS.get(plat, T.TEXT_SECONDARY)
        ctk.CTkLabel(
            header, text=plat.upper(),
            font=T.font_badge(), text_color=color,
        ).pack(side="left")

        author = reply.get("author_username", "")
        if author:
            ctk.CTkLabel(
                header, text=f"@{author}",
                font=T.font_small(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left", padx=T.PAD_SM)

        sent_at = reply.get("sent_at") or reply.get("created_at") or ""
        if sent_at:
            ctk.CTkLabel(
                header, text=sent_at[:16],
                font=T.font_caption(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left", padx=T.PAD_XS)

        if is_deleted:
            ctk.CTkLabel(
                header, text="已刪除",
                font=T.font_badge(), text_color=T.ERROR,
            ).pack(side="right")
        else:
            status = reply.get("status", "")
            status_color = T.STATUS_COLORS.get(status, T.TEXT_TERTIARY)
            ctk.CTkLabel(
                header, text=self._STATUS_ZH.get(status, status),
                font=T.font_badge(), text_color=status_color,
            ).pack(side="right")

        tpl_code = reply.get("template_code", "")
        category = reply.get("category", "")
        if tpl_code or category:
            tpl_text = " / ".join(filter(None, [tpl_code, category]))
            ctk.CTkLabel(
                header, text=tpl_text,
                font=T.font_caption(), text_color=T.GOLD_500,
            ).pack(side="right", padx=T.PAD_MD)

        # Original post preview
        post_content = reply.get("post_content", "")
        if post_content:
            ExpandableText(
                card, text=post_content, prefix="原文: ", max_preview=100,
                wraplength=700, font=T.font_small(), text_color=T.TEXT_TERTIARY,
            ).grid(row=1, column=0, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_XS, 0))

        # Reply content
        reply_content = reply.get("reply_content", "")
        ExpandableText(
            card, text=reply_content, prefix="回覆: ", max_preview=100,
            wraplength=700, font=T.font_body(),
        ).grid(row=2, column=0, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_XS, T.PAD_XS))

        # Actions
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_SM))

        post_url = reply.get("post_url", "")
        if post_url:
            ctk.CTkButton(
                footer, text="查看原文", width=70, height=24,
                font=T.font_caption(),
                **T.BTN_GHOST,
                command=lambda url=post_url: webbrowser.open(url),
            ).pack(side="left", padx=(0, T.PAD_SM))

        platform_reply_id = reply.get("platform_reply_id", "")
        reply_id = reply.get("id")

        if not is_deleted and platform_reply_id and reply.get("status") == "sent":
            ctk.CTkButton(
                footer, text="刪除回覆", width=70, height=24,
                font=T.font_caption(),
                **T.BTN_DANGER,
                command=lambda rid=reply_id, prid=platform_reply_id, p=plat: self._delete_reply(rid, prid, p),
            ).pack(side="right")

        if not is_deleted and reply.get("status") in ("pending", "retrying"):
            ctk.CTkButton(
                footer, text="取消發送", width=70, height=24,
                font=T.font_caption(),
                **T.BTN_GHOST_DANGER,
                command=lambda rid=reply_id: self._cancel_pending_reply(rid),
            ).pack(side="right")

        return card

    def _toggle_sending(self):
        scheduler = self.app.scheduler
        if scheduler.is_sending_paused:
            scheduler.resume_sending()
        else:
            scheduler.pause_sending()
        self._update_sending_btn()

    def _update_sending_btn(self):
        scheduler = self.app.scheduler
        if not scheduler.is_running:
            self._sending_btn.configure(
                text="未啟動海巡", state="disabled",
                fg_color=T.TEXT_TERTIARY, hover_color=T.TEXT_TERTIARY,
                text_color=T.NAVY_800,
            )
        elif scheduler.is_sending_paused:
            self._sending_btn.configure(
                text="開始發送", state="normal",
                **T.BTN_SUCCESS,
            )
        else:
            self._sending_btn.configure(
                text="暫停發送", state="normal",
                **T.BTN_WARNING,
            )

    def _cancel_pending_reply(self, reply_id: int):
        if CTkMessagebox:
            msg = CTkMessagebox(
                title="確認取消",
                message="確定要取消這則待送出的回覆？\n貼文將回到審核佇列。",
                icon="warning",
                option_1="取消", option_2="確定",
            )
            if msg.get() != "確定":
                return

        post_id = self.app.repo.cancel_pending_reply(reply_id)
        if post_id is None:
            show_toast(self, "無法取消（狀態已改變）", "warning")
            self.refresh()
            return

        self.app.reply_engine.cancel_reply(reply_id)
        self.app.repo.update_post_status(post_id, "pending")
        self.app.repo.log_audit("REPLY_CANCELLED", {
            "reply_id": reply_id, "post_id": post_id,
        })
        show_toast(self, "已取消，貼文已回到審核佇列", "success")
        self.refresh()

    def _delete_reply(self, reply_id: int, platform_reply_id: str, platform: str):
        if CTkMessagebox:
            msg = CTkMessagebox(
                title="確認刪除回覆",
                message=f"確定要從 {platform.capitalize()} 刪除這則回覆？\n此操作無法復原。",
                icon="warning",
                option_1="取消", option_2="刪除",
            )
            if msg.get() != "刪除":
                return

        adapter = self.app.reply_engine.adapters.get(platform)
        if not adapter:
            show_toast(self, f"{platform.capitalize()} 未連線，無法刪除", "error", duration_ms=3000)
            return

        show_toast(self, "刪除中...", "info", duration_ms=10000)

        def _worker():
            try:
                success, error = adapter.delete_reply(platform_reply_id)
            except Exception as e:
                success, error = False, str(e)

            def _finish():
                if success:
                    self.app.repo.mark_reply_deleted(reply_id)
                    self.app.repo.log_audit("REPLY_DELETED", {
                        "reply_id": reply_id,
                        "platform": platform,
                        "platform_reply_id": platform_reply_id,
                    })
                    show_toast(self, "回覆已從平台刪除", "success")
                    self.refresh()
                else:
                    show_toast(self, f"刪除失敗: {error[:60]}", "error", duration_ms=4000)

            self.app.run_in_gui(_finish)

        threading.Thread(target=_worker, daemon=True).start()
