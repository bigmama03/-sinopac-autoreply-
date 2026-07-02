"""Monitor frame — patrol view with browser preview and activity log."""

import io
import tkinter as tk
import threading
from datetime import datetime
import customtkinter as ctk
from PIL import Image

from src.gui import theme as T

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class _ChannelSelectDialog(ctk.CTkToplevel):
    def __init__(self, parent, configured_platforms: list[str], all_platforms: list[str]):
        super().__init__(parent)
        self.result = None
        self._vars: dict[str, tk.BooleanVar] = {}
        self.title("選擇平台")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=T.BG_ELEVATED)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=T.PAD_XL, pady=T.PAD_XL)

        ctk.CTkLabel(
            container, text="選擇要啟動海巡的平台",
            font=T.font_section(), text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, T.PAD_MD))

        for plat in all_platforms:
            if plat in configured_platforms:
                value = tk.BooleanVar(value=True)
                self._vars[plat] = value
                ctk.CTkCheckBox(
                    container, text=plat.capitalize(), variable=value,
                    onvalue=True, offvalue=False,
                    text_color=T.TEXT_PRIMARY, fg_color=T.GOLD_500,
                    hover_color=T.GOLD_400, checkmark_color=T.TEXT_INVERSE,
                ).pack(anchor="w", pady=T.PAD_XS)
            else:
                ctk.CTkLabel(
                    container, text=f"{plat.capitalize()} (未設定)",
                    text_color=T.TEXT_TERTIARY,
                ).pack(anchor="w", pady=T.PAD_XS)

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(T.PAD_LG, 0))
        ctk.CTkButton(btn_row, text="啟動", width=90, **T.BTN_SUCCESS,
                      command=self._confirm).pack(side="right", padx=(T.PAD_SM, 0))
        ctk.CTkButton(btn_row, text="取消", width=90, **T.BTN_GHOST,
                      command=self._cancel).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(10, lambda: self._center_on_parent(parent))
        self.grab_set()

    def _center_on_parent(self, parent):
        if not self.winfo_exists():
            return
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if parent.winfo_ismapped() and pw > 1 and ph > 1:
            x = parent.winfo_rootx() + max((pw - w) // 2, 0)
            y = parent.winfo_rooty() + max((ph - h) // 2, 0)
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _confirm(self):
        self.result = [p for p, v in self._vars.items() if v.get()]
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class MonitorFrame(ctk.CTkFrame):
    _PATROL_PLATFORMS = ["threads", "facebook", "instagram"]
    _COMING_SOON_PLATS = {"facebook", "instagram"}
    _PLATFORM_LABELS = {"threads": "Threads", "facebook": "Facebook", "instagram": "Instagram"}

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ──
        header = T.page_header(self, "海巡監測")
        header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._patrol_btn = ctk.CTkButton(
            header, text="啟動海巡", width=120, height=32,
            **T.BTN_SUCCESS,
            command=self._toggle_patrol,
        )
        self._patrol_btn.pack(side="right", padx=T.PAD_SM)

        self._sending_btn = ctk.CTkButton(
            header, text="暫停發送", width=100, height=32,
            **T.BTN_WARNING,
            command=self._toggle_sending,
        )
        # Hidden initially, shown when patrol is running
        self._sending_btn.pack(side="right", padx=(0, T.PAD_SM))
        self._sending_btn.pack_forget()

        self._patrol_indicator = ctk.CTkLabel(
            header, text="", text_color=T.TEAL_500,
            font=T.font_small(),
        )
        self._patrol_indicator.pack(side="right", padx=T.PAD_MD)

        # ── Content: browser preview (top) + patrol log (bottom) ──
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=3)
        content.grid_rowconfigure(1, weight=1)

        # Browser preview (top)
        preview_frame = T.card_frame(content)
        preview_frame.grid(row=0, column=0, sticky="nsew", pady=(0, T.PAD_SM))

        ctk.CTkLabel(
            preview_frame, text="瀏覽器即時預覽",
            font=T.font_card_title(), text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        self._preview_label = ctk.CTkLabel(
            preview_frame, text="海巡未啟動",
            text_color=T.TEXT_TERTIARY,
        )
        self._preview_label.pack(padx=T.PAD_MD, pady=(0, T.PAD_SM), expand=True, fill="both")
        self._preview_image = None
        self._preview_after_id = None

        # Patrol log (bottom)
        log_frame = T.card_frame(content)
        log_frame.grid(row=1, column=0, sticky="nsew")

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        ctk.CTkLabel(
            log_header, text="海巡活動日誌",
            font=T.font_card_title(), text_color=T.TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkButton(
            log_header, text="清除", width=50, height=24,
            font=T.font_caption(),
            **T.BTN_GHOST,
            command=self._clear_patrol_log,
        ).pack(side="right")

        self._log_follow = True
        self._follow_btn = ctk.CTkButton(
            log_header, text="暫停追蹤", width=80, height=24,
            font=T.font_caption(),
            **T.BTN_GHOST,
            command=self._toggle_log_follow,
        )
        self._follow_btn.pack(side="right", padx=(0, T.PAD_XS))

        self._log_textbox = ctk.CTkTextbox(
            log_frame, font=T.font_mono(),
            state="disabled", wrap="word",
            fg_color=T.NAVY_900, text_color=T.TEXT_SECONDARY,
            border_width=1, border_color=T.BORDER_SUBTLE,
            corner_radius=T.RADIUS_MD,
        )
        self._log_textbox.pack(fill="both", expand=True, padx=T.PAD_MD, pady=(0, T.PAD_SM))
        self._patrol_log_lines: list[str] = []
        self._max_log_lines = 200

    # ── Patrol control ──

    def _toggle_patrol(self):
        scheduler = self.app.scheduler
        if scheduler.is_running:
            self._patrol_btn.configure(text="停止中...", state="disabled")

            def _stop_in_bg():
                try:
                    scheduler.stop()
                finally:
                    self.app.run_in_gui(lambda: self._patrol_btn.configure(state="normal"))
                    self.app.run_in_gui(self._update_patrol_ui)
                    self.app.run_in_gui(self._sync_dashboard)

            threading.Thread(target=_stop_in_bg, daemon=True).start()
        else:
            configured = []
            all_plats = [p for p in self._PATROL_PLATFORMS if p not in self._COMING_SOON_PLATS]
            bm = self.app.browser_manager
            for plat in all_plats:
                config = self.app.repo.get_platform_config(plat)
                if config and config.is_enabled and bm.has_session(plat):
                    configured.append(plat)

            if not configured:
                if CTkMessagebox:
                    CTkMessagebox(
                        title="無法啟動",
                        message="請先到「設定」頁面登入至少一個平台的瀏覽器",
                        icon="warning",
                    )
                return

            if self.app.template_manager.count() == 0:
                if CTkMessagebox:
                    CTkMessagebox(
                        title="無法啟動",
                        message="請先到「文案管理」頁面匯入文案",
                        icon="warning",
                    )
                return

            dialog = _ChannelSelectDialog(self, configured, all_plats)
            self.wait_window(dialog)
            if dialog.result is None or len(dialog.result) == 0:
                return

            self._patrol_btn.configure(text="啟動中...", state="disabled")
            try:
                scheduler.start(platforms=dialog.result)
            finally:
                self._patrol_btn.configure(state="normal")

            self._update_patrol_ui()
            self._sync_dashboard()

    def _toggle_sending(self):
        scheduler = self.app.scheduler
        if scheduler.is_sending_paused:
            scheduler.resume_sending()
        else:
            scheduler.pause_sending()
        self._update_sending_btn()
        self._sync_dashboard_sending()

    def _sync_dashboard_sending(self):
        if "dashboard" in self.app._frames:
            frame = self.app._frames["dashboard"]
            if hasattr(frame, "_update_sending_btn"):
                frame._update_sending_btn()

    def _update_sending_btn(self):
        if self.app.scheduler.is_sending_paused:
            self._sending_btn.configure(text="開始發送", **T.BTN_SUCCESS)
        else:
            self._sending_btn.configure(text="暫停發送", **T.BTN_WARNING)

    def _update_patrol_ui(self):
        if self.app.scheduler.is_running:
            self._patrol_btn.configure(text="停止海巡", **T.BTN_DANGER)
            active = getattr(self.app.scheduler, "active_platforms", None)
            if active and set(active) != set(self._PATROL_PLATFORMS):
                labels = [self._PLATFORM_LABELS.get(p, p) for p in active]
                self._patrol_indicator.configure(text=f"海巡中 ({', '.join(labels)})")
            else:
                self._patrol_indicator.configure(text="海巡中...")
            self._sending_btn.pack(side="right", padx=(0, T.PAD_SM), before=self._patrol_btn)
            self._update_sending_btn()
            self._start_preview_polling()
        else:
            self._patrol_btn.configure(text="啟動海巡", **T.BTN_SUCCESS)
            self._patrol_indicator.configure(text="")
            self._sending_btn.pack_forget()
            self._stop_preview_polling()

    def _sync_dashboard(self):
        """Keep dashboard patrol UI in sync."""
        if "dashboard" in self.app._frames:
            frame = self.app._frames["dashboard"]
            if hasattr(frame, "_update_patrol_ui"):
                frame._update_patrol_ui()

    # ── Refresh ──

    def refresh(self):
        if hasattr(self.app, "_patrol_log_buffer") and self.app._patrol_log_buffer:
            for level, message in self.app._patrol_log_buffer:
                self.append_patrol_log(level, message)
            self.app._patrol_log_buffer.clear()

        self._update_patrol_ui()

    # ── Patrol log ──

    _LOG_LEVEL_PREFIX = {
        "info": "INFO",
        "success": "OK  ",
        "warning": "WARN",
        "error": "ERR ",
    }

    def append_patrol_log(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = self._LOG_LEVEL_PREFIX.get(level, "INFO")
        line = f"[{ts}] [{prefix}] {message}"

        self._patrol_log_lines.append(line)

        self._log_textbox.configure(state="normal")
        self._log_textbox.insert("end", line + "\n")

        if len(self._patrol_log_lines) > self._max_log_lines:
            overflow = len(self._patrol_log_lines) - self._max_log_lines
            self._patrol_log_lines = self._patrol_log_lines[-self._max_log_lines:]
            self._log_textbox.delete("1.0", f"{overflow + 1}.0")

        if self._log_follow:
            self._log_textbox.see("end")
        self._log_textbox.configure(state="disabled")

    def _toggle_log_follow(self):
        self._log_follow = not self._log_follow
        if self._log_follow:
            self._follow_btn.configure(text="暫停追蹤")
            self._log_textbox.configure(state="normal")
            self._log_textbox.see("end")
            self._log_textbox.configure(state="disabled")
        else:
            self._follow_btn.configure(text="繼續追蹤")

    def _clear_patrol_log(self):
        self._patrol_log_lines.clear()
        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")
        self._log_textbox.configure(state="disabled")

    # ── Browser PIP preview ──

    def _start_preview_polling(self):
        if self._preview_after_id is not None:
            return
        self._poll_preview()

    def _stop_preview_polling(self):
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def _poll_preview(self):
        try:
            data = self.app.browser_manager.get_screenshot()
            if data:
                lw = self._preview_label.winfo_width()
                lh = self._preview_label.winfo_height()
                if lw > 100 and lh > 100:
                    max_w = lw - 16
                    max_h = lh - 16
                else:
                    max_w = 640
                    max_h = 480

                img = Image.open(io.BytesIO(data))
                img.thumbnail((max_w, max_h), Image.LANCZOS)
                ctk_img = ctk.CTkImage(
                    light_image=img, dark_image=img,
                    size=(img.width, img.height),
                )
                self._preview_label.configure(image=ctk_img, text="")
                self._preview_image = ctk_img
            elif self.app.scheduler.is_running:
                self._preview_label.configure(text="等待瀏覽器截圖...")
        except Exception:
            pass

        if self.app.scheduler.is_running:
            self._preview_after_id = self.after(1500, self._poll_preview)
        else:
            self._preview_after_id = None
            self._preview_label.configure(text="海巡未啟動")
            self._preview_image = None
            self.app.browser_manager.clear_screenshot()

    def destroy(self):
        self._stop_preview_polling()
        super().destroy()
