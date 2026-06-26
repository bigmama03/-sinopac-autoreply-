"""Audit log viewer frame."""

import csv
import json
import customtkinter as ctk
from tkinter import filedialog

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
        ctk.CTkLabel(
            self, text="稽核日誌",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Controls
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(ctrl_frame, text="篩選:").pack(side="left")
        self._filter_var = ctk.StringVar(value="")
        self._filter_entry = ctk.CTkEntry(
            ctrl_frame, textvariable=self._filter_var, width=200,
            placeholder_text="輸入動作關鍵字...",
        )
        self._filter_entry.pack(side="left", padx=5)

        ctk.CTkButton(
            ctrl_frame, text="搜尋", width=60,
            command=self.refresh,
        ).pack(side="left", padx=5)

        self._clear_filter_btn = ctk.CTkButton(
            ctrl_frame, text="清除篩選", width=80, height=28,
            fg_color="transparent", border_width=1,
            command=self._clear_filter,
        )
        self._clear_filter_btn.pack(side="left", padx=5)

        ctk.CTkButton(
            ctrl_frame, text="匯出稽核日誌", width=110,
            fg_color="transparent", border_width=1,
            command=self._export_audit_csv,
        ).pack(side="right")

        ctk.CTkButton(
            ctrl_frame, text="匯出回覆紀錄", width=110,
            fg_color="transparent", border_width=1,
            command=self._export_reply_csv,
        ).pack(side="right", padx=(0, 8))

        # Log table (scrollable)
        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.grid(row=2, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(1, weight=1)

        # Header row
        headers = ["時間", "動作", "詳細資訊"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(
                self._scroll_frame, text=h,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=i, sticky="w", padx=8, pady=4)

        self._log_widgets: list[list] = []

    def refresh(self):
        # Clear old rows
        for row_widgets in self._log_widgets:
            for w in row_widgets:
                w.destroy()
        self._log_widgets.clear()

        action_filter = self._filter_var.get().strip() or None
        logs = self.app.repo.get_audit_logs(limit=500, action_filter=action_filter)

        if not logs:
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text="尚無稽核日誌\n\n系統操作（啟動海巡、核准回覆、刪除等）都會自動記錄在這裡",
                text_color="gray50", font=ctk.CTkFont(size=14),
                justify="center",
            )
            empty.grid(row=1, column=0, columnspan=3, pady=40)
            self._log_widgets.append([empty])
            return

        for i, log in enumerate(logs):
            row_num = i + 1  # Skip header row
            widgets = []

            ts_label = ctk.CTkLabel(
                self._scroll_frame, text=(log.timestamp or "")[:19],
                font=ctk.CTkFont(size=11), text_color="gray60",
            )
            ts_label.grid(row=row_num, column=0, sticky="nw", padx=8, pady=1)
            widgets.append(ts_label)

            action_label = ctk.CTkLabel(
                self._scroll_frame, text=log.action,
                font=ctk.CTkFont(size=11, weight="bold"),
            )
            action_label.grid(row=row_num, column=1, sticky="nw", padx=8, pady=1)
            widgets.append(action_label)

            # Expandable details: show truncated by default, click to expand
            raw_details = log.details or ""
            details_preview = self._format_details(raw_details, truncate=True)
            details_full = self._format_details(raw_details, truncate=False)
            is_long = len(raw_details) > 80

            details_label = ctk.CTkLabel(
                self._scroll_frame, text=details_preview,
                font=ctk.CTkFont(size=10), text_color="gray50",
                wraplength=500, justify="left",
                cursor="hand2" if is_long else "",
            )
            details_label.grid(row=row_num, column=2, sticky="nw", padx=8, pady=1)
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
        """Format JSON details for display."""
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
