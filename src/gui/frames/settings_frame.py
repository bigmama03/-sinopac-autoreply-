"""Settings frame — browser login, mode toggle, and safety parameters."""

import logging
import threading
import customtkinter as ctk
from src.gui.widgets.toast import show_toast

logger = logging.getLogger(__name__)

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
        self._browser_status_labels: dict[str, ctk.CTkLabel] = {}
        self._browser_test_labels: dict[str, ctk.CTkLabel] = {}
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

        # ── Browser Settings ──
        for platform, title in (
            ("threads", "Threads 瀏覽器設定"),
            ("facebook", "Facebook 瀏覽器設定"),
            ("instagram", "Instagram 瀏覽器設定"),
        ):
            row = self._add_section_title(scroll, title, row)

            platform_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            platform_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)

            status_label = ctk.CTkLabel(
                platform_frame, text="未登入", text_color=("gray50", "gray60"),
            )
            status_label.pack(side="left", padx=(0, 15))
            self._browser_status_labels[platform] = status_label

            login_btn = ctk.CTkButton(
                platform_frame,
                text="登入瀏覽器",
                width=100,
                height=28,
                command=lambda p=platform: self._browser_login(p),
            )
            login_btn.pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                platform_frame,
                text="登出",
                width=60,
                height=28,
                fg_color="transparent",
                border_width=1,
                command=lambda p=platform: self._browser_logout(p),
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                platform_frame,
                text="測試連線",
                width=80,
                height=28,
                fg_color="transparent",
                border_width=1,
                command=lambda p=platform: self._test_browser_connection(p),
            ).pack(side="left", padx=(0, 8))

            test_status = ctk.CTkLabel(
                platform_frame,
                text="",
                text_color="gray50",
                font=ctk.CTkFont(size=11),
            )
            test_status.pack(side="left", padx=5)
            self._browser_test_labels[platform] = test_status

            row += 1

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

        # ── Safety Parameters ──
        row = self._add_section_title(scroll, "安全防護設定", row)
        row = self._add_entry(scroll, "daily_limit_threads", "Threads 每日上限", row, default="40")
        row = self._add_entry(scroll, "daily_limit_facebook", "Facebook 每日上限", row, default="25")
        row = self._add_entry(scroll, "daily_limit_instagram", "Instagram 每日上限", row, default="25")
        row = self._add_entry(scroll, "reply_interval_min_sec", "回覆間隔最小 (秒)", row, default="120")
        row = self._add_entry(scroll, "reply_interval_max_sec", "回覆間隔最大 (秒)", row, default="300")
        row = self._add_entry(scroll, "business_hours_start", "營業時間起始 (HH:MM)", row, default="09:00")
        row = self._add_entry(scroll, "business_hours_end", "營業時間結束 (HH:MM)", row, default="18:00")

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

    def _browser_login(self, platform: str):
        urls = {
            "threads": "https://www.threads.net/login",
            "facebook": "https://www.facebook.com/login",
            "instagram": "https://www.instagram.com/accounts/login/",
        }
        url = urls.get(platform, "")
        if not url:
            return
        status_label = self._browser_status_labels.get(platform)
        if status_label:
            status_label.configure(
                text="登入中... 請在彈出的瀏覽器中完成登入",
                text_color=("#FF9800", "#FFA726"),
            )

        def _worker():
            try:
                if self.app._shutting_down:
                    return
                # login_interactive uses a separate headed browser internally
                bm = self.app.browser_manager
                success = bm.login_interactive(platform, url)

                def _finish():
                    if success:
                        self._update_browser_status(platform)
                        show_toast(self, f"{platform.capitalize()} 登入成功", "success")
                        self.app.repo.update_platform_config(platform, is_enabled=1)
                    else:
                        if status_label:
                            status_label.configure(
                                text="登入失敗或逾時",
                                text_color=("#F44336", "#EF5350"),
                            )
                        show_toast(self, f"{platform.capitalize()} 登入失敗", "error")

                self.app.run_in_gui(_finish)
            except Exception as e:
                def _error(err=str(e)):
                    if status_label:
                        status_label.configure(
                            text=f"錯誤: {err[:40]}",
                            text_color=("#F44336", "#EF5350"),
                        )

                self.app.run_in_gui(_error)

        threading.Thread(target=_worker, daemon=True).start()

    def _browser_logout(self, platform: str):
        bm = self.app.browser_manager
        bm.close_context(platform)
        bm.delete_session(platform)
        self.app.repo.update_platform_config(platform, is_enabled=0)
        self._update_browser_status(platform)
        show_toast(self, f"{platform.capitalize()} 已登出", "success")

    def _test_browser_connection(self, platform: str):
        test_label = self._browser_test_labels.get(platform)
        if test_label:
            test_label.configure(text="測試中...", text_color=("#FF9800", "#FFA726"))

        def _worker():
            try:
                if self.app._shutting_down:
                    return
                bm = self.app.browser_manager
                if platform == "threads":
                    from src.platforms.threads_browser import ThreadsBrowserAdapter
                    adapter = ThreadsBrowserAdapter(bm)
                elif platform == "facebook":
                    from src.platforms.facebook_browser import FacebookBrowserAdapter
                    adapter = FacebookBrowserAdapter(bm)
                elif platform == "instagram":
                    from src.platforms.instagram_browser import InstagramBrowserAdapter
                    adapter = InstagramBrowserAdapter(bm)
                else:
                    return
                success, message = adapter.check_connection()

                def _finish():
                    if test_label:
                        color = ("#4CAF50", "#66BB6A") if success else ("#F44336", "#EF5350")
                        test_label.configure(text=message, text_color=color)

                self.app.run_in_gui(_finish)
            except Exception as e:
                self.app.run_in_gui(
                    lambda err=str(e): test_label.configure(
                        text=f"錯誤: {err[:40]}",
                        text_color=("#F44336", "#EF5350"),
                    ) if test_label else None
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _update_browser_status(self, platform: str):
        bm = self.app.browser_manager
        has_session = bm.has_session(platform)
        label = self._browser_status_labels.get(platform)
        if label:
            if has_session:
                label.configure(text="● 已登入", text_color=("#4CAF50", "#66BB6A"))
            else:
                label.configure(text="○ 未登入", text_color=("gray50", "gray60"))

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
        for platform in ("threads", "facebook", "instagram"):
            self._update_browser_status(platform)

    def _set_entry(self, key: str, value: str):
        entry = self._entries.get(key)
        if entry:
            entry.delete(0, "end")
            if value:
                entry.insert(0, value)

    def _get_entry(self, key: str) -> str:
        entry = self._entries.get(key)
        return entry.get().strip() if entry else ""

    def _save_settings(self):
        try:
            self._do_save()
        except Exception as e:
            logger.error("Settings save failed: %s", e)
            if CTkMessagebox:
                CTkMessagebox(title="儲存失敗", message=f"設定儲存時發生錯誤:\n{e}", icon="cancel")

    def _test_ollama_connection(self):
        url = self._get_entry("ollama_url") or "http://localhost:11434"
        model = self._get_entry("ollama_model") or "llama3.2"
        self._ollama_status_label.configure(text="連線中...", text_color=("#FF9800", "#FFA726"))

        def _test():
            from src.core.ollama_judge import OllamaJudge
            judge = OllamaJudge(url=url, model=model)
            success, message = judge.check_connection()
            if success:
                self.app.run_in_gui(lambda: self._ollama_status_label.configure(
                    text=message, text_color=("#4CAF50", "#66BB6A"),
                ))
            else:
                self.app.run_in_gui(lambda m=message: self._ollama_status_label.configure(
                    text=m, text_color=("red", "#EF5350"),
                ))

        threading.Thread(target=_test, daemon=True).start()

    def _do_save(self):
        repo = self.app.repo

        # Validate all fields BEFORE committing any DB writes
        numeric_keys = (
            "daily_limit_threads", "daily_limit_facebook", "daily_limit_instagram",
            "reply_interval_min_sec", "reply_interval_max_sec",
        )
        numeric_labels = {
            "daily_limit_threads": "Threads 每日上限",
            "daily_limit_facebook": "Facebook 每日上限",
            "daily_limit_instagram": "Instagram 每日上限",
            "reply_interval_min_sec": "回覆間隔最小",
            "reply_interval_max_sec": "回覆間隔最大",
        }
        for key in numeric_keys:
            val = self._get_entry(key)
            if val and (not val.isdigit() or int(val) < 0):
                show_toast(self, f"「{numeric_labels.get(key, key)}」必須為正整數", "error", duration_ms=3000)
                return

        for key in ("business_hours_start", "business_hours_end"):
            val = self._get_entry(key)
            if val:
                label = "營業時間起始" if key == "business_hours_start" else "營業時間結束"
                try:
                    from datetime import datetime as _dt
                    _dt.strptime(val, "%H:%M")
                except ValueError:
                    show_toast(self, f"「{label}」格式錯誤，請用 HH:MM（如 09:00）", "error", duration_ms=3000)
                    return

        # All validation passed — now commit to DB

        # Mode
        mode = "full_auto" if self._mode_switch_var.get() == "1" else "semi_auto"
        repo.set_setting("reply_mode", mode)

        # Ollama settings
        ollama_enabled = self._ollama_switch_var.get()
        repo.set_setting("ollama_enabled", ollama_enabled)
        for key in ("ollama_url", "ollama_model"):
            default = "http://localhost:11434" if key == "ollama_url" else "llama3.2"
            val = self._get_entry(key) or default
            repo.set_setting(key, val)

        # Safety settings (already validated above)
        for key in numeric_keys:
            val = self._get_entry(key)
            if val:
                repo.set_setting(key, val)

        for key in ("business_hours_start", "business_hours_end"):
            val = self._get_entry(key)
            if val:
                repo.set_setting(key, val)

        self.app.reload_ollama_judge()
        repo.log_audit("SETTINGS_SAVED", {"mode": mode})

        show_toast(self, "設定已儲存", "success")

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
