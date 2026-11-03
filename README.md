# Auditly

**Open-source technical SEO crawler and auditor** — a modern desktop app for Windows, macOS and Linux, plus a
command line for CI/CD. Crawl a site, get 125+ checks with severity, affected URLs and how to fix each one, then
export to CSV, Excel, JSON, HTML/PDF or an AI-ready prompt — or ask Claude about your crawl directly.

Light and dark themes · English and Arabic (right-to-left) interface · exports go to your **Downloads/Auditly**
folder by default, or any folder you choose.

---

## Get the app

### Windows (.exe)

* **Download** `Auditly.exe` from the project's GitHub Actions / Releases page and double-click it. No Python needed.
* **Or build it yourself:** install [Python 3.10+](https://www.python.org/downloads/) (tick *“Add python.exe to PATH”*),
  then double-click **`build-windows.bat`**. The app appears in `dist\Auditly.exe`.
* **Or run from source:** double-click **`run-windows.bat`**.

### Linux — install as an app

```bash
./install-linux.sh            # builds if needed, then adds Auditly to your app menu with its icon
./install-linux.sh --uninstall
```

### macOS and Linux (Python)

```bash
./run-linux-mac.sh
```

The first run creates a private `.venv` and installs everything; later runs start straight away.
Fedora: `sudo dnf install python3` · Ubuntu/Debian: `sudo apt install python3 python3-venv` ·
macOS: Python from python.org or `brew install python`.

To build a standalone app instead: `python3 build.py` → `dist/Auditly` (Linux) or `dist/Auditly.app` (macOS).

### Build all three automatically

Push the project to GitHub and run the **Build apps** workflow (Actions tab), or push a tag like `v1.0.0`.
It produces `Auditly.exe`, `Auditly-macOS.zip` and the Linux `Auditly` binary as downloadable artifacts.
(PyInstaller can only build for the system it runs on, which is why the workflow uses Windows, macOS and Linux runners.)

---

## Using it

1. Type a URL in the top bar and press **Start audit** (or Enter). Pick the mode next to it:
   *Spider* (whole site), *List of URLs*, *Sitemap only* or *Single URL*.
2. **Crawl settings** (sliders icon): threads, delay, limits, robots.txt, subdomains, include/exclude regex,
   user-agent (Googlebot, Bingbot, GPTBot, ClaudeBot, PerplexityBot, mobile…), login (Basic auth, cookies, headers),
   JavaScript rendering, mobile-vs-desktop comparison and custom extraction (CSS / XPath / Regex).
   Save and load these as YAML **profiles**.
3. Watch pages appear live. **Pause**, **Resume** or **Stop** at any time; every crawl is saved and an interrupted
   crawl (even after a crash) can be resumed from **History**.
4. When it finishes:
   * **Dashboard** — health score, critical/warning/opportunity counts, top issues, status codes, site checks
     (SSL, robots.txt, sitemap, llms.txt, AI crawler access) and issues by category.
   * **Pages** — every URL with search, filter chips, column picker and a detail panel (issues, inlinks, outlinks).
   * **Issues** — issue → why it matters → how to fix → affected URLs (copy or export).
   * **Site structure** — URL tree, click-depth chart and strongest pages by internal link score.
   * **AI assistant** — Claude-powered tasks and *Chat with your crawl* (see below).
   * **Compare crawls** — before/after: fixed findings, new findings, new/removed URLs, status changes.
   * **Exports** — choose formats and folder.
   * **Integrations** — PageSpeed Insights (Core Web Vitals) and IndexNow.

### Where files go

Exports are saved to **`Downloads/Auditly/<site> <date>/`**. Change the folder in **Exports** or **Settings**, or tick
*“Ask where to save every time”*. Crawl databases live in the app data folder
(`%APPDATA%\Auditly`, `~/Library/Application Support/Auditly`, `~/.local/share/Auditly`).

| Export | What you get |
|---|---|
| Master CSV | One row per URL with every key metric and the list of issues on that page |
| CSV set | pages, external links, links, issues (with fixes), images, hreflang, sitemap URLs, PageSpeed |
| Excel | Summary, issue overview with fixes, all issues, pages, links, images, hreflang, sitemap |
| JSON | Everything above, machine-readable |
| HTML / PDF report | Client-ready report; white-label it with your name, colour and logo in Settings |
| AI prompt (.md) | A ready-to-paste analysis prompt + all findings and URLs, in English or Arabic |

### AI features (Claude)

Add your Anthropic API key in **Settings → AI** (or set `ANTHROPIC_API_KEY`). Default model: `claude-opus-5-5`.

* **Chat with your crawl** — ask “which pages lost internal links?” or “list 404s and who links to them”.
  Claude answers by running read-only SQL against the crawl database (writes are blocked).
* Executive summary · prioritised task list (impact × affected URLs ÷ effort) · title & meta rewrites ·
  internal linking suggestions · search intent per URL · topic clusters · semantic cannibalisation check ·
  schema (JSON-LD) generator · alt text generator (looks at the images) · content quality & gap analysis for a page.
* Output in English or Arabic. Save any result to your exports folder.

Nothing is sent to Claude until you run a task or ask a question.

---

## Checks (126 built in)

| Category | Examples |
|---|---|
| Response codes | 4xx, 5xx, timeouts, connection errors, redirects, 302s that should be 301, redirect chains and loops, broken internal/external links, links to redirects, noindex, blocked by robots.txt, soft 404s |
| Page titles | missing, duplicate, too long/short, wider than 580 px, same as H1, multiple title tags |
| Meta descriptions | missing, duplicate, too long/short, multiple tags |
| Headings | missing/multiple/duplicate H1, skipped levels, empty headings, H1–title mismatch |
| Canonicals | missing, multiple, to redirect/error, to noindex, chains, non-self, canonical–hreflang conflicts |
| Content | thin, exact and near-duplicate (SimHash), high keyword repetition, readability (Flesch), low text ratio, stale content, no in-body links |
| Images | missing/empty alt, missing width/height, non-WebP/AVIF, no lazy-loading, broken, oversized |
| Links | click depth, few inlinks, orphan pages, too many links, dead ends, generic anchors, empty anchors, nofollow internal links, internal PageRank (link score) |
| Security | not HTTPS, HTTP→HTTPS redirect, mixed content, insecure forms, HSTS, CSP/X-Frame-Options/X-Content-Type-Options, SSL expiry, protocol-relative links |
| URL structure | uppercase, underscores, spaces, non-ASCII, long, many parameters, trailing-slash duplicates, parameter duplicates |
| Hreflang | invalid codes, missing return links, missing x-default, missing self-reference, non-200/noindex targets, lang mismatch |
| Structured data | invalid JSON-LD, missing required/recommended properties; JSON-LD, Microdata and RDFa types detected |
| Performance | slow response, TTFB, large HTML, many resources, render-blocking, no compression, no caching headers, LCP/INP/CLS and score via PageSpeed Insights |
| Mobile | missing/bad viewport, mobile vs desktop content parity, small fonts |
| Pagination | rel=next/prev targets, paginated pages canonicalised/noindexed, faceted-navigation crawl traps |
| Sitemaps & robots.txt | missing sitemap, sitemap errors/size/URL limits, non-200 and non-indexable URLs in sitemap, pages missing from sitemap, robots.txt syntax, CSS/JS blocked |
| AI / GEO readiness | AI crawlers (GPTBot, ClaudeBot, PerplexityBot…) blocked, llms.txt, answer-friendly structure, FAQ markup, Organization schema, author, dates, citations, About/Contact pages |

Run `auditly audits` to list them all with their IDs.

---

## Command line (CI/CD, schedules, servers)

```bash
python run_auditly.py crawl https://example.com -f master_csv,xlsx,html,prompt
python run_auditly.py crawl --profile profiles/example.yaml --fail-on critical     # exit 1 if critical issues (CI)
python run_auditly.py crawl https://example.com --min-health 80 --json-summary
python run_auditly.py crawl --list-file urls.txt                                  # list mode
python run_auditly.py crawl --resume "<session folder>"                           # continue an interrupted crawl
python run_auditly.py sessions                                                    # saved crawls
python run_auditly.py compare "<before session>" "<after session>"
python run_auditly.py export "<session>" -f pdf,html -o ~/Desktop
```

The packaged app accepts the same commands (`Auditly.exe crawl …`, `./Auditly crawl …`).

**Scheduled crawls:** use the command line with your system scheduler, e.g. Linux/macOS cron
`0 6 * * 1 /path/to/Auditly crawl https://example.com -q`, or Windows Task Scheduler running
`Auditly.exe crawl https://example.com -q`.

**Docker:**

```bash
docker build -t auditly .
docker run --rm -v "$PWD/reports:/reports" auditly crawl https://example.com -o /reports
```

---

## Plugins and profiles

* **Plugins:** drop a `.py` file into the plugins folder (Settings → *Open plugins folder*). See
  [`plugins/_example_plugin.py`](plugins/_example_plugin.py) and [CONTRIBUTING.md](CONTRIBUTING.md).
* **Profiles:** reusable YAML crawl settings — see [`profiles/example.yaml`](profiles/example.yaml).

## Not included yet (roadmap)

Google Search Console, GA4, Bing Webmaster Tools, CrUX history, Google Indexing API, keyword and backlink providers
(DataForSEO, Semrush, Ahrefs, Majestic, Moz, SerpApi), OpenAI/Gemini as alternative AI providers, a REST API server,
an interactive link-graph view, tap-target analysis (needs a rendered layout), built-in scheduling inside the app,
and Arabic translations of the individual audit names (the interface itself is translated).

## Responsible use

Only crawl sites you own or have permission to audit. Auditly respects robots.txt by default; keep the delay and
thread count reasonable on shared hosting.
