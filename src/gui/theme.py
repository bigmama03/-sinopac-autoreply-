"""Centralized design tokens — SinoPac Securities brand identity.

All colors, fonts, spacing, and styling constants live here.
Every GUI module imports from this file instead of hardcoding values.

Brand DNA: 專業金融 × 數位科技 × 高效率作業
"""

import functools
import customtkinter as ctk


# ─── Brand Colors ─────────────────────────────────────────────
# SinoPac Securities primary palette
NAVY_900 = "#0A1628"       # Deepest navy — sidebar bg
NAVY_800 = "#0F1F36"       # Dark panel backgrounds
NAVY_700 = "#152A45"       # Card backgrounds
NAVY_600 = "#1B3A5C"       # Elevated cards / hover
NAVY_500 = "#234B73"       # Active selections
NAVY_400 = "#2E6090"       # Secondary interactive

GOLD_500 = "#C8A951"       # Primary accent — brand gold
GOLD_400 = "#D4B968"       # Lighter gold for hover
GOLD_300 = "#E0CA80"       # Subtle gold tint
GOLD_600 = "#B8963C"       # Darker gold

TEAL_500 = "#00B4A0"       # Success / active states
TEAL_400 = "#26C6B0"       # Lighter success
TEAL_300 = "#4DD8C0"       # Subtle teal

# ─── Semantic Colors ──────────────────────────────────────────
SUCCESS = TEAL_500
SUCCESS_LIGHT = TEAL_400
WARNING = "#E5A100"
WARNING_LIGHT = "#F5B800"
ERROR = "#E53935"
ERROR_LIGHT = "#EF5350"
INFO = "#2196F3"
INFO_LIGHT = "#42A5F5"

# ─── Text Colors ──────────────────────────────────────────────
TEXT_PRIMARY = "#F0F2F5"    # Main text (white-ish)
TEXT_SECONDARY = "#A0AEC0"  # Muted text
TEXT_TERTIARY = "#5A6A80"   # Disabled / hint text
TEXT_INVERSE = "#0A1628"    # Text on light backgrounds
TEXT_ACCENT = GOLD_500      # Accent text

# ─── Background Colors ───────────────────────────────────────
BG_APP = NAVY_800           # Main content area background
BG_SIDEBAR = NAVY_900       # Sidebar background
BG_CARD = NAVY_700          # Card / panel background
BG_CARD_HOVER = NAVY_600    # Card hover state
BG_ELEVATED = NAVY_600      # Elevated surfaces (dialogs, dropdowns)
BG_INPUT = "#0D1A2D"        # Input field background
BG_SCROLLBAR = NAVY_600     # Scrollbar track

# ─── Border Colors ────────────────────────────────────────────
BORDER_DEFAULT = "#1E3450"  # Standard border
BORDER_SUBTLE = "#162840"   # Subtle separator
BORDER_FOCUS = GOLD_500     # Focus ring
BORDER_HOVER = NAVY_400     # Hover state

# ─── Platform Colors ─────────────────────────────────────────
PLATFORM_THREADS = "#1DA1F2"
PLATFORM_FACEBOOK = "#1877F2"
PLATFORM_INSTAGRAM = "#E4405F"

PLATFORM_COLORS = {
    "threads": PLATFORM_THREADS,
    "facebook": PLATFORM_FACEBOOK,
    "instagram": PLATFORM_INSTAGRAM,
}

# ─── Status Colors ────────────────────────────────────────────
STATUS_PENDING = WARNING
STATUS_APPROVED = INFO
STATUS_REPLIED = SUCCESS
STATUS_REJECTED = ERROR
STATUS_FAILED = ERROR
STATUS_SKIPPED = TEXT_TERTIARY
STATUS_CANCELLED = TEXT_TERTIARY
STATUS_RETRYING = WARNING
STATUS_SENT = SUCCESS

STATUS_COLORS = {
    "pending": WARNING,
    "sending": INFO,
    "approved": INFO,
    "replied": SUCCESS,
    "rejected": ERROR,
    "failed": ERROR,
    "skipped": TEXT_TERTIARY,
    "cancelled": TEXT_TERTIARY,
    "retrying": WARNING,
    "sent": SUCCESS,
}

# ─── Spacing ──────────────────────────────────────────────────
PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 24
PAD_2XL = 32

# ─── Corner Radii ─────────────────────────────────────────────
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_XL = 16
RADIUS_PILL = 20

# ─── Sidebar ──────────────────────────────────────────────────
SIDEBAR_WIDTH = 220
SIDEBAR_BTN_HEIGHT = 38
SIDEBAR_ICON_SIZE = 16

# ─── Chart Colors ─────────────────────────────────────────────
CHART_BG = NAVY_800
CHART_AXIS_BG = NAVY_700
CHART_TEXT = TEXT_SECONDARY
CHART_GRID = "#1E3450"
CHART_SPINE = "#2A4060"

CHART_FONTS = [
    "PingFang TC",
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "Noto Sans CJK TC",
    "Arial Unicode MS",
    "sans-serif",
]


# ─── Font Helpers ─────────────────────────────────────────────
# Cached: CTkFont objects are immutable in practice, so reusing them is safe.
@functools.lru_cache(maxsize=1)
def font_title() -> ctk.CTkFont:
    return ctk.CTkFont(size=20, weight="bold")

@functools.lru_cache(maxsize=1)
def font_section() -> ctk.CTkFont:
    return ctk.CTkFont(size=15, weight="bold")

@functools.lru_cache(maxsize=1)
def font_card_title() -> ctk.CTkFont:
    return ctk.CTkFont(size=13, weight="bold")

@functools.lru_cache(maxsize=1)
def font_body() -> ctk.CTkFont:
    return ctk.CTkFont(size=12)

@functools.lru_cache(maxsize=1)
def font_small() -> ctk.CTkFont:
    return ctk.CTkFont(size=11)

@functools.lru_cache(maxsize=1)
def font_caption() -> ctk.CTkFont:
    return ctk.CTkFont(size=10)

@functools.lru_cache(maxsize=1)
def font_stat() -> ctk.CTkFont:
    return ctk.CTkFont(size=28, weight="bold")

@functools.lru_cache(maxsize=1)
def font_mono() -> ctk.CTkFont:
    return ctk.CTkFont(family="monospace", size=11)

@functools.lru_cache(maxsize=1)
def font_badge() -> ctk.CTkFont:
    return ctk.CTkFont(size=10, weight="bold")


# ─── Button Presets ───────────────────────────────────────────
BTN_PRIMARY = {
    "fg_color": GOLD_500,
    "hover_color": GOLD_400,
    "text_color": TEXT_INVERSE,
    "corner_radius": RADIUS_MD,
}

BTN_SUCCESS = {
    "fg_color": TEAL_500,
    "hover_color": TEAL_400,
    "text_color": "#FFFFFF",
    "corner_radius": RADIUS_MD,
}

BTN_DANGER = {
    "fg_color": ERROR,
    "hover_color": ERROR_LIGHT,
    "text_color": "#FFFFFF",
    "corner_radius": RADIUS_MD,
}

BTN_WARNING = {
    "fg_color": WARNING,
    "hover_color": WARNING_LIGHT,
    "text_color": TEXT_INVERSE,
    "corner_radius": RADIUS_MD,
}

BTN_GHOST = {
    "fg_color": "transparent",
    "hover_color": NAVY_600,
    "text_color": TEXT_SECONDARY,
    "border_width": 1,
    "border_color": BORDER_DEFAULT,
    "corner_radius": RADIUS_MD,
}

BTN_GHOST_ACCENT = {
    "fg_color": "transparent",
    "hover_color": NAVY_600,
    "text_color": GOLD_500,
    "border_width": 1,
    "border_color": GOLD_500,
    "corner_radius": RADIUS_MD,
}

BTN_GHOST_DANGER = {
    "fg_color": "transparent",
    "hover_color": "#2A1520",
    "text_color": ERROR,
    "border_width": 1,
    "border_color": BORDER_DEFAULT,
    "corner_radius": RADIUS_MD,
}


# ─── Component Builders ──────────────────────────────────────
def section_title(parent, text: str, *, row: int = 0, column: int = 0,
                  columnspan: int = 3, muted: bool = False):
    """Create a styled section title with accent bar."""
    container = ctk.CTkFrame(parent, fg_color="transparent")
    container.grid(row=row, column=column, columnspan=columnspan,
                   sticky="ew", pady=(PAD_LG, PAD_SM), padx=PAD_XS)

    accent_color = TEXT_TERTIARY if muted else GOLD_500
    accent = ctk.CTkFrame(container, width=3, height=18,
                          fg_color=accent_color, corner_radius=2)
    accent.pack(side="left", padx=(0, PAD_SM))

    text_color = TEXT_TERTIARY if muted else TEXT_PRIMARY
    ctk.CTkLabel(
        container, text=text,
        font=font_section(), text_color=text_color,
    ).pack(side="left")

    return container


def card_frame(parent, **grid_kwargs) -> ctk.CTkFrame:
    """Create a styled card frame."""
    card = ctk.CTkFrame(
        parent,
        fg_color=BG_CARD,
        corner_radius=RADIUS_LG,
        border_width=1,
        border_color=BORDER_SUBTLE,
    )
    if grid_kwargs:
        card.grid(**grid_kwargs)
    return card


def stat_card(parent, title: str, value: str, accent_color: str = GOLD_500,
              **grid_kwargs) -> dict:
    """Create a data stat card with accent top border."""
    outer = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=RADIUS_LG,
                         border_width=1, border_color=BORDER_SUBTLE)
    if grid_kwargs:
        outer.grid(**grid_kwargs)

    # Accent line at top
    accent_line = ctk.CTkFrame(outer, height=3, fg_color=accent_color,
                               corner_radius=0)
    accent_line.pack(fill="x", side="top")

    body = ctk.CTkFrame(outer, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=PAD_LG, pady=(PAD_SM, PAD_LG))

    title_label = ctk.CTkLabel(body, text=title, font=font_small(),
                               text_color=TEXT_SECONDARY)
    title_label.pack(anchor="w")

    value_label = ctk.CTkLabel(body, text=value, font=font_stat(),
                               text_color=TEXT_PRIMARY)
    value_label.pack(anchor="w", pady=(PAD_XS, 0))

    return {"frame": outer, "body": body, "title_label": title_label,
            "value_label": value_label}


def status_badge(parent, text: str, status: str) -> ctk.CTkLabel:
    """Create a colored status badge label."""
    color = STATUS_COLORS.get(status, TEXT_TERTIARY)
    return ctk.CTkLabel(
        parent, text=text,
        font=font_badge(), text_color=color,
    )


def platform_badge(parent, platform: str) -> ctk.CTkLabel:
    """Create a platform name badge."""
    color = PLATFORM_COLORS.get(platform, TEXT_SECONDARY)
    return ctk.CTkLabel(
        parent, text=platform.upper(),
        font=font_badge(), text_color=color,
    )


def page_header(parent, title: str) -> ctk.CTkFrame:
    """Create a page header with title. Returns the header frame."""
    header = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        header, text=title,
        font=font_title(), text_color=TEXT_PRIMARY,
    ).pack(side="left")
    return header
