"""Example Auditly plugin.

Copy this file without the leading underscore (e.g. my_checks.py) into the plugins folder
(Settings → Plugins & data → Open plugins folder) and it runs on the next crawl.

An audit yields (url, detail) pairs. Use `sql` for a simple query, or a function that receives an
AuditContext with: ctx.db (sqlite3), ctx.pages / ctx.html / ctx.indexable (lists of page dicts),
ctx.by_url, ctx.inlinks, ctx.sitemap_urls, ctx.meta(key) and ctx.data(page) (headings, images, schema…).
"""
from auditly.audits import Audit


def long_urls_with_dates(ctx):
    import re
    for p in ctx.indexable:
        if re.search(r"/20\d\d/\d\d/", p["url"]):
            yield p["url"], "dated URL path"


AUDITS = [
    Audit(id="x_dated_urls", category="URL structure", title="Dates in URL paths", severity="opportunity",
          why="Dates in URLs make evergreen content look stale and make updates harder.",
          fix="Use date-free slugs for evergreen content and 301-redirect the old URLs.",
          fn=long_urls_with_dates),
    Audit(id="x_no_og_image", category="Content", title="Very long titles (>90 chars)", severity="opportunity",
          why="Extremely long titles are always truncated.", fix="Shorten the title.",
          sql="SELECT url, title_len FROM pages WHERE internal=1 AND status=200 AND title_len>90"),
]
