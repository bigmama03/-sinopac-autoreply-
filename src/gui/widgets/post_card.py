"""Reusable post summary card widget."""

import customtkinter as ctk


class PostCard(ctk.CTkFrame):
    """Display a compact summary for a detected post."""

    _PLATFORM_COLORS = {
        "threads": "#1DA1F2",
        "facebook": "#1877F2",
        "instagram": "#E4405F",
    }

    _STATUS_COLORS = {
        "pending": "#FF9800",
        "approved": "#2196F3",
        "replied": "#4CAF50",
        "rejected": "#F44336",
        "failed": "#F44336",
        "skipped": "#9E9E9E",
    }

    def __init__(self, master, post: dict, **kwargs):
        super().__init__(master, **kwargs)
        self.post = post

        self.grid_columnconfigure(1, weight=1)

        platform = str(post.get("platform", "")).lower()
        author = post.get("author", "") or "Unknown"
        content = post.get("content", "") or ""
        score = post.get("score", 0)
        status = str(post.get("status", "")).lower()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text=platform.upper() if platform else "UNKNOWN",
            fg_color=self._PLATFORM_COLORS.get(platform, "#607D8B"),
            corner_radius=999,
            text_color="white",
            padx=10,
            pady=3,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=author,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        ctk.CTkLabel(
            header,
            text="●",
            text_color=self._STATUS_COLORS.get(status, "#9E9E9E"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=2, sticky="e")

        preview = content[:120] + ("..." if len(content) > 120 else "")
        ctk.CTkLabel(
            self,
            text=preview,
            justify="left",
            wraplength=520,
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 10))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer,
            text=f"Reply Score: {score}",
            text_color="gray60",
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            footer,
            text=status or "unknown",
            text_color=self._STATUS_COLORS.get(status, "#9E9E9E"),
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=1, sticky="e")
