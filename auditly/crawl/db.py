"""SQLite storage for a crawl session."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

PAGE_COLS = [
    "url", "internal", "depth", "status", "redirect_to", "content_type", "size", "response_ms", "ttfb_ms",
    "title", "title_count", "title_len", "title_px", "meta_description", "meta_description_count",
    "meta_description_len", "h1", "h1_count", "h2_count", "canonical", "canonical_count", "meta_robots",
    "x_robots_tag", "indexability", "lang", "hreflang_count", "viewport", "rel_next", "rel_prev",
    "word_count", "text_ratio", "readability", "content_hash", "simhash", "top_keyword", "top_keyword_density",
    "question_headings", "lists", "tables", "images", "images_missing_alt", "images_empty_alt",
    "internal_links", "external_links", "body_internal_links", "scripts", "stylesheets", "render_blocking",
    "schema_types", "author", "published", "modified", "last_modified", "content_encoding", "cache_control",
    "hsts", "csp", "x_frame", "x_content_type", "mixed_content", "insecure_forms", "protocol_relative",
    "small_fonts", "mobile_word_count", "mobile_links", "error", "crawled_at", "data",
]
INT_COLS = {"internal", "depth", "status", "size", "response_ms", "ttfb_ms", "title_count", "title_len", "title_px",
            "meta_description_count", "meta_description_len", "h1_count", "h2_count", "canonical_count",
            "hreflang_count", "word_count", "question_headings", "lists", "tables", "images", "images_missing_alt",
            "images_empty_alt", "internal_links", "external_links", "body_internal_links", "scripts", "stylesheets",
            "render_blocking", "mixed_content", "insecure_forms", "protocol_relative", "small_fonts",
            "mobile_word_count", "mobile_links"}
REAL_COLS = {"text_ratio", "readability", "top_keyword_density"}


def _coltype(c: str) -> str:
    if c == "url":
        return "TEXT PRIMARY KEY"
    if c in INT_COLS:
        return "INTEGER"
    if c in REAL_COLS:
        return "REAL"
    return "TEXT"


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS pages ({', '.join(f'{c} {_coltype(c)}' for c in PAGE_COLS)});
CREATE TABLE IF NOT EXISTS links (src TEXT, dst TEXT, anchor TEXT, internal INTEGER, nofollow INTEGER,
                                  kind TEXT DEFAULT 'a', in_body INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS hreflang (src TEXT, lang TEXT, href TEXT);
CREATE TABLE IF NOT EXISTS resources (url TEXT PRIMARY KEY, kind TEXT, status INTEGER, size INTEGER,
                                      content_type TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS queue (url TEXT PRIMARY KEY, depth INTEGER, kind TEXT, done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sitemap_urls (url TEXT PRIMARY KEY, sitemap TEXT, lastmod TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS issues (audit_id TEXT, url TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS psi (url TEXT, strategy TEXT, score REAL, lcp REAL, inp REAL, cls REAL, fcp REAL,
                                ttfb REAL, source TEXT, fetched_at TEXT, PRIMARY KEY (url, strategy));
CREATE TABLE IF NOT EXISTS scores (url TEXT PRIMARY KEY, inlinks INTEGER, link_score REAL);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_pages_title ON pages(title);
CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash);
CREATE INDEX IF NOT EXISTS idx_issues_audit ON issues(audit_id);
CREATE INDEX IF NOT EXISTS idx_issues_url ON issues(url);
CREATE INDEX IF NOT EXISTS idx_hreflang_src ON hreflang(src);
"""


def connect(path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        db = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        db = sqlite3.connect(str(path), check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    return db


def get_meta(db: sqlite3.Connection, key: str, default=None, as_json: bool = False):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    if as_json:
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return default
    return row[0]


def set_meta(db: sqlite3.Connection, key: str, value) -> None:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))
