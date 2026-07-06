"""Audit log viewer frame."""

import csv
import json
import customtkinter as ctk
from tkinter import filedialog

from src.gui import theme as T
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class LogsFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title
        header = T.page_header(self, "稽核日誌")
        header.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        # Controls
        ctrl_frame = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=T.RADIUS_MD,
                                  border_width=1, border_color=T.BORDER_SUBTLE)
        ctrl_frame.grid(row=1, column=0, sticky="ew", pady=(0, T.PAD_SM))

        ctrl_inner = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        ctrl_inner.pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM)

        ctk.CTkLabel(ctrl_inner, text="篩選:", text_color=T.TEXT_SECONDARY,
                     font=T.font_small()).pack(side="left")
        self._filter_var = ctk.StringVar(value="")
        self._filter_entry = ctk.CTkEntry(
            ctrl_inner, textvariable=self._filter_var, width=200,
            placeholder_text="輸入動作關鍵字...",
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._filter_entry.pack(side="left", padx=T.PAD_XS)

        ctk.CTkButton(
            ctrl_inner, text="搜尋", width=60,
            **T.BTN_GHOST_ACCENT,
            command=self.refresh,
        ).pack(side="left", padx=T.PAD_XS)

        self._clear_filter_btn = ctk.CTkButton(
            ctrl_inner, text="清除篩選", width=80, height=28,
            **T.BTN_GHOST,
            command=self._clear_filter,
        )
        self._clear_filter_btn.pack(side="left", padx=T.PAD_XS)

        ctk.CTkButton(
            ctrl_inner, text="匯出稽核日誌", width=110,
            **T.BTN_GHOST,
            command=self._export_audit_csv,
        ).pack(side="right")

        ctk.CTkButton(
            ctrl_inner, text="匯出回覆紀錄", width=110,
            **T.BTN_GHOST,
            command=self._export_reply_csv,
        ).pack(side="right", padx=(0, T.PAD_SM))

        # Log table
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(1, weight=1)

        # Header row
        headers = ["時間", "動作", "詳細資訊"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(
                self._scroll_frame, text=h,
                font=T.font_badge(), text_color=T.TEXT_TERTIARY,
            ).grid(row=0, column=i, sticky="w", padx=T.PAD_SM, pady=T.PAD_XS)

        self._log_widgets: list[list] = []
        self._all_logs = []
        self._page_size = 50
        self._displayed = 0

    def refresh(self):
        for row_widgets in self._log_widgets:
            for w in row_widgets:
                w.destroy()
        self._log_widgets.clear()
        self._displayed = 0

        action_filter = self._filter_var.get().strip() or None
        self._all_logs = self.app.repo.get_audit_logs(limit=500, action_filter=action_filter)

        if not self._all_logs:
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text="尚無稽核日誌\n\n系統操作（啟動海巡、核准回覆、刪除等）都會自動記錄在這裡",
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
                justify="center",
            )
            empty.grid(row=1, column=0, columnspan=3, pady=40)
            self._log_widgets.append([empty])
            return

        self._load_more()

    def _load_more(self):
        """Render the next page of log entries."""
        end = min(self._displayed + self._page_size, len(self._all_logs))
        for i in range(self._displayed, end):
            log = self._all_logs[i]
            row_num = i + 1
            self._render_log_row(log, row_num)
        self._displayed = end

        # Remove old "load more" button if any
        if hasattr(self, "_load_more_btn") and self._load_more_btn is not None:
            self._load_more_btn.destroy()
            self._load_more_btn = None

        if self._displayed < len(self._all_logs):
            remaining = len(self._all_logs) - self._displayed
            self._load_more_btn = ctk.CTkButton(
                self._scroll_frame,
                text=f"載入更多 ({remaining} 筆)",
                width=200, height=32,
                **T.BTN_GHOST_ACCENT,
                command=self._load_more,
            )
            self._load_more_btn.grid(row=self._displayed + 1, column=0, columnspan=3, pady=T.PAD_MD)
        else:
            self._load_more_btn = None

    def _render_log_row(self, log, row_num: int):
        widgets = []

        ts_label = ctk.CTkLabel(
            self._scroll_frame, text=(log.timestamp or "")[:19],
            font=T.font_small(), text_color=T.TEXT_TERTIARY,
        )
        ts_label.grid(row=row_num, column=0, sticky="nw", padx=T.PAD_SM, pady=1)
        widgets.append(ts_label)

        action_label = ctk.CTkLabel(
            self._scroll_frame, text=log.action,
            font=T.font_badge(), text_color=T.GOLD_500,
        )
        action_label.grid(row=row_num, column=1, sticky="nw", padx=T.PAD_SM, pady=1)
        widgets.append(action_label)

        raw_details = log.details or ""
        details_preview = self._format_details(raw_details, truncate=True)
        details_full = self._format_details(raw_details, truncate=False)
        is_long = len(raw_details) > 80

        details_label = ctk.CTkLabel(
            self._scroll_frame, text=details_preview,
            font=T.font_caption(), text_color=T.TEXT_TERTIARY,
            wraplength=500, justify="left",
            cursor="hand2" if is_long else "",
        )
        details_label.grid(row=row_num, column=2, sticky="nw", padx=T.PAD_SM, pady=1)
        if is_long:
            details_label._expanded = False
            details_label.bind("<Button-1>", lambda e, lbl=details_label, short=details_preview, full=details_full: self._toggle_detail(lbl, short, full))
        widgets.append(details_label)

        self._log_widgets.append(widgets)

    def _clear_filter(self):
        self._filter_var.set("")
        self.refresh()

    @staticmethod
    def _format_details(raw: str, truncate: bool = True) -> str:
        if not raw:
            return ""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                parts = [f"{k}: {v}" for k, v in data.items()]
                text = ", ".join(parts)
            else:
                text = str(data)
        except (json.JSONDecodeError, TypeError):
            text = raw
        if truncate and len(text) > 80:
            return text[:80] + "..."
        return text

    @staticmethod
    def _toggle_detail(label, short_text: str, full_text: str):
        if label._expanded:
            label.configure(text=short_text)
            label._expanded = False
        else:
            label.configure(text=full_text)
            label._expanded = True

    def _export_audit_csv(self):
        logs = self.app.repo.get_audit_logs(limit=10000)
        if not logs:
            show_toast(self, "沒有稽核日誌可匯出", "info")
            return

        file_path = filedialog.asksaveasfilename(
            title="匯出稽核日誌",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="audit_log.csv",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "時間", "動作", "詳細資訊"])
                for log in logs:
                    writer.writerow([log.id, log.timestamp, log.action, log.details])
        except OSError as e:
            show_toast(self, f"匯出失敗: {e}", "error", duration_ms=4000)
            return

        show_toast(self, f"已匯出 {len(logs)} 筆稽核日誌", "success")

    def _export_reply_csv(self):
        logs = self.app.repo.get_all_reply_logs(limit=10000)
        if not logs:
            show_toast(self, "沒有回覆紀錄可匯出", "info")
            return

        file_path = filedialog.asksaveasfilename(
            title="匯出回覆紀錄",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="reply_log.csv",
        )
        if not file_path:
            return

        headers = [
            "ID", "平台", "貼文作者", "貼文內容", "貼文連結",
            "回覆內容", "文案編號", "文案分類", "回覆模式", "狀態",
            "錯誤訊息", "重試次數", "送出時間", "建立時間",
        ]
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in logs:
                    writer.writerow([
                        r["id"], r["platform"], r.get("author_username", ""),
                        r.get("post_content", ""), r.get("post_url", ""),
                        r["reply_content"], r.get("template_code", ""),
                        r.get("category", ""), r["reply_mode"], r["status"],
                        r.get("error_message", ""), r["retry_count"],
                        r.get("sent_at", ""), r["created_at"],
                    ])
        except OSError as e:
            show_toast(self, f"匯出失敗: {e}", "error", duration_ms=4000)
            return

        show_toast(self, f"已匯出 {len(logs)} 筆回覆紀錄", "success")
