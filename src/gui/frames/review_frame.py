"""Review queue frame — detected posts with inline review for pending posts."""

import json
import webbrowser
import customtkinter as ctk

from src.gui import theme as T
from src.gui.widgets.expandable_text import ExpandableText
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class ReviewFrame(ctk.CTkFrame):
    _STATUS_ZH = {
        "pending": "待處理", "replied": "已回覆", "approved": "已審核",
        "rejected": "已拒絕", "failed": "失敗", "skipped": "已跳過",
    }

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── Header ──
        header = T.page_header(self, "審核佇列")
        header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._status_label = ctk.CTkLabel(
            header, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_small(),
        )
        self._status_label.pack(side="left", padx=T.PAD_LG)

        self._shortcut_label = ctk.CTkLabel(
            header, text="", font=T.font_caption(),
            text_color=T.TEXT_TERTIARY,
        )
        self._shortcut_label.pack(side="right")

        # ── Filter row ──
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
        self._status_filter.set("待處理")
        self._status_filter.pack(side="left", padx=(T.PAD_XS, T.PAD_MD))

        ctk.CTkLabel(filter_inner, text="類型:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._type_filter = ctk.CTkOptionMenu(
            filter_inner, values=["全部", "貼文", "留言"],
            width=90, command=lambda _: self._apply_filter(),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        self._type_filter.pack(side="left", padx=(T.PAD_XS, T.PAD_MD))

        ctk.CTkLabel(filter_inner, text="搜尋:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            filter_inner, textvariable=self._search_var, width=150,
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

        # ── Batch action bar ──
        batch_row = ctk.CTkFrame(self, fg_color="transparent")
        batch_row.grid(row=2, column=0, sticky="ew", pady=(0, T.PAD_XS))

        self._select_all_var = ctk.StringVar(value="0")
        ctk.CTkCheckBox(
            batch_row, text="全選", variable=self._select_all_var,
            onvalue="1", offvalue="0",
            command=self._toggle_select_all, width=60,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            checkmark_color=T.TEXT_INVERSE,
            text_color=T.TEXT_SECONDARY,
        ).pack(side="left")

        self._selected_label = ctk.CTkLabel(
            batch_row, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_caption(),
        )
        self._selected_label.pack(side="left", padx=T.PAD_SM)

        ctk.CTkButton(
            batch_row, text="批次刪除", width=90, height=28,
            **T.BTN_DANGER,
            command=self._batch_delete,
        ).pack(side="left", padx=T.PAD_SM)

        ctk.CTkButton(
            batch_row, text="批次拒絕", width=90, height=28,
            **T.BTN_GHOST_DANGER,
            command=self._batch_reject,
        ).pack(side="left", padx=(0, T.PAD_SM))

        ctk.CTkButton(
            batch_row, text="批次跳過", width=90, height=28,
            **T.BTN_GHOST,
            command=self._batch_skip,
        ).pack(side="left")

        # ── Post list ──
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        self._scroll_frame.grid(row=3, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._post_widgets: list[ctk.CTkFrame] = []
        self._filtered_posts = []
        self._page_size = 15
        self._displayed = 0
        self._check_vars: dict[int, ctk.StringVar] = {}

        # Review state for pending cards
        self._card_data: list[dict] = []
        self._selected_index = 0
        self._templates_cache = []
        self._keys_bound = False

        self.bind("<Map>", lambda e: self._on_visible())
        self.bind("<Unmap>", lambda e: self._unbind_keys())

    # ── Visibility & keyboard ──

    def _on_visible(self, event=None):
        self._bind_keys_if_pending()

    def _bind_keys_if_pending(self):
        if self._keys_bound:
            return
        top = self.winfo_toplevel()
        top.bind("<a>", lambda e: self._key_approve())
        top.bind("<A>", lambda e: self._key_approve())
        top.bind("<r>", lambda e: self._key_reject())
        top.bind("<R>", lambda e: self._key_reject())
        top.bind("<s>", lambda e: self._key_skip())
        top.bind("<S>", lambda e: self._key_skip())
        top.bind("<Up>", lambda e: self._move_selection(-1))
        top.bind("<Down>", lambda e: self._move_selection(1))
        self._keys_bound = True

    def _unbind_keys(self):
        if not self._keys_bound:
            return
        top = self.winfo_toplevel()
        for key in ("<a>", "<A>", "<r>", "<R>", "<s>", "<S>", "<Up>", "<Down>"):
            top.unbind(key)
        self._keys_bound = False

    def _is_typing(self) -> bool:
        focus = self.winfo_toplevel().focus_get()
        if focus is None:
            return False
        if isinstance(focus, (ctk.CTkTextbox, ctk.CTkEntry, ctk.CTkOptionMenu)):
            return True
        widget = focus
        for _ in range(5):
            widget = getattr(widget, "master", None)
            if widget is None:
                break
            if isinstance(widget, ctk.CTkOptionMenu):
                return True
        return False

    _PLATFORM_MAP = {
        "全部": None, "Threads": "threads",
        "Facebook": "facebook", "Instagram": "instagram",
    }
    _STATUS_MAP = {
        "全部": None, "待處理": "pending", "已回覆": "replied",
        "已跳過": "skipped", "已審核": "approved", "已拒絕": "rejected", "失敗": "failed",
    }
    _TYPE_MAP = {
        "全部": None, "貼文": "post", "留言": "comment",
    }

    # ── Refresh & filter ──

    def refresh(self):
        self._templates_cache = self.app.template_manager.get_all()
        self._apply_filter()

    def _apply_filter(self):
        plat = self._PLATFORM_MAP.get(self._platform_filter.get())
        status = self._STATUS_MAP.get(self._status_filter.get())
        post_type = self._TYPE_MAP.get(self._type_filter.get())
        search = self._search_var.get().strip()

        # Single DB query with filters pushed down to SQL
        posts, total = self.app.repo.get_posts_filtered(
            status=status, platform=plat, search=search or None,
            post_type=post_type, limit=200,
        )

        self._filtered_posts = posts
        # Batch load comment counts to avoid N+1 queries
        post_ids = [p.id for p in posts if getattr(p, "post_type", "post") == "post"]
        self._comment_counts = self.app.repo.get_comment_counts_batch(post_ids)
        self._displayed = 0
        self._check_vars.clear()
        self._select_all_var.set("0")
        self._update_selected_count()

        self._card_data.clear()
        self._selected_index = 0

        for w in self._post_widgets:
            w.destroy()
        self._post_widgets.clear()

        self._status_label.configure(text=f"共 {total} 筆")

        has_pending = any(p.status == "pending" for p in posts)
        self._shortcut_label.configure(
            text="快捷鍵: A 核准 / R 拒絕 / S 跳過 / ↑↓ 切換" if has_pending else ""
        )

        if not posts:
            shown = len(posts)
            self._count_label.configure(text=f"顯示 0/{shown} 筆（共 {total} 筆）")
            empty_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            empty_frame.grid(row=0, column=0, pady=40)

            is_patrolling = self.app.scheduler.is_running
            has_filters = (
                self._platform_filter.get() != "全部"
                or self._status_filter.get() != "全部"
                or self._type_filter.get() != "全部"
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
        if self._card_data:
            self._highlight_selected()

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
        shown = len(posts)
        self._count_label.configure(text=f"顯示 {self._displayed}/{shown} 筆")

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

    # ── Card rendering ──

    def _create_post_card(self, post, index: int) -> ctk.CTkFrame:
        card = T.card_frame(self._scroll_frame,
                            row=index, column=0, sticky="ew",
                            pady=T.PAD_XS, padx=2)
        card.grid_columnconfigure(1, weight=1)

        is_pending = post.status == "pending"

        if is_pending:
            card.bind("<Button-1>", lambda e, idx=len(self._card_data): self._select_card(idx))

        # Checkbox
        var = ctk.StringVar(value="0")
        self._check_vars[post.id] = var
        ctk.CTkCheckBox(
            card, text="", variable=var, width=24,
            onvalue="1", offvalue="0",
            command=self._update_selected_count,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            checkmark_color=T.TEXT_INVERSE,
        ).grid(row=0, column=0, rowspan=8, padx=(T.PAD_SM, 0), pady=T.PAD_SM, sticky="n")

        # Header: platform + author + time + status + score
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.grid(row=0, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        color = T.PLATFORM_COLORS.get(post.platform, T.TEXT_SECONDARY)
        ctk.CTkLabel(hdr, text=post.platform.upper(),
                     font=T.font_badge(), text_color=color).pack(side="left")

        if getattr(post, "post_type", "post") == "comment":
            ctk.CTkLabel(
                hdr, text="[留言]", font=T.font_badge(),
                text_color=T.TEAL_500,
            ).pack(side="left", padx=(T.PAD_XS, 0))
        elif getattr(post, "post_type", "post") == "post":
            comment_count = self._comment_counts.get(post.id, 0)
            if comment_count > 0:
                ctk.CTkLabel(
                    hdr, text=f"💬 {comment_count}", font=T.font_badge(),
                    text_color=T.TEXT_TERTIARY,
                ).pack(side="left", padx=(T.PAD_XS, 0))

        if post.author_username:
            ctk.CTkLabel(hdr, text=f"@{post.author_username}",
                         font=T.font_small(), text_color=T.TEXT_TERTIARY).pack(side="left", padx=T.PAD_SM)

        if post.detected_at:
            ctk.CTkLabel(hdr, text=post.detected_at[:16],
                         font=T.font_caption(), text_color=T.TEXT_TERTIARY).pack(side="left", padx=T.PAD_XS)

        s_color = T.STATUS_COLORS.get(post.status, T.TEXT_TERTIARY)
        ctk.CTkLabel(hdr, text=self._STATUS_ZH.get(post.status, post.status),
                     font=T.font_badge(), text_color=s_color).pack(side="right")

        if post.relevance_score:
            score_color = T.TEAL_500 if post.relevance_score >= 4.0 else (
                T.WARNING if post.relevance_score >= 3.0 else T.TEXT_TERTIARY
            )
            ctk.CTkLabel(hdr, text=f"相關性 {post.relevance_score:.1f}",
                         font=T.font_caption(), text_color=score_color).pack(side="right", padx=T.PAD_MD)

        # Content
        ExpandableText(
            card, text=post.post_content or "", max_preview=100,
            wraplength=700, font=T.font_body(),
        ).grid(row=1, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_XS, T.PAD_XS))

        # Footer: keywords + view original
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=2, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_XS))

        keywords = self._parse_keywords(post.matched_keywords)
        if keywords:
            kw_frame = ctk.CTkFrame(footer, fg_color="transparent")
            kw_frame.pack(side="left")
            ctk.CTkLabel(kw_frame, text="關鍵字:",
                         font=T.font_caption(), text_color=T.TEXT_TERTIARY).pack(side="left")
            for kw in keywords[:5]:
                ctk.CTkLabel(
                    kw_frame, text=kw, font=T.font_caption(),
                    text_color=T.GOLD_500, fg_color=T.NAVY_600,
                    corner_radius=T.RADIUS_SM, padx=T.PAD_XS, pady=1,
                ).pack(side="left", padx=2)
            if len(keywords) > 5:
                ctk.CTkLabel(kw_frame, text=f"+{len(keywords) - 5}",
                             font=T.font_caption(), text_color=T.TEXT_TERTIARY).pack(side="left", padx=2)

        if post.post_url:
            ctk.CTkButton(
                footer, text="查看原文", width=70, height=24,
                font=T.font_caption(), **T.BTN_GHOST_ACCENT,
                command=lambda url=post.post_url: webbrowser.open(url),
            ).pack(side="right")

        # Pending-only: inline review UI
        if is_pending:
            self._build_review_section(card, post)

        return card

    def _build_review_section(self, card, post):
        templates = list(self._templates_cache)
        if post.recommended_template_id:
            rec = next((t for t in templates if t.id == post.recommended_template_id), None)
            if rec:
                templates = [rec] + [t for t in templates if t.id != rec.id]

        rec_id = post.recommended_template_id
        template_options = [
            f"{'* ' if t.id == rec_id else ''}[{t.template_code}] {t.content[:50]}..."
            for t in templates
        ]
        template_ids = [t.id for t in templates]

        # Template selector
        select_frame = ctk.CTkFrame(card, fg_color="transparent")
        select_frame.grid(row=3, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_XS))

        hint = "文案 (* 推薦):" if rec_id else "文案:"
        ctk.CTkLabel(select_frame, text=hint, font=T.font_small(),
                     text_color=T.TEXT_SECONDARY).pack(side="left")
        template_var = ctk.StringVar(value=template_options[0] if template_options else "")
        card_data_index = len(self._card_data)
        ctk.CTkOptionMenu(
            select_frame, values=template_options, variable=template_var, width=500,
            command=lambda val, idx=card_data_index: self._on_template_change(idx),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        ).pack(side="left", padx=T.PAD_XS)

        # Reply preview
        ctk.CTkLabel(card, text="回覆預覽:", font=T.font_card_title(),
                     text_color=T.TEXT_SECONDARY,
                     ).grid(row=4, column=1, sticky="w", padx=T.PAD_MD, pady=(T.PAD_XS, 0))

        initial_content = templates[0].content if templates else ""
        reply_textbox = ctk.CTkTextbox(
            card, height=60, wrap="word",
            fg_color=T.BG_INPUT, text_color=T.TEXT_PRIMARY,
            border_width=1, border_color=T.BORDER_DEFAULT,
            corner_radius=T.RADIUS_MD,
        )
        reply_textbox.grid(row=5, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_XS, T.PAD_XS))
        reply_textbox.insert("0.0", initial_content)

        edit_indicator = ctk.CTkLabel(card, text="", font=T.font_caption(), text_color=T.WARNING)
        edit_indicator.grid(row=4, column=1, sticky="e", padx=T.PAD_MD, pady=(T.PAD_XS, 0))
        reply_textbox._original_content = initial_content
        reply_textbox.bind("<KeyRelease>", lambda e, tb=reply_textbox, ind=edit_indicator: ind.configure(
            text="(已編輯)" if tb.get("0.0", "end").strip() != tb._original_content else ""
        ))

        # Action buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=6, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_SM))

        def get_reply_content():
            return reply_textbox.get("0.0", "end").strip()

        def approve():
            idx = template_options.index(template_var.get()) if template_var.get() in template_options else 0
            if idx < len(template_ids):
                self._approve_post(post.id, template_ids[idx], get_reply_content())

        ctk.CTkButton(btn_frame, text="核准 (A)", width=100, height=30,
                      **T.BTN_SUCCESS, command=approve).pack(side="left", padx=(0, T.PAD_SM))
        ctk.CTkButton(btn_frame, text="跳過 (S)", width=80, height=30,
                      **T.BTN_GHOST, command=lambda pid=post.id: self._skip_post(pid),
                      ).pack(side="left", padx=(0, T.PAD_SM))
        ctk.CTkButton(btn_frame, text="拒絕 (R)", width=80, height=30,
                      **T.BTN_GHOST_DANGER, command=lambda pid=post.id: self._reject_post(pid),
                      ).pack(side="left")

        self._card_data.append({
            "post": post, "card": card,
            "template_var": template_var,
            "template_options": template_options,
            "template_ids": template_ids,
            "templates": templates,
            "reply_textbox": reply_textbox,
            "edit_indicator": edit_indicator,
            "approve_fn": approve,
        })

    def _on_template_change(self, card_index: int):
        if card_index >= len(self._card_data):
            return
        data = self._card_data[card_index]
        selected = data["template_var"].get()
        options = data["template_options"]
        templates = data["templates"]
        try:
            idx = options.index(selected)
            content = templates[idx].content if idx < len(templates) else ""
        except ValueError:
            content = ""
        textbox = data["reply_textbox"]
        textbox.delete("0.0", "end")
        textbox.insert("0.0", content)
        textbox._original_content = content
        data["edit_indicator"].configure(text="")

    # ── Card selection ──

    def _select_card(self, index: int):
        self._selected_index = index
        self._highlight_selected()

    def _move_selection(self, delta: int):
        if not self.winfo_ismapped() or self._is_typing() or not self._card_data:
            return
        new_idx = max(0, min(self._selected_index + delta, len(self._card_data) - 1))
        self._selected_index = new_idx
        self._highlight_selected()

    def _highlight_selected(self):
        for i, data in enumerate(self._card_data):
            if i == self._selected_index:
                data["card"].configure(border_width=2, border_color=T.GOLD_500)
            else:
                data["card"].configure(border_width=1, border_color=T.BORDER_SUBTLE)

    def _key_approve(self):
        if not self.winfo_ismapped() or self._is_typing() or not self._card_data:
            return
        if self._selected_index < len(self._card_data):
            self._card_data[self._selected_index]["approve_fn"]()

    def _key_reject(self):
        if not self.winfo_ismapped() or self._is_typing() or not self._card_data:
            return
        if self._selected_index < len(self._card_data):
            self._reject_post(self._card_data[self._selected_index]["post"].id)

    def _key_skip(self):
        if not self.winfo_ismapped() or self._is_typing() or not self._card_data:
            return
        if self._selected_index < len(self._card_data):
            self._skip_post(self._card_data[self._selected_index]["post"].id)

    # ── Review actions ──

    def _approve_post(self, post_id: int, template_id: int, reply_content: str = ""):
        try:
            template = self.app.template_manager.get_by_id(template_id)
            if not template:
                self._show_error("找不到指定文案")
                return

            platform = self.app.repo.get_post_platform(post_id)
            if not platform:
                self._show_error("找不到指定貼文")
                return

            if self.app.repo.has_active_reply(post_id):
                self._show_error("此貼文已有排程或已送出的回覆")
                return

            content = reply_content or template.content

            from src.data.models import ReplyLog
            reply = ReplyLog(
                detected_post_id=post_id,
                template_id=template_id,
                platform=platform,
                reply_content=content,
                reply_mode="semi_auto",
                status="pending",
            )
            self.app.repo.insert_reply_log(reply)
            self.app.repo.update_post_status(post_id, "approved")
            self.app.repo.log_audit("REPLY_APPROVED", {
                "post_id": post_id, "template_id": template_id,
            })
            show_toast(self, "已核准，回覆將自動送出", "success")
        except Exception as e:
            self._show_error(f"核准失敗: {e}")
        self.refresh()
        self.app._update_sidebar_badges()

    def _skip_post(self, post_id: int):
        try:
            self.app.repo.update_post_status(post_id, "skipped")
            self.app.repo.log_audit("POST_SKIPPED", {"post_id": post_id})
            show_toast(self, "已跳過", "info")
        except Exception as e:
            self._show_error(f"操作失敗: {e}")
        self.refresh()
        self.app._update_sidebar_badges()

    def _reject_post(self, post_id: int):
        try:
            self.app.repo.update_post_status(post_id, "rejected")
            self.app.repo.log_audit("POST_REJECTED", {"post_id": post_id})
            show_toast(self, "已拒絕", "warning")
        except Exception as e:
            self._show_error(f"操作失敗: {e}")
        self.refresh()
        self.app._update_sidebar_badges()

    def _show_error(self, msg: str):
        if CTkMessagebox:
            CTkMessagebox(title="錯誤", message=msg, icon="cancel")
        else:
            show_toast(self, msg, "error")

    # ── Batch operations ──

    def _get_selected_ids(self) -> list[int]:
        return [pid for pid, var in self._check_vars.items() if var.get() == "1"]

    def _update_selected_count(self):
        count = len(self._get_selected_ids())
        self._selected_label.configure(text=f"已選 {count} 筆" if count else "")

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
                icon="warning", option_1="取消", option_2="刪除",
            )
            if msg.get() != "刪除":
                return
        deleted = self.app.repo.delete_detected_posts(ids)
        self.app.repo.log_audit("BATCH_DELETE_POSTS", {"count": deleted, "post_ids": ids})
        show_toast(self, f"已刪除 {deleted} 筆貼文", "success")
        self.refresh()
        self.app._update_sidebar_badges()

    def _batch_reject(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        if CTkMessagebox:
            result = CTkMessagebox(
                title="批次拒絕", message=f"確定要拒絕 {len(ids)} 則貼文嗎？",
                icon="question", option_1="取消", option_2="確定拒絕",
            ).get()
            if result != "確定拒絕":
                return
        count = self.app.repo.batch_update_post_status(ids, "rejected")
        self.app.repo.log_audit("BATCH_REJECTED", {"count": count, "post_ids": ids})
        show_toast(self, f"已批次拒絕 {count} 則貼文", "success")
        self.refresh()
        self.app._update_sidebar_badges()

    def _batch_skip(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        if CTkMessagebox:
            result = CTkMessagebox(
                title="批次跳過", message=f"確定要跳過 {len(ids)} 則貼文嗎？",
                icon="question", option_1="取消", option_2="確定跳過",
            ).get()
            if result != "確定跳過":
                return
        count = self.app.repo.batch_update_post_status(ids, "skipped")
        self.app.repo.log_audit("BATCH_SKIPPED", {"count": count, "post_ids": ids})
        show_toast(self, f"已批次跳過 {count} 則貼文", "info")
        self.refresh()
        self.app._update_sidebar_badges()

    @staticmethod
    def _parse_keywords(raw) -> list[str]:
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

    def destroy(self):
        self._unbind_keys()
        super().destroy()
