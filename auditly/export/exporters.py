"""Export a crawl session: master CSV, CSV set, Excel, JSON, HTML, PDF and an AI-ready prompt."""
from __future__ import annotations

import base64
import csv
import html
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .. import APP_NAME, __version__
from ..audits import CATEGORIES, all_audits
from ..crawl import db as dbm
from ..crawl.urls import strip_www

FORMATS = {
    "master_csv": "Master CSV (all data in one file)",
    "csv": "CSV set (pages, links, issues, images…)",
    "xlsx": "Excel workbook",
    "json": "JSON",
    "html": "HTML report",
    "pdf": "PDF report",
    "prompt": "AI analysis prompt (.md)",
}
SEV_LABEL = {"critical": "Critical", "warning": "Warning", "opportunity": "Opportunity"}
SEV_ORDER = {"critical": 0, "warning": 1, "opportunity": 2}
MASTER_COLS = ["url", "status", "indexability", "depth", "inlinks", "link_score", "title", "title_len",
               "meta_description", "meta_description_len", "h1", "h1_count", "canonical", "meta_robots", "word_count",
               "readability", "response_ms", "ttfb_ms", "size", "images", "images_missing_alt", "internal_links",
               "external_links", "schema_types", "lang", "hreflang_count", "redirect_to", "error"]


def export_dir_for(root: Path, start_url: str) -> Path:
    host = strip_www(urlsplit(start_url).hostname or "site")
    d = Path(root) / f"{host} {datetime.now().strftime('%Y-%m-%d %H-%M')}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _audits_by_id():
    return {a.id: a for a in all_audits()}


def collect(db: sqlite3.Connection) -> dict:
    """Everything the report formats need, in plain Python structures."""
    audits = _audits_by_id()
    groups = defaultdict(list)
    for aid, url, detail in db.execute("SELECT audit_id, url, detail FROM issues"):
        groups[aid].append((url, detail))
    issues = []
    for aid, rows in groups.items():
        a = audits.get(aid)
        if not a:
            continue
        issues.append({"id": aid, "title": a.title, "category": a.category, "severity": a.severity, "why": a.why,
                       "fix": a.fix, "count": len(rows), "urls": rows})
    issues.sort(key=lambda i: (SEV_ORDER[i["severity"]], -i["count"]))
    status = [(r[0], r[1]) for r in db.execute(
        "SELECT status, COUNT(*) FROM pages WHERE internal=1 GROUP BY status ORDER BY status")]
    total = db.execute("SELECT COUNT(*) FROM pages WHERE internal=1").fetchone()[0]
    indexable = db.execute("SELECT COUNT(*) FROM pages WHERE internal=1 AND indexability='Indexable'").fetchone()[0]
    avg_ms = db.execute("SELECT AVG(response_ms) FROM pages WHERE internal=1 AND status=200").fetchone()[0] or 0
    sev_counts = {s: sum(i["count"] for i in issues if i["severity"] == s) for s in SEV_ORDER}
    return {"start_url": dbm.get_meta(db, "start_url", ""), "started": dbm.get_meta(db, "started_at", ""),
            "finished": dbm.get_meta(db, "finished_at", ""), "health": dbm.get_meta(db, "health", 0, as_json=True),
            "total": total, "indexable": indexable, "avg_ms": int(avg_ms), "status": status, "issues": issues,
            "sev_counts": sev_counts}


def _master_rows(db):
    issue_map = defaultdict(list)
    audits = _audits_by_id()
    for aid, url in db.execute("SELECT DISTINCT audit_id, url FROM issues"):
        a = audits.get(aid)
        if a:
            issue_map[url].append(f"[{SEV_LABEL[a.severity]}] {a.title}")
    cols = ", ".join(f"p.{c}" for c in MASTER_COLS if c not in ("inlinks", "link_score"))
    q = (f"SELECT {cols}, COALESCE(s.inlinks,0) AS inlinks, s.link_score FROM pages p "
         "LEFT JOIN scores s ON s.url=p.url WHERE p.internal=1 ORDER BY p.depth, p.url")
    for r in db.execute(q):
        d = dict(r)
        d["issue_count"] = len(issue_map.get(d["url"], []))
        d["issues"] = " | ".join(sorted(issue_map.get(d["url"], [])))
        yield d


def write_master_csv(db, path: Path) -> Path:
    cols = MASTER_COLS + ["issue_count", "issues"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in _master_rows(db):
            w.writerow(row)
    return path


def _write_query(db, path: Path, q: str) -> None:
    cur = db.execute(q)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        for r in cur:
            w.writerow(list(r))


CSV_QUERIES = {
    "internal_pages.csv": "SELECT p.*, COALESCE(s.inlinks,0) AS inlinks, s.link_score FROM pages p LEFT JOIN scores s "
                          "ON s.url=p.url WHERE p.internal=1 ORDER BY p.depth, p.url",
    "external_links.csv": "SELECT url, status, error, response_ms FROM pages WHERE internal=0 ORDER BY url",
    "links.csv": "SELECT src AS source, dst AS destination, anchor, internal, nofollow, kind, in_body FROM links",
    "images.csv": "SELECT l.src AS page, l.dst AS image, l.anchor AS alt, r.status, r.size, r.content_type FROM links l "
                  "LEFT JOIN resources r ON r.url=l.dst WHERE l.kind='img'",
    "hreflang.csv": "SELECT src AS page, lang, href FROM hreflang",
    "sitemap_urls.csv": "SELECT s.url, s.sitemap, s.lastmod, p.status, p.indexability FROM sitemap_urls s "
                        "LEFT JOIN pages p ON p.url=s.url",
    "pagespeed.csv": "SELECT * FROM psi",
}


def write_issues_csv(db, path: Path) -> None:
    audits = _audits_by_id()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["severity", "category", "issue", "url", "detail", "how_to_fix"])
        rows = []
        for aid, url, detail in db.execute("SELECT audit_id, url, detail FROM issues"):
            a = audits.get(aid)
            if a:
                rows.append((SEV_ORDER[a.severity], a.category, a.title, url, detail, a.fix, a.severity))
        rows.sort()
        for r in rows:
            w.writerow([SEV_LABEL[r[6]], r[1], r[2], r[3], r[4], r[5]])


def write_csv_set(db, folder: Path) -> list[Path]:
    out = []
    write_issues_csv(db, folder / "issues.csv")
    out.append(folder / "issues.csv")
    for name, q in CSV_QUERIES.items():
        _write_query(db, folder / name, q)
        out.append(folder / name)
    return out


def write_xlsx(db, path: Path, data: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="161B22")
    head_font = Font(bold=True, color="FFFFFF")
    sev_fill = {"critical": "FDE2E1", "warning": "FFF1D6", "opportunity": "DDF4FF"}

    def sheet(ws, header, rows, widths=None):
        ws.append(header)
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
        for r in rows:
            ws.append([_xl(v) for v in r])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, w in enumerate(widths or [], 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.active
    ws.title = "Summary"
    ws.append([f"{APP_NAME} SEO audit"])
    ws["A1"].font = Font(bold=True, size=16)
    for k, v in [("Website", data["start_url"]), ("Crawled", data["finished"] or data["started"]),
                 ("Health score", data["health"]), ("Pages crawled", data["total"]), ("Indexable pages", data["indexable"]),
                 ("Avg response (ms)", data["avg_ms"]), ("Critical findings", data["sev_counts"]["critical"]),
                 ("Warnings", data["sev_counts"]["warning"]), ("Opportunities", data["sev_counts"]["opportunity"])]:
        ws.append([k, v])
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 60

    ws = wb.create_sheet("Issue overview")
    sheet(ws, ["Severity", "Category", "Issue", "URLs", "Why it matters", "How to fix"],
          [(SEV_LABEL[i["severity"]], i["category"], i["title"], i["count"], i["why"], i["fix"]) for i in data["issues"]],
          [13, 22, 44, 8, 60, 60])
    for row in ws.iter_rows(min_row=2):
        sev = str(row[0].value).lower()
        if sev in sev_fill:
            row[0].fill = PatternFill("solid", fgColor=sev_fill[sev])
        for c in row[4:6]:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    ws = wb.create_sheet("All issues")
    sheet(ws, ["Severity", "Category", "Issue", "URL", "Detail"],
          [(SEV_LABEL[i["severity"]], i["category"], i["title"], u, d) for i in data["issues"] for u, d in i["urls"]],
          [13, 22, 40, 70, 60])

    ws = wb.create_sheet("Pages")
    rows = list(_master_rows(db))
    cols = MASTER_COLS + ["issue_count", "issues"]
    sheet(ws, cols, [[r.get(c) for c in cols] for r in rows], [70] + [14] * (len(cols) - 1))

    for title, q in [("Links", CSV_QUERIES["links.csv"]), ("External", CSV_QUERIES["external_links.csv"]),
                     ("Images", CSV_QUERIES["images.csv"]), ("Hreflang", CSV_QUERIES["hreflang.csv"]),
                     ("Sitemap", CSV_QUERIES["sitemap_urls.csv"])]:
        cur = db.execute(q)
        hdr = [d[0] for d in cur.description]
        rows = cur.fetchmany(1_000_000)
        if rows:
            sheet(wb.create_sheet(title), hdr, rows, [50] * len(hdr))
    wb.save(path)
    return path


def _xl(v):
    if isinstance(v, str) and len(v) > 32000:
        return v[:32000]
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v  # avoid formula injection from crawled content
    return v


def write_json(db, path: Path, data: dict) -> Path:
    pages = list(_master_rows(db))
    out = {"generator": f"{APP_NAME} {__version__}", **{k: v for k, v in data.items() if k != "issues"},
           "issues": [{**{k: v for k, v in i.items() if k != "urls"},
                       "urls": [{"url": u, "detail": d} for u, d in i["urls"]]} for i in data["issues"]],
           "pages": pages}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------- HTML / PDF
def _logo_tag(logo: str) -> str:
    if not logo or not Path(logo).is_file():
        return ""
    ext = Path(logo).suffix.lower().lstrip(".") or "png"
    mime = "svg+xml" if ext == "svg" else ext
    b64 = base64.b64encode(Path(logo).read_bytes()).decode()
    return f'<img class="logo" src="data:image/{mime};base64,{b64}" alt="">'


def render_html(data: dict, brand: str = "", color: str = "#00E676", logo: str = "", max_urls: int = 100,
                for_pdf: bool = False) -> str:
    e = html.escape
    brand = brand or APP_NAME
    sev_color = {"critical": "#CF222E", "warning": "#BF8700", "opportunity": "#0969DA"}
    by_cat = defaultdict(lambda: defaultdict(int))
    for i in data["issues"]:
        by_cat[i["category"]][i["severity"]] += i["count"]
    h = data["health"] or 0
    hcol = "#1A7F37" if h >= 80 else "#BF8700" if h >= 50 else "#CF222E"
    parts = [f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(brand)} — SEO audit — {e(data['start_url'])}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Inter,Roboto,Helvetica,Arial,sans-serif;color:#1F2328;background:#F6F8FA;margin:0}}
.wrap{{max-width:1080px;margin:0 auto;padding:32px 24px}}
header{{display:flex;align-items:center;gap:16px;border-bottom:4px solid {e(color)};padding-bottom:16px;margin-bottom:24px}}
.logo{{height:44px}} h1{{font-size:26px;margin:0}} .muted{{color:#656D76}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0 28px}}
.card{{background:#fff;border:1px solid #D0D7DE;border-radius:12px;padding:16px}}
.big{{font-size:30px;font-weight:700}} h2{{font-size:20px;margin:32px 0 12px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #D0D7DE;border-radius:12px;overflow:hidden;font-size:13px}}
th,td{{text-align:left;padding:8px 12px;border-bottom:1px solid #EAEEF2;vertical-align:top;word-break:break-word}}
th{{background:#F6F8FA;font-weight:600}}
.pill{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}}
.issue{{background:#fff;border:1px solid #D0D7DE;border-radius:12px;padding:16px 20px;margin:12px 0;page-break-inside:avoid}}
.issue h3{{margin:0 0 6px;font-size:16px}} .issue p{{margin:6px 0}} details summary{{cursor:pointer;color:#0969DA}}
ul.urls{{font-size:12px;columns:1;margin:6px 0;padding-left:18px}} footer{{margin:40px 0 0;font-size:12px}}
</style></head><body><div class="wrap">
<header>{_logo_tag(logo)}<div><h1>SEO audit report</h1><div class="muted">{e(data['start_url'])} · {e((data['finished'] or data['started'] or '')[:16].replace('T', ' '))}</div></div></header>
<div class="grid">
<div class="card"><div class="muted">Health score</div><div class="big" style="color:{hcol}">{h}/100</div></div>
<div class="card"><div class="muted">Pages crawled</div><div class="big">{data['total']:,}</div></div>
<div class="card"><div class="muted">Indexable</div><div class="big">{data['indexable']:,}</div></div>
<div class="card"><div class="muted">Critical</div><div class="big" style="color:#CF222E">{data['sev_counts']['critical']:,}</div></div>
<div class="card"><div class="muted">Warnings</div><div class="big" style="color:#BF8700">{data['sev_counts']['warning']:,}</div></div>
<div class="card"><div class="muted">Opportunities</div><div class="big" style="color:#0969DA">{data['sev_counts']['opportunity']:,}</div></div>
</div>
<h2>Issues by category</h2><table><tr><th>Category</th><th>Critical</th><th>Warning</th><th>Opportunity</th></tr>"""]
    if for_pdf:  # Qt's PDF renderer has no CSS grid: use a table for the KPI row
        kpis = [("Health score", f"{h}/100", hcol), ("Pages crawled", f"{data['total']:,}", "#1F2328"),
                ("Indexable", f"{data['indexable']:,}", "#1F2328"), ("Critical", f"{data['sev_counts']['critical']:,}", "#CF222E"),
                ("Warnings", f"{data['sev_counts']['warning']:,}", "#BF8700"),
                ("Opportunities", f"{data['sev_counts']['opportunity']:,}", "#0969DA")]
        cells = "".join(f"<td style='padding:10px'><span style='color:#656D76'>{k}</span><br>"
                        f"<span style='font-size:22px;font-weight:bold;color:{c}'>{v}</span></td>" for k, v, c in kpis)
        first = parts[0]
        start, end = first.index('<div class="grid">'), first.index("<h2>Issues by category</h2>")
        parts[0] = first[:start] + f"<table width='100%' cellspacing='6'><tr>{cells}</tr></table>" + first[end:]
    for cat in CATEGORIES:
        if cat in by_cat:
            c = by_cat[cat]
            parts.append(f"<tr><td>{e(cat)}</td><td>{c['critical'] or ''}</td><td>{c['warning'] or ''}</td><td>{c['opportunity'] or ''}</td></tr>")
    parts.append("</table><h2>Status codes</h2><table><tr><th>Status</th><th>Pages</th></tr>")
    for st, n in data["status"]:
        parts.append(f"<tr><td>{e(str(st if st else 'No response / blocked'))}</td><td>{n:,}</td></tr>")
    parts.append("</table><h2>Findings and how to fix them</h2>")
    for i in data["issues"]:
        urls = i["urls"][:max_urls]
        lis = "".join(f"<li>{e(u)}{(' — ' + e(d)) if d else ''}</li>" for u, d in urls)
        more = f"<li>… and {i['count'] - len(urls):,} more (see the CSV/Excel export)</li>" if i["count"] > len(urls) else ""
        listing = f"<ul class='urls'>{lis}{more}</ul>" if for_pdf else \
            f"<details><summary>Affected URLs ({i['count']:,})</summary><ul class='urls'>{lis}{more}</ul></details>"
        parts.append(f"""<div class="issue"><span class="pill" style="background:{sev_color[i['severity']]}">{SEV_LABEL[i['severity']]}</span>
<span class="muted"> {e(i['category'])}</span><h3>{e(i['title'])} · {i['count']:,}</h3>
<p><b>Why it matters:</b> {e(i['why'])}</p><p><b>How to fix:</b> {e(i['fix'])}</p>{listing}</div>""")
    if not data["issues"]:
        parts.append("<p>No issues found. 🎉</p>")
    parts.append(f"<footer class='muted'>Generated by {e(brand)}"
                 f"{'' if brand == APP_NAME else ''} · {datetime.now().strftime('%Y-%m-%d %H:%M')}</footer></div></body></html>")
    return "".join(parts)


def write_pdf(path: Path, html_text: str) -> Path:
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    app = QGuiApplication.instance()
    if app is None:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QGuiApplication([])
    writer = QPdfWriter(str(path))
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(14, 14, 14, 14),
                                     QPageLayout.Millimeter))
    writer.setResolution(110)
    doc = QTextDocument()
    doc.setDefaultStyleSheet("body{font-family:Arial} table{border-collapse:collapse} td,th{padding:4px;border:1px solid #ddd}")
    doc.setHtml(html_text)
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print_(writer)
    return path


# ------------------------------------------------------------------------------- AI prompt
PROMPT_TEXT = {
    "en": {
        "title": "SEO AUDIT — AI ANALYSIS PACK",
        "lang": "English",
    },
    "ar": {
        "title": "تدقيق SEO — حزمة التحليل بالذكاء الاصطناعي",
        "lang": "Arabic (Modern Standard Arabic, right-to-left)",
    },
}


def render_prompt(data: dict, language: str = "en", max_urls: int = 500) -> str:
    t = PROMPT_TEXT.get(language, PROMPT_TEXT["en"])
    lines = [f"# {t['title']}", "", f"Website: {data['start_url']}", f"Crawled: {data['finished'] or data['started']}",
             f"Pages crawled: {data['total']:,} · Indexable: {data['indexable']:,} · Health score: {data['health']}/100", "",
             "---", "", "## PROMPT", "",
             "You are a senior technical SEO consultant and project manager. Turn the verified crawl findings below into "
             "a practical, prioritised execution plan.", "",
             f"OUTPUT LANGUAGE: {t['lang']}. Keep URLs unchanged.", "",
             "RULES:",
             "- Use only the evidence in this file. Never invent URLs, metrics or causes.",
             "- Group URLs that share the same fix into one task, and list ALL affected URLs for each task "
             "(split long lists into numbered batches rather than dropping any).",
             "- For each task give: ID, title, priority (P1–P4) with a one-line reason, evidence, affected URLs, the exact fix, "
             "implementation notes, how to validate the fix, owner (SEO / developer / content) and effort (S/M/L).",
             "- Score priority by impact × number of affected URLs ÷ effort. Critical findings come first.",
             "- Separate crawler facts from assumptions, and flag anything that needs manual checking.",
             "- Never recommend blanket redirects, noindex, canonical changes or deletions without checking page intent.",
             "- Structure: 1) Executive summary for a non-technical client, 2) Prioritised task list, 3) Quick wins (under 1 day), "
             "4) Dependencies, 5) QA checklist.", "",
             "## FINDINGS", ""]
    if not data["issues"]:
        lines.append("No issues were found.")
    for i in data["issues"]:
        lines += [f"### [{SEV_LABEL[i['severity']]}] {i['title']}", f"- Category: {i['category']}",
                  f"- Affected URLs: {i['count']:,}", f"- Why it matters: {i['why']}", f"- Suggested fix: {i['fix']}", "- URLs:"]
        for u, d in i["urls"][:max_urls]:
            lines.append(f"  - {u}" + (f" — {d}" if d else ""))
        if i["count"] > max_urls:
            lines.append(f"  - … {i['count'] - max_urls:,} more in the master CSV")
        lines.append("")
    lines += ["---", "", "The master CSV exported alongside this file has one row per page with every metric and the "
              "list of issues for that page, if more detail is needed."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------- bundle
def export_bundle(session_path: str | Path, formats: set[str], out_root: Path, brand: str = "", color: str = "#00E676",
                  logo: str = "", language: str = "en", folder: Path | None = None) -> tuple[Path, list[Path]]:
    db = dbm.connect(Path(session_path) / "crawl.db", readonly=True)
    try:
        data = collect(db)
        dest = folder or export_dir_for(out_root, data["start_url"])
        dest.mkdir(parents=True, exist_ok=True)
        host = strip_www(urlsplit(data["start_url"]).hostname or "site")
        files: list[Path] = []
        if "master_csv" in formats:
            files.append(write_master_csv(db, dest / f"{host}_master.csv"))
        if "csv" in formats:
            sub = dest / "csv"
            sub.mkdir(exist_ok=True)
            files += write_csv_set(db, sub)
        if "xlsx" in formats:
            files.append(write_xlsx(db, dest / f"{host}_audit.xlsx", data))
        if "json" in formats:
            files.append(write_json(db, dest / f"{host}_audit.json", data))
        if "html" in formats:
            p = dest / f"{host}_report.html"
            p.write_text(render_html(data, brand, color, logo), encoding="utf-8")
            files.append(p)
        if "pdf" in formats:
            files.append(write_pdf(dest / f"{host}_report.pdf", render_html(data, brand, color, logo, max_urls=25, for_pdf=True)))
        if "prompt" in formats:
            p = dest / f"{host}_AI_prompt.md"
            p.write_text(render_prompt(data, language), encoding="utf-8")
            files.append(p)
        return dest, files
    finally:
        db.close()
