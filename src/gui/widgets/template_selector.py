"""Template selection widget."""

import customtkinter as ctk


class TemplateSelector(ctk.CTkFrame):
    """Wrap a template dropdown with a small, reusable API."""

    def __init__(self, master, templates: list[str], on_select: callable, **kwargs):
        super().__init__(master, **kwargs)
        self._templates = templates or [""]
        self.grid_columnconfigure(0, weight=1)

        self._menu = ctk.CTkOptionMenu(
            self,
            values=self._templates,
            command=on_select,
        )
        self._menu.grid(row=0, column=0, sticky="ew")

        if self._templates:
            self._menu.set(self._templates[0])

    def get(self) -> str:
        return self._menu.get()

    def set(self, value: str):
        self._menu.set(value)
