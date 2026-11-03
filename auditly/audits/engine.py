"""Audit framework: definitions, plugin loading, running, scoring."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable, Iterable

from ..crawl import db as dbm
from ..paths import plugin_dirs

SEVERITIES = ("critical", "warning", "opportunity")
SEV_WEIGHT = {"critical": 3.0, "warning": 1.0, "opportunity": 0.2}
CATEGORIES = [
    "Response codes", "Page titles", "Meta descriptions", "Headings", "Canonicals", "Content", "Images",
    "Links", "Security", "URL structure", "Hreflang", "Structured data", "Performance", "Mobile",
    "Pagination", "Sitemaps & robots.txt", "AI / GEO readiness",
]


@dataclass
class Audit:
    id: str
    category: str
    title: str
    severity: str
    why: str
    fix: str
    sql: str | None = None
    fn: Callable[["AuditContext"], Iterable[tuple]] | None = None
    site_level: bool = False  # one finding about the whole site

    def run(self, ctx: "AuditContext") -> list[tuple[str, str]]:
        if self.sql:
            return [(r[0], "" if r[1] is None else str(r[1])) for r in ctx.db.execute(self.sql)]
        if self.fn:
            return [(u, "" if d is None else str(d)) for u, d in self.fn(ctx)]
        return []


class AuditContext:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.start_url = dbm.get_meta(db, "start_url", "")

    def meta(self, key, default=None):
        return dbm.get_meta(self.db, key, default, as_json=True)

    @cached_property
    def pages(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM pages WHERE internal=1")]

    @cached_property
    def by_url(self) -> dict[str, dict]:
        return {p["url"]: p for p in self.pages}

    @cached_property
    def html(self) -> list[dict]:
        return [p for p in self.pages if p["status"] == 200 and "html" in (p["content_type"] or "html")]

    @cached_property
    def indexable(self) -> list[dict]:
        return [p for p in self.html if p["indexability"] == "Indexable"]

    @cached_property
    def inlinks(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.db.execute("SELECT url, inlinks FROM scores")}

    def data(self, page: dict) -> dict:
        try:
            return json.loads(page.get("data") or "{}")
        except ValueError:
            return {}

    @cached_property
    def sitemap_urls(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT url FROM sitemap_urls")}


def _load_plugins() -> list[Audit]:
    out: list[Audit] = []
    for d in plugin_dirs():
        for f in sorted(Path(d).glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"auditly_plugin_{f.stem}", f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                if hasattr(mod, "register"):
                    mod.register(out.append)
                for a in getattr(mod, "AUDITS", []):
                    out.append(a)
            except Exception as e:  # a broken plugin must not break the app
                print(f"[Auditly] plugin {f.name} failed to load: {e}")
    return out


def all_audits(include_plugins: bool = True) -> list[Audit]:
    from .builtin import BUILTIN
    audits = list(BUILTIN)
    if include_plugins:
        known = {a.id for a in audits}
        audits += [a for a in _load_plugins() if a.id not in known]
    return audits


def compute_link_scores(db: sqlite3.Connection, iterations: int = 25, damping: float = 0.85) -> None:
    """Internal PageRank on followed <a> links, scaled 0-100 (log-scaled like popular crawlers)."""
    import math
    pages = [r[0] for r in db.execute(
        "SELECT url FROM pages WHERE internal=1 AND status=200 AND (content_type LIKE '%html%' OR content_type='')")]
    idx = {u: i for i, u in enumerate(pages)}
    n = len(pages)
    db.execute("DELETE FROM scores")
    if not n:
        return
    out: list[set] = [set() for _ in range(n)]
    inl = [0] * n
    seen_pairs = set()
    for src, dst, nofollow in db.execute("SELECT src, dst, nofollow FROM links WHERE internal=1 AND kind='a' AND src<>dst"):
        s, t = idx.get(src), idx.get(dst)
        if t is None or s is None:
            continue
        if (s, t) not in seen_pairs:
            seen_pairs.add((s, t))
            inl[t] += 1
        if not nofollow:
            out[s].add(t)
    pr = [1.0 / n] * n
    for _ in range(iterations):
        nxt = [(1 - damping) / n] * n
        dangling = sum(pr[i] for i in range(n) if not out[i])
        for i in range(n):
            if out[i]:
                share = damping * pr[i] / len(out[i])
                for t in out[i]:
                    nxt[t] += share
        add = damping * dangling / n
        pr = [v + add for v in nxt]
    lo, hi = math.log(min(pr)), math.log(max(pr))
    span = (hi - lo) or 1.0
    db.executemany("INSERT INTO scores(url, inlinks, link_score) VALUES (?,?,?)",
                   [(pages[i], inl[i], round(100 * (math.log(pr[i]) - lo) / span, 1)) for i in range(n)])


def run_audits(db_path: str | Path, progress: Callable[[str], None] | None = None) -> dict:
    """Run every audit, store findings in the `issues` table, return a summary dict."""
    db = dbm.connect(db_path)
    try:
        compute_link_scores(db)
        db.commit()
        ctx = AuditContext(db)
        db.execute("DELETE FROM issues")
        counts: dict[str, int] = {}
        failures: dict[str, str] = {}
        for a in all_audits():
            if progress:
                progress(a.title)
            try:
                rows = a.run(ctx)
            except Exception as e:
                failures[a.id] = f"{type(e).__name__}: {e}"
                continue
            seen = set()
            uniq = []
            for u, d in rows:
                if (u, d) not in seen:
                    seen.add((u, d))
                    uniq.append((a.id, u, d))
            db.executemany("INSERT INTO issues(audit_id, url, detail) VALUES (?,?,?)", uniq)
            counts[a.id] = len(uniq)
        dbm.set_meta(db, "audit_failures", failures)
        dbm.set_meta(db, "audit_counts", counts)
        dbm.set_meta(db, "health", health_score(db))
        db.commit()
        return {"counts": counts, "failures": failures}
    finally:
        db.close()


def health_score(db: sqlite3.Connection) -> int:
    """0-100. Weighted share of pages affected by each issue type."""
    total = db.execute("SELECT COUNT(*) FROM pages WHERE internal=1").fetchone()[0] or 1
    sev = {a.id: a.severity for a in all_audits()}
    site = {a.id for a in all_audits() if a.site_level}
    penalty = 0.0
    for aid, n in db.execute("SELECT audit_id, COUNT(DISTINCT url) FROM issues GROUP BY audit_id"):
        w = SEV_WEIGHT.get(sev.get(aid, "opportunity"), 0.2)
        share = 0.25 if aid in site else min(1.0, n / total)
        penalty += w * (0.3 + 0.7 * share) * 4
    return max(0, min(100, round(100 - penalty)))
