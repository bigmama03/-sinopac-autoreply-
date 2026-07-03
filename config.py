"""Application configuration constants."""

import os
import sys
import platform

# Application info
APP_NAME = "SinoPac AutoReply"
APP_VERSION = "1.0.0"
APP_NAME_ZH = "永豐金證券 社群自動回覆系統"

# Data directory (platform-aware)
if platform.system() == "Windows":
    APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", "."), "SinoPacAutoReply")
elif platform.system() == "Darwin":
    APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "SinoPacAutoReply")
else:
    APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".sinopac_autoreply")

os.makedirs(APP_DATA_DIR, exist_ok=True)
BROWSER_DATA_DIR = os.path.join(APP_DATA_DIR, 'browser_sessions')
os.makedirs(BROWSER_DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(APP_DATA_DIR, "sinopac_autoreply.db")
LOG_DIR = os.path.join(APP_DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Resource path helper (PyInstaller compatible)
def get_resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

# Default safety settings
DEFAULT_SETTINGS = {
    "reply_mode": "semi_auto",           # semi_auto | full_auto
    "daily_limit_threads": 40,
    "daily_limit_facebook": 25,
    "daily_limit_instagram": 25,
    "reply_interval_min_sec": 120,       # 2 minutes
    "reply_interval_max_sec": 300,       # 5 minutes
    "reply_delay_min_sec": 180,          # 3 minutes
    "reply_delay_max_sec": 900,          # 15 minutes
    "business_hours_start": "09:00",
    "business_hours_end": "18:00",
    "warmup_days": 3,
    "warmup_ratio": 0.3,
    "polling_interval_threads_sec": 300,  # 5 minutes
    "polling_interval_facebook_sec": 120, # 2 minutes
    "polling_interval_instagram_sec": 300,
    "search_scroll_count": 6,
    "comment_scan_enabled": "1",
    "comment_scan_limit_per_patrol": 3,
    "comment_scan_age_hours": 24,
    "comment_scroll_count": 4,
    "auto_cleanup_days": 30,
    "sending_paused": "0",
    "relevance_threshold": 3.0,
    "threads_enabled": False,
    "facebook_enabled": False,
    "instagram_enabled": False,
}

# Default keywords with weights
DEFAULT_KEYWORDS = [
    {"keyword": "證券開戶", "category": "開戶", "weight": 5.0},
    {"keyword": "豐存股", "category": "品牌", "weight": 5.0},
    {"keyword": "開戶", "category": "開戶", "weight": 3.0},
    {"keyword": "怎麼買股票", "category": "新手", "weight": 4.0},
    {"keyword": "手續費", "category": "手續費", "weight": 3.0},
    {"keyword": "永豐", "category": "品牌", "weight": 4.0},
    {"keyword": "新手", "category": "新手", "weight": 2.0},
    {"keyword": "證券", "category": "一般", "weight": 1.5},
    {"keyword": "股票", "category": "一般", "weight": 1.0},
    {"keyword": "投資", "category": "一般", "weight": 1.0},
]

# Default Ollama system prompt
DEFAULT_OLLAMA_PROMPT = """你是永豐金證券的社群行銷助理。你的任務是判斷一則社群貼文是否適合由永豐金證券的官方帳號回覆推廣內容。

判斷標準：
1. 貼文是否在討論投資、開戶、股票、手續費等相關話題
2. 貼文語氣是否正面或中性（負面抱怨、客訴、爭議性話題不適合回覆）
3. 貼文是否有商業推廣的空間（純個人情緒抒發、政治討論不適合）
4. 貼文作者是否可能是潛在客戶（正在尋找投資管道、比較券商）

請只回覆 JSON 格式：
{"should_reply": true/false, "reason": "簡短原因"}"""

# Negative keywords (force human review)
NEGATIVE_KEYWORDS = ["詐騙", "爛", "虧錢", "客訴", "垃圾", "黑心"]

# Platforms
PLATFORMS = ["threads", "facebook", "instagram"]
