# Contributing to Auditly

Thanks for helping! Bug reports, new audits, translations and integrations are all welcome.

## Set up

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip …
.venv/bin/python run_auditly.py               # desktop app
.venv/bin/python run_auditly.py crawl https://example.com --max-urls 50
```

## Project layout

```
auditly/
  crawl/        config.py (CrawlConfig, YAML profiles) · crawler.py (async engine) · parser.py (HTML extraction) · db.py (SQLite schema)
  audits/       engine.py (Audit, AuditContext, run_audits, link score, health score) · builtin.py (all built-in checks)
  export/       exporters.py (master CSV, CSV set, Excel, JSON, HTML, PDF, AI prompt)
  integrations/ claude.py · pagespeed.py · indexnow.py
  ui/           app.py (main window) · theme.py · i18n.py · widgets.py · views/ (one file per screen)
  cli.py        command line
plugins/        example plugin
profiles/       example crawl profile
```

## The audit format

Every audit is an `Audit`:

| Field | Meaning |
|---|---|
| `id` | unique, stable id (`t_missing`, `x_my_check` for plugins) |
| `category` | one of `auditly.audits.CATEGORIES` |
| `title` | short name shown in the UI |
| `severity` | `critical`, `warning` or `opportunity` |
| `why` | one or two sentences: why it matters |
| `fix` | concrete instructions to fix it |
| `sql` **or** `fn` | a SQL query returning `(url, detail)` rows, or a function `fn(ctx)` yielding `(url, detail)` |
| `site_level` | `True` when the finding is about the whole site rather than individual pages |

Guidelines:

* The affected URL is where the fix happens (e.g. for a broken link, the page containing the link; the broken
  target goes in `detail`).
* Keep `detail` short and specific (`"2 H1s"`, `"→ /old (404)"`).
* Avoid false positives: if a signal is often legitimate, use `opportunity` and say so in `why`.
* Add the audit to `auditly/audits/builtin.py` in the right section, or ship it as a plugin.

### The data you can use

* `pages` — one row per URL (see `auditly/crawl/db.py` → `PAGE_COLS`), plus a JSON `data` column with headings,
  images, schema details, render-blocking resources and custom extractions (`ctx.data(page)`).
* `links (src, dst, anchor, internal, nofollow, kind 'a'|'img'|'redirect', in_body)`
* `hreflang`, `sitemap_urls`, `resources` (images), `psi` (PageSpeed), `scores (url, inlinks, link_score)`, `meta`.
* `AuditContext` helpers: `ctx.pages`, `ctx.html`, `ctx.indexable`, `ctx.by_url`, `ctx.inlinks`,
  `ctx.sitemap_urls`, `ctx.meta(key)`, `ctx.start_url`.

## Plugins

A plugin is a `.py` file in the plugins folder that defines `AUDITS = [Audit(...), …]` or a
`register(add)` function that calls `add(Audit(...))`. Files starting with `_` are ignored. A plugin that fails to
load is skipped with a message; it never breaks a crawl. See `plugins/_example_plugin.py`.

## Translations

UI strings go through `t("English text")` in `auditly/ui/i18n.py`. Add the Arabic (or a new language's) string to
the dictionary; anything missing falls back to English. Test right-to-left layouts with the language switch in the
sidebar.

## Integrations

Add a module under `auditly/integrations/` that stores its results in the crawl database (new table or `meta`),
then add audits that read it (see how `psi` feeds the Performance audits) and a card in
`ui/views/integrations.py`.

## Pull requests

* Keep changes focused; describe what you changed and how you tested it (a crawl of a real or local test site).
* Run `python run_auditly.py audits` to make sure everything loads.
