"""Settings frame — API credentials, mode toggle, safety parameters."""

import customtkinter as ctk
from src.utils.crypto import encrypt_token, decrypt_token

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class SettingsFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)

        # Scrollable content
        scroll = ctk.CTkScrollableFrame(self)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._scroll = scroll
        self._entries: dict[str, ctk.CTkEntry | ctk.CTkSwitch | ctk.CTkOptionMenu] = {}
        self._decrypt_failed: set = set()
        row = 0

        # ── Mode Toggle ──
        row = self._add_section_title(scroll, "回覆模式", row)
        self._mode_switch_var = ctk.StringVar(value="0")
        mode_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        ctk.CTkLabel(mode_frame, text="半自動").pack(side="left")
        self._mode_switch = ctk.CTkSwitch(
            mode_frame, text="全自動", variable=self._mode_switch_var,
            onvalue="1", offvalue="0",
        )
        self._mode_switch.pack(side="left", padx=10)
        row += 1

        # ── Threads API ──
        row = self._add_section_title(scroll, "Threads API 設定", row)
        row = self._add_entry(scroll, "threads_user_id", "Threads User ID", row)
        row = self._add_entry(scroll, "threads_access_token", "Access Token", row, show="*")

        # ── Facebook API ──
        row = self._add_section_title(scroll, "Facebook API 設定", row)
        row = self._add_entry(scroll, "fb_app_id", "App ID", row)
        row = self._add_entry(scroll, "fb_app_secret", "App Secret", row, show="*")
        row = self._add_entry(scroll, "fb_page_id", "Page ID", row)
        row = self._add_entry(scroll, "fb_access_token", "Page Access Token", row, show="*")

        # ── Facebook Monitor Targets ──
        row = self._add_section_title(scroll, "Facebook 監控社團 / 粉專", row)

        # Add target form
        fb_target_form = ctk.CTkFrame(scroll, fg_color="transparent")
        fb_target_form.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        fb_target_form.grid_columnconfigure(2, weight=1)

        self._fb_target_type_var = ctk.StringVar(value="group")
        ctk.CTkOptionMenu(
            fb_target_form,
            values=["group", "page"],
            variable=self._fb_target_type_var,
            width=100,
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        self._fb_target_id_entry = ctk.CTkEntry(
            fb_target_form, placeholder_text="Group / Page ID", width=200,
        )
        self._fb_target_id_entry.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self._fb_target_name_entry = ctk.CTkEntry(
            fb_target_form, placeholder_text="名稱（選填）", width=180,
        )
        self._fb_target_name_entry.grid(row=0, column=2, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            fb_target_form, text="新增", width=70,
            command=self._add_fb_target,
        ).grid(row=0, column=3, sticky="e")
        row += 1

        # Target list container
        self._fb_targets_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._fb_targets_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 4))
        self._fb_targets_frame.grid_columnconfigure(0, weight=1)
        self._fb_target_widgets: list[ctk.CTkFrame] = []
        row += 1

        # ── Ollama AI Judge ──
        row = self._add_section_title(scroll, "Ollama AI 判斷", row)

        ctk.CTkLabel(
            scroll,
            text="需先安裝 Ollama (https://ollama.com)，安裝後於終端機執行 ollama pull <模型名稱>（如 ollama pull llama3.2）下載模型",
            text_color="gray50", font=ctk.CTkFont(size=12),
            wraplength=500, justify="left",
        ).grid(row=row, column=0, sticky="w", padx=14, pady=(0, 4))
        row += 1

        ollama_toggle_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ollama_toggle_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        ctk.CTkLabel(ollama_toggle_frame, text="停用").pack(side="left")
        self._ollama_switch_var = ctk.StringVar(value="0")
        self._ollama_switch = ctk.CTkSwitch(
            ollama_toggle_frame, text="啟用（全自動模式下由 AI 判斷是否回覆）",
            variable=self._ollama_switch_var,
            onvalue="1", offvalue="0",
        )
        self._ollama_switch.pack(side="left", padx=10)
        row += 1

        row = self._add_entry(scroll, "ollama_url", "Ollama URL", row, default="http://localhost:11434")
        row = self._add_entry(scroll, "ollama_model", "模型名稱", row, default="llama3.2")

        test_btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        test_btn_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        ctk.CTkButton(
            test_btn_frame, text="測試連線", width=100,
            command=self._test_ollama_connection,
        ).pack(side="left")
        self._ollama_status_label = ctk.CTkLabel(
            test_btn_frame, text="", text_color="gray50",
        )
        self._ollama_status_label.pack(side="left", padx=10)
        row += 1

        # ── Instagram API ──
        row = self._add_section_title(scroll, "Instagram API 設定", row)
        row = self._add_entry(scroll, "ig_user_id", "IG Business Account ID", row)
        row = self._add_entry(scroll, "ig_access_token", "Access Token", row, show="*")

        # ── Safety Parameters ──
        row = self._add_section_title(scroll, "安全防護設定", row)
        row = self._add_entry(scroll, "daily_limit_threads", "Threads 每日上限", row, default="40")
        row = self._add_entry(scroll, "daily_limit_facebook", "Facebook 每日上限", row, default="25")
        row = self._add_entry(scroll, "daily_limit_instagram", "Instagram 每日上限", row, default="25")
        row = self._add_entry(scroll, "reply_interval_min_sec", "回覆間隔最小 (秒)", row, default="120")
        row = self._add_entry(scroll, "reply_interval_max_sec", "回覆間隔最大 (秒)", row, default="300")
        row = self._add_entry(scroll, "business_hours_start", "營業時間起始", row, default="09:00")
        row = self._add_entry(scroll, "business_hours_end", "營業時間結束", row, default="18:00")

        # Save button
        ctk.CTkButton(
            scroll, text="儲存設定", height=40,
            command=self._save_settings,
        ).grid(row=row, column=0, pady=20, padx=10, sticky="ew")

    def _add_section_title(self, parent, title: str, row: int) -> int:
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=10, pady=(15, 5))
        return row + 1

    def _add_entry(self, parent, key: str, label: str, row: int,
                   show: str = "", default: str = "") -> int:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=label, width=180, anchor="w").grid(row=0, column=0, sticky="w")
        entry = ctk.CTkEntry(frame, show=show if show else "", placeholder_text=default)
        entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self._entries[key] = entry
        return row + 1

    def refresh(self):
        repo = self.app.repo

        # Mode
        mode = repo.get_setting("reply_mode", "semi_auto")
        self._mode_switch_var.set("1" if mode == "full_auto" else "0")

        self._decrypt_failed.clear()

        # Threads
        t_config = repo.get_platform_config("threads")
        if t_config:
            self._set_entry("threads_user_id", t_config.threads_user_id or "")
            self._set_entry("threads_access_token", self._safe_decrypt(t_config.access_token, "threads_access_token"))

        # Facebook
        fb_config = repo.get_platform_config("facebook")
        if fb_config:
            self._set_entry("fb_app_id", fb_config.app_id or "")
            self._set_entry("fb_app_secret", self._safe_decrypt(fb_config.app_secret, "fb_app_secret"))
            self._set_entry("fb_page_id", fb_config.page_id or "")
            self._set_entry("fb_access_token", self._safe_decrypt(fb_config.access_token, "fb_access_token"))

        # Instagram
        ig_config = repo.get_platform_config("instagram")
        if ig_config:
            self._set_entry("ig_user_id", ig_config.ig_user_id or "")
            self._set_entry("ig_access_token", self._safe_decrypt(ig_config.access_token, "ig_access_token"))

        # Ollama settings
        ollama_enabled = repo.get_setting("ollama_enabled", "0")
        self._ollama_switch_var.set(ollama_enabled)
        for key in ("ollama_url", "ollama_model"):
            default = "http://localhost:11434" if key == "ollama_url" else "llama3.2"
            self._set_entry(key, repo.get_setting(key, default))
        self._ollama_status_label.configure(text="", text_color="gray50")

        # Safety settings
        for key in ("daily_limit_threads", "daily_limit_facebook", "daily_limit_instagram",
                     "reply_interval_min_sec", "reply_interval_max_sec",
                     "business_hours_start", "business_hours_end"):
            val = repo.get_setting(key, "")
            if val:
                self._set_entry(key, val)
        self._refresh_fb_targets()

    def _set_entry(self, key: str, value: str):
        entry = self._entries.get(key)
        if entry:
            entry.delete(0, "end")
            if value:
                entry.insert(0, value)

    def _get_entry(self, key: str) -> str:
        entry = self._entries.get(key)
        return entry.get().strip() if entry else ""

    def _safe_decrypt(self, value: str | None, field_key: str = "") -> str:
        if not value:
            return ""
        try:
            return decrypt_token(value)
        except ValueError:
            if field_key:
                self._decrypt_failed.add(field_key)
            return ""

    def _save_settings(self):
        try:
            self._do_save()
        except Exception as e:
            if CTkMessagebox:
                CTkMessagebox(title="儲存失敗", message=f"設定儲存時發生錯誤:\n{e}", icon="cancel")

    def _test_ollama_connection(self):
        url = self._get_entry("ollama_url") or "http://localhost:11434"
        model = self._get_entry("ollama_model") or "llama3.2"

        from src.core.ollama_judge import OllamaJudge
        judge = OllamaJudge(url=url, model=model)
        success, message = judge.check_connection()

        if success:
            self._ollama_status_label.configure(text=message, text_color=("#4CAF50", "#66BB6A"))
        else:
            self._ollama_status_label.configure(text=message, text_color=("red", "#EF5350"))

    def _do_save(self):
        repo = self.app.repo

        # Mode
        mode = "full_auto" if self._mode_switch_var.get() == "1" else "semi_auto"
        repo.set_setting("reply_mode", mode)

        # Threads — skip token update if field is empty AND decryption had failed
        threads_token = self._get_entry("threads_access_token")
        threads_update = {"threads_user_id": self._get_entry("threads_user_id")}
        if threads_token:
            threads_update["access_token"] = encrypt_token(threads_token)
            threads_update["is_enabled"] = 1
        elif "threads_access_token" not in self._decrypt_failed:
            threads_update["access_token"] = ""
            threads_update["is_enabled"] = 0
        repo.update_platform_config("threads", **threads_update)

        # Facebook
        fb_token = self._get_entry("fb_access_token")
        fb_secret = self._get_entry("fb_app_secret")
        fb_update = {
            "app_id": self._get_entry("fb_app_id"),
            "page_id": self._get_entry("fb_page_id"),
        }
        if fb_secret:
            fb_update["app_secret"] = encrypt_token(fb_secret)
        elif "fb_app_secret" not in self._decrypt_failed:
            fb_update["app_secret"] = ""
        if fb_token:
            fb_update["access_token"] = encrypt_token(fb_token)
            fb_update["is_enabled"] = 1
        elif "fb_access_token" not in self._decrypt_failed:
            fb_update["access_token"] = ""
            fb_update["is_enabled"] = 0
        repo.update_platform_config("facebook", **fb_update)

        # Instagram
        ig_token = self._get_entry("ig_access_token")
        ig_update = {"ig_user_id": self._get_entry("ig_user_id")}
        if ig_token:
            ig_update["access_token"] = encrypt_token(ig_token)
            ig_update["is_enabled"] = 1
        elif "ig_access_token" not in self._decrypt_failed:
            ig_update["access_token"] = ""
            ig_update["is_enabled"] = 0
        repo.update_platform_config("instagram", **ig_update)

        # Ollama settings
        ollama_enabled = self._ollama_switch_var.get()
        repo.set_setting("ollama_enabled", ollama_enabled)
        for key in ("ollama_url", "ollama_model"):
            default = "http://localhost:11434" if key == "ollama_url" else "llama3.2"
            val = self._get_entry(key) or default
            repo.set_setting(key, val)

        # Safety settings
        for key in ("daily_limit_threads", "daily_limit_facebook", "daily_limit_instagram",
                     "reply_interval_min_sec", "reply_interval_max_sec",
                     "business_hours_start", "business_hours_end"):
            val = self._get_entry(key)
            if val:
                repo.set_setting(key, val)

        self.app.reload_ollama_judge()
        repo.log_audit("SETTINGS_SAVED", {"mode": mode})
        self._decrypt_failed.clear()
        self._ollama_status_label.configure(text="設定已套用", text_color=("#4CAF50", "#66BB6A"))

        if CTkMessagebox:
            CTkMessagebox(title="儲存成功", message="設定已儲存", icon="check")

    def _add_fb_target(self):
        target_id = self._fb_target_id_entry.get().strip()
        if not target_id:
            self._show_msg("新增失敗", "請輸入 Group / Page ID", "warning")
            return
        target_type = self._fb_target_type_var.get()
        target_name = self._fb_target_name_entry.get().strip()
        self.app.repo.add_fb_monitor_target(target_type, target_id, target_name)
        self.app.repo.log_audit("FB_TARGET_ADDED", {
            "target_type": target_type, "target_id": target_id, "target_name": target_name,
        })
        self._fb_target_id_entry.delete(0, "end")
        self._fb_target_name_entry.delete(0, "end")
        self._refresh_fb_targets()

    def _remove_fb_target(self, target_id: str):
        self.app.repo.remove_fb_monitor_target(target_id)
        self.app.repo.log_audit("FB_TARGET_REMOVED", {"target_id": target_id})
        self._refresh_fb_targets()

    def _refresh_fb_targets(self):
        for w in self._fb_target_widgets:
            w.destroy()
        self._fb_target_widgets.clear()

        targets = self.app.repo.get_fb_monitor_targets(active_only=True)
        if not targets:
            empty = ctk.CTkLabel(
                self._fb_targets_frame, text="尚未設定監控目標",
                text_color="gray50", font=ctk.CTkFont(size=12),
            )
            empty.grid(row=0, column=0, pady=8)
            self._fb_target_widgets.append(empty)
            return

        for i, t in enumerate(targets):
            row_frame = ctk.CTkFrame(self._fb_targets_frame)
            row_frame.grid(row=i, column=0, sticky="ew", pady=2)
            row_frame.grid_columnconfigure(2, weight=1)

            type_text = "社團" if t["target_type"] == "group" else "粉專"
            ctk.CTkLabel(
                row_frame, text=f"[{type_text}]",
                font=ctk.CTkFont(size=11), text_color=("blue", "#64B5F6"),
                width=50,
            ).grid(row=0, column=0, padx=(8, 4), pady=6, sticky="w")

            display_name = t.get("target_name") or t["target_id"]
            ctk.CTkLabel(
                row_frame, text=display_name,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=1, padx=(0, 8), pady=6, sticky="w")

            ctk.CTkLabel(
                row_frame, text=t["target_id"],
                font=ctk.CTkFont(size=10), text_color="gray50",
            ).grid(row=0, column=2, pady=6, sticky="w")

            ctk.CTkButton(
                row_frame, text="移除", width=50, height=26,
                fg_color="transparent", border_width=1,
                text_color=("red", "#EF5350"),
                hover_color=("gray90", "gray20"),
                command=lambda tid=t["target_id"]: self._remove_fb_target(tid),
            ).grid(row=0, column=3, padx=8, pady=4, sticky="e")

            self._fb_target_widgets.append(row_frame)

    def _show_msg(self, title: str, message: str, icon: str = "info"):
        if CTkMessagebox:
            CTkMessagebox(title=title, message=message, icon=icon)
