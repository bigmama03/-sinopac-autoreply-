"""Review queue frame — semi-auto approval workflow."""

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
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title
        header = T.page_header(self, "審核佇列")
        header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_SM))

        self._count_label = ctk.CTkLabel(
            header, text="0 則待審核",
            text_color=T.TEXT_TERTIARY, font=T.font_small(),
        )
        self._count_label.pack(side="left", padx=T.PAD_LG)

        ctk.CTkLabel(
            header, text="快捷鍵: A 核准 / R 拒絕 / S 跳過 / ↑↓ 切換",
            font=T.font_caption(), text_color=T.TEXT_TERTIARY,
        ).pack(side="right")

        # Batch action bar
        batch_bar = ctk.CTkFrame(self, fg_color="transparent")
        batch_bar.grid(row=1, column=0, sticky="ew", pady=(0, T.PAD_SM))

        self._select_all_var = ctk.BooleanVar(value=False)
        self._select_all_cb = ctk.CTkCheckBox(
            batch_bar, text="全選", variable=self._select_all_var,
            command=self._on_select_all,
            font=T.font_small(), text_color=T.TEXT_SECONDARY,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            border_color=T.BORDER_DEFAULT,
            width=24, height=24,
        )
        self._select_all_cb.pack(side="left", padx=(0, T.PAD_MD))

        self._batch_reject_btn = ctk.CTkButton(
            batch_bar, text="批次拒絕 (0)", width=120, height=30,
            **T.BTN_GHOST_DANGER,
            state="disabled",
            command=self._batch_reject,
        )
        self._batch_reject_btn.pack(side="left", padx=(0, T.PAD_SM))

        self._batch_skip_btn = ctk.CTkButton(
            batch_bar, text="批次跳過 (0)", width=120, height=30,
            **T.BTN_GHOST,
            state="disabled",
            command=self._batch_skip,
        )
        self._batch_skip_btn.pack(side="left")

        # Scrollable list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._widgets: list[ctk.CTkFrame] = []
        self._pending_posts = []
        self._selected_index = 0
        self._card_data: list[dict] = []
        self._page_size = 10
        self._displayed = 0
        self._cached_post_ids: list[int] = []
        self._selected_ids: set[int] = set()

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

        if new_ids == self._cached_post_ids:
            return

        self._pending_posts = posts
        self._cached_post_ids = new_ids
        self._count_label.configure(text=f"{len(posts)} 則待審核")

        self._templates_cache = self.app.template_manager.get_all()

        for w in self._widgets:
            w.destroy()
        self._widgets.clear()
        self._card_data.clear()
        self._displayed = 0
        self._selected_ids.clear()
        self._select_all_var.set(False)
        self._update_batch_buttons()

        if not posts:
            self._selected_index = 0
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text="目前沒有待審核的貼文\n\n啟動海巡後，偵測到的相關貼文會出現在這裡",
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
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
        start = self._displayed
        end = min(start + self._page_size, len(self._pending_posts))

        if self._widgets and isinstance(self._widgets[-1], ctk.CTkButton):
            self._widgets[-1].destroy()
            self._widgets.pop()

        for i in range(start, end):
            card = self._create_review_card(self._pending_posts[i], i)
            self._widgets.append(card)

        self._displayed = end

        remaining = len(self._pending_posts) - self._displayed
        if remaining > 0:
            btn = ctk.CTkButton(
                self._scroll_frame,
                text=f"載入更多（剩餘 {remaining} 則）",
                width=200, height=32,
                **T.BTN_GHOST,
                command=self._load_page,
            )
            btn.grid(row=self._displayed, column=0, pady=T.PAD_MD)
            self._widgets.append(btn)

    def _create_review_card(self, post, index: int) -> ctk.CTkFrame:
        card = T.card_frame(self._scroll_frame,
                            row=index, column=0, sticky="ew",
                            pady=T.PAD_XS, padx=2)
        card.grid_columnconfigure(1, weight=1)

        card.bind("<Button-1>", lambda event, idx=index: self._select_card(idx))

        # Column 0: Checkbox
        cb_var = ctk.BooleanVar(value=False)
        cb = ctk.CTkCheckBox(
            card, text="", variable=cb_var, width=24, height=24,
            fg_color=T.GOLD_500, hover_color=T.GOLD_400,
            border_color=T.BORDER_DEFAULT,
            command=lambda pid=post.id, var=cb_var: self._on_checkbox_toggle(pid, var),
        )
        cb.grid(row=0, column=0, rowspan=6, padx=(T.PAD_SM, 0), pady=T.PAD_SM, sticky="n")

        # Row 0: Post info
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        color = T.PLATFORM_COLORS.get(post.platform, T.TEXT_SECONDARY)
        ctk.CTkLabel(
            info_frame, text=post.platform.upper(),
            font=T.font_badge(), text_color=color,
        ).pack(side="left")

        if post.author_username:
            ctk.CTkLabel(
                info_frame, text=f"@{post.author_username}",
                font=T.font_small(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left", padx=T.PAD_SM)

        if post.detected_at:
            ctk.CTkLabel(
                info_frame, text=post.detected_at[:16],
                font=T.font_caption(), text_color=T.TEXT_TERTIARY,
            ).pack(side="left", padx=T.PAD_XS)

        score_color = T.TEAL_500 if (post.relevance_score or 0) >= 4.0 else (
            T.WARNING if (post.relevance_score or 0) >= 3.0 else T.TEXT_TERTIARY
        )
        ctk.CTkLabel(
            info_frame, text=f"相關性: {post.relevance_score:.1f}" if post.relevance_score else "",
            font=T.font_small(), text_color=score_color,
        ).pack(side="right")

        # Row 1: Post content
        ExpandableText(
            card, text=post.post_content or "", max_preview=100,
            wraplength=700,
        ).grid(row=1, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_XS))

        # Row 2: Template selector
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
        select_frame.grid(row=2, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_XS))

        template_hint = "文案:" if not rec_id else "文案 (* 推薦):"
        ctk.CTkLabel(select_frame, text=template_hint, font=T.font_small(),
                     text_color=T.TEXT_SECONDARY).pack(side="left")
        template_var = ctk.StringVar(value=template_options[0] if template_options else "")
        template_menu = ctk.CTkOptionMenu(
            select_frame, values=template_options, variable=template_var, width=500,
            command=lambda val, idx=index: self._on_template_change(idx),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        template_menu.pack(side="left", padx=T.PAD_XS)

        # Row 3: Reply preview
        preview_label = ctk.CTkLabel(
            card, text="回覆預覽:", font=T.font_card_title(),
            text_color=T.TEXT_SECONDARY,
        )
        preview_label.grid(row=3, column=1, sticky="w", padx=T.PAD_MD, pady=(T.PAD_XS, 0))

        initial_content = templates[0].content if templates else ""
        reply_textbox = ctk.CTkTextbox(
            card, height=60, wrap="word",
            fg_color=T.BG_INPUT, text_color=T.TEXT_PRIMARY,
            border_width=1, border_color=T.BORDER_DEFAULT,
            corner_radius=T.RADIUS_MD,
        )
        reply_textbox.grid(row=4, column=1, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_XS, T.PAD_XS))
        reply_textbox.insert("0.0", initial_content)

        edit_indicator = ctk.CTkLabel(
            card, text="", font=T.font_caption(), text_color=T.WARNING,
        )
        edit_indicator.grid(row=3, column=1, sticky="e", padx=T.PAD_MD, pady=(T.PAD_XS, 0))
        reply_textbox._original_content = initial_content
        reply_textbox.bind("<KeyRelease>", lambda e, tb=reply_textbox, ind=edit_indicator: ind.configure(
            text="(已編輯)" if tb.get("0.0", "end").strip() != tb._original_content else ""
        ))

        # Row 5: Action buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=5, column=1, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_SM))

        def get_reply_content():
            return reply_textbox.get("0.0", "end").strip()

        def approve():
            idx = template_options.index(template_var.get()) if template_var.get() in template_options else 0
            if idx < len(template_ids):
                self._approve_post(post.id, template_ids[idx], get_reply_content())

        ctk.CTkButton(
            btn_frame, text="核准 (A)", width=100, height=30,
            **T.BTN_SUCCESS,
            command=approve,
        ).pack(side="left", padx=(0, T.PAD_SM))

        ctk.CTkButton(
            btn_frame, text="跳過 (S)", width=80, height=30,
            **T.BTN_GHOST,
            command=lambda pid=post.id: self._skip_post(pid),
        ).pack(side="left", padx=(0, T.PAD_SM))

        ctk.CTkButton(
            btn_frame, text="拒絕 (R)", width=80, height=30,
            **T.BTN_GHOST_DANGER,
            command=lambda pid=post.id: self._reject_post(pid),
        ).pack(side="left")

        if post.post_url:
            ctk.CTkButton(
                btn_frame, text="查看原文", width=80, height=30,
                **T.BTN_GHOST_ACCENT,
                command=lambda url=post.post_url: webbrowser.open(url),
            ).pack(side="right")

        self._card_data.append({
            "post": post,
            "card": card,
            "cb_var": cb_var,
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

    # ── Batch selection ──

    def _on_checkbox_toggle(self, post_id: int, var: ctk.BooleanVar):
        if var.get():
            self._selected_ids.add(post_id)
        else:
            self._selected_ids.discard(post_id)
        self._sync_select_all_state()
        self._update_batch_buttons()

    def _on_select_all(self):
        checked = self._select_all_var.get()
        for data in self._card_data:
            data["cb_var"].set(checked)
            pid = data["post"].id
            if checked:
                self._selected_ids.add(pid)
            else:
                self._selected_ids.discard(pid)
        self._update_batch_buttons()

    def _sync_select_all_state(self):
        if not self._card_data:
            self._select_all_var.set(False)
            return
        all_checked = all(d["cb_var"].get() for d in self._card_data)
        self._select_all_var.set(all_checked)

    def _update_batch_buttons(self):
        n = len(self._selected_ids)
        state = "normal" if n > 0 else "disabled"
        self._batch_reject_btn.configure(text=f"批次拒絕 ({n})", state=state)
        self._batch_skip_btn.configure(text=f"批次跳過 ({n})", state=state)

    def _batch_reject(self):
        self._batch_action("rejected", "拒絕")

    def _batch_skip(self):
        self._batch_action("skipped", "跳過")

    def _batch_action(self, status: str, action_zh: str):
        ids = list(self._selected_ids)
        if not ids:
            return
        if CTkMessagebox:
            result = CTkMessagebox(
                title=f"批次{action_zh}",
                message=f"確定要{action_zh} {len(ids)} 則貼文嗎？",
                icon="question",
                option_1="取消", option_2=f"確定{action_zh}",
            ).get()
            if result != f"確定{action_zh}":
                return
        try:
            count = self.app.repo.batch_update_post_status(ids, status)
            audit_action = f"BATCH_{status.upper()}"
            self.app.repo.log_audit(audit_action, {"count": count, "post_ids": ids})
            show_toast(self, f"已批次{action_zh} {count} 則貼文", "success")
        except Exception as e:
            show_toast(self, f"批次操作失敗: {e}", "error")
        self._selected_ids.clear()
        self._cached_post_ids.clear()
        self.refresh()
        self.app._update_sidebar_badges()

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
                data["card"].configure(border_width=2, border_color=T.GOLD_500)
            else:
                data["card"].configure(border_width=1, border_color=T.BORDER_SUBTLE)

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

            # Guard: prevent duplicate replies for the same post
            existing = self.app.repo.db.execute(
                "SELECT id FROM reply_log WHERE detected_post_id = ? AND status IN ('pending', 'sending', 'retrying', 'sent')",
                (post_id,),
            ).fetchone()
            if existing:
                self._show_error("此貼文已有排程或已送出的回覆")
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
        self._cached_post_ids.clear()
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
