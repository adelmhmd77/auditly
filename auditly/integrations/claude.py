"""Claude-powered analysis: one-shot AI tasks over crawl data, and "chat with your crawl"."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable

import anthropic

from ..audits import all_audits
from ..crawl import db as dbm
from ..export.exporters import SEV_LABEL, collect

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
LANG_NAME = {"en": "English", "ar": "Arabic (Modern Standard Arabic)"}

BASE_SYSTEM = ("You are a senior technical SEO consultant working inside Auditly, a website crawler. "
               "Base every statement on the crawl data provided; never invent URLs or numbers. "
               "When you are inferring rather than reading data, say so. Format answers in clear Markdown with "
               "headings, short paragraphs, bullet lists and tables where they help.")


class AIError(RuntimeError):
    pass


def _client(api_key: str) -> anthropic.Anthropic:
    if not api_key:
        raise AIError("Add your Anthropic API key in Settings → AI to use the AI features.")
    return anthropic.Anthropic(api_key=api_key, max_retries=3)


def _wrap_errors(fn):
    def inner(*a, **kw):
        try:
            return fn(*a, **kw)
        except AIError:
            raise
        except anthropic.AuthenticationError:
            raise AIError("The Anthropic API key was rejected. Check it in Settings → AI.")
        except anthropic.PermissionDeniedError:
            raise AIError("This API key doesn't have access to the selected model.")
        except anthropic.NotFoundError:
            raise AIError("Model not found. Check the model name in Settings → AI.")
        except anthropic.RateLimitError:
            raise AIError("Rate limited by the Anthropic API. Wait a minute and try again.")
        except anthropic.APIStatusError as e:
            raise AIError(f"Anthropic API error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError:
            raise AIError("Couldn't reach the Anthropic API. Check your internet connection.")
    return inner


@_wrap_errors
def stream_text(api_key: str, model: str, system: str, user_content, on_text: Callable[[str], None],
                effort: str = "medium", max_tokens: int = 64000) -> str:
    """Stream a single answer. `user_content` is a string or a list of content blocks."""
    client = _client(api_key)
    out = []
    with client.beta.messages.stream(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for text in stream.text_stream:
            out.append(text)
            on_text(text)
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise AIError("Claude declined this request. Try rephrasing it.")
    if msg.stop_reason == "max_tokens":
        on_text("\n\n_(Answer cut off at the length limit.)_")
    return "".join(out)


# ----------------------------------------------------------------------------------- data packing
def _rows(db, q, params=()):
    return [dict(r) for r in db.execute(q, params)]


def _table(rows: list[dict], cols: list[str], limit: int) -> str:
    lines = ["\t".join(cols)]
    for r in rows[:limit]:
        lines.append("\t".join(str(r.get(c, "") or "").replace("\t", " ").replace("\n", " ")[:200] for c in cols))
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more rows not shown")
    return "\n".join(lines)


def _findings(data: dict, per_issue: int) -> str:
    out = []
    for i in data["issues"]:
        out.append(f"### [{SEV_LABEL[i['severity']]}] {i['title']} ({i['category']}) — {i['count']} URLs\n"
                   f"Fix guidance: {i['fix']}\n" +
                   "\n".join(f"- {u}" + (f" — {d}" if d else "") for u, d in i["urls"][:per_issue]))
    return "\n\n".join(out) or "No issues found."


def _overview(data: dict) -> str:
    return (f"Website: {data['start_url']}\nPages crawled: {data['total']}\nIndexable: {data['indexable']}\n"
            f"Health score: {data['health']}/100\nAvg response: {data['avg_ms']} ms\n"
            f"Findings: {data['sev_counts']['critical']} critical, {data['sev_counts']['warning']} warnings, "
            f"{data['sev_counts']['opportunity']} opportunities\n"
            f"Status codes: {', '.join(f'{s}: {n}' for s, n in data['status'])}")


PAGE_Q = ("SELECT p.url, p.title, p.meta_description, p.h1, p.word_count, p.top_keyword, p.depth, p.schema_types, "
          "COALESCE(s.inlinks,0) AS inlinks, s.link_score FROM pages p LEFT JOIN scores s ON s.url=p.url "
          "WHERE p.internal=1 AND p.status=200 AND p.indexability='Indexable' ")

TASKS = {
    "summary": {"label": "Executive summary", "desc": "Plain-language summary of site health for clients and managers.",
                "effort": "medium"},
    "plan": {"label": "Prioritised task list", "desc": "Issues scored by impact, effort and affected URLs.",
             "effort": "high"},
    "rewrite": {"label": "Title & meta rewrites", "desc": "New titles and meta descriptions for pages with problems.",
                "effort": "medium"},
    "linking": {"label": "Internal linking ideas", "desc": "Which page should link to which, with anchor text.",
                "effort": "high"},
    "intent": {"label": "Search intent per URL", "desc": "Informational / commercial / transactional / navigational.",
               "effort": "low"},
    "clusters": {"label": "Topic clusters", "desc": "Site-wide topical map grouping pages into clusters.",
                 "effort": "medium"},
    "cannibal": {"label": "Cannibalisation check", "desc": "Pages likely competing for the same queries (semantic).",
                 "effort": "high"},
    "schema": {"label": "Schema generator", "desc": "JSON-LD for pages missing structured data.", "effort": "medium"},
    "alt": {"label": "Alt text generator", "desc": "Looks at images missing alt text and writes descriptions.",
            "effort": "low"},
    "quality": {"label": "Content quality & gaps", "desc": "Scores depth, originality, helpfulness and gaps for a page.",
                "effort": "high"},
}


def build_task(task: str, db_path: str | Path, language: str = "en", page_url: str = "") -> tuple[str, object]:
    """Returns (system, user_content) for an AI task."""
    db = dbm.connect(db_path, readonly=True)
    try:
        data = collect(db)
        lang = LANG_NAME.get(language, "English")
        system = BASE_SYSTEM + f"\nWrite your entire answer in {lang}. Keep URLs, code and JSON unchanged."
        ov = _overview(data)
        if task == "summary":
            user = (f"{ov}\n\nFindings:\n{_findings(data, 5)}\n\nWrite an executive summary for a non-technical client: "
                    "overall verdict, the 3–5 most important problems and why they matter for traffic/revenue, quick wins, "
                    "and a suggested 30/60/90-day plan. Avoid jargon; keep it under 600 words.")
        elif task == "plan":
            user = (f"{ov}\n\nFindings:\n{_findings(data, 25)}\n\nCreate a prioritised task list. For each task: ID, title, "
                    "priority P1–P4, impact (1–5), effort (1–5), number of affected URLs, owner (SEO/dev/content), exact fix, "
                    "how to validate. Score = impact × log(affected URLs + 1) ÷ effort. Present as a table sorted by score, "
                    "then detail the top 10 tasks.")
        elif task == "rewrite":
            ids = ("t_missing", "t_dup", "t_long", "t_short", "t_px", "m_missing", "m_dup", "m_long", "m_short")
            urls = [r[0] for r in db.execute(f"SELECT DISTINCT url FROM issues WHERE audit_id IN ({','.join('?' * len(ids))})", ids)]
            rows = [r for r in _rows(db, PAGE_Q) if r["url"] in set(urls)][:60]
            if not rows:
                raise AIError("No pages with title or meta description problems were found. Nothing to rewrite.")
            user = (f"Pages with title/meta description problems:\n{_table(rows, ['url', 'title', 'meta_description', 'h1', 'top_keyword'], 60)}\n\n"
                    "For each page write a new title (max 60 chars, ~580px) and meta description (120–155 chars) that match "
                    "the page's likely intent, include the main keyword naturally, and are unique. Output a Markdown table: "
                    "URL | New title | New meta description | Why.")
        elif task == "linking":
            rows = _rows(db, PAGE_Q + "ORDER BY s.link_score DESC LIMIT 250")
            user = (f"Indexable pages (inlinks = internal pages linking to it, link_score = internal PageRank 0–100):\n"
                    f"{_table(rows, ['url', 'title', 'h1', 'inlinks', 'link_score', 'depth'], 250)}\n\n"
                    "Suggest 20–40 internal links that would most help weakly linked but important pages. Output a table: "
                    "Source page | Target page | Suggested anchor text | Reason. Prefer topically related pairs and strong sources.")
        elif task == "intent":
            rows = _rows(db, PAGE_Q + "ORDER BY p.depth LIMIT 200")
            user = (f"{_table(rows, ['url', 'title', 'h1'], 200)}\n\nClassify each URL's primary search intent "
                    "(Informational, Commercial investigation, Transactional, Navigational) and guess the main target query. "
                    "Output a table: URL | Intent | Likely target query | Confidence. Then summarise the intent mix.")
        elif task == "clusters":
            rows = _rows(db, PAGE_Q + "ORDER BY p.depth LIMIT 400")
            user = (f"{_table(rows, ['url', 'title', 'h1'], 400)}\n\nGroup these pages into topic clusters. For each cluster: "
                    "name, suggested pillar page, member URLs, and missing subtopics worth creating. Finish with a site-wide "
                    "topical map (as a nested list) and the biggest coverage gaps.")
        elif task == "cannibal":
            rows = _rows(db, PAGE_Q + "ORDER BY p.url LIMIT 400")
            user = (f"{_table(rows, ['url', 'title', 'h1', 'top_keyword'], 400)}\n\nFind groups of pages that likely target "
                    "the same search query or intent (keyword cannibalisation), judging meaning rather than exact words. For "
                    "each group: URLs, shared intent, and a recommendation (merge + 301, differentiate, canonicalise, or keep).")
        elif task == "schema":
            rows = _rows(db, PAGE_Q + "AND (p.schema_types IS NULL OR p.schema_types='') ORDER BY s.link_score DESC LIMIT 10")
            if not rows:
                raise AIError("Every indexable page already has structured data. Nothing to generate.")
            user = (f"Pages without structured data:\n{_table(rows, ['url', 'title', 'meta_description', 'h1'], 10)}\n\n"
                    "For each page, pick the most appropriate schema.org type(s) and write ready-to-paste JSON-LD. Use "
                    "placeholders like \"TODO: …\" for facts that aren't in the data. Explain which rich results it enables.")
        elif task == "alt":
            imgs = _rows(db, "SELECT l.src AS page, l.dst AS image FROM links l WHERE l.kind='img' AND (l.anchor IS NULL OR l.anchor='') "
                             "AND (l.dst LIKE '%.jpg' OR l.dst LIKE '%.jpeg' OR l.dst LIKE '%.png' OR l.dst LIKE '%.webp' "
                             "OR l.dst LIKE '%.gif') GROUP BY l.dst LIMIT 8")
            if not imgs:
                raise AIError("No images without alt text were found in this crawl.")
            blocks: list = []
            for i, im in enumerate(imgs, 1):
                blocks.append({"type": "text", "text": f"Image {i}: {im['image']} (on page {im['page']})"})
                blocks.append({"type": "image", "source": {"type": "url", "url": im["image"]}})
            blocks.append({"type": "text", "text": "Write concise, descriptive alt text (max 125 characters) for each image above. "
                                                   "Output a table: Image URL | Page | Suggested alt text. Mark purely decorative "
                                                   "images as alt=\"\"."})
            return system, blocks
        elif task == "quality":
            url = page_url or data["start_url"]
            text = fetch_page_text(url)
            p = _rows(db, "SELECT title, meta_description, h1, word_count FROM pages WHERE url=?", (url,))
            meta = p[0] if p else {}
            user = (f"URL: {url}\nTitle: {meta.get('title', '')}\nMeta description: {meta.get('meta_description', '')}\n"
                    f"H1: {meta.get('h1', '')}\n\nMain text:\n\"\"\"\n{text[:60000]}\n\"\"\"\n\n"
                    "Score this page 1–10 on depth, originality, helpfulness, E-E-A-T signals and AI-citation readiness (clear "
                    "answers, lists, FAQs). Identify the likely search intent, content gaps versus what a searcher would expect, "
                    "and give a prioritised list of concrete improvements.")
        else:
            raise AIError(f"Unknown AI task {task}")
        return system, user
    finally:
        db.close()


def fetch_page_text(url: str) -> str:
    import httpx
    from lxml import etree, html as lhtml
    r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (compatible; Auditly/1.0)"})
    doc = lhtml.fromstring(r.content)
    body = doc.find(".//body")
    body = body if body is not None else doc
    etree.strip_elements(body, "script", "style", "noscript", "template", "svg", with_tail=False)
    for tag in ("nav", "footer", "header", "aside"):
        for el in body.iter(tag):
            el.drop_tree()
    return "\n".join(line.strip() for line in body.text_content().splitlines() if line.strip())


# ----------------------------------------------------------------------------------- chat with your crawl
SQL_TOOL = {
    "name": "run_sql",
    "description": "Run a read-only SQLite SELECT query against the crawl database and get up to 200 rows back as "
                   "tab-separated text. Use it to answer questions about pages, links, issues and scores.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "A single SELECT statement."}},
                     "required": ["query"], "additionalProperties": False},
    "strict": True,
}


def _schema_doc() -> str:
    audits = "\n".join(f"  {a.id}: [{a.severity}] {a.category} — {a.title}" for a in all_audits())
    return f"""Crawl database (SQLite):
- pages(url PK, internal 1/0, depth, status (0 = no response/blocked), redirect_to, content_type, size bytes, response_ms,
  ttfb_ms, title, title_len, title_px, meta_description, meta_description_len, h1, h1_count, h2_count, canonical,
  meta_robots, x_robots_tag, indexability ('Indexable', 'Non-Indexable: noindex', 'Non-Indexable: canonicalised',
  'Non-Indexable: redirect 301', 'Blocked by robots.txt', ...), lang, hreflang_count, viewport, word_count, text_ratio,
  readability, content_hash, top_keyword, top_keyword_density, images, images_missing_alt, internal_links, external_links,
  body_internal_links, scripts, stylesheets, render_blocking, schema_types (comma list), author, published, modified,
  last_modified, content_encoding, cache_control, hsts, csp, mixed_content, error, crawled_at)
- links(src, dst, anchor, internal 1/0, nofollow 1/0, kind 'a'|'img'|'redirect', in_body 1/0)
- scores(url, inlinks = distinct internal pages linking here, link_score = internal PageRank 0-100)
- issues(audit_id, url, detail) — one row per finding. audit ids:
{audits}
- hreflang(src, lang, href); sitemap_urls(url, sitemap, lastmod); resources(url, kind, status, size, content_type);
  psi(url, strategy, score, lcp ms, inp ms, cls, fcp, ttfb); meta(key, value) with keys start_url, started_at, robots_txt, ssl, ...
Internal HTML pages: internal=1 AND status=200 AND content_type LIKE '%html%'."""


def _authorizer(action, *args):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def run_sql(db_path: str | Path, query: str) -> str:
    q = query.strip().rstrip(";")
    if ";" in q:
        return "Error: only one statement is allowed."
    db = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    db.set_authorizer(_authorizer)
    try:
        cur = db.execute(q)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(201)
        lines = ["\t".join(cols)] + ["\t".join("" if v is None else str(v)[:300] for v in r) for r in rows[:200]]
        if len(rows) > 200:
            lines.append("... more rows (refine the query or use COUNT/LIMIT)")
        return "\n".join(lines) if rows else "\t".join(cols) + "\n(no rows)"
    except sqlite3.Error as e:
        return f"SQL error: {e}"
    finally:
        db.close()


class CrawlChat:
    """Multi-turn chat where Claude can query the crawl database."""

    def __init__(self, api_key: str, model: str, db_path: str | Path, language: str = "en"):
        self.api_key, self.model, self.db_path = api_key, model or DEFAULT_MODEL, db_path
        self.messages: list = []
        db = dbm.connect(db_path, readonly=True)
        start = dbm.get_meta(db, "start_url", "")
        db.close()
        self.system = (BASE_SYSTEM + f"\n\nYou are answering questions about the crawl of {start}. Use the run_sql tool to look "
                       "up facts — don't guess. Run as many queries as you need, then answer concisely, showing URLs and "
                       "counts. Reply in the user's language (Arabic or English).\n\n" + _schema_doc())

    @_wrap_errors
    def ask(self, question: str, on_tool: Callable[[str], None] | None = None) -> str:
        client = _client(self.api_key)
        self.messages.append({"role": "user", "content": question})
        for _ in range(12):
            resp = client.beta.messages.create(
                model=self.model, max_tokens=16000, thinking={"type": "adaptive"}, output_config={"effort": "medium"},
                betas=[FALLBACK_BETA], fallbacks="default",
                system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                tools=[SQL_TOOL], messages=self.messages)
            self.messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "refusal":
                return "Claude declined to answer this. Try rephrasing the question."
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text") or "(no answer)"
            results = []
            for b in resp.content:
                if b.type != "tool_use":
                    continue
                q = b.input.get("query", "") if isinstance(b.input, dict) else ""
                if on_tool:
                    on_tool(q)
                out = run_sql(self.db_path, q) if q else "Error: missing query"
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out[:30000],
                                "is_error": out.startswith(("SQL error", "Error"))})
            self.messages.append({"role": "user", "content": results})
        return "I ran out of steps while looking this up. Try a more specific question."


def json_dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False)
