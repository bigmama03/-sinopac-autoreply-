"""Reply mode toggle widget."""

import customtkinter as ctk


class ModeToggle(ctk.CTkFrame):
    """Toggle between semi-auto and full-auto reply modes."""

    def __init__(self, master, on_change: callable, **kwargs):
        super().__init__(master, **kwargs)
        self._on_change = on_change
        self._value = ctk.StringVar(value="0")

        ctk.CTkLabel(self, text="半自動").pack(side="left")
        self._switch = ctk.CTkSwitch(
            self,
            text="全自動",
            variable=self._value,
            onvalue="1",
            offvalue="0",
            command=self._emit_change,
        )
        self._switch.pack(side="left", padx=10)

    def _emit_change(self):
        if self._on_change:
            self._on_change(self.get_mode())

    def get_mode(self) -> str:
        return "全自動" if self._value.get() == "1" else "半自動"
