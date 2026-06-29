"""Review queue frame — semi-auto approval workflow."""

import customtkinter as ctk

from src.gui.widgets.expandable_text import ExpandableText
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class ReviewFrame(ctk.CTkFrame):
    _PLATFORM_COLORS = {
        "threads": "#1DA1F2", "facebook": "#1877F2", "instagram": "#E4405F",
    }

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Title
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(
            header, text="審核佇列",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

        self._count_label = ctk.CTkLabel(header, text="0 則待審核", text_color="gray50")
        self._count_label.pack(side="left", padx=15)

        # Shortcut hint
        ctk.CTkLabel(
            header, text="快捷鍵: A 核准 / R 拒絕 / S 跳過 / ↑↓ 切換",
            font=ctk.CTkFont(size=10), text_color="gray50",
        ).pack(side="right")

        # Scrollable list
        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.grid(row=1, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._widgets: list[ctk.CTkFrame] = []
        self._pending_posts = []
        self._selected_index = 0
        self._card_data: list[dict] = []
        self._page_size = 10
        self._displayed = 0
        self._cached_post_ids: list[int] = []  # track if data changed

        # Keyboard bindings — bind on show, unbind on hide
        self.bind("<Map>", lambda e: self._on_visible())
        self.bind("<Unmap>", lambda e: self._unbind_keys())

    def _on_visible(self, event=None):
        top = self.winfo_toplevel()
        top.bind("<a>", lambda e: self._key_approve())
        top.bind("<A>", lambda e: self._key_approve())
        top.bind("<r>", lambda e: self._key_reject())
        top.bind("<R>", lambda e: self._key_reject())
        top.bind("<s>", lambda e: self._key_skip())
        top.bind("<S>", lambda e: self._key_skip())
        top.bind("<Up>", lambda e: self._move_selection(-1))
        top.bind("<Down>", lambda e: self._move_selection(1))

    def _unbind_keys(self):
        top = self.winfo_toplevel()
        for key in ("<a>", "<A>", "<r>", "<R>", "<s>", "<S>", "<Up>", "<Down>"):
            top.unbind(key)

    def refresh(self):
        posts = self.app.repo.get_pending_posts()
        new_ids = [p.id for p in posts]

        # Skip full rebuild if data hasn't changed
        if new_ids == self._cached_post_ids:
            return

        self._pending_posts = posts
        self._cached_post_ids = new_ids
        self._count_label.configure(text=f"{len(posts)} 則待審核")

        # Load templates once for all cards
        self._templates_cache = self.app.template_manager.get_all()

        # Clear all widgets
        for w in self._widgets:
            w.destroy()
        self._widgets.clear()
        self._card_data.clear()
        self._displayed = 0

        if not posts:
            self._selected_index = 0
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text="目前沒有待審核的貼文\n\n啟動海巡後，偵測到的相關貼文會出現在這裡",
                text_color="gray50", font=ctk.CTkFont(size=14),
                justify="center",
            )
            empty.grid(row=0, column=0, pady=40)
            self._widgets.append(empty)
            return

        self._load_page()

        if self._selected_index >= len(self._pending_posts):
            self._selected_index = max(0, len(self._pending_posts) - 1)
        self._highlight_selected()

    def _load_page(self):
        """Load next batch of review cards."""
        start = self._displayed
        end = min(start + self._page_size, len(self._pending_posts))

        # Remove previous "load more" button
        if self._widgets and isinstance(self._widgets[-1], ctk.CTkButton):
            self._widgets[-1].destroy()
            self._widgets.pop()

        for i in range(start, end):
            card = self._create_review_card(self._pending_posts[i], i)
            self._widgets.append(card)

        self._displayed = end

        # Add "load more" if needed
        remaining = len(self._pending_posts) - self._displayed
        if remaining > 0:
            btn = ctk.CTkButton(
                self._scroll_frame,
                text=f"載入更多（剩餘 {remaining} 則）",
                width=200, height=32,
                fg_color="transparent", border_width=1,
                command=self._load_page,
            )
            btn.grid(row=self._displayed, column=0, pady=10)
            self._widgets.append(btn)

    def _create_review_card(self, post, index: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._scroll_frame)
        card.grid(row=index, column=0, sticky="ew", pady=4, padx=2)
        card.grid_columnconfigure(0, weight=1)

        card.bind("<Button-1>", lambda event, idx=index: self._select_card(idx))

        # Row 0: Post info
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            info_frame, text=post.platform.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self._PLATFORM_COLORS.get(post.platform, "#1877F2"),
        ).pack(side="left")

        if post.author_username:
            ctk.CTkLabel(
                info_frame, text=f"@{post.author_username}",
                font=ctk.CTkFont(size=11), text_color="gray50",
            ).pack(side="left", padx=8)

        if post.detected_at:
            ctk.CTkLabel(
                info_frame, text=post.detected_at[:16],
                font=ctk.CTkFont(size=10), text_color="gray50",
            ).pack(side="left", padx=4)

        score_color = "#4CAF50" if (post.relevance_score or 0) >= 4.0 else (
            "#FF9800" if (post.relevance_score or 0) >= 3.0 else "gray50"
        )
        ctk.CTkLabel(
            info_frame, text=f"相關性: {post.relevance_score:.1f}" if post.relevance_score else "",
            font=ctk.CTkFont(size=11), text_color=score_color,
        ).pack(side="right")

        # Row 1: Post content (expandable)
        ExpandableText(
            card, text=post.post_content or "", max_preview=100,
            wraplength=700,
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))

        # Row 2: Template selector — use cached templates
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

        select_frame = ctk.CTkFrame(card, fg_color="transparent")
        select_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))

        template_hint = "文案:" if not rec_id else "文案 (* 推薦):"
        ctk.CTkLabel(select_frame, text=template_hint, font=ctk.CTkFont(size=11)).pack(side="left")
        template_var = ctk.StringVar(value=template_options[0] if template_options else "")
        template_menu = ctk.CTkOptionMenu(
            select_frame, values=template_options, variable=template_var, width=500,
            command=lambda val, idx=index: self._on_template_change(idx),
        )
        template_menu.pack(side="left", padx=5)

        # Row 3: Reply preview (editable)
        preview_label = ctk.CTkLabel(
            card, text="回覆預覽:", font=ctk.CTkFont(size=11, weight="bold"),
        )
        preview_label.grid(row=3, column=0, sticky="w", padx=10, pady=(4, 0))

        initial_content = templates[0].content if templates else ""
        reply_textbox = ctk.CTkTextbox(card, height=60, wrap="word")
        reply_textbox.grid(row=4, column=0, sticky="ew", padx=10, pady=(2, 4))
        reply_textbox.insert("0.0", initial_content)

        edit_indicator = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=10), text_color=("#FF9800", "#FFA726"),
        )
        edit_indicator.grid(row=3, column=0, sticky="e", padx=10, pady=(4, 0))
        reply_textbox._original_content = initial_content
        reply_textbox.bind("<KeyRelease>", lambda e, tb=reply_textbox, ind=edit_indicator: ind.configure(
            text="(已編輯)" if tb.get("0.0", "end").strip() != tb._original_content else ""
        ))

        # Row 5: Action buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 8))

        def get_reply_content():
            return reply_textbox.get("0.0", "end").strip()

        def approve():
            idx = template_options.index(template_var.get()) if template_var.get() in template_options else 0
            if idx < len(template_ids):
                self._approve_post(post.id, template_ids[idx], get_reply_content())

        ctk.CTkButton(
            btn_frame, text="核准 (A)", width=100, height=30,
            fg_color="#4CAF50", hover_color="#388E3C",
            command=approve,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="跳過 (S)", width=80, height=30,
            fg_color="transparent", border_width=1,
            command=lambda pid=post.id: self._skip_post(pid),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="拒絕 (R)", width=80, height=30,
            fg_color="transparent", border_width=1,
            text_color=("red", "#EF5350"),
            command=lambda pid=post.id: self._reject_post(pid),
        ).pack(side="left")

        self._card_data.append({
            "post": post,
            "card": card,
            "template_var": template_var,
            "template_options": template_options,
            "template_ids": template_ids,
            "templates": templates,
            "reply_textbox": reply_textbox,
            "edit_indicator": edit_indicator,
            "approve_fn": approve,
        })

        return card

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

    # ── Selection & keyboard ──

    def _select_card(self, index: int):
        self._selected_index = index
        self._highlight_selected()

    def _move_selection(self, delta: int):
        if self._is_typing() or not self._card_data:
            return
        new_idx = self._selected_index + delta
        new_idx = max(0, min(new_idx, len(self._card_data) - 1))
        self._selected_index = new_idx
        self._highlight_selected()

    def _highlight_selected(self):
        for i, data in enumerate(self._card_data):
            if i == self._selected_index:
                data["card"].configure(border_width=2, border_color=("#2196F3", "#64B5F6"))
            else:
                data["card"].configure(border_width=0)

    def _is_typing(self) -> bool:
        focus = self.winfo_toplevel().focus_get()
        return isinstance(focus, (ctk.CTkTextbox, ctk.CTkEntry))

    def _key_approve(self):
        if self._is_typing() or not self._card_data:
            return
        data = self._card_data[self._selected_index]
        data["approve_fn"]()

    def _key_reject(self):
        if self._is_typing() or not self._card_data:
            return
        post = self._card_data[self._selected_index]["post"]
        self._reject_post(post.id)

    def _key_skip(self):
        if self._is_typing() or not self._card_data:
            return
        post = self._card_data[self._selected_index]["post"]
        self._skip_post(post.id)

    # ── Actions ──

    def _approve_post(self, post_id: int, template_id: int, reply_content: str = ""):
        try:
            template = self.app.template_manager.get_by_id(template_id)
            if not template:
                self._show_error("找不到指定文案")
                return

            post_row = self.app.repo.db.execute(
                "SELECT platform FROM detected_posts WHERE id = ?", (post_id,)
            ).fetchone()
            if not post_row:
                self._show_error("找不到指定貼文")
                return

            content = reply_content or template.content

            from src.data.models import ReplyLog
            reply = ReplyLog(
                detected_post_id=post_id,
                template_id=template_id,
                platform=post_row["platform"],
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
        self._cached_post_ids.clear()  # force rebuild on next refresh
        self.refresh()

    def _skip_post(self, post_id: int):
        try:
            self.app.repo.update_post_status(post_id, "skipped")
            self.app.repo.log_audit("POST_SKIPPED", {"post_id": post_id})
            show_toast(self, "已跳過", "info")
        except Exception as e:
            self._show_error(f"操作失敗: {e}")
        self._cached_post_ids.clear()
        self.refresh()

    def _reject_post(self, post_id: int):
        try:
            self.app.repo.update_post_status(post_id, "rejected")
            self.app.repo.log_audit("POST_REJECTED", {"post_id": post_id})
            show_toast(self, "已拒絕", "warning")
        except Exception as e:
            self._show_error(f"操作失敗: {e}")
        self._cached_post_ids.clear()
        self.refresh()

    def _show_error(self, msg: str):
        if CTkMessagebox:
            CTkMessagebox(title="錯誤", message=msg, icon="cancel")

    def destroy(self):
        self._unbind_keys()
        super().destroy()
