"""Review queue frame — semi-auto approval workflow."""

import customtkinter as ctk

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class ReviewFrame(ctk.CTkFrame):
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

        # Scrollable list
        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.grid(row=1, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._widgets: list[ctk.CTkFrame] = []

    def refresh(self):
        pending = self.app.repo.get_pending_posts()
        self._count_label.configure(text=f"{len(pending)} 則待審核")

        for w in self._widgets:
            w.destroy()
        self._widgets.clear()

        if not pending:
            empty = ctk.CTkLabel(
                self._scroll_frame, text="目前沒有待審核的貼文",
                text_color="gray50", font=ctk.CTkFont(size=14),
            )
            empty.grid(row=0, column=0, pady=40)
            self._widgets.append(empty)
            return

        for i, post in enumerate(pending):
            card = self._create_review_card(post, i)
            self._widgets.append(card)

    def _create_review_card(self, post, index: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._scroll_frame)
        card.grid(row=index, column=0, sticky="ew", pady=4, padx=2)
        card.grid_columnconfigure(0, weight=1)

        # Post info
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        platform_colors = {
            "threads": "#1DA1F2", "facebook": "#1877F2", "instagram": "#E4405F",
        }
        ctk.CTkLabel(
            info_frame, text=post.platform.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=platform_colors.get(post.platform, "#1877F2"),
        ).pack(side="left")

        if post.author_username:
            ctk.CTkLabel(
                info_frame, text=f"@{post.author_username}",
                font=ctk.CTkFont(size=11), text_color="gray50",
            ).pack(side="left", padx=8)

        ctk.CTkLabel(
            info_frame, text=f"相關性: {post.relevance_score:.1f}",
            font=ctk.CTkFont(size=11), text_color="orange",
        ).pack(side="right")

        # Post content
        content = (post.post_content or "")[:200]
        if len(post.post_content or "") > 200:
            content += "..."
        ctk.CTkLabel(
            card, text=content, wraplength=700, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        # Template selector
        templates = self.app.template_manager.get_all()
        if post.recommended_template_id:
            rec = self.app.template_manager.get_by_id(post.recommended_template_id)
            if rec:
                templates = [rec] + [t for t in templates if t.id != rec.id]

        template_options = [f"[{t.template_code}] {t.content[:50]}..." for t in templates]
        template_ids = [t.id for t in templates]

        select_frame = ctk.CTkFrame(card, fg_color="transparent")
        select_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))

        ctk.CTkLabel(select_frame, text="選擇文案:", font=ctk.CTkFont(size=11)).pack(side="left")
        template_var = ctk.StringVar(value=template_options[0] if template_options else "")
        template_menu = ctk.CTkOptionMenu(
            select_frame, values=template_options, variable=template_var, width=500,
        )
        template_menu.pack(side="left", padx=5)

        # Action buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        def approve():
            idx = template_options.index(template_var.get()) if template_var.get() in template_options else 0
            if idx < len(template_ids):
                self._approve_post(post.id, template_ids[idx])

        ctk.CTkButton(
            btn_frame, text="核准回覆", width=100, height=30,
            fg_color="#4CAF50", hover_color="#388E3C",
            command=approve,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="跳過", width=80, height=30,
            fg_color="transparent", border_width=1,
            command=lambda pid=post.id: self._skip_post(pid),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="拒絕", width=80, height=30,
            fg_color="transparent", border_width=1,
            text_color=("red", "#EF5350"),
            command=lambda pid=post.id: self._reject_post(pid),
        ).pack(side="left")

        return card

    def _approve_post(self, post_id: int, template_id: int):
        try:
            template = self.app.template_manager.get_by_id(template_id)
            if not template:
                self._show_error("找不到指定文案")
                return

            # Get post platform first
            post_row = self.app.repo.db.execute(
                "SELECT platform FROM detected_posts WHERE id = ?", (post_id,)
            ).fetchone()
            if not post_row:
                self._show_error("找不到指定貼文")
                return

            # All checks passed — now update atomically
            from src.data.models import ReplyLog
            reply = ReplyLog(
                detected_post_id=post_id,
                template_id=template_id,
                platform=post_row["platform"],
                reply_content=template.content,
                reply_mode="semi_auto",
                status="pending",
            )
            self.app.repo.insert_reply_log(reply)
            self.app.repo.update_post_status(post_id, "approved")
            self.app.repo.log_audit("REPLY_APPROVED", {
                "post_id": post_id, "template_id": template_id,
            })
        except Exception as e:
            self._show_error(f"核准失敗: {e}")
        self.refresh()

    def _skip_post(self, post_id: int):
        try:
            self.app.repo.update_post_status(post_id, "skipped")
            self.app.repo.log_audit("POST_SKIPPED", {"post_id": post_id})
        except Exception as e:
            self._show_error(f"操作失敗: {e}")
        self.refresh()

    def _reject_post(self, post_id: int):
        try:
            self.app.repo.update_post_status(post_id, "rejected")
            self.app.repo.log_audit("POST_REJECTED", {"post_id": post_id})
        except Exception as e:
            self._show_error(f"操作失敗: {e}")
        self.refresh()

    def _show_error(self, msg: str):
        if CTkMessagebox:
            CTkMessagebox(title="錯誤", message=msg, icon="cancel")
