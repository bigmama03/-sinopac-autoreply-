"""Settings frame — browser login, mode toggle, and safety parameters."""

import logging
import threading
import customtkinter as ctk

from src.gui import theme as T
from src.gui.widgets.toast import show_toast

logger = logging.getLogger(__name__)

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class SettingsFrame(ctk.CTkFrame):
    _COMING_SOON_PLATS = {"facebook", "instagram"}

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)

        # Scrollable content
        scroll = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._scroll = scroll
        self._entries: dict[str, ctk.CTkEntry | ctk.CTkSwitch | ctk.CTkOptionMenu] = {}
        self._browser_status_labels: dict[str, ctk.CTkLabel] = {}
        self._browser_test_labels: dict[str, ctk.CTkLabel] = {}
        row = 0

        # ── Page title ──
        ctk.CTkLabel(
            scroll, text="設定",
            font=T.font_title(), text_color=T.TEXT_PRIMARY,
        ).grid(row=row, column=0, sticky="w", padx=T.PAD_MD, pady=(0, T.PAD_LG))
        row += 1

        # ── Mode Toggle ──
        row = self._add_section_title(scroll, "回覆模式", row)
        self._mode_switch_var = ctk.StringVar(value="0")
        mode_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=T.PAD_XS)
        ctk.CTkLabel(mode_frame, text="半自動",
                     text_color=T.TEXT_SECONDARY).pack(side="left")
        self._mode_switch = ctk.CTkSwitch(
            mode_frame, text="全自動", variable=self._mode_switch_var,
            onvalue="1", offvalue="0",
            fg_color=T.NAVY_600, progress_color=T.GOLD_500,
            button_color=T.TEXT_PRIMARY, button_hover_color=T.GOLD_400,
            text_color=T.TEXT_SECONDARY,
        )
        self._mode_switch.pack(side="left", padx=T.PAD_MD)
        row += 1

        # ── Browser Visible Toggle ──
        visible_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        visible_frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=T.PAD_XS)
        self._visible_switch_var = ctk.StringVar(value="0")
        self._visible_switch = ctk.CTkSwitch(
            visible_frame, text="顯示海巡瀏覽器視窗（除錯用）",
            variable=self._visible_switch_var,
            onvalue="1", offvalue="0",
            command=self._on_browser_visible_change,
            fg_color=T.NAVY_600, progress_color=T.GOLD_500,
            button_color=T.TEXT_PRIMARY, button_hover_color=T.GOLD_400,
            text_color=T.TEXT_SECONDARY,
        )
        self._visible_switch.pack(side="left")
        row += 1

        # ── Browser Settings ──
        for platform, title in (
            ("threads", "Threads 瀏覽器設定"),
            ("facebook", "Facebook 瀏覽器設定"),
            ("instagram", "Instagram 瀏覽器設定"),
        ):
            coming = platform in self._COMING_SOON_PLATS
            suffix = "（即將推出）" if coming else ""
            row = self._add_section_title(scroll, title + suffix, row, muted=coming)

            platform_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            platform_frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=T.PAD_XS)

            status_label = ctk.CTkLabel(
                platform_frame, text="未登入", text_color=T.TEXT_TERTIARY,
                font=T.font_small(),
            )
            status_label.pack(side="left", padx=(0, T.PAD_LG))
            self._browser_status_labels[platform] = status_label

            login_btn = ctk.CTkButton(
                platform_frame, text="登入瀏覽器", width=100, height=28,
                **T.BTN_PRIMARY,
                command=lambda p=platform: self._browser_login(p),
            )
            login_btn.pack(side="left", padx=(0, T.PAD_SM))

            ctk.CTkButton(
                platform_frame, text="登出", width=60, height=28,
                **T.BTN_GHOST,
                command=lambda p=platform: self._browser_logout(p),
            ).pack(side="left", padx=(0, T.PAD_SM))

            ctk.CTkButton(
                platform_frame, text="測試連線", width=80, height=28,
                **T.BTN_GHOST,
                command=lambda p=platform: self._test_browser_connection(p),
            ).pack(side="left", padx=(0, T.PAD_SM))

            test_status = ctk.CTkLabel(
                platform_frame, text="",
                text_color=T.TEXT_TERTIARY, font=T.font_caption(),
            )
            test_status.pack(side="left", padx=T.PAD_XS)
            self._browser_test_labels[platform] = test_status

            if coming:
                self._disable_frame_children(platform_frame)

            row += 1

        # ── Facebook Monitor Targets ──
        row = self._add_section_title(scroll, "Facebook 監控社團 / 粉專（即將推出）", row, muted=True)

        fb_target_form = ctk.CTkFrame(scroll, fg_color="transparent")
        fb_target_form.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=T.PAD_XS)
        fb_target_form.grid_columnconfigure(2, weight=1)

        self._fb_target_type_var = ctk.StringVar(value="group")
        ctk.CTkOptionMenu(
            fb_target_form, values=["group", "page"],
            variable=self._fb_target_type_var, width=100,
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=(0, T.PAD_SM), sticky="w")

        self._fb_target_id_entry = ctk.CTkEntry(
            fb_target_form, placeholder_text="Group / Page ID", width=200,
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._fb_target_id_entry.grid(row=0, column=1, padx=(0, T.PAD_SM), sticky="w")

        self._fb_target_name_entry = ctk.CTkEntry(
            fb_target_form, placeholder_text="名稱（選填）", width=180,
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._fb_target_name_entry.grid(row=0, column=2, padx=(0, T.PAD_SM), sticky="ew")

        ctk.CTkButton(
            fb_target_form, text="新增", width=70,
            **T.BTN_PRIMARY,
            command=self._add_fb_target,
        ).grid(row=0, column=3, sticky="e")
        self._disable_frame_children(fb_target_form)
        row += 1

        self._fb_targets_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._fb_targets_frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=(0, T.PAD_XS))
        self._fb_targets_frame.grid_columnconfigure(0, weight=1)
        self._fb_target_widgets: list[ctk.CTkFrame] = []
        row += 1

        # ── Ollama AI Judge ──
        row = self._add_section_title(scroll, "Ollama AI 判斷（即將推出）", row, muted=True)

        ctk.CTkLabel(
            scroll,
            text="需先安裝 Ollama (https://ollama.com)，安裝後於終端機執行 ollama pull <模型名稱>（如 ollama pull llama3.2）下載模型",
            text_color=T.TEXT_TERTIARY, font=T.font_small(),
            wraplength=500, justify="left",
        ).grid(row=row, column=0, sticky="w", padx=(T.PAD_LG + 2), pady=(0, T.PAD_XS))
        row += 1

        ollama_toggle_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ollama_toggle_frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=T.PAD_XS)
        ctk.CTkLabel(ollama_toggle_frame, text="停用",
                     text_color=T.TEXT_TERTIARY).pack(side="left")
        self._ollama_switch_var = ctk.StringVar(value="0")
        self._ollama_switch = ctk.CTkSwitch(
            ollama_toggle_frame, text="啟用（全自動模式下由 AI 判斷是否回覆）",
            variable=self._ollama_switch_var,
            onvalue="1", offvalue="0",
            fg_color=T.NAVY_600, progress_color=T.GOLD_500,
            button_color=T.TEXT_PRIMARY, button_hover_color=T.GOLD_400,
            text_color=T.TEXT_TERTIARY,
        )
        self._ollama_switch.pack(side="left", padx=T.PAD_MD)
        self._disable_frame_children(ollama_toggle_frame)
        row += 1

        row = self._add_entry(scroll, "ollama_url", "Ollama URL", row, default="http://localhost:11434")
        row = self._add_entry(scroll, "ollama_model", "模型名稱", row, default="llama3.2")
        self._entries["ollama_url"].configure(state="disabled")
        self._entries["ollama_model"].configure(state="disabled")

        test_btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        test_btn_frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=T.PAD_XS)
        ctk.CTkButton(
            test_btn_frame, text="測試連線", width=100,
            **T.BTN_GHOST,
            command=self._test_ollama_connection,
        ).pack(side="left")
        self._ollama_status_label = ctk.CTkLabel(
            test_btn_frame, text="", text_color=T.TEXT_TERTIARY,
        )
        self._ollama_status_label.pack(side="left", padx=T.PAD_MD)
        self._disable_frame_children(test_btn_frame)
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
        row = self._add_entry(scroll, "search_scroll_count", "搜尋滾動次數 (越多抓越多貼文)", row, default="6")
        row = self._add_entry(scroll, "auto_cleanup_days", "自動清理天數 (0=停用)", row, default="30")

        # Save button
        ctk.CTkButton(
            scroll, text="儲存設定", height=40,
            **T.BTN_PRIMARY,
            command=self._save_settings,
        ).grid(row=row, column=0, pady=T.PAD_XL, padx=T.PAD_MD, sticky="ew")

    def _add_section_title(self, parent, title: str, row: int, muted: bool = False) -> int:
        T.section_title(parent, title, row=row, columnspan=1, muted=muted)
        return row + 1

    @staticmethod
    def _disable_frame_children(frame):
        for child in frame.winfo_children():
            try:
                child.configure(state="disabled")
            except Exception:
                pass
            if hasattr(child, "winfo_children"):
                SettingsFrame._disable_frame_children(child)

    def _on_browser_visible_change(self):
        visible = self._visible_switch_var.get() == "1"
        self.app.repo.set_setting("browser_visible", "1" if visible else "0")
        self.app.browser_manager.set_headless(not visible)
        show_toast(self, "海巡瀏覽器將以可見模式執行" if visible else "海巡瀏覽器已切回背景模式", "info")

    def _browser_login(self, platform: str):
        urls = {
            "threads": "https://www.threads.com/login",
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
                text_color=T.WARNING,
            )

        def _worker():
            try:
                if self.app._shutting_down:
                    return
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
                                text="登入失敗或逾時", text_color=T.ERROR,
                            )
                        show_toast(self, f"{platform.capitalize()} 登入失敗", "error")

                self.app.run_in_gui(_finish)
            except Exception as e:
                def _error(err=str(e)):
                    if status_label:
                        status_label.configure(
                            text=f"錯誤: {err[:40]}", text_color=T.ERROR,
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
            test_label.configure(text="測試中...", text_color=T.WARNING)

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
                        color = T.TEAL_500 if success else T.ERROR
                        test_label.configure(text=message, text_color=color)

                self.app.run_in_gui(_finish)
            except Exception as e:
                self.app.run_in_gui(
                    lambda err=str(e): test_label.configure(
                        text=f"錯誤: {err[:40]}", text_color=T.ERROR,
                    ) if test_label else None
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _update_browser_status(self, platform: str):
        bm = self.app.browser_manager
        has_session = bm.has_session(platform)
        label = self._browser_status_labels.get(platform)
        if label:
            if has_session:
                label.configure(text="● 已登入", text_color=T.TEAL_500)
            else:
                label.configure(text="○ 未登入", text_color=T.TEXT_TERTIARY)

    def _add_entry(self, parent, key: str, label: str, row: int,
                   show: str = "", default: str = "") -> int:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=T.PAD_MD, pady=2)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=label, width=180, anchor="w",
                     text_color=T.TEXT_SECONDARY, font=T.font_small()).grid(row=0, column=0, sticky="w")
        entry = ctk.CTkEntry(
            frame, show=show if show else "", placeholder_text=default,
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        entry.grid(row=0, column=1, sticky="ew", padx=(T.PAD_MD, 0))
        self._entries[key] = entry
        return row + 1

    def refresh(self):
        repo = self.app.repo

        mode = repo.get_setting("reply_mode", "semi_auto")
        self._mode_switch_var.set("1" if mode == "full_auto" else "0")

        browser_visible = repo.get_setting("browser_visible", "0")
        self._visible_switch_var.set(browser_visible)

        self._ollama_switch_var.set("0")
        for key in ("ollama_url", "ollama_model"):
            default = "http://localhost:11434" if key == "ollama_url" else "llama3.2"
            self._set_entry(key, repo.get_setting(key, default))
        self._ollama_status_label.configure(text="", text_color=T.TEXT_TERTIARY)

        from config import DEFAULT_SETTINGS
        for key in ("daily_limit_threads", "daily_limit_facebook", "daily_limit_instagram",
                     "reply_interval_min_sec", "reply_interval_max_sec",
                     "business_hours_start", "business_hours_end",
                     "search_scroll_count", "auto_cleanup_days"):
            default = str(DEFAULT_SETTINGS.get(key, ""))
            val = repo.get_setting(key, default)
            if val:
                self._set_entry(key, val)
        self._refresh_fb_targets()
        for platform in ("threads", "facebook", "instagram"):
            if platform in self._COMING_SOON_PLATS:
                self._browser_status_labels[platform].configure(
                    text="即將推出", text_color=T.TEXT_TERTIARY,
                )
            else:
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
        self._ollama_status_label.configure(text="連線中...", text_color=T.WARNING)

        def _test():
            from src.core.ollama_judge import OllamaJudge
            judge = OllamaJudge(url=url, model=model)
            success, message = judge.check_connection()
            if success:
                self.app.run_in_gui(lambda: self._ollama_status_label.configure(
                    text=message, text_color=T.TEAL_500,
                ))
            else:
                self.app.run_in_gui(lambda m=message: self._ollama_status_label.configure(
                    text=m, text_color=T.ERROR,
                ))

        threading.Thread(target=_test, daemon=True).start()

    def _do_save(self):
        repo = self.app.repo

        numeric_keys = (
            "daily_limit_threads", "daily_limit_facebook", "daily_limit_instagram",
            "reply_interval_min_sec", "reply_interval_max_sec",
            "search_scroll_count", "auto_cleanup_days",
        )
        numeric_labels = {
            "daily_limit_threads": "Threads 每日上限",
            "daily_limit_facebook": "Facebook 每日上限",
            "daily_limit_instagram": "Instagram 每日上限",
            "reply_interval_min_sec": "回覆間隔最小",
            "reply_interval_max_sec": "回覆間隔最大",
            "search_scroll_count": "搜尋滾動次數",
            "auto_cleanup_days": "自動清理天數",
        }
        # auto_cleanup_days allows 0 (disabled), others must be > 0
        allow_zero = {"auto_cleanup_days"}
        for key in numeric_keys:
            val = self._get_entry(key)
            if not val:
                continue
            if key in allow_zero:
                if not val.isdigit():
                    show_toast(self, f"「{numeric_labels.get(key, key)}」必須為非負整數", "error", duration_ms=3000)
                    return
            elif not val.isdigit() or int(val) <= 0:
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

        mode = "full_auto" if self._mode_switch_var.get() == "1" else "semi_auto"
        repo.set_setting("reply_mode", mode)

        repo.set_setting("ollama_enabled", "0")
        for key in ("ollama_url", "ollama_model"):
            default = "http://localhost:11434" if key == "ollama_url" else "llama3.2"
            val = self._get_entry(key) or default
            repo.set_setting(key, val)

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
                text_color=T.TEXT_TERTIARY, font=T.font_small(),
            )
            empty.grid(row=0, column=0, pady=T.PAD_SM)
            self._fb_target_widgets.append(empty)
            return

        for i, t in enumerate(targets):
            row_frame = T.card_frame(self._fb_targets_frame,
                                     row=i, column=0, sticky="ew", pady=2)
            row_frame.grid_columnconfigure(2, weight=1)

            type_text = "社團" if t["target_type"] == "group" else "粉專"
            ctk.CTkLabel(
                row_frame, text=f"[{type_text}]",
                font=T.font_small(), text_color=T.GOLD_500,
                width=50,
            ).grid(row=0, column=0, padx=(T.PAD_SM, T.PAD_XS), pady=T.PAD_SM, sticky="w")

            display_name = t.get("target_name") or t["target_id"]
            ctk.CTkLabel(
                row_frame, text=display_name,
                font=T.font_body(), text_color=T.TEXT_PRIMARY,
            ).grid(row=0, column=1, padx=(0, T.PAD_SM), pady=T.PAD_SM, sticky="w")

            ctk.CTkLabel(
                row_frame, text=t["target_id"],
                font=T.font_caption(), text_color=T.TEXT_TERTIARY,
            ).grid(row=0, column=2, pady=T.PAD_SM, sticky="w")

            ctk.CTkButton(
                row_frame, text="移除", width=50, height=26,
                **T.BTN_GHOST_DANGER,
                command=lambda tid=t["target_id"]: self._remove_fb_target(tid),
            ).grid(row=0, column=3, padx=T.PAD_SM, pady=T.PAD_XS, sticky="e")

            self._disable_frame_children(row_frame)
            self._fb_target_widgets.append(row_frame)

    def _show_msg(self, title: str, message: str, icon: str = "info"):
        if CTkMessagebox:
            CTkMessagebox(title=title, message=message, icon=icon)
