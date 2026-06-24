# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

SinoPac AutoReply (永豐金證券 社群自動回覆系統) — a desktop app that monitors social media posts (Threads, Facebook, Instagram) for relevant keywords and auto-replies with pre-approved templates. Built for a single user, packaged as exe/app via PyInstaller.

## Running

```bash
pip install -r requirements.txt
python main.py
```

No test framework is configured yet. The `tests/` directory exists but is empty.

## Architecture

**Entry point**: `main.py` → sets up logging, opens SQLite DB, launches `App(db)` GUI.

**Layer structure**:

```
GUI (CustomTkinter)  →  Core (business logic)  →  Data (SQLite + Repository)
                         ↓
                     Platforms (API adapters)
```

- **Data layer** (`src/data/`): `models.py` defines dataclasses (Template, DetectedPost, ReplyLog, PlatformConfig, Keyword, AuditLog). `database.py` manages schema, thread-safe connections (WAL mode, `threading.local()`). `repository.py` is the sole data access layer with 40+ methods.

- **Core layer** (`src/core/`): `scheduler.py` runs APScheduler background jobs that call platform adapters to fetch posts. `reply_engine.py` orchestrates the full flow: score posts via `keyword_matcher.py`, recommend templates, check `compliance.py` rules (daily limits, business hours, warmup, duplicate prevention), then dispatch replies. `template_manager.py` handles template CRUD and CSV/Excel import.

- **Platform layer** (`src/platforms/`): `base.py` defines `PlatformAdapter` ABC with `fetch_posts()`, `reply_to_post()`, `check_connection()`, `check_already_replied()`. Concrete adapters for Threads (Graph API v1.0), Facebook (Graph API v25.0), Instagram (Graph API v25.0). `rate_limiter.py` implements token-bucket rate limiting per platform.

- **GUI layer** (`src/gui/`): `app.py` is the main window with sidebar navigation. Frames are lazy-loaded via `_create_frame()`. Background thread updates reach the GUI through a `queue.Queue` polled every 200ms (`_poll_queue()`).

**Key data flow**: Scheduler patrol → adapter.fetch_posts(keywords) → ReplyEngine.process_fetched_posts() → KeywordMatcher scoring → template recommendation → compliance check → status assignment (approved in full_auto, pending in semi_auto) → send_pending_replies() → adapter.reply_to_post()

## Important Conventions

- **Reply modes**: `semi_auto` (human approves each reply) and `full_auto` (auto-approve if no negative keywords). Controlled by `reply_mode` setting in DB.
- **Negative keywords** (config.py `NEGATIVE_KEYWORDS`): force posts into pending/human review regardless of mode.
- **Token encryption**: API tokens stored encrypted via Fernet (`src/utils/crypto.py`). Key file is OS-specific with chmod 0o600. Always use `encrypt_token()`/`decrypt_token()`.
- **Thread safety**: DB uses thread-local connections. GUI updates from background threads must go through the message queue, not direct widget calls.
- **CSV import**: `src/utils/csv_parser.py` normalizes Chinese column headers to English (e.g. 文案編號 → template_code). Required columns: template_code, category, content, platforms. Supports UTF-8, Big5, CP950 encodings.
- **Compliance rules** are in `src/core/compliance.py`: no duplicate replies, daily per-platform limits, business hours enforcement (default 09:00-18:00), warmup period for new accounts.
- **Audit trail**: All significant actions logged to immutable `audit_log` and `reply_log` tables.
- **SQL safety**: Repository uses parameterized queries and a column-name whitelist for dynamic UPDATE.

## Workflow

- **Claude** — 負責所有規劃、架構設計、任務拆解、決策
- **Codex** — 負責所有程式碼撰寫與 code review。每完成一個程式碼單元，須交由 Codex 審查後才繼續下一步。

## Configuration

All runtime settings live in the `app_settings` SQLite table as key-value pairs. Defaults are defined in `config.py` (`DEFAULT_SETTINGS` dict). Platform-specific settings include daily limits, polling intervals, reply delays (with random jitter), and business hours.
