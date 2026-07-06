"""SQLite database connection manager and schema initialization."""

import sqlite3
import threading
import weakref
from typing import Optional

SCHEMA_VERSION = 5

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    description TEXT
);

-- Reply templates (imported from CSV/Excel)
CREATE TABLE IF NOT EXISTS templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_code   TEXT UNIQUE NOT NULL,
    category        TEXT NOT NULL,
    content         TEXT NOT NULL,
    platforms       TEXT NOT NULL DEFAULT 'threads;fb;ig',
    keywords        TEXT,
    priority        INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    approved_by     TEXT,
    approved_at     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Detected posts from monitoring
CREATE TABLE IF NOT EXISTS detected_posts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    platform                TEXT NOT NULL CHECK(platform IN ('facebook', 'instagram', 'threads')),
    platform_post_id        TEXT NOT NULL,
    post_url                TEXT,
    author_username         TEXT,
    post_content            TEXT NOT NULL,
    matched_keywords        TEXT,
    relevance_score         REAL DEFAULT 0.0,
    recommended_template_id INTEGER REFERENCES templates(id),
    status                  TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending', 'approved', 'rejected', 'replied', 'failed', 'skipped')),
    detected_at             TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    reviewed_at             TEXT,
    parent_post_id          INTEGER REFERENCES detected_posts(id),
    post_type               TEXT NOT NULL DEFAULT 'post' CHECK(post_type IN ('post', 'comment')),
    comments_scanned_at     TEXT,
    UNIQUE(platform, platform_post_id)
);

-- Reply log (immutable audit trail)
CREATE TABLE IF NOT EXISTS reply_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_post_id    INTEGER NOT NULL REFERENCES detected_posts(id),
    template_id         INTEGER NOT NULL REFERENCES templates(id),
    platform            TEXT NOT NULL,
    reply_content       TEXT NOT NULL,
    reply_mode          TEXT NOT NULL CHECK(reply_mode IN ('semi_auto', 'full_auto')),
    platform_reply_id   TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'sending', 'sent', 'failed', 'retrying', 'cancelled')),
    error_message       TEXT,
    retry_count         INTEGER DEFAULT 0,
    sent_at             TEXT,
    deleted_at          TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Platform API configuration
CREATE TABLE IF NOT EXISTS platform_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT UNIQUE NOT NULL,
    is_enabled      INTEGER DEFAULT 0,
    access_token    TEXT,
    page_id         TEXT,
    ig_user_id      TEXT,
    threads_user_id TEXT,
    app_id          TEXT,
    app_secret      TEXT,
    token_expires_at TEXT,
    last_connected_at TEXT,
    config_json     TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Keyword configuration
CREATE TABLE IF NOT EXISTS keywords (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL UNIQUE,
    category    TEXT,
    weight      REAL DEFAULT 1.0,
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Application settings
CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Audit log (immutable)
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    details     TEXT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Patrol session history
CREATE TABLE IF NOT EXISTS patrol_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    stopped_at      TEXT,
    platforms       TEXT,
    total_detected  INTEGER DEFAULT 0,
    total_replied   INTEGER DEFAULT 0,
    total_skipped   INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running', 'stopped', 'error'))
);

-- Facebook monitored groups/pages
CREATE TABLE IF NOT EXISTS fb_monitor_targets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL CHECK(target_type IN ('group', 'page')),
    target_id   TEXT NOT NULL UNIQUE,
    target_name TEXT,
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_detected_posts_status ON detected_posts(status);
CREATE INDEX IF NOT EXISTS idx_detected_posts_platform ON detected_posts(platform, detected_at);
CREATE INDEX IF NOT EXISTS idx_reply_log_sent_at ON reply_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_reply_log_status ON reply_log(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(category);
-- idx_detected_posts_parent and idx_detected_posts_type are created by migration v5
-- to avoid errors on existing databases where the columns don't exist yet.
"""

_MIGRATIONS = [
    # (version, description, [sql_statements])
    (2, "Add deleted_at to reply_log", [
        "ALTER TABLE reply_log ADD COLUMN deleted_at TEXT;",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_deleted_at ON reply_log(deleted_at);",
    ]),
    (3, "Add cancelled to reply_log status (superseded by v4)", [
        # SQLite cannot ALTER CHECK constraints — recreate the table
        """CREATE TABLE IF NOT EXISTS reply_log_new (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_post_id    INTEGER NOT NULL REFERENCES detected_posts(id),
            template_id         INTEGER NOT NULL REFERENCES templates(id),
            platform            TEXT NOT NULL,
            reply_content       TEXT NOT NULL,
            reply_mode          TEXT NOT NULL CHECK(reply_mode IN ('semi_auto', 'full_auto')),
            platform_reply_id   TEXT,
            status              TEXT NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending', 'sending', 'sent', 'failed', 'retrying', 'cancelled')),
            error_message       TEXT,
            retry_count         INTEGER DEFAULT 0,
            sent_at             TEXT,
            deleted_at          TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );""",
        """INSERT OR IGNORE INTO reply_log_new
           SELECT id, detected_post_id, template_id, platform, reply_content,
                  reply_mode, platform_reply_id, status, error_message,
                  retry_count, sent_at, deleted_at, created_at
           FROM reply_log;""",
        "DROP TABLE IF EXISTS reply_log;",
        "ALTER TABLE reply_log_new RENAME TO reply_log;",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_sent_at ON reply_log(sent_at);",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_status ON reply_log(status);",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_deleted_at ON reply_log(deleted_at);",
    ]),
    (4, "Add sending status to reply_log for atomic claim", [
        """CREATE TABLE IF NOT EXISTS reply_log_new (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_post_id    INTEGER NOT NULL REFERENCES detected_posts(id),
            template_id         INTEGER NOT NULL REFERENCES templates(id),
            platform            TEXT NOT NULL,
            reply_content       TEXT NOT NULL,
            reply_mode          TEXT NOT NULL CHECK(reply_mode IN ('semi_auto', 'full_auto')),
            platform_reply_id   TEXT,
            status              TEXT NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending', 'sending', 'sent', 'failed', 'retrying', 'cancelled')),
            error_message       TEXT,
            retry_count         INTEGER DEFAULT 0,
            sent_at             TEXT,
            deleted_at          TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );""",
        """INSERT OR IGNORE INTO reply_log_new
           SELECT id, detected_post_id, template_id, platform, reply_content,
                  reply_mode, platform_reply_id, status, error_message,
                  retry_count, sent_at, deleted_at, created_at
           FROM reply_log;""",
        "DROP TABLE IF EXISTS reply_log;",
        "ALTER TABLE reply_log_new RENAME TO reply_log;",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_sent_at ON reply_log(sent_at);",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_status ON reply_log(status);",
        "CREATE INDEX IF NOT EXISTS idx_reply_log_deleted_at ON reply_log(deleted_at);",
    ]),
    (5, "Add comment crawling support to detected_posts", [
        "ALTER TABLE detected_posts ADD COLUMN parent_post_id INTEGER REFERENCES detected_posts(id);",
        "ALTER TABLE detected_posts ADD COLUMN post_type TEXT NOT NULL DEFAULT 'post';",
        "ALTER TABLE detected_posts ADD COLUMN comments_scanned_at TEXT;",
        "CREATE INDEX IF NOT EXISTS idx_detected_posts_parent ON detected_posts(parent_post_id);",
        "CREATE INDEX IF NOT EXISTS idx_detected_posts_type ON detected_posts(post_type);",
    ]),
]


class Database:
    """Thread-safe SQLite database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._all_conns: weakref.WeakSet[sqlite3.Connection] = weakref.WeakSet()
        self._conn_lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
            with self._conn_lock:
                self._all_conns.add(conn)
        return self._local.conn

    def initialize(self):
        """Create schema and seed default data if needed."""
        cursor = self.conn.cursor()
        cursor.executescript(SCHEMA_SQL)

        # Check schema version
        cursor.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        current_version = row[0] if row[0] is not None else 0

        # Run pending migrations first, record version only after success
        for ver, desc, statements in _MIGRATIONS:
            if current_version < ver:
                for sql in statements:
                    try:
                        cursor.execute(sql)
                    except sqlite3.OperationalError:
                        pass  # Column/index already exists from fresh schema
                cursor.execute(
                    "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
                    (ver, desc),
                )

        # Record current schema version for fresh databases
        if current_version == 0:
            cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
                (SCHEMA_VERSION, "Initial schema"),
            )

        # Seed default data using INSERT OR IGNORE to avoid race conditions
        from config import DEFAULT_SETTINGS, DEFAULT_KEYWORDS, PLATFORMS

        for key, value in DEFAULT_SETTINGS.items():
            cursor.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

        for kw in DEFAULT_KEYWORDS:
            cursor.execute(
                "INSERT OR IGNORE INTO keywords (keyword, category, weight) VALUES (?, ?, ?)",
                (kw["keyword"], kw["category"], kw["weight"]),
            )

        for plat in PLATFORMS:
            cursor.execute(
                "INSERT OR IGNORE INTO platform_config (platform) VALUES (?)",
                (plat,),
            )

        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        return self.conn.executemany(sql, params_list)

    def commit(self):
        self.conn.commit()

    def close(self):
        """Close all thread-local connections (not just the calling thread's)."""
        with self._conn_lock:
            for conn in list(self._all_conns):
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
        # Also clear the calling thread's reference
        if hasattr(self._local, "conn"):
            self._local.conn = None
