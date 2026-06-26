"""Reply records frame — browse and manage sent replies."""

import threading
import webbrowser
import customtkinter as ctk

from src.gui.widgets.expandable_text import ExpandableText
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class RepliesFrame(ctk.CTkFrame):
    _PLATFORM_COLORS = {
        "threads": "#1DA1F2",
        "facebook": "#1877F2",
        "instagram": "#E4405F",
    }
    _STATUS_ZH = {
        "pending": "待送出", "sent": "已送出",
        "failed": "失敗", "retrying": "重試中",
    }
    _STATUS_COLORS = {
        "pending": ("#FF9800", "#FFA726"),
        "sent": ("#4CAF50", "#66BB6A"),
        "failed": ("#F44336", "#EF5350"),
        "retrying": ("#FF9800", "#FFA726"),
    }

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title
        ctk.CTkLabel(
            self, text="回覆紀錄",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Filter row
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(filter_row, text="平台:").pack(side="left")
        self._platform_filter = ctk.CTkOptionMenu(
            filter_row, values=["全部", "Threads", "Facebook", "Instagram"],
            width=120, command=lambda _: self._apply_filter(),
        )
        self._platform_filter.pack(side="left", padx=(5, 15))

        ctk.CTkLabel(filter_row, text="搜尋:").pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            filter_row, textvariable=self._search_var, width=200,
            placeholder_text="搜尋回覆內容、貼文或作者...",
        )
        self._search_entry.pack(side="left", padx=5)
        self._search_entry.bind("<Return>", lambda _: self._apply_filter())

        ctk.CTkButton(
            filter_row, text="搜尋", width=50, height=28,
            command=self._apply_filter,
        ).pack(side="left", padx=5)

        self._show_deleted_var = ctk.StringVar(value="0")
        ctk.CTkCheckBox(
            filter_row, text="顯示已刪除", variable=self._show_deleted_var,
            onvalue="1", offvalue="0", width=100,
            command=self._apply_filter,
        ).pack(side="left", padx=15)

        self._count_label = ctk.CTkLabel(
            filter_row, text="", text_color="gray50", font=ctk.CTkFont(size=11),
        )
        self._count_label.pack(side="right")

        # Reply list
        self._scroll_frame = ctk.CTkScrollableFrame(self)
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

    def _apply_filter(self):
        platform = self._get_platform_filter()
        search = self._search_var.get().strip() or None
        show_deleted = self._show_deleted_var.get() == "1"

        self._total_count = self.app.repo.count_reply_logs_filtered(
            platform=platform, search=search, show_deleted=show_deleted,
        )
        self._all_replies = self.app.repo.get_reply_logs_filtered(
            platform=platform, search=search, show_deleted=show_deleted,
            limit=self._page_size, offset=0,
        )
        self._displayed = 0

        # Clear
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
                text_color="gray50", font=ctk.CTkFont(size=14),
                justify="center",
            ).pack(pady=(0, 12))
            ctk.CTkButton(
                empty_frame, text="前往審核佇列",
                width=140, height=32,
                fg_color="transparent", border_width=1,
                command=lambda: self.app._show_frame("review"),
            ).pack()
            self._reply_widgets.append(empty_frame)
            return

        self._load_page(self._all_replies)

    def _load_page(self, replies: list[dict]):
        # Remove previous "load more" button
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
                fg_color="transparent", border_width=1,
                command=self._load_more,
            )
            btn.grid(row=self._displayed, column=0, pady=10)
            self._reply_widgets.append(btn)

    def _load_more(self):
        platform = self._get_platform_filter()
        search = self._search_var.get().strip() or None
        show_deleted = self._show_deleted_var.get() == "1"

        more = self.app.repo.get_reply_logs_filtered(
            platform=platform, search=search, show_deleted=show_deleted,
            limit=self._page_size, offset=self._displayed,
        )
        if more:
            self._load_page(more)

    def _create_reply_card(self, reply: dict, index: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._scroll_frame)
        card.grid(row=index, column=0, sticky="ew", pady=3, padx=2)
        card.grid_columnconfigure(0, weight=1)

        is_deleted = reply.get("deleted_at") is not None

        # Row 0: platform + author + time + status
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))

        plat = reply.get("platform", "")
        color = self._PLATFORM_COLORS.get(plat, "gray")
        ctk.CTkLabel(
            header, text=plat.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color,
        ).pack(side="left")

        author = reply.get("author_username", "")
        if author:
            ctk.CTkLabel(
                header, text=f"@{author}",
                font=ctk.CTkFont(size=11), text_color="gray50",
            ).pack(side="left", padx=8)

        sent_at = reply.get("sent_at") or reply.get("created_at") or ""
        if sent_at:
            ctk.CTkLabel(
                header, text=sent_at[:16],
                font=ctk.CTkFont(size=10), text_color="gray50",
            ).pack(side="left", padx=4)

        # Status / deleted badge
        if is_deleted:
            ctk.CTkLabel(
                header, text="已刪除",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("#F44336", "#EF5350"),
            ).pack(side="right")
        else:
            status = reply.get("status", "")
            status_color = self._STATUS_COLORS.get(status, ("gray50", "gray60"))
            ctk.CTkLabel(
                header, text=self._STATUS_ZH.get(status, status),
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=status_color,
            ).pack(side="right")

        # Template info
        tpl_code = reply.get("template_code", "")
        category = reply.get("category", "")
        if tpl_code or category:
            tpl_text = " / ".join(filter(None, [tpl_code, category]))
            ctk.CTkLabel(
                header, text=tpl_text,
                font=ctk.CTkFont(size=10), text_color=("#2196F3", "#64B5F6"),
            ).pack(side="right", padx=10)

        # Row 1: original post preview (expandable)
        post_content = reply.get("post_content", "")
        if post_content:
            ExpandableText(
                card, text=post_content, prefix="原文: ", max_preview=100,
                wraplength=700, font=ctk.CTkFont(size=11), text_color="gray50",
            ).grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 0))

        # Row 2: reply content (expandable)
        reply_content = reply.get("reply_content", "")
        ExpandableText(
            card, text=reply_content, prefix="回覆: ", max_preview=100,
            wraplength=700, font=ctk.CTkFont(size=12),
        ).grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 4))

        # Row 3: actions
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        post_url = reply.get("post_url", "")
        if post_url:
            ctk.CTkButton(
                footer, text="查看原文", width=70, height=24,
                font=ctk.CTkFont(size=10),
                fg_color="transparent", border_width=1,
                command=lambda url=post_url: webbrowser.open(url),
            ).pack(side="left", padx=(0, 8))

        platform_reply_id = reply.get("platform_reply_id", "")
        reply_id = reply.get("id")

        if not is_deleted and platform_reply_id and reply.get("status") == "sent":
            ctk.CTkButton(
                footer, text="刪除回覆", width=70, height=24,
                font=ctk.CTkFont(size=10),
                fg_color="#F44336", hover_color="#D32F2F",
                command=lambda rid=reply_id, prid=platform_reply_id, p=plat: self._delete_reply(rid, prid, p),
            ).pack(side="right")

        return card

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
