"""Expandable text label — shows truncated preview with expand/collapse toggle."""

import customtkinter as ctk


class ExpandableText(ctk.CTkFrame):
    """A text label that shows a preview (default 100 chars) with expand/collapse."""

    def __init__(self, parent, text: str, prefix: str = "",
                 max_preview: int = 100, wraplength: int = 700,
                 font=None, text_color=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._full_text = text or ""
        self._prefix = prefix
        self._max_preview = max_preview
        self._expanded = False
        self._needs_toggle = len(self._full_text) > max_preview

        display_font = font or ctk.CTkFont(size=12)
        toggle_font = ctk.CTkFont(size=11)

        self._label = ctk.CTkLabel(
            self, text=self._get_display_text(), wraplength=wraplength,
            justify="left", font=display_font,
            **({"text_color": text_color} if text_color else {}),
        )
        self._label.grid(row=0, column=0, sticky="w")

        if self._needs_toggle:
            self._toggle_btn = ctk.CTkButton(
                self, text="展開全文", width=60, height=20,
                font=toggle_font, fg_color="transparent",
                text_color=("#2196F3", "#64B5F6"), hover_color=("gray85", "gray25"),
                command=self._toggle,
            )
            self._toggle_btn.grid(row=1, column=0, sticky="w", pady=(2, 0))

    def _get_display_text(self) -> str:
        if self._expanded or not self._needs_toggle:
            content = self._full_text
        else:
            content = self._full_text[:self._max_preview] + "..."
        return f"{self._prefix}{content}" if self._prefix else content

    def _toggle(self):
        self._expanded = not self._expanded
        self._label.configure(text=self._get_display_text())
        if self._needs_toggle:
            self._toggle_btn.configure(text="收合" if self._expanded else "展開全文")
