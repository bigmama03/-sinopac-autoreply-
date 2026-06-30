"""Non-blocking toast notification widget."""

import weakref
import customtkinter as ctk

from src.gui import theme as T


class Toast(ctk.CTkFrame):
    """A small overlay that auto-dismisses after a few seconds."""

    _STYLES = {
        "success": {"fg": T.TEAL_500, "text": "#FFFFFF"},
        "error": {"fg": T.ERROR, "text": "#FFFFFF"},
        "info": {"fg": T.INFO, "text": "#FFFFFF"},
        "warning": {"fg": T.WARNING, "text": "#FFFFFF"},
    }

    def __init__(self, parent, message: str, style: str = "success",
                 duration_ms: int = 2500):
        colors = self._STYLES.get(style, self._STYLES["info"])
        super().__init__(parent, fg_color=colors["fg"],
                         corner_radius=T.RADIUS_MD,
                         border_width=1, border_color=colors["fg"])

        self._duration = duration_ms
        self._after_id = None

        ctk.CTkLabel(
            self, text=message, text_color=colors["text"],
            font=T.font_body(), wraplength=350,
        ).pack(padx=T.PAD_LG, pady=T.PAD_MD)

        self.place(relx=0.5, y=10, anchor="n")
        self.lift()

        self._after_id = self.after(self._duration, self._dismiss)

    def _dismiss(self):
        self._after_id = None
        try:
            self.place_forget()
            self.destroy()
        except Exception:
            pass

    def destroy(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        super().destroy()


_active_toasts: weakref.WeakValueDictionary[int, "Toast"] = weakref.WeakValueDictionary()


def show_toast(parent, message: str, style: str = "success",
               duration_ms: int = 2500):
    """Convenience function to show a toast on any widget. One per parent."""
    parent_id = id(parent)
    existing = _active_toasts.get(parent_id)
    if existing is not None:
        try:
            existing.destroy()
        except Exception:
            pass
    toast = Toast(parent, message, style=style, duration_ms=duration_ms)
    _active_toasts[parent_id] = toast
    return toast
