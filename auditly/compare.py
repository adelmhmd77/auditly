"""Compare two crawls (before vs after) to track fixes and regressions."""
from __future__ import annotations

from pathlib import Path

from .audits import all_audits
from .crawl import db as dbm


def _load(path):
    db = dbm.connect(Path(path) / "crawl.db", readonly=True)
    pages = {r["url"]: dict(r) for r in db.execute(
        "SELECT url, status, indexability, title, word_count FROM pages WHERE internal=1")}
    issues: dict[str, set] = {}
    for aid, url in db.execute("SELECT audit_id, url FROM issues"):
        issues.setdefault(aid, set()).add(url)
    meta = {"url": dbm.get_meta(db, "start_url", ""), "started": dbm.get_meta(db, "started_at", ""),
            "health": dbm.get_meta(db, "health", None, as_json=True)}
    db.close()
    return pages, issues, meta


def compare(before: str | Path, after: str | Path) -> dict:
    pa, ia, ma = _load(before)
    pb, ib, mb = _load(after)
    titles = {a.id: a for a in all_audits()}
    rows = []
    for aid in sorted(set(ia) | set(ib)):
        a, b = ia.get(aid, set()), ib.get(aid, set())
        au = titles.get(aid)
        rows.append({"id": aid, "title": au.title if au else aid, "severity": au.severity if au else "opportunity",
                     "category": au.category if au else "", "before": len(a), "after": len(b),
                     "fixed": sorted(a - b), "new": sorted(b - a)})
    rows.sort(key=lambda r: (-(abs(r["after"] - r["before"])), r["title"]))
    status_changes = [(u, pa[u]["status"], pb[u]["status"]) for u in pa.keys() & pb.keys()
                      if pa[u]["status"] != pb[u]["status"]]
    title_changes = [(u, pa[u]["title"], pb[u]["title"]) for u in pa.keys() & pb.keys()
                     if (pa[u]["title"] or "") != (pb[u]["title"] or "")]
    return {
        "before": ma, "after": mb,
        "added": sorted(pb.keys() - pa.keys()), "removed": sorted(pa.keys() - pb.keys()),
        "status_changes": status_changes, "title_changes": title_changes, "issues": rows,
        "fixed_total": sum(len(r["fixed"]) for r in rows), "new_total": sum(len(r["new"]) for r in rows),
    }
