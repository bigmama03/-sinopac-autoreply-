"""Monitor frame — patrol view with browser preview and activity log."""

import io
from datetime import datetime
import customtkinter as ctk
from PIL import Image

from src.gui import theme as T


class MonitorFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ──
        header = T.page_header(self, "海巡監測")
        header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._patrol_indicator = ctk.CTkLabel(
            header, text="", text_color=T.TEAL_500,
            font=T.font_small(),
        )
        self._patrol_indicator.pack(side="right", padx=T.PAD_MD)

        # ── Content: browser preview (left) + patrol log (right) ──
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        # Browser preview (left)
        preview_frame = T.card_frame(content)
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, T.PAD_SM))

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

        # Patrol log (right)
        log_frame = T.card_frame(content)
        log_frame.grid(row=0, column=1, sticky="nsew")

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

    # ── Refresh ──

    def refresh(self):
        if hasattr(self.app, "_patrol_log_buffer") and self.app._patrol_log_buffer:
            for level, message in self.app._patrol_log_buffer:
                self.append_patrol_log(level, message)
            self.app._patrol_log_buffer.clear()

        if self.app.scheduler.is_running:
            self._patrol_indicator.configure(text="海巡中...")
            self._start_preview_polling()
        else:
            self._patrol_indicator.configure(text="")
            self._stop_preview_polling()

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
                # Size to fit the available label area
                lw = self._preview_label.winfo_width()
                lh = self._preview_label.winfo_height()
                max_w = max(lw - 16, 320)
                max_h = max(lh - 16, 240)

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
