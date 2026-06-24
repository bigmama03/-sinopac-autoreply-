"""Keyword management frame — create, view, delete."""

import csv

import customtkinter as ctk
from tkinter import filedialog

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class KeywordsFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._keyword_widgets: list[ctk.CTkBaseClass] = []
        self._all_keywords = []
        self._category_values = ["開戶", "手續費", "投資", "一般"]

        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_row,
            text="關鍵字管理",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self._count_label = ctk.CTkLabel(
            title_row,
            text="共 0 個關鍵字",
            text_color="gray60",
        )
        self._count_label.grid(row=0, column=1, sticky="e")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkButton(btn_row, text="匯入 CSV/Excel", command=self._import_file, width=150).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="下載匯入範本",
            command=self._download_template,
            width=130,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
        ).pack(side="left", padx=(0, 8))

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        filter_row.grid_columnconfigure(2, weight=1)

        self._search_entry = ctk.CTkEntry(
            filter_row,
            width=250,
            placeholder_text="搜尋關鍵字...",
        )
        self._search_entry.grid(row=0, column=0, padx=(0, 8), sticky="w")
        self._search_entry.bind("<KeyRelease>", lambda _event: self._apply_filter())

        self._filter_category_var = ctk.StringVar(value="全部分類")
        self._filter_category_menu = ctk.CTkOptionMenu(
            filter_row,
            values=["全部分類", "開戶", "手續費", "投資", "一般"],
            variable=self._filter_category_var,
            width=140,
            command=lambda _value: self._apply_filter(),
        )
        self._filter_category_menu.grid(row=0, column=1, sticky="w")

        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.grid(row=3, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

    def refresh(self):
        self._all_keywords = self.app.repo.get_all_keywords(active_only=True)
        self._sync_keyword_matcher(self._all_keywords)
        self._apply_filter()

    def _import_file(self):
        file_path = filedialog.askopenfilename(
            title="選擇關鍵字檔案",
            filetypes=[
                ("CSV / Excel", "*.csv *.xlsx"),
                ("CSV", "*.csv"),
                ("Excel", "*.xlsx"),
            ],
        )
        if not file_path:
            return
        from src.utils.csv_parser import parse_keyword_file
        entries, error = parse_keyword_file(file_path)
        if error:
            self._show_message("匯入失敗", error, "cancel")
            return
        if not entries:
            self._show_message("匯入失敗", "檔案中沒有有效的關鍵字資料", "warning")
            return

        imported = 0
        for entry in entries:
            self.app.repo.upsert_keyword(entry["keyword"], entry["category"], entry["weight"])
            imported += 1
        self.app.repo.log_audit("KEYWORDS_IMPORTED", {"count": imported, "file": file_path})
        self._show_message("匯入完成", f"成功匯入 {imported} 個關鍵字", "check")
        self.refresh()

    def _download_template(self):
        file_path = filedialog.asksaveasfilename(
            title="儲存關鍵字匯入範本",
            defaultextension=".csv",
            initialfile="關鍵字匯入範本.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["關鍵字", "分類", "權重"])
                writer.writerow(["證券開戶", "開戶", "5.0"])
                writer.writerow(["手續費優惠", "手續費", "3.5"])
                writer.writerow(["怎麼買股票", "投資", "3.0"])
            self._show_message("下載完成", f"範本已儲存至:\n{file_path}", "check")
        except Exception as e:
            self._show_message("儲存失敗", str(e), "cancel")

    def _delete_keyword(self, keyword_id: int):
        keywords = self.app.repo.get_all_keywords(active_only=True)
        keyword_obj = next((item for item in keywords if item.id == keyword_id), None)
        if keyword_obj is None:
            self._show_message("刪除失敗", "找不到要刪除的關鍵字", "warning")
            self.refresh()
            return

        self.app.repo.delete_keyword(keyword_id)
        self.app.repo.log_audit("KEYWORD_DELETED", {
            "keyword_id": keyword_id,
            "keyword": keyword_obj.keyword if keyword_obj else None,
        })
        self.refresh()

    def _create_keyword_card(self, keyword, index: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._scroll_frame)
        card.grid(row=index, column=0, sticky="ew", pady=3, padx=2)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=keyword.keyword,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=10)

        ctk.CTkLabel(
            card,
            text=keyword.category or "一般",
            font=ctk.CTkFont(size=11),
            text_color=("blue", "#64B5F6"),
        ).grid(row=0, column=1, sticky="w", padx=(0, 8), pady=10)

        ctk.CTkLabel(
            card,
            text=f"weight {keyword.weight:.1f}",
            text_color="gray60",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=2, sticky="w", padx=(0, 12), pady=10)

        ctk.CTkButton(
            card,
            text="刪除",
            width=60,
            height=28,
            fg_color="transparent",
            border_width=1,
            text_color=("red", "#EF5350"),
            hover_color=("gray90", "gray20"),
            command=lambda kid=keyword.id: self._delete_keyword(kid),
        ).grid(row=0, column=3, sticky="e", padx=12, pady=8)

        return card

    def _sync_keyword_matcher(self, keywords):
        if hasattr(self.app, "keyword_matcher"):
            self.app.keyword_matcher.keywords = keywords

    def _apply_filter(self):
        search_text = self._search_entry.get().strip().lower()
        category = self._filter_category_var.get()

        filtered = [
            keyword for keyword in self._all_keywords
            if search_text in keyword.keyword.lower()
            and (category == "全部分類" or keyword.category == category)
        ]

        total = len(self._all_keywords)
        if len(filtered) == total:
            self._count_label.configure(text=f"共 {total} 個關鍵字")
        else:
            self._count_label.configure(text=f"顯示 {len(filtered)} / 共 {total} 個關鍵字")

        for widget in self._keyword_widgets:
            widget.destroy()
        self._keyword_widgets.clear()

        if not filtered:
            empty_text = "尚未建立關鍵字\n請點擊「匯入 CSV/Excel」按鈕" if total == 0 else "沒有符合條件的關鍵字"
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text=empty_text,
                text_color="gray50",
                font=ctk.CTkFont(size=14),
            )
            empty.grid(row=0, column=0, pady=40)
            self._keyword_widgets.append(empty)
            return

        for index, keyword in enumerate(filtered):
            card = self._create_keyword_card(keyword, index)
            self._keyword_widgets.append(card)

    def _show_message(self, title: str, message: str, icon: str = "info"):
        if CTkMessagebox:
            CTkMessagebox(title=title, message=message, icon=icon)
