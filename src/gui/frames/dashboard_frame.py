"""Dashboard overview frame."""

import json
import platform as _platform
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

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

        for platform_name in all_platforms:
            if platform_name in configured_platforms:
                value = tk.BooleanVar(value=True)
                self._vars[platform_name] = value
                ctk.CTkCheckBox(
                    container,
                    text=platform_name.capitalize(),
                    variable=value,
                    onvalue=True, offvalue=False,
                    text_color=T.TEXT_PRIMARY,
                    fg_color=T.GOLD_500,
                    hover_color=T.GOLD_400,
                    checkmark_color=T.TEXT_INVERSE,
                ).pack(anchor="w", pady=T.PAD_XS)
            else:
                ctk.CTkLabel(
                    container,
                    text=f"{platform_name.capitalize()} (未設定)",
                    text_color=T.TEXT_TERTIARY,
                ).pack(anchor="w", pady=T.PAD_XS)

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(T.PAD_LG, 0))

        ctk.CTkButton(
            btn_row, text="啟動", width=90,
            **T.BTN_SUCCESS,
            command=self._confirm,
        ).pack(side="right", padx=(T.PAD_SM, 0))
        ctk.CTkButton(
            btn_row, text="取消", width=90,
            **T.BTN_GHOST,
            command=self._cancel,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        self._center_on_parent(parent)
        self.grab_set()

    def _center_on_parent(self, parent):
        parent.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        if parent.winfo_ismapped() and parent_width > 1 and parent_height > 1:
            x = parent.winfo_rootx() + max((parent_width - width) // 2, 0)
            y = parent.winfo_rooty() + max((parent_height - height) // 2, 0)
        else:
            x = (self.winfo_screenwidth() - width) // 2
            y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _confirm(self):
        self.result = [
            platform_name for platform_name, value in self._vars.items()
            if value.get()
        ]
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class DashboardFrame(ctk.CTkFrame):
    _PERIOD_MAP = {"日": "day", "週": "week", "月": "month"}
    _PLATFORM_MAP = {"全部": None, "Threads": "threads", "Facebook": "facebook", "Instagram": "instagram"}
    _RANGE_PRESETS = {"近7天": 7, "近14天": 14, "近30天": 30, "近90天": 90}
    _PATROL_PLATFORMS = ["threads", "facebook", "instagram"]
    _PATROL_PLATFORM_LABELS = {
        "threads": "Threads",
        "facebook": "Facebook",
        "instagram": "Instagram",
    }
    _COMING_SOON_PLATS = {"facebook", "instagram"}

    def __init__(self, parent, app):
        self._configure_matplotlib()
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._destroyed = False

        # Outer layout: scrollable canvas + scrollbar
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._scroll_canvas = tk.Canvas(
            self, bg=T.BG_APP, highlightthickness=0, bd=0,
        )
        self._scrollbar = ctk.CTkScrollbar(self, command=self._scroll_canvas.yview,
                                           fg_color=T.BG_APP,
                                           button_color=T.NAVY_600,
                                           button_hover_color=T.NAVY_500)

        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

        self._inner = ctk.CTkFrame(self._scroll_canvas, fg_color="transparent")
        self._canvas_window_id = self._scroll_canvas.create_window(
            (0, 0), window=self._inner, anchor="nw",
        )

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self._scroll_canvas.bind("<Enter>", self._bind_mousewheel)
        self._scroll_canvas.bind("<Leave>", self._unbind_mousewheel)

        self._inner.grid_columnconfigure((0, 1, 2), weight=1)

        # ── Row 0: Title + patrol controls ──
        header = ctk.CTkFrame(self._inner, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, T.PAD_LG))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="總覽儀表板",
            font=T.font_title(), text_color=T.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        btn_row = ctk.CTkFrame(header, fg_color="transparent")
        btn_row.grid(row=0, column=2, sticky="e")

        self._sending_btn = ctk.CTkButton(
            btn_row, text="暫停發送", width=100, height=34,
            **T.BTN_WARNING,
            command=self._toggle_sending,
        )
        self._sending_btn.pack(side="left", padx=(0, T.PAD_SM))
        self._sending_btn.pack_forget()

        self._patrol_btn = ctk.CTkButton(
            btn_row, text="啟動海巡", width=120, height=34,
            **T.BTN_SUCCESS,
            command=self._toggle_patrol,
        )
        self._patrol_btn.pack(side="left")

        self._patrol_status = ctk.CTkLabel(
            header, text="未啟動", text_color=T.TEXT_TERTIARY,
            font=T.font_small(),
        )
        self._patrol_status.grid(row=0, column=1, sticky="e", padx=T.PAD_MD)

        self._live_counter = ctk.CTkLabel(
            header, text="", text_color=T.TEXT_TERTIARY,
            font=T.font_caption(),
        )
        self._live_counter.grid(row=1, column=0, columnspan=3, sticky="e", padx=T.PAD_MD)

        self._live_counter_after_id = None

        # ── Row 1: Stat cards ──
        self._cards: dict[str, ctk.CTkLabel] = {}
        card_configs = [
            ("pending_count", "待審核貼文", "0", "monitor", T.WARNING),
            ("replied_today", "今日已回覆", "0", "replies", T.TEAL_500),
            ("template_count", "文案數量", "0", "templates", T.GOLD_500),
        ]
        for i, (key, title, default, target, accent) in enumerate(card_configs):
            card = self._create_stat_card(title, default, target, accent)
            card["frame"].grid(row=1, column=i, padx=T.PAD_SM, pady=T.PAD_SM, sticky="nsew")
            self._cards[key] = card["value_label"]

        # ── Row 2-3: Platform status + Mode ──
        T.section_title(self._inner, "平台連線狀態", row=2)

        status_row = T.card_frame(self._inner,
                                  row=3, column=0, columnspan=3,
                                  sticky="ew", padx=T.PAD_XS, pady=(0, T.PAD_XS))
        status_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._platform_status: dict[str, ctk.CTkLabel] = {}
        platforms = [
            ("threads", "Threads", T.PLATFORM_THREADS),
            ("facebook", "Facebook", T.PLATFORM_FACEBOOK),
            ("instagram", "Instagram", T.PLATFORM_INSTAGRAM),
        ]
        for i, (key, label, accent) in enumerate(platforms):
            coming = key in self._COMING_SOON_PLATS
            cell = ctk.CTkFrame(status_row, fg_color="transparent")
            cell.grid(row=0, column=i, padx=T.PAD_MD, pady=T.PAD_MD, sticky="nsew")

            # Platform indicator dot + name
            name_frame = ctk.CTkFrame(cell, fg_color="transparent")
            name_frame.pack(anchor="w")

            title_text = f"{label}{'  (即將推出)' if coming else ''}"
            title_color = T.TEXT_TERTIARY if coming else accent
            ctk.CTkLabel(
                name_frame, text=title_text,
                font=T.font_card_title(), text_color=title_color,
            ).pack(side="left")

            status_text = "即將推出" if coming else "未設定"
            status_label = ctk.CTkLabel(
                cell, text=status_text,
                text_color=T.TEXT_TERTIARY, font=T.font_small(),
            )
            status_label.pack(anchor="w", pady=(T.PAD_XS, 0))
            self._platform_status[key] = status_label

        # Mode cell
        mode_cell = ctk.CTkFrame(status_row, fg_color="transparent")
        mode_cell.grid(row=0, column=3, padx=T.PAD_MD, pady=T.PAD_MD, sticky="nsew")
        ctk.CTkLabel(
            mode_cell, text="目前模式",
            font=T.font_card_title(), text_color=T.TEXT_SECONDARY,
        ).pack(anchor="w")
        self._mode_label = ctk.CTkLabel(
            mode_cell, text="半自動",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=T.TEAL_500,
        )
        self._mode_label.pack(anchor="w", pady=(T.PAD_XS, 0))

        # ── Row 4-5: Chart section ──
        T.section_title(self._inner, "回覆趨勢", row=4)

        chart_card = T.card_frame(self._inner,
                                  row=5, column=0, columnspan=3,
                                  sticky="ew", padx=T.PAD_XS, pady=(0, T.PAD_XS))
        chart_card.grid_columnconfigure(0, weight=1)

        row0 = ctk.CTkFrame(chart_card, fg_color="transparent")
        row0.grid(row=0, column=0, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_MD, 0))
        row0.grid_columnconfigure(1, weight=1)

        controls = ctk.CTkFrame(row0, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="e")

        self._period_seg = ctk.CTkSegmentedButton(
            controls, values=["日", "週", "月"],
            command=self._on_period_change,
            fg_color=T.NAVY_600, selected_color=T.GOLD_500,
            selected_hover_color=T.GOLD_400,
            unselected_color=T.NAVY_700,
            unselected_hover_color=T.NAVY_500,
            text_color=T.TEXT_PRIMARY,
            text_color_disabled=T.TEXT_TERTIARY,
        )
        self._period_seg.set("日")
        self._period_seg.pack(side="left", padx=(0, T.PAD_MD))

        self._chart_platform_var = ctk.StringVar(value="全部")
        ctk.CTkOptionMenu(
            controls, values=["全部", "Threads", "Facebook", "Instagram"],
            variable=self._chart_platform_var,
            command=self._on_chart_filter_change,
            width=120,
            fg_color=T.NAVY_700, button_color=T.NAVY_600,
            button_hover_color=T.NAVY_500,
            dropdown_fg_color=T.BG_ELEVATED,
            text_color=T.TEXT_PRIMARY,
        ).pack(side="left")

        # Date range controls
        row1 = ctk.CTkFrame(chart_card, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", padx=T.PAD_MD, pady=(T.PAD_SM, T.PAD_SM))

        today = date.today()
        default_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
        default_end = today.strftime("%Y-%m-%d")

        ctk.CTkLabel(row1, text="起始", font=T.font_small(),
                     text_color=T.TEXT_SECONDARY).pack(side="left")
        self._start_date_var = ctk.StringVar(value=default_start)
        self._start_entry = ctk.CTkEntry(
            row1, textvariable=self._start_date_var, width=100,
            placeholder_text="YYYY-MM-DD",
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._start_entry.pack(side="left", padx=(T.PAD_XS, T.PAD_SM))

        ctk.CTkLabel(row1, text="結束", font=T.font_small(),
                     text_color=T.TEXT_SECONDARY).pack(side="left")
        self._end_date_var = ctk.StringVar(value=default_end)
        self._end_entry = ctk.CTkEntry(
            row1, textvariable=self._end_date_var, width=100,
            placeholder_text="YYYY-MM-DD",
            fg_color=T.BG_INPUT, border_color=T.BORDER_DEFAULT,
            text_color=T.TEXT_PRIMARY,
        )
        self._end_entry.pack(side="left", padx=(T.PAD_XS, T.PAD_MD))

        ctk.CTkButton(
            row1, text="套用", width=50, height=28,
            **T.BTN_GHOST_ACCENT,
            command=self._on_date_apply,
        ).pack(side="left", padx=(0, T.PAD_MD))

        self._range_seg = ctk.CTkSegmentedButton(
            row1, values=list(self._RANGE_PRESETS.keys()),
            command=self._on_range_preset,
            fg_color=T.NAVY_600, selected_color=T.GOLD_500,
            selected_hover_color=T.GOLD_400,
            unselected_color=T.NAVY_700,
            unselected_hover_color=T.NAVY_500,
            text_color=T.TEXT_PRIMARY,
        )
        self._range_seg.set("近7天")
        self._range_seg.pack(side="left")

        # Chart canvas
        self._fig = Figure(figsize=(8, 3), dpi=100)
        self._fig.set_facecolor(T.CHART_BG)
        self._ax = self._fig.add_subplot(111)
        self._chart_container = tk.Frame(chart_card, bg=T.CHART_BG,
                                         highlightthickness=0, height=250)
        self._chart_container.grid(row=2, column=0, sticky="ew",
                                   padx=T.PAD_XS, pady=(0, T.PAD_SM))
        self._chart_container.grid_propagate(False)
        self._chart_container.grid_columnconfigure(0, weight=1)
        self._chart_container.grid_rowconfigure(0, weight=1)
        self._chart_canvas = FigureCanvasTkAgg(self._fig, master=self._chart_container)
        canvas_widget = self._chart_canvas.get_tk_widget()
        canvas_widget.configure(highlightthickness=0)
        canvas_widget.grid(row=0, column=0, sticky="nsew")
        self._style_axis(self._ax)
        self._chart_canvas.draw()
        self._update_chart()

        # ── Row 6-7: Patrol history ──
        T.section_title(self._inner, "海巡紀錄", row=6)

        self._session_container = T.card_frame(self._inner,
                                               row=7, column=0, columnspan=3,
                                               sticky="ew", padx=T.PAD_XS,
                                               pady=(0, T.PAD_XL))
        self._session_container.grid_columnconfigure(0, weight=1)
        self._session_widgets: list[ctk.CTkFrame] = []

    # ── Scroll helpers ──

    def _on_inner_configure(self, event):
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._scroll_canvas.itemconfigure(self._canvas_window_id, width=event.width)

    def _bind_mousewheel(self, event):
        canvas = self._scroll_canvas
        if _platform.system() == "Darwin":
            canvas.bind("<MouseWheel>", self._on_mousewheel)
        else:
            canvas.bind("<MouseWheel>", self._on_mousewheel)
            canvas.bind("<Button-4>", self._on_mousewheel_linux)
            canvas.bind("<Button-5>", self._on_mousewheel_linux)

    def _unbind_mousewheel(self, event):
        canvas = self._scroll_canvas
        canvas.unbind("<MouseWheel>")
        if _platform.system() != "Darwin":
            canvas.unbind("<Button-4>")
            canvas.unbind("<Button-5>")

    def _on_mousewheel(self, event):
        if self._destroyed:
            return
        if _platform.system() == "Darwin":
            self._scroll_canvas.yview_scroll(-event.delta, "units")
        else:
            self._scroll_canvas.yview_scroll(-event.delta // 120, "units")

    def _on_mousewheel_linux(self, event):
        if self._destroyed:
            return
        if event.num == 4:
            self._scroll_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._scroll_canvas.yview_scroll(1, "units")

    # ── UI helpers ──

    def _create_stat_card(self, title: str, value: str, target: str = "",
                          accent_color: str = T.GOLD_500) -> dict:
        is_clickable = bool(target)
        frame = ctk.CTkFrame(
            self._inner,
            fg_color=T.BG_CARD,
            corner_radius=T.RADIUS_LG,
            border_width=1,
            border_color=T.BORDER_SUBTLE,
            cursor="hand2" if is_clickable else "",
        )

        # Accent top bar
        accent_bar = ctk.CTkFrame(frame, height=3, fg_color=accent_color,
                                  corner_radius=0)
        accent_bar.pack(fill="x", side="top")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=T.PAD_LG, pady=(T.PAD_SM, T.PAD_LG))

        title_label = ctk.CTkLabel(
            body, text=title, font=T.font_small(),
            text_color=T.TEXT_SECONDARY,
        )
        title_label.pack(anchor="w")

        value_label = ctk.CTkLabel(
            body, text=value, font=T.font_stat(),
            text_color=T.TEXT_PRIMARY,
        )
        value_label.pack(anchor="w", pady=(T.PAD_XS, 0))

        if is_clickable:
            hint = ctk.CTkLabel(
                body, text="查看 →", font=T.font_caption(),
                text_color=T.GOLD_500,
            )
            hint.pack(anchor="w", pady=(T.PAD_XS, 0))

            def on_enter(e):
                frame.configure(fg_color=T.BG_CARD_HOVER)
            def on_leave(e):
                frame.configure(fg_color=T.BG_CARD)

            for widget in (frame, body, title_label, value_label, hint, accent_bar):
                widget.bind("<Button-1>", lambda e, t=target: self.app._show_frame(t))
                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)

        return {"frame": frame, "value_label": value_label}

    # ── Patrol toggle ──

    def _toggle_patrol(self):
        scheduler = self.app.scheduler
        if scheduler.is_running:
            self._patrol_btn.configure(text="停止中...", state="disabled")
            self.update_idletasks()

            def _stop_in_bg():
                try:
                    scheduler.stop()
                finally:
                    self.app.run_in_gui(lambda: self._patrol_btn.configure(state="normal"))
                    self.app.run_in_gui(self._update_patrol_ui)

            threading.Thread(target=_stop_in_bg, daemon=True).start()
            return
        else:
            configured_platforms = []
            all_platforms = [p for p in self._PATROL_PLATFORMS if p not in self._COMING_SOON_PLATS]
            bm = self.app.browser_manager
            for plat in all_platforms:
                config = self.app.repo.get_platform_config(plat)
                if config and config.is_enabled and bm.has_session(plat):
                    configured_platforms.append(plat)

            if not configured_platforms:
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

            dialog = _ChannelSelectDialog(self, configured_platforms, all_platforms)
            self.wait_window(dialog)
            if dialog.result is None or len(dialog.result) == 0:
                return

            self._patrol_btn.configure(text="啟動中...", state="disabled")
            self.update_idletasks()
            try:
                scheduler.start(platforms=dialog.result)
            finally:
                self._patrol_btn.configure(state="normal")

        self._update_patrol_ui()

    def _toggle_sending(self):
        scheduler = self.app.scheduler
        if scheduler.is_sending_paused:
            scheduler.resume_sending()
        else:
            scheduler.pause_sending()
        self._update_sending_btn()

    def _update_sending_btn(self):
        scheduler = self.app.scheduler
        if scheduler.is_sending_paused:
            self._sending_btn.configure(
                text="開始發送", **T.BTN_SUCCESS,
            )
        else:
            self._sending_btn.configure(
                text="暫停發送", **T.BTN_WARNING,
            )

    def _update_patrol_ui(self):
        if self.app.scheduler.is_running:
            self._patrol_btn.configure(text="停止海巡", **T.BTN_DANGER)
            active_platforms = getattr(self.app.scheduler, "active_platforms", None)
            status_text = "海巡中"
            if active_platforms and set(active_platforms) != set(self._PATROL_PLATFORMS):
                labels = [
                    self._PATROL_PLATFORM_LABELS.get(platform, platform)
                    for platform in active_platforms
                ]
                status_text = f"海巡中 ({', '.join(labels)})"
            self._patrol_status.configure(text=status_text, text_color=T.TEAL_500)
            self._sending_btn.pack(side="left", padx=(0, T.PAD_SM), before=self._patrol_btn)
            self._update_sending_btn()
            self._refresh_live_counter()
            self._start_live_counter_loop()
        else:
            self._patrol_btn.configure(text="啟動海巡", **T.BTN_SUCCESS)
            self._patrol_status.configure(text="未啟動", text_color=T.TEXT_TERTIARY)
            self._live_counter.configure(text="")
            self._sending_btn.pack_forget()
            self._stop_live_counter_loop()

    def _refresh_live_counter(self):
        if self._destroyed:
            return
        session = self.app.repo.get_active_patrol_session()
        if session:
            self._live_counter.configure(
                text=f"本次偵測 {session.total_detected} 筆 / 回覆 {session.total_replied} 筆",
                text_color=T.TEAL_400,
            )
        else:
            self._live_counter.configure(text="")

    def _start_live_counter_loop(self):
        self._stop_live_counter_loop()
        if self._destroyed or not self.app.scheduler.is_running:
            return
        self._refresh_live_counter()
        self._live_counter_after_id = self.after(10000, self._start_live_counter_loop)

    def _stop_live_counter_loop(self):
        if self._live_counter_after_id is not None:
            self.after_cancel(self._live_counter_after_id)
            self._live_counter_after_id = None

    # ── Chart ──

    def _on_period_change(self, value: str):
        self._update_chart()

    def _on_chart_filter_change(self, value: str):
        self._update_chart()

    def _on_range_preset(self, value: str):
        days = self._RANGE_PRESETS.get(value, 7)
        today = date.today()
        self._start_date_var.set((today - timedelta(days=days - 1)).strftime("%Y-%m-%d"))
        self._end_date_var.set(today.strftime("%Y-%m-%d"))
        self._update_chart()

    def _on_date_apply(self):
        self._update_chart()

    @staticmethod
    def _valid_date(s: str) -> bool:
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _update_chart(self):
        if self._destroyed:
            return
        period = self._PERIOD_MAP.get(self._period_seg.get(), "day")
        platform = self._PLATFORM_MAP.get(self._chart_platform_var.get())
        start_date = self._start_date_var.get().strip()
        end_date = self._end_date_var.get().strip()

        if start_date and not self._valid_date(start_date):
            start_date = ""
        if end_date and not self._valid_date(end_date):
            end_date = ""
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        stats = self.app.repo.get_reply_stats(
            period=period, platform=platform,
            start_date=start_date or None, end_date=end_date or None,
        )

        ax = self._ax
        ax.clear()
        self._fig.set_facecolor(T.CHART_BG)
        ax.set_facecolor(T.CHART_AXIS_BG)

        if not stats:
            ax.text(
                0.5, 0.5, "尚無回覆資料", ha="center", va="center",
                color=T.TEXT_TERTIARY, fontsize=14, transform=ax.transAxes,
            )
            ax.set_xticks([])
            ax.set_yticks([])
            self._style_axis(ax)
            self._fig.tight_layout()
            self._chart_canvas.draw_idle()
            return

        all_labels = sorted(set(s["label"] for s in stats))
        platform_colors = {
            "threads": T.PLATFORM_THREADS,
            "facebook": T.PLATFORM_FACEBOOK,
            "instagram": T.PLATFORM_INSTAGRAM,
        }

        if platform:
            counts = []
            for label in all_labels:
                c = sum(s["count"] for s in stats if s["label"] == label)
                counts.append(c)
            color = platform_colors.get(platform, T.GOLD_500)
            ax.bar(range(len(all_labels)), counts, color=color, alpha=0.85)
        else:
            plats = ["threads", "facebook", "instagram"]
            bottom = [0] * len(all_labels)
            for plat in plats:
                counts = []
                for label in all_labels:
                    c = sum(s["count"] for s in stats if s["label"] == label and s["platform"] == plat)
                    counts.append(c)
                color = platform_colors.get(plat, T.TEXT_TERTIARY)
                ax.bar(range(len(all_labels)), counts, bottom=bottom,
                       color=color, alpha=0.85, label=plat.capitalize())
                bottom = [b + c for b, c in zip(bottom, counts)]
            legend = ax.legend(
                loc="upper left", fontsize=8,
                facecolor=T.CHART_BG, edgecolor=T.CHART_SPINE,
                labelcolor=T.CHART_TEXT,
            )
            if legend:
                legend.get_frame().set_alpha(0.95)

        ax.set_xticks(range(len(all_labels)))
        display_labels = self._format_labels(all_labels, period)
        ax.set_xticklabels(display_labels, rotation=45, ha="right", fontsize=8)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        self._style_axis(ax)
        self._fig.tight_layout()
        self._chart_canvas.draw_idle()

    def _format_labels(self, labels: list[str], period: str) -> list[str]:
        years = {lb[:4] for lb in labels if len(lb) >= 4}
        include_year = len(years) > 1

        if period == "day":
            if include_year:
                return [lb.replace("-", "/") for lb in labels]
            return [lb[5:].replace("-", "/") for lb in labels]
        if period == "week":
            return [lb.replace("-W", " W") for lb in labels]
        return [lb.replace("-", "/") for lb in labels]

    def _style_axis(self, ax):
        ax.set_facecolor(T.CHART_AXIS_BG)
        ax.tick_params(colors=T.CHART_TEXT, labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(T.CHART_SPINE)
        ax.spines["left"].set_color(T.CHART_SPINE)
        ax.xaxis.label.set_color(T.CHART_TEXT)
        ax.yaxis.label.set_color(T.CHART_TEXT)
        ax.title.set_color(T.CHART_TEXT)
        ax.grid(axis="y", color=T.CHART_GRID, alpha=0.35, linewidth=0.8)
        ax.set_axisbelow(True)

    # ── Patrol sessions ──

    def _update_sessions(self):
        for w in self._session_widgets:
            w.destroy()
        self._session_widgets.clear()

        sessions = self.app.repo.get_patrol_sessions(limit=10)
        if not sessions:
            empty = ctk.CTkLabel(
                self._session_container, text="尚無海巡紀錄",
                text_color=T.TEXT_TERTIARY, font=T.font_body(),
            )
            empty.grid(row=0, column=0, pady=T.PAD_MD)
            self._session_widgets.append(empty)
            return

        # Header
        hdr = ctk.CTkFrame(self._session_container, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=T.PAD_XS, pady=(T.PAD_XS, T.PAD_XS))
        for col, (text, w) in enumerate([
            ("狀態", 60), ("開始時間", 130), ("結束時間", 130),
            ("平台", 140), ("偵測", 50), ("回覆", 50), ("持續時間", 80),
        ]):
            ctk.CTkLabel(
                hdr, text=text, width=w,
                font=T.font_badge(), text_color=T.TEXT_TERTIARY,
            ).grid(row=0, column=col, padx=2, sticky="w")
        self._session_widgets.append(hdr)

        for i, s in enumerate(sessions):
            row = ctk.CTkFrame(self._session_container, fg_color="transparent")
            row.grid(row=i + 1, column=0, sticky="ew", padx=T.PAD_XS, pady=1)

            if s.status == "running":
                status_text, status_color = "進行中", T.TEAL_500
            else:
                status_text, status_color = "已結束", T.TEXT_TERTIARY
            ctk.CTkLabel(
                row, text=status_text, width=60,
                font=T.font_small(), text_color=status_color,
            ).grid(row=0, column=0, padx=2, sticky="w")

            ctk.CTkLabel(
                row, text=(s.started_at or "")[:16], width=130,
                font=T.font_small(), text_color=T.TEXT_SECONDARY,
            ).grid(row=0, column=1, padx=2, sticky="w")

            ctk.CTkLabel(
                row, text=(s.stopped_at or "-")[:16], width=130,
                font=T.font_small(), text_color=T.TEXT_TERTIARY,
            ).grid(row=0, column=2, padx=2, sticky="w")

            try:
                plats = json.loads(s.platforms) if s.platforms else []
            except (json.JSONDecodeError, TypeError):
                plats = []
            plat_text = ", ".join(p.capitalize() for p in plats) if plats else "-"
            ctk.CTkLabel(
                row, text=plat_text, width=140,
                font=T.font_small(), text_color=T.TEXT_SECONDARY,
            ).grid(row=0, column=3, padx=2, sticky="w")

            ctk.CTkLabel(
                row, text=str(s.total_detected), width=50,
                font=T.font_small(), text_color=T.TEXT_PRIMARY,
            ).grid(row=0, column=4, padx=2, sticky="w")

            ctk.CTkLabel(
                row, text=str(s.total_replied), width=50,
                font=T.font_small(), text_color=T.TEXT_PRIMARY,
            ).grid(row=0, column=5, padx=2, sticky="w")

            duration = self._calc_duration(s.started_at, s.stopped_at)
            ctk.CTkLabel(
                row, text=duration, width=80,
                font=T.font_small(), text_color=T.TEXT_TERTIARY,
            ).grid(row=0, column=6, padx=2, sticky="w")

            self._session_widgets.append(row)

    @staticmethod
    def _calc_duration(start: str | None, end: str | None) -> str:
        if not start:
            return "-"
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            t_start = datetime.strptime(start, fmt)
            t_end = datetime.strptime(end, fmt) if end else datetime.now()
            delta = t_end - t_start
            total_sec = int(delta.total_seconds())
            if total_sec < 60:
                return f"{total_sec}秒"
            if total_sec < 3600:
                return f"{total_sec // 60}分{total_sec % 60}秒"
            hours = total_sec // 3600
            mins = (total_sec % 3600) // 60
            return f"{hours}時{mins}分"
        except (ValueError, TypeError):
            return "-"

    def _configure_matplotlib(self):
        plt.rcParams["font.sans-serif"] = T.CHART_FONTS
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["axes.unicode_minus"] = False

    def destroy(self):
        self._destroyed = True
        self._stop_live_counter_loop()
        self._unbind_mousewheel(None)
        if hasattr(self, "_chart_canvas") and self._chart_canvas is not None:
            if hasattr(self._chart_canvas, "close_event"):
                self._chart_canvas.close_event()
            self._chart_canvas.get_tk_widget().destroy()
            self._chart_canvas = None
        if hasattr(self, "_fig") and self._fig is not None:
            self._fig.clf()
            plt.close(self._fig)
            self._fig = None
        super().destroy()

    def refresh(self):
        if self._destroyed:
            return
        repo = self.app.repo

        pending = repo.count_posts_by_status("pending")
        self._cards["pending_count"].configure(text=str(pending))

        replied = sum(
            repo.count_replies_today(p) for p in ("threads", "facebook", "instagram")
        )
        self._cards["replied_today"].configure(text=str(replied))

        templates = self.app.template_manager.count()
        self._cards["template_count"].configure(text=str(templates))

        bm = self.app.browser_manager
        for plat_key, label in self._platform_status.items():
            if plat_key in self._COMING_SOON_PLATS:
                continue
            config = repo.get_platform_config(plat_key)
            has_session = bm.has_session(plat_key)
            if config and config.is_enabled and has_session:
                label.configure(text="已登入", text_color=T.TEAL_500)
            else:
                label.configure(text="未設定", text_color=T.TEXT_TERTIARY)

        mode = repo.get_setting("reply_mode", "semi_auto")
        mode_text = "半自動" if mode == "semi_auto" else "全自動"
        mode_color = T.TEAL_500 if mode == "semi_auto" else T.WARNING
        self._mode_label.configure(text=mode_text, text_color=mode_color)

        self._update_patrol_ui()
        self._update_chart()
        self._update_sessions()
