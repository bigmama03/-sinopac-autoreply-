"""Keyword management frame — create, view, delete."""

import csv

import customtkinter as ctk
from tkinter import filedialog

from src.gui import theme as T
from src.gui.widgets.toast import show_toast

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
        self._search_debounce_id = None

        title_row = T.page_header(self, "關鍵字管理")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._count_label = ctk.CTkLabel(
            title_row, text="共 0 個關鍵字",
            text_color=T.TEXT_TERTIARY, font=T.font_small(),
        )
        self._count_label.pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=(0, T.PAD_MD))

        ctk.CTkButton(
            btn_row, text="匯入 CSV/Excel", width=150,
            **T.BTN_PRIMARY,
            command=self._import_file,
        ).pack(side="left", padx=(0, T.PAD_SM))

        ctk.CTkButton(
            btn_row, text="下載匯入範本", width=130,
            **T.BTN_GHOST,
            command=self._download_template,
        ).pack(side="left", padx=(0, T.PAD_SM))

        # Filter row
        filter_row = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=T.RADIUS_MD,
                                  border_width=1, border_color=T.BORDER_SUBTLE)
        filter_row.grid(row=2, column=0, sticky="ew", pady=(0, T.PAD_SM))

        filter_inner = ctk.CTkFrame(filter_row, fg_color="transparent")
        filter_inner.pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM)

        self._search_entry = ctk.CTkEntry(
            filter_inner, width=250,
            placeholder_text="搜尋關鍵字...",
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._search_entry.pack(side="left", padx=(0, T.PAD_SM))
        self._search_entry.bind("<KeyRelease>", lambda _event: self._debounced_filter())

        self._filter_category_var = ctk.StringVar(value="全部分類")
        self._filter_category_menu = ctk.CTkOptionMenu(
            filter_inner,
            values=["全部分類", "開戶", "手續費", "投資", "一般"],
            variable=self._filter_category_var, width=130,
            command=lambda _value: self._apply_filter(),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        self._filter_category_menu.pack(side="left", padx=(0, T.PAD_SM))

        self._sort_var = ctk.StringVar(value="權重高→低")
        self._sort_menu = ctk.CTkOptionMenu(
            filter_inner,
            values=["權重高→低", "權重低→高", "名稱 A→Z", "名稱 Z→A"],
            variable=self._sort_var, width=130,
            command=lambda _value: self._apply_filter(),
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        )
        self._sort_menu.pack(side="left")

        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
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
        show_toast(self, f"成功匯入 {imported} 個關鍵字", "success")
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
        show_toast(self, f"已刪除關鍵字「{keyword_obj.keyword}」", "success")
        self.refresh()

    def _create_keyword_card(self, keyword, index: int) -> ctk.CTkFrame:
        card = T.card_frame(self._scroll_frame,
                            row=index, column=0, sticky="ew",
                            pady=T.PAD_XS, padx=2)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=keyword.keyword,
            font=T.font_card_title(), text_color=T.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(T.PAD_MD, T.PAD_SM), pady=T.PAD_MD)

        ctk.CTkLabel(
            card, text=keyword.category or "一般",
            font=T.font_small(), text_color=T.GOLD_500,
        ).grid(row=0, column=1, sticky="w", padx=(0, T.PAD_SM), pady=T.PAD_MD)

        weight_label = ctk.CTkLabel(
            card, text=f"權重 {keyword.weight:.1f}",
            text_color=T.TEXT_TERTIARY, font=T.font_small(),
        )
        weight_label.grid(row=0, column=2, sticky="w", padx=(0, T.PAD_MD), pady=T.PAD_MD)
        weight_label.bind("<Enter>", lambda e, w=weight_label: w.configure(
            text=f"權重 {keyword.weight:.1f}（越高越優先匹配）"
        ))
        weight_label.bind("<Leave>", lambda e, w=weight_label, kw=keyword: w.configure(
            text=f"權重 {kw.weight:.1f}"
        ))

        ctk.CTkButton(
            card, text="刪除", width=60, height=28,
            **T.BTN_GHOST_DANGER,
            command=lambda kid=keyword.id: self._delete_keyword(kid),
        ).grid(row=0, column=3, sticky="e", padx=T.PAD_MD, pady=T.PAD_SM)

        return card

    def _sync_keyword_matcher(self, keywords):
        if hasattr(self.app, "keyword_matcher"):
            self.app.keyword_matcher.keywords = keywords

    def _debounced_filter(self):
        """Schedule _apply_filter after 300ms, cancelling any pending call."""
        if self._search_debounce_id is not None:
            self.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.after(300, self._apply_filter)

    def _apply_filter(self):
        self._search_debounce_id = None
        search_text = self._search_entry.get().strip().lower()
        category = self._filter_category_var.get()

        filtered = [
            keyword for keyword in self._all_keywords
            if search_text in keyword.keyword.lower()
            and (category == "全部分類" or keyword.category == category)
        ]

        sort_mode = self._sort_var.get()
        if sort_mode == "權重高→低":
            filtered.sort(key=lambda k: (-k.weight, k.keyword.lower()))
        elif sort_mode == "權重低→高":
            filtered.sort(key=lambda k: (k.weight, k.keyword.lower()))
        elif sort_mode == "名稱 A→Z":
            filtered.sort(key=lambda k: (k.keyword.lower(), -k.weight))
        elif sort_mode == "名稱 Z→A":
            filtered.sort(key=lambda k: k.keyword.lower(), reverse=True)

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
                self._scroll_frame, text=empty_text,
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
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
