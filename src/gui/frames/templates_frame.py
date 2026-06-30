"""Template management frame — import, view, delete."""

import csv
import customtkinter as ctk
from tkinter import filedialog

from src.gui import theme as T
from src.gui.widgets.toast import show_toast

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:
    CTkMessagebox = None


class TemplatesFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title row
        title_row = T.page_header(self, "文案管理")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD_MD))

        self._count_label = ctk.CTkLabel(
            title_row, text="共 0 則文案",
            text_color=T.TEXT_TERTIARY, font=T.font_small(),
        )
        self._count_label.pack(side="left", padx=T.PAD_LG)

        # Buttons row
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

        ctk.CTkButton(
            btn_row, text="清除全部文案", width=130,
            **T.BTN_GHOST_DANGER,
            command=self._clear_all,
        ).pack(side="left", padx=(0, T.PAD_SM))

        # Template list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=T.BG_APP,
            scrollbar_fg_color=T.BG_APP,
            scrollbar_button_color=T.NAVY_600,
            scrollbar_button_hover_color=T.NAVY_500,
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._template_widgets: list[ctk.CTkFrame] = []

    def refresh(self):
        templates = self.app.template_manager.get_all()
        self._count_label.configure(text=f"共 {len(templates)} 則文案")

        for w in self._template_widgets:
            w.destroy()
        self._template_widgets.clear()

        if not templates:
            empty = ctk.CTkLabel(
                self._scroll_frame, text="尚未匯入文案\n請點擊「匯入 CSV/Excel」按鈕",
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
            )
            empty.grid(row=0, column=0, pady=40)
            self._template_widgets.append(empty)
            return

        for i, t in enumerate(templates):
            card = self._create_template_card(t, i)
            self._template_widgets.append(card)

    def _create_template_card(self, template, index: int) -> ctk.CTkFrame:
        card = T.card_frame(self._scroll_frame,
                            row=index, column=0, sticky="ew",
                            pady=T.PAD_XS, padx=2)
        card.grid_columnconfigure(1, weight=1)

        # Header: code + category + platforms
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew",
                    padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_XS))

        ctk.CTkLabel(
            header, text=template.template_code,
            font=T.font_card_title(), text_color=T.TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            header, text=f"[{template.category}]",
            font=T.font_small(), text_color=T.GOLD_500,
        ).pack(side="left", padx=T.PAD_SM)

        ctk.CTkLabel(
            header, text=template.platforms,
            font=T.font_caption(), text_color=T.TEXT_TERTIARY,
        ).pack(side="left")

        # Content preview
        preview = template.content[:120] + ("..." if len(template.content) > 120 else "")
        ctk.CTkLabel(
            card, text=preview, wraplength=700, justify="left",
            font=T.font_body(), text_color=T.TEXT_SECONDARY,
        ).grid(row=1, column=0, columnspan=2, sticky="w",
               padx=T.PAD_MD, pady=(0, T.PAD_SM))

        # Delete button
        ctk.CTkButton(
            card, text="刪除", width=60, height=28,
            **T.BTN_GHOST_DANGER,
            command=lambda tid=template.id: self._delete_template(tid),
        ).grid(row=0, column=1, sticky="e", padx=T.PAD_MD, pady=T.PAD_SM)

        return card

    def _download_template(self):
        file_path = filedialog.asksaveasfilename(
            title="儲存匯入範本",
            defaultextension=".csv",
            initialfile="文案匯入範本.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["文案編號", "分類", "文案內容", "適用平台"])
                writer.writerow(["TPL-001", "開戶推廣", "立即開戶享手續費優惠！新戶限定好禮等你拿", "Threads, Facebook"])
                writer.writerow(["TPL-002", "活動宣傳", "年終感恩回饋季，交易滿額抽大獎！", "Threads, Instagram"])
            self._show_message("下載完成", f"範本已儲存至:\n{file_path}", "check")
        except Exception as e:
            self._show_message("儲存失敗", str(e), "cancel")

    def _import_file(self):
        file_path = filedialog.askopenfilename(
            title="選擇文案檔案",
            filetypes=[
                ("CSV / Excel", "*.csv *.xlsx"),
                ("CSV", "*.csv"),
                ("Excel", "*.xlsx"),
            ],
        )
        if not file_path:
            return

        imported, skipped, error = self.app.template_manager.import_from_file(file_path)
        if error:
            show_toast(self, f"匯入失敗: {error[:60]}", "error", duration_ms=4000)
        else:
            msg = f"成功匯入 {imported} 則文案"
            if skipped > 0:
                msg += f"，跳過 {skipped} 則重複"
            show_toast(self, msg, "success")

        self.refresh()

    def _delete_template(self, template_id: int):
        if CTkMessagebox:
            msg = CTkMessagebox(
                title="確認刪除",
                message="確定要刪除這則文案嗎？",
                icon="warning",
                option_1="取消", option_2="刪除",
            )
            if msg.get() != "刪除":
                return
        self.app.template_manager.delete(template_id)
        show_toast(self, "文案已刪除", "success")
        self.refresh()

    def _clear_all(self):
        count = self.app.template_manager.count()
        if count == 0:
            return
        if CTkMessagebox:
            msg = CTkMessagebox(
                title="確認清除",
                message=f"確定要清除全部 {count} 則文案嗎？",
                icon="warning",
                option_1="取消", option_2="確定清除",
            )
            if msg.get() != "確定清除":
                return
        self.app.template_manager.clear_all()
        show_toast(self, "全部文案已清除", "success")
        self.refresh()

    def _show_message(self, title: str, message: str, icon: str = "info"):
        if CTkMessagebox:
            CTkMessagebox(title=title, message=message, icon=icon)
