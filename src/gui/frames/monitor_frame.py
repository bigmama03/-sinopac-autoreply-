"""Monitor frame — shows detected posts from patrol."""

import json
import webbrowser
import customtkinter as ctk

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class MonitorFrame(ctk.CTkFrame):
    _PLATFORM_COLORS = {
        "threads": "#1DA1F2",
        "facebook": "#1877F2",
        "instagram": "#E4405F",
    }
    _STATUS_COLORS = {
        "pending": ("#FF9800", "#FFA726"),
        "replied": ("#4CAF50", "#66BB6A"),
        "approved": ("#2196F3", "#42A5F5"),
        "rejected": ("#F44336", "#EF5350"),
        "failed": ("#F44336", "#EF5350"),
        "skipped": ("gray50", "gray60"),
    }
    _STATUS_ZH = {
        "pending": "待處理", "replied": "已回覆", "approved": "已審核",
        "rejected": "已拒絕", "failed": "失敗", "skipped": "已跳過",
    }

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Title + status
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="海巡監測",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self._status_label = ctk.CTkLabel(
            header, text="未啟動", text_color="gray50",
        )
        self._status_label.grid(row=0, column=1, sticky="w", padx=15)

        self._patrol_indicator = ctk.CTkLabel(
            header, text="", text_color=("#4CAF50", "#66BB6A"),
            font=ctk.CTkFont(size=12),
        )
        self._patrol_indicator.grid(row=0, column=2, sticky="e", padx=10)

        # Filter row
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(filter_row, text="平台:").pack(side="left")
        self._platform_filter = ctk.CTkOptionMenu(
            filter_row, values=["全部", "Threads", "Facebook", "Instagram"],
            width=120, command=lambda _: self._apply_filter(),
        )
        self._platform_filter.pack(side="left", padx=(5, 15))

        ctk.CTkLabel(filter_row, text="狀態:").pack(side="left")
        self._status_filter = ctk.CTkOptionMenu(
            filter_row, values=["全部", "待處理", "已回覆", "已跳過", "已審核", "已拒絕", "失敗"],
            width=120, command=lambda _: self._apply_filter(),
        )
        self._status_filter.pack(side="left", padx=(5, 15))

        ctk.CTkLabel(filter_row, text="搜尋:").pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            filter_row, textvariable=self._search_var, width=180,
            placeholder_text="搜尋貼文內容或作者...",
        )
        self._search_entry.pack(side="left", padx=5)
        self._search_entry.bind("<Return>", lambda _: self._apply_filter())

        ctk.CTkButton(
            filter_row, text="搜尋", width=50, height=28,
            command=self._apply_filter,
        ).pack(side="left", padx=5)

        self._count_label = ctk.CTkLabel(
            filter_row, text="", text_color="gray50", font=ctk.CTkFont(size=11),
        )
        self._count_label.pack(side="right")

        # Batch action bar
        batch_row = ctk.CTkFrame(self, fg_color="transparent")
        batch_row.grid(row=2, column=0, sticky="ew", pady=(0, 4))

        self._select_all_var = ctk.StringVar(value="0")
        self._select_all_cb = ctk.CTkCheckBox(
            batch_row, text="全選", variable=self._select_all_var,
            onvalue="1", offvalue="0",
            command=self._toggle_select_all, width=60,
        )
        self._select_all_cb.pack(side="left")

        self._selected_label = ctk.CTkLabel(
            batch_row, text="", text_color="gray50", font=ctk.CTkFont(size=11),
        )
        self._selected_label.pack(side="left", padx=8)

        self._batch_delete_btn = ctk.CTkButton(
            batch_row, text="批次刪除", width=90, height=28,
            fg_color="#F44336", hover_color="#D32F2F",
            command=self._batch_delete,
        )
        self._batch_delete_btn.pack(side="left", padx=8)

        self._batch_skip_btn = ctk.CTkButton(
            batch_row, text="批次跳過", width=90, height=28,
            fg_color="transparent", border_width=1,
            command=self._batch_skip,
        )
        self._batch_skip_btn.pack(side="left")

        # Post list
        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.grid(row=3, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._post_widgets: list[ctk.CTkFrame] = []
        self._all_posts = []
        self._filtered_posts = []
        self._page_size = 30
        self._displayed = 0
        self._check_vars: dict[int, ctk.StringVar] = {}  # post.id -> var

    _STATUS_PRIORITY = {
        "pending": 0, "approved": 1, "failed": 2,
        "replied": 3, "skipped": 4, "rejected": 5,
    }

    def refresh(self):
        # Update patrol indicator
        if self.app.scheduler.is_running:
            self._patrol_indicator.configure(text="海巡中...")
        else:
            self._patrol_indicator.configure(text="")

        # Load all posts
        self._all_posts = []
        for s in ("pending", "approved", "replied", "rejected", "failed", "skipped"):
            self._all_posts.extend(self.app.repo.get_posts_by_status(s, limit=100))

        # Sort: pending/approved first, then by detected_at desc within same priority
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

        # Clear
        for w in self._post_widgets:
            w.destroy()
        self._post_widgets.clear()

        total = len(self._all_posts)
        self._status_label.configure(text=f"共 {total} 筆")

        if not posts:
            self._count_label.configure(text=f"顯示 0 / 共 {total} 筆")
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text="尚無偵測到的貼文\n啟動海巡後，相關貼文會出現在這裡",
                text_color="gray50", font=ctk.CTkFont(size=14),
            )
            empty.grid(row=0, column=0, pady=40)
            self._post_widgets.append(empty)
            return

        self._load_more()

    def _load_more(self):
        """Load the next page of posts."""
        posts = self._filtered_posts
        start = self._displayed
        end = min(start + self._page_size, len(posts))

        # Remove previous "load more" button if exists
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

        # Add "load more" button if there are more
        if self._displayed < len(posts):
            remaining = len(posts) - self._displayed
            btn = ctk.CTkButton(
                self._scroll_frame,
                text=f"載入更多（剩餘 {remaining} 筆）",
                width=200, height=32,
                fg_color="transparent", border_width=1,
                command=self._load_more,
            )
            btn.grid(row=self._displayed, column=0, pady=10)
            self._post_widgets.append(btn)

    def _create_post_card(self, post, index: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._scroll_frame)
        card.grid(row=index, column=0, sticky="ew", pady=3, padx=2)
        card.grid_columnconfigure(1, weight=1)

        # Checkbox column
        var = ctk.StringVar(value="0")
        self._check_vars[post.id] = var
        cb = ctk.CTkCheckBox(
            card, text="", variable=var, width=24,
            onvalue="1", offvalue="0",
            command=self._update_selected_count,
        )
        cb.grid(row=0, column=0, rowspan=3, padx=(8, 0), pady=8, sticky="n")

        # Row 0: platform badge + author + time + status
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=10, pady=(8, 2))

        color = self._PLATFORM_COLORS.get(post.platform, "gray")
        ctk.CTkLabel(
            header, text=post.platform.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color,
        ).pack(side="left")

        if post.author_username:
            ctk.CTkLabel(
                header, text=f"@{post.author_username}",
                font=ctk.CTkFont(size=11), text_color="gray50",
            ).pack(side="left", padx=8)

        if post.detected_at:
            ctk.CTkLabel(
                header, text=post.detected_at[:16],
                font=ctk.CTkFont(size=10), text_color="gray50",
            ).pack(side="left", padx=4)

        # Status badge (right side)
        s_color = self._STATUS_COLORS.get(post.status, ("gray", "gray"))
        ctk.CTkLabel(
            header, text=self._STATUS_ZH.get(post.status, post.status),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=s_color,
        ).pack(side="right")

        # Score (right side, before status)
        if post.relevance_score:
            score_color = "#4CAF50" if post.relevance_score >= 4.0 else (
                "#FF9800" if post.relevance_score >= 3.0 else "gray50"
            )
            ctk.CTkLabel(
                header, text=f"相關性 {post.relevance_score:.1f}",
                font=ctk.CTkFont(size=10), text_color=score_color,
            ).pack(side="right", padx=10)

        # Row 1: content preview
        preview = (post.post_content or "")[:200]
        if len(post.post_content or "") > 200:
            preview += "..."
        ctk.CTkLabel(
            card, text=preview, wraplength=700, justify="left",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(2, 4))

        # Row 2: matched keywords + actions
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=2, column=1, sticky="ew", padx=10, pady=(0, 8))

        # Matched keywords badges
        keywords = self._parse_keywords(post.matched_keywords)
        if keywords:
            kw_frame = ctk.CTkFrame(footer, fg_color="transparent")
            kw_frame.pack(side="left")
            ctk.CTkLabel(
                kw_frame, text="關鍵字:",
                font=ctk.CTkFont(size=10), text_color="gray50",
            ).pack(side="left")
            for kw in keywords[:5]:
                ctk.CTkLabel(
                    kw_frame, text=kw,
                    font=ctk.CTkFont(size=10),
                    text_color=("#2196F3", "#64B5F6"),
                    fg_color=("gray85", "gray25"),
                    corner_radius=4,
                    padx=4, pady=1,
                ).pack(side="left", padx=2)
            if len(keywords) > 5:
                ctk.CTkLabel(
                    kw_frame, text=f"+{len(keywords) - 5}",
                    font=ctk.CTkFont(size=10), text_color="gray50",
                ).pack(side="left", padx=2)

        # Open URL button
        if post.post_url:
            ctk.CTkButton(
                footer, text="查看原文", width=70, height=24,
                font=ctk.CTkFont(size=10),
                fg_color="transparent", border_width=1,
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
        self.refresh()

    def _batch_skip(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        for pid in ids:
            self.app.repo.update_post_status(pid, "skipped")
        self.app.repo.log_audit("BATCH_SKIP_POSTS", {"count": len(ids)})
        self.refresh()

    def _parse_keywords(self, raw) -> list[str]:
        """Parse matched_keywords field (JSON string or list)."""
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
