"""Built-in audits. Each yields (url, detail) findings."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib import robotparser
from urllib.parse import parse_qsl, urlsplit

from .engine import Audit
from .langcodes import valid_hreflang

H = "internal=1 AND status=200 AND (content_type LIKE '%html%' OR content_type='' OR content_type IS NULL)"
IDX = H + " AND indexability='Indexable'"
GENERIC_ANCHORS = {"click here", "here", "read more", "more", "learn more", "this", "link", "click", "continue",
                   "details", "more info", "go", "this page", "see more", "find out more", "اضغط هنا", "هنا",
                   "المزيد", "اقرأ المزيد", "اعرف المزيد", "التفاصيل", "انقر هنا"}
SOFT404 = re.compile(r"\b(404|not found|page not found|doesn'?t exist|no longer available|nothing (was )?found)\b|"
                     r"الصفحة غير موجودة|غير موجودة|لم يتم العثور", re.I)
OLD_FORMATS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff")
WORD = re.compile(r"\w+", re.U)

B: list[Audit] = []


def audit(id, category, title, severity, why, fix, sql=None, site_level=False):
    def deco(fn=None):
        B.append(Audit(id, category, title, severity, why, fix, sql=sql, fn=fn, site_level=site_level))
        return fn
    if sql:
        deco()
        return None
    return deco


def _date(s: str):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _dupes(ctx, key, pages=None):
    groups = defaultdict(list)
    for p in pages if pages is not None else ctx.indexable:
        v = (p.get(key) or "").strip()
        if v:
            groups[v.lower()].append(p)
    for v, ps in groups.items():
        if len(ps) > 1:
            for p in ps:
                yield p["url"], f"{len(ps)} pages share: {p.get(key)}"[:300]


def _site(ctx):
    return ctx.start_url or (ctx.pages[0]["url"] if ctx.pages else "")


# =====================================================================================
# 1. Response codes & indexability
# =====================================================================================
C = "Response codes"
audit("r_4xx", C, "Client error (4xx) pages", "critical",
      "Pages returning 4xx can't rank and waste crawl budget; internal links to them frustrate users.",
      "Restore the page, 301-redirect it to the most relevant live URL, or remove internal links pointing to it.",
      sql="SELECT url, status FROM pages WHERE internal=1 AND status BETWEEN 400 AND 499")
audit("r_5xx", C, "Server error (5xx) pages", "critical",
      "Server errors stop search engines from indexing the page and, if frequent, slow down crawling of the whole site.",
      "Check server logs for the failing URLs, fix the application error or capacity issue, then re-crawl.",
      sql="SELECT url, status FROM pages WHERE internal=1 AND status BETWEEN 500 AND 599")
audit("r_timeout", C, "Timeouts", "critical",
      "Pages that time out are treated like errors by crawlers.",
      "Investigate slow back-end queries or blocking scripts; make sure the page responds within a few seconds.",
      sql="SELECT url, error FROM pages WHERE internal=1 AND status=0 AND error LIKE 'Timeout%'")
audit("r_noresp", C, "No response / connection error", "critical",
      "The server didn't answer (DNS, TLS or connection failure).",
      "Check DNS, TLS certificates and firewall/WAF rules that may block crawlers.",
      sql="SELECT url, error FROM pages WHERE internal=1 AND status=0 AND error IS NOT NULL "
          "AND error NOT LIKE 'Timeout%' AND error <> 'Blocked by robots.txt'")
audit("r_3xx", C, "Redirected internal URLs (3xx)", "opportunity",
      "Every redirect adds latency and leaks a little link equity.",
      "Update internal links to point straight to the final destination URL.",
      sql="SELECT url, status || ' → ' || COALESCE(redirect_to,'') FROM pages WHERE internal=1 AND status BETWEEN 300 AND 399")
audit("r_302", C, "Temporary redirects (302/303/307)", "warning",
      "Temporary redirects tell search engines the old URL will come back, so signals may not consolidate on the target.",
      "If the move is permanent, change it to a 301 (or 308) redirect.",
      sql="SELECT url, status || ' → ' || COALESCE(redirect_to,'') FROM pages WHERE internal=1 AND status IN (302,303,307)")


def _redirect_paths(ctx):
    by = ctx.by_url
    for p in ctx.pages:
        if not (300 <= (p["status"] or 0) < 400):
            continue
        path, cur, seen = [p["url"]], p.get("redirect_to"), {p["url"]}
        loop = False
        while cur:
            if cur in seen:
                loop = True
                path.append(cur)
                break
            seen.add(cur)
            path.append(cur)
            nxt = by.get(cur)
            if not nxt or not (300 <= (nxt["status"] or 0) < 400):
                break
            cur = nxt.get("redirect_to")
        yield p, path, loop


@audit("r_chain", C, "Redirect chains", "warning",
       "Chains of 2+ redirects slow users down and search engines may stop following them.",
       "Point the first URL (and all internal links) directly at the final destination.")
def _(ctx):
    for p, path, loop in _redirect_paths(ctx):
        if not loop and len(path) > 2:
            yield p["url"], f"{len(path) - 1} hops: " + " → ".join(path)[:400]


@audit("r_loop", C, "Redirect loops", "critical",
       "A loop never resolves, so the page is unreachable for users and search engines.",
       "Fix the redirect rules so the chain ends at a 200 page.")
def _(ctx):
    for p, path, loop in _redirect_paths(ctx):
        if loop:
            yield p["url"], " → ".join(path)[:400]


audit("r_broken_int", C, "Broken internal links", "critical",
      "Links to error pages waste link equity and send users to dead ends.",
      "Update or remove each link on the source page (the affected URL) — the detail shows the broken target.",
      sql="SELECT l.src, '→ ' || l.dst || ' (' || CASE WHEN p.status=0 THEN 'no response' ELSE p.status END || ')' "
          "FROM links l JOIN pages p ON p.url=l.dst WHERE l.kind='a' AND p.internal=1 AND "
          "(p.status>=400 OR (p.status=0 AND p.error IS NOT 'Blocked by robots.txt'))")
BLOCKED_CODES = "(401, 403, 429, 999)"
audit("r_broken_ext", C, "Broken external links", "warning",
      "Outbound links to dead pages hurt user experience and perceived quality.",
      "Replace the link with a working source or remove it.",
      sql="SELECT l.src, '→ ' || l.dst || ' (' || CASE WHEN p.status=0 THEN COALESCE(p.error,'no response') ELSE p.status END || ')' "
          "FROM links l JOIN pages p ON p.url=l.dst WHERE l.kind='a' AND p.internal=0 AND "
          f"((p.status>=400 AND p.status NOT IN {BLOCKED_CODES}) OR (p.status=0 AND p.error NOT LIKE 'Timeout%'))")
audit("r_ext_unverified", C, "External links that couldn't be verified", "opportunity",
      "These sites blocked the crawler or rate-limited it (401/403/429/999, or timed out), so their status is unknown.",
      "Open a few in your browser to confirm they work; lower the crawl speed if many are rate-limited (429).",
      sql="SELECT l.src, '→ ' || l.dst || ' (' || CASE WHEN p.status=0 THEN 'timeout' ELSE p.status END || ')' "
          "FROM links l JOIN pages p ON p.url=l.dst WHERE l.kind='a' AND p.internal=0 AND "
          f"(p.status IN {BLOCKED_CODES} OR (p.status=0 AND p.error LIKE 'Timeout%'))")
audit("r_link_redirect", C, "Internal links to redirects", "opportunity",
      "Linking to redirecting URLs adds a hop for users and crawlers.",
      "Change the link on the source page to the final URL shown in the detail.",
      sql="SELECT l.src, '→ ' || l.dst || ' ⇒ ' || COALESCE(p.redirect_to,'') FROM links l JOIN pages p ON p.url=l.dst "
          "WHERE l.kind='a' AND p.internal=1 AND p.status BETWEEN 300 AND 399")
audit("r_noindex", C, "Noindex pages", "opportunity",
      "These pages ask search engines not to index them. Make sure that is intentional.",
      "Remove the noindex directive (meta robots or X-Robots-Tag) from pages that should rank.",
      sql=f"SELECT url, TRIM(COALESCE(meta_robots,'') || ' ' || COALESCE(x_robots_tag,'')) FROM pages WHERE {H} "
          "AND indexability='Non-Indexable: noindex'")
audit("r_blocked", C, "Blocked by robots.txt", "opportunity",
      "Search engines can't crawl these URLs, so they can't see their content (they may still be indexed without it).",
      "Allow the paths in robots.txt if the pages should rank; use noindex instead if they should be removed.",
      sql="SELECT url, '' FROM pages WHERE internal=1 AND indexability='Blocked by robots.txt'")


@audit("r_soft404", C, "Soft 404 pages", "warning",
       "The page returns 200 but looks like an error page, which Google reports as a soft 404.",
       "Return a real 404/410 status for missing content, or add useful content to the page.")
def _(ctx):
    for p in ctx.html:
        t = f"{p['title'] or ''} {p['h1'] or ''}"
        if SOFT404.search(t) or ((p["word_count"] or 0) < 15 and p["depth"]):
            yield p["url"], f"title: {p['title'] or '—'} · {p['word_count']} words"


# =====================================================================================
# 2. Page titles
# =====================================================================================
C = "Page titles"
audit("t_missing", C, "Missing title", "critical",
      "The title is the main headline in search results and a strong relevance signal.",
      "Add a unique, descriptive <title> of about 30–60 characters to every page.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND (title IS NULL OR title='')")


@audit("t_dup", C, "Duplicate titles", "warning",
       "Identical titles make pages compete with each other and confuse searchers.",
       "Write a unique title for each page that reflects its specific content.")
def _(ctx):
    yield from _dupes(ctx, "title")


audit("t_long", C, "Title too long (>60 characters)", "opportunity",
      "Long titles get truncated in search results.",
      "Keep the most important words first and trim the title to ~60 characters.",
      sql=f"SELECT url, title_len || ' chars: ' || title FROM pages WHERE {H} AND title_len>60")
audit("t_short", C, "Title too short (<30 characters)", "opportunity",
      "Very short titles miss the chance to describe the page and include relevant keywords.",
      "Expand the title to 30–60 characters with descriptive keywords.",
      sql=f"SELECT url, title_len || ' chars: ' || title FROM pages WHERE {H} AND title_len>0 AND title_len<30")
audit("t_px", C, "Title wider than 580 pixels", "opportunity",
      "Google truncates desktop titles by pixel width (~580px), not character count.",
      "Shorten the title or use narrower characters.",
      sql=f"SELECT url, title_px || ' px: ' || title FROM pages WHERE {H} AND title_px>580")
audit("t_same_h1", C, "Title same as H1", "opportunity",
      "Not an error, but using a different (complementary) H1 lets you cover more query variations.",
      "Consider making the title and H1 complementary rather than identical.",
      sql=f"SELECT url, title FROM pages WHERE {H} AND title<>'' AND LOWER(TRIM(title))=LOWER(TRIM(h1))")
audit("t_multiple", C, "Multiple title tags", "warning",
      "With several <title> tags, search engines may pick the wrong one.",
      "Keep exactly one <title> in the <head>.",
      sql=f"SELECT url, title_count || ' titles' FROM pages WHERE {H} AND title_count>1")

# =====================================================================================
# 3. Meta descriptions
# =====================================================================================
C = "Meta descriptions"
audit("m_missing", C, "Missing meta description", "warning",
      "Without a description, search engines generate a snippet that may not sell the click.",
      "Write a unique, compelling meta description of ~70–160 characters.",
      sql=f"SELECT url, '' FROM pages WHERE {IDX} AND (meta_description IS NULL OR meta_description='')")


@audit("m_dup", C, "Duplicate meta descriptions", "warning",
       "Duplicate descriptions make different pages look the same in search results.",
       "Write a unique description for each page.")
def _(ctx):
    yield from _dupes(ctx, "meta_description")


audit("m_long", C, "Meta description too long (>160)", "opportunity",
      "Long descriptions are truncated in search results.",
      "Trim to ~155–160 characters and put the key message first.",
      sql=f"SELECT url, meta_description_len || ' chars' FROM pages WHERE {H} AND meta_description_len>160")
audit("m_short", C, "Meta description too short (<70)", "opportunity",
      "Short descriptions waste valuable space in the search snippet.",
      "Expand to 70–160 characters with a clear benefit and call to action.",
      sql=f"SELECT url, meta_description_len || ' chars' FROM pages WHERE {H} AND meta_description_len>0 AND meta_description_len<70")
audit("m_multiple", C, "Multiple meta descriptions", "warning",
      "Several description tags are ambiguous; search engines may ignore them.",
      "Keep exactly one meta description tag.",
      sql=f"SELECT url, meta_description_count || ' tags' FROM pages WHERE {H} AND meta_description_count>1")

# =====================================================================================
# 4. Headings
# =====================================================================================
C = "Headings"
audit("h_missing", C, "Missing H1", "warning",
      "The H1 tells users and search engines what the page is about.",
      "Add one descriptive H1 near the top of the main content.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND h1_count=0")
audit("h_multi", C, "Multiple H1s", "opportunity",
      "Several H1s can dilute the main topic of the page.",
      "Use a single H1 for the main topic and H2–H6 for sub-sections.",
      sql=f"SELECT url, h1_count || ' H1s' FROM pages WHERE {H} AND h1_count>1")


@audit("h_dup", C, "Duplicate H1s", "opportunity",
       "Pages sharing an H1 may be competing for the same topic.",
       "Give each page a unique H1 that matches its specific intent.")
def _(ctx):
    yield from _dupes(ctx, "h1")


@audit("h_skip", C, "Skipped heading levels", "opportunity",
       "Jumping levels (e.g. H2 → H4) breaks the document outline for screen readers and parsers.",
       "Nest headings in order: H1 → H2 → H3 …")
def _(ctx):
    for p in ctx.html:
        prev = 0
        for lvl, t in ctx.data(p).get("headings", []):
            if prev and lvl > prev + 1:
                yield p["url"], f"H{prev} → H{lvl} ({t[:60]})"
                break
            prev = lvl


@audit("h_empty", C, "Empty headings", "opportunity",
       "Empty heading tags add noise for assistive technology and crawlers.",
       "Remove empty headings or add text (icons-only headings need an accessible label).")
def _(ctx):
    for p in ctx.html:
        empties = [lvl for lvl, t in ctx.data(p).get("headings", []) if not t.strip()]
        if empties:
            yield p["url"], ", ".join(f"H{x}" for x in empties[:10])


@audit("h_mismatch", C, "H1 and title don't share any words", "opportunity",
       "When the title and H1 describe different things, relevance signals are mixed.",
       "Make sure the title and the H1 describe the same main topic.")
def _(ctx):
    for p in ctx.indexable:
        t = {w for w in WORD.findall((p["title"] or "").lower()) if len(w) > 2}
        h = {w for w in WORD.findall((p["h1"] or "").lower()) if len(w) > 2}
        if t and h and not (t & h):
            yield p["url"], f"title: {p['title'][:80]} · H1: {p['h1'][:80]}"


# =====================================================================================
# 5. Canonicals
# =====================================================================================
C = "Canonicals"
audit("c_missing", C, "Missing canonical", "warning",
      "Without a canonical, parameters and duplicates can split ranking signals.",
      "Add a self-referencing <link rel=\"canonical\"> with the absolute preferred URL.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND (canonical IS NULL OR canonical='') AND indexability<>'Non-Indexable: noindex'")
audit("c_multiple", C, "Multiple canonicals", "warning",
      "Conflicting canonical tags are ignored by search engines.",
      "Keep exactly one canonical tag (check CMS plugins/themes adding a second one).",
      sql=f"SELECT url, canonical_count || ' canonical tags' FROM pages WHERE {H} AND canonical_count>1")
audit("c_non_self", C, "Canonicalised pages (non-self canonical)", "opportunity",
      "These pages point their canonical to another URL, so they won't be indexed themselves.",
      "Confirm each is a true duplicate; otherwise make the canonical self-referencing.",
      sql=f"SELECT url, '→ ' || canonical FROM pages WHERE {H} AND indexability='Non-Indexable: canonicalised'")


@audit("c_bad_target", C, "Canonical points to a redirect or error", "critical",
       "A canonical must point to a live (200), indexable URL or it will be ignored.",
       "Update the canonical to the final 200 URL.")
def _(ctx):
    by = ctx.by_url
    for p in ctx.html:
        c = p["canonical"]
        if c and c != p["url"] and c in by:
            t = by[c]
            if (t["status"] or 0) != 200:
                yield p["url"], f"→ {c} ({t['status'] or t['error']})"


@audit("c_noindex", C, "Canonical points to a noindex page", "critical",
       "Mixed signals: the canonical target asks not to be indexed.",
       "Point the canonical at an indexable page, or remove noindex from the target.")
def _(ctx):
    by = ctx.by_url
    for p in ctx.html:
        c = p["canonical"]
        if c and c != p["url"] and c in by and by[c]["indexability"] == "Non-Indexable: noindex":
            yield p["url"], f"→ {c}"


@audit("c_chain", C, "Canonical chains", "warning",
       "The canonical target is itself canonicalised elsewhere; search engines may not follow the chain.",
       "Point the canonical straight at the final preferred URL.")
def _(ctx):
    by = ctx.by_url
    for p in ctx.html:
        c = p["canonical"]
        if c and c != p["url"] and c in by:
            c2 = by[c]["canonical"]
            if c2 and c2 != c:
                yield p["url"], f"→ {c} → {c2}"


@audit("c_hreflang", C, "Canonical and hreflang conflict", "warning",
       "hreflang should reference canonical URLs; pointing at canonicalised pages sends mixed signals.",
       "Make hreflang annotations reference the canonical version of each page.")
def _(ctx):
    by = ctx.by_url
    for src, lang, href in ctx.db.execute("SELECT src, lang, href FROM hreflang"):
        t = by.get(href)
        if t and t["indexability"] == "Non-Indexable: canonicalised":
            yield src, f"hreflang {lang} → {href} (canonicalised to {t['canonical']})"


# =====================================================================================
# 6. Content
# =====================================================================================
C = "Content"
audit("ct_thin", C, "Thin content (<200 words)", "warning",
      "Pages with little main content rarely satisfy search intent.",
      "Expand with useful, original content, merge with a related page, or noindex if it has no search value.",
      sql=f"SELECT url, word_count || ' words' FROM pages WHERE {IDX} AND word_count<200")


@audit("ct_dup", C, "Exact duplicate content", "warning",
       "Identical pages compete with each other and split ranking signals.",
       "Keep one version and 301-redirect or canonicalise the others to it.")
def _(ctx):
    groups = defaultdict(list)
    for p in ctx.indexable:
        if p["content_hash"]:
            groups[p["content_hash"]].append(p["url"])
    for urls in groups.values():
        if len(urls) > 1:
            for u in urls:
                yield u, f"{len(urls)} identical pages, e.g. {next(x for x in urls if x != u)}"


@audit("ct_near", C, "Near-duplicate content", "warning",
       "Pages that are ~90%+ similar look like duplicates to search engines.",
       "Differentiate the content, consolidate the pages, or canonicalise to the main version.")
def _(ctx):
    items = [(p["url"], int(p["simhash"], 16), p["content_hash"]) for p in ctx.indexable
             if p["simhash"] and (p["word_count"] or 0) >= 50]
    buckets = defaultdict(list)
    for i, (_, h, _) in enumerate(items):
        for band in range(4):
            buckets[(band, (h >> (band * 16)) & 0xFFFF)].append(i)
    pairs = set()
    for idxs in buckets.values():
        if len(idxs) > 200:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if items[i][2] == items[j][2]:
                    continue  # exact dupes are reported separately
                if bin(items[i][1] ^ items[j][1]).count("1") <= 4:
                    pairs.add((min(i, j), max(i, j)))
    for i, j in pairs:
        yield items[i][0], f"≈ {items[j][0]}"
        yield items[j][0], f"≈ {items[i][0]}"


@audit("ct_stuffing", C, "High keyword repetition", "opportunity",
       "One word makes up a large share of the main content. On normal prose this can read as keyword stuffing; "
       "on listings (downloads, products) it's often fine.",
       "Check the page reads naturally; use synonyms and related terms instead of repeating one keyword.")
def _(ctx):
    for p in ctx.indexable:
        kw, dens = (p["top_keyword"] or ""), p["top_keyword_density"] or 0
        if (p["word_count"] or 0) >= 300 and dens >= 5 and kw and kw not in urlsplit(p["url"]).netloc.lower():
            yield p["url"], f'"{kw}" = {dens}% of words'

audit("ct_readability", C, "Hard to read (Flesch < 30)", "opportunity",
      "Very complex text is harder to understand and less likely to be quoted in answers.",
      "Use shorter sentences, simpler words, sub-headings and lists. (English text only.)",
      sql=f"SELECT url, 'Flesch ' || readability FROM pages WHERE {IDX} AND readability IS NOT NULL AND readability<30")
audit("ct_text_ratio", C, "Low text-to-HTML ratio (<10%)", "opportunity",
      "A very low share of visible text often means heavy markup/scripts or little content.",
      "Reduce boilerplate markup and inline scripts; add meaningful content.",
      sql=f"SELECT url, text_ratio || '%' FROM pages WHERE {IDX} AND text_ratio<10")
audit("ct_no_body_links", C, "No internal links in the main content", "opportunity",
      "Contextual links in body copy pass more value than navigation links and help discovery.",
      "Add relevant in-text links to related pages.",
      sql=f"SELECT url, '' FROM pages WHERE {IDX} AND word_count>=200 AND COALESCE(body_internal_links,0)=0")


@audit("ct_stale", C, "Content not updated in over a year", "opportunity",
       "Freshness matters for many queries and for AI answers that prefer current information.",
       "Review and update the content; show an accurate 'last updated' date.")
def _(ctx):
    now = datetime.now(timezone.utc)
    for p in ctx.indexable:
        d = _date(p["modified"]) or _date(p["last_modified"]) or _date(p["published"])
        if d and (now - d).days > 365:
            yield p["url"], f"last updated {d.date().isoformat()} ({(now - d).days} days ago)"


# =====================================================================================
# 7. Images
# =====================================================================================
C = "Images"


def _images(ctx):
    for p in ctx.html:
        for im in ctx.data(p).get("images", []):
            yield p, im


@audit("i_missing_alt", C, "Images missing alt attribute", "warning",
       "Alt text describes images to screen readers and search engines (image search, context).",
       "Add descriptive alt text to every meaningful image; use alt=\"\" only for decorative ones.")
def _(ctx):
    for p in ctx.html:
        miss = [im["src"] for im in ctx.data(p).get("images", []) if im.get("alt") is None]
        if miss:
            yield p["url"], f"{len(miss)} images, e.g. {miss[0]}"


@audit("i_empty_alt", C, "Images with empty alt", "opportunity",
       "alt=\"\" is right for decorative images, but content images need a description.",
       "Check each image; add alt text if it conveys information.")
def _(ctx):
    for p in ctx.html:
        e = [im["src"] for im in ctx.data(p).get("images", []) if im.get("alt") is not None and not im["alt"].strip()]
        if e:
            yield p["url"], f"{len(e)} images, e.g. {e[0]}"


@audit("i_dims", C, "Images missing width/height (CLS risk)", "opportunity",
       "Without dimensions the browser can't reserve space, causing layout shift (CLS).",
       "Add width and height attributes (or CSS aspect-ratio) to every image.")
def _(ctx):
    for p in ctx.html:
        m = [im["src"] for im in ctx.data(p).get("images", []) if not (im.get("w") and im.get("h"))]
        if m:
            yield p["url"], f"{len(m)} images, e.g. {m[0]}"


@audit("i_format", C, "Images not in a modern format", "opportunity",
       "WebP and AVIF are typically 25–50% smaller than JPEG/PNG at the same quality.",
       "Serve WebP/AVIF (e.g. with <picture> or your CDN's automatic format conversion).")
def _(ctx):
    for p in ctx.html:
        old = {im["src"] for im in ctx.data(p).get("images", [])
               if urlsplit(im["src"]).path.lower().endswith(OLD_FORMATS)}
        if old:
            yield p["url"], f"{len(old)} images, e.g. {sorted(old)[0]}"


@audit("i_lazy", C, "Below-the-fold images not lazy-loaded", "opportunity",
       "Loading every image up-front slows the initial render.",
       "Add loading=\"lazy\" to images below the fold (but not to the main/LCP image).")
def _(ctx):
    for p in ctx.html:
        imgs = ctx.data(p).get("images", [])
        m = [im["src"] for im in imgs[3:] if im.get("loading") != "lazy"]
        if m:
            yield p["url"], f"{len(m)} images, e.g. {m[0]}"


@audit("i_broken", C, "Broken images", "critical",
       "Broken images look unprofessional and waste requests.",
       "Fix the image path or remove the reference.")
def _(ctx):
    bad = {r[0]: r[1] or r[2] for r in ctx.db.execute(
        "SELECT url, status, error FROM resources WHERE kind='image' AND (status>=400 OR status=0)")}
    if bad:
        for src, dst in ctx.db.execute("SELECT DISTINCT src, dst FROM links WHERE kind='img'"):
            if dst in bad:
                yield src, f"{dst} ({bad[dst]})"


@audit("i_large", C, "Oversized images (>200 KB)", "warning",
       "Heavy images are the most common cause of slow pages and poor LCP.",
       "Compress, resize to the displayed size, and serve modern formats.")
def _(ctx):
    big = {r[0]: r[1] for r in ctx.db.execute("SELECT url, size FROM resources WHERE kind='image' AND size>204800")}
    if big:
        for src, dst in ctx.db.execute("SELECT DISTINCT src, dst FROM links WHERE kind='img'"):
            if dst in big:
                yield src, f"{dst} ({big[dst] // 1024} KB)"


# =====================================================================================
# 8. Links & architecture
# =====================================================================================
C = "Links"
audit("l_deep", C, "Deep pages (click depth > 3)", "opportunity",
      "Pages many clicks from the homepage get crawled less and are seen as less important.",
      "Link to important pages from the homepage, hubs or navigation to bring them within 3 clicks.",
      sql=f"SELECT url, 'depth ' || depth FROM pages WHERE {IDX} AND depth>3")


@audit("l_few_inlinks", C, "Pages with only one internal inlink", "warning",
       "Weakly linked pages receive little internal PageRank and are harder to discover.",
       "Add contextual links from related, well-linked pages.")
def _(ctx):
    for p in ctx.indexable:
        n = ctx.inlinks.get(p["url"], 0)
        if p["depth"] and n <= 1:
            yield p["url"], f"{n} inlink"


@audit("l_orphan", C, "Orphan pages (in sitemap, no inlinks)", "warning",
       "Pages no other page links to are hard for users and crawlers to find.",
       "Link to these pages from relevant content, or remove them from the sitemap if they're obsolete.")
def _(ctx):
    for u in ctx.sitemap_urls:
        p = ctx.by_url.get(u)
        if p and p["status"] == 200 and not ctx.inlinks.get(u, 0) and p["url"] != ctx.start_url:
            yield u, "0 internal inlinks"


audit("l_many_out", C, "Too many internal links on page (>150)", "opportunity",
      "Very large numbers of links dilute the value passed by each one.",
      "Trim mega-menus and footers; prioritise the most important links.",
      sql=f"SELECT url, internal_links || ' internal links' FROM pages WHERE {H} AND internal_links>150")
audit("l_no_out", C, "Pages without internal outlinks", "opportunity",
      "Dead-end pages stop crawlers and users from moving through the site.",
      "Add navigation and contextual links to related pages.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND COALESCE(internal_links,0)=0")


@audit("l_generic", C, "Generic anchor text", "opportunity",
       "Anchors like \"click here\" or \"read more\" give no context about the target page.",
       "Use descriptive anchor text that says what the linked page is about.")
def _(ctx):
    q = "SELECT src, dst, anchor FROM links WHERE kind='a' AND internal=1"
    hits = defaultdict(list)
    for src, dst, anchor in ctx.db.execute(q):
        if (anchor or "").strip().lower().strip(".…»>›→ ") in GENERIC_ANCHORS:
            hits[src].append(f"\"{anchor}\" → {dst}")
    for src, items in hits.items():
        yield src, f"{len(items)} links, e.g. {items[0]}"[:300]


@audit("l_empty_anchor", C, "Links without anchor text", "opportunity",
       "Links with no text (or alt/aria-label) give no context and are inaccessible.",
       "Add text, an image alt, or an aria-label to every link.")
def _(ctx):
    q = "SELECT src, COUNT(*), MIN(dst) FROM links WHERE kind='a' AND internal=1 AND (anchor IS NULL OR anchor='') GROUP BY src"
    for src, n, dst in ctx.db.execute(q):
        yield src, f"{n} links, e.g. → {dst}"


@audit("l_nofollow", C, "Nofollow internal links", "warning",
       "nofollow on internal links stops PageRank flowing to your own pages.",
       "Remove rel=\"nofollow\" from internal links (use noindex/robots for pages you want excluded).")
def _(ctx):
    q = "SELECT src, COUNT(*), MIN(dst) FROM links WHERE kind='a' AND internal=1 AND nofollow=1 GROUP BY src"
    for src, n, dst in ctx.db.execute(q):
        yield src, f"{n} links, e.g. → {dst}"


# =====================================================================================
# 9. Security
# =====================================================================================
C = "Security"


@audit("s_http_site", C, "Site not served over HTTPS", "critical",
       "HTTPS is a ranking signal and browsers flag HTTP pages as \"Not secure\".",
       "Install a TLS certificate, serve every page over HTTPS and 301-redirect HTTP to HTTPS.", site_level=True)
def _(ctx):
    if ctx.start_url.startswith("http://"):
        yield ctx.start_url, "start URL uses http://"


@audit("s_http_redirect", C, "HTTP doesn't redirect to HTTPS", "critical",
       "If the HTTP version stays reachable, duplicates and insecure sessions are possible.",
       "Add a site-wide 301 redirect from http:// to https://.", site_level=True)
def _(ctx):
    r = ctx.meta("http_redirect")
    if r and r.get("status") and not (r["status"] in (301, 308, 302, 307) and r.get("location", "").startswith("https://")):
        yield _site(ctx), f"http:// returned {r['status']} {r.get('location', '')}"


audit("s_http_pages", C, "Internal pages on HTTP", "warning",
      "Some internal URLs are still served over insecure HTTP.",
      "Update internal links to HTTPS and redirect the HTTP versions.",
      sql="SELECT url, status FROM pages WHERE internal=1 AND url LIKE 'http://%' AND EXISTS "
          "(SELECT 1 FROM meta WHERE key='start_url' AND value LIKE 'https://%')")
audit("s_mixed", C, "Mixed content", "critical",
      "HTTPS pages loading HTTP resources trigger browser warnings or blocked resources.",
      "Load every image, script, stylesheet and iframe over HTTPS.",
      sql=f"SELECT url, mixed_content || ' insecure resources' FROM pages WHERE {H} AND mixed_content>0")
audit("s_forms", C, "Insecure forms", "critical",
      "Forms posting to HTTP (or password fields on HTTP pages) expose user data.",
      "Serve the page over HTTPS and make form actions use https://.",
      sql=f"SELECT url, insecure_forms || ' forms' FROM pages WHERE {H} AND insecure_forms>0")
audit("s_hsts", C, "Missing HSTS header", "warning",
      "Strict-Transport-Security makes browsers always use HTTPS, preventing downgrade attacks.",
      "Send `Strict-Transport-Security: max-age=31536000; includeSubDomains` on HTTPS responses.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND url LIKE 'https://%' AND (hsts IS NULL OR hsts='')")


@audit("s_headers", C, "Missing security headers", "opportunity",
       "CSP, X-Frame-Options and X-Content-Type-Options protect users against XSS, clickjacking and MIME sniffing.",
       "Add Content-Security-Policy, X-Frame-Options (or CSP frame-ancestors) and X-Content-Type-Options: nosniff.")
def _(ctx):
    for p in ctx.html:
        miss = [n for n, k in (("CSP", "csp"), ("X-Frame-Options", "x_frame"), ("X-Content-Type-Options", "x_content_type"))
                if not p[k] and not (k == "x_frame" and "frame-ancestors" in (p["csp"] or ""))]
        if miss:
            yield p["url"], "missing: " + ", ".join(miss)


@audit("s_ssl", C, "SSL certificate problem or expiring soon", "critical",
       "An expired or invalid certificate blocks visitors with a full-page browser warning.",
       "Renew the certificate (enable auto-renewal, e.g. Let's Encrypt) and check the chain is complete.", site_level=True)
def _(ctx):
    s = ctx.meta("ssl")
    if not s:
        return
    if not s.get("valid"):
        yield _site(ctx), s.get("error", "invalid certificate")
    elif s.get("days_left", 999) < 30:
        yield _site(ctx), f"expires in {s['days_left']} days ({s.get('expires', '')[:10]})"


audit("s_protocol_rel", C, "Protocol-relative links (//)", "opportunity",
      "Protocol-relative URLs are an outdated pattern and can load resources over HTTP.",
      "Use explicit https:// URLs.",
      sql=f"SELECT url, protocol_relative || ' links' FROM pages WHERE {H} AND protocol_relative>0")

# =====================================================================================
# 10. URL structure
# =====================================================================================
C = "URL structure"


def _paths(ctx):
    for p in ctx.html:
        yield p, urlsplit(p["url"])


@audit("u_upper", C, "URLs with uppercase characters", "opportunity",
       "URLs are case-sensitive; mixed case can create duplicates.",
       "Use lowercase URLs and redirect uppercase variants.")
def _(ctx):
    for p, s in _paths(ctx):
        if s.path != s.path.lower():
            yield p["url"], ""


@audit("u_underscore", C, "URLs with underscores", "opportunity",
       "Google treats hyphens as word separators, but not underscores.",
       "Use hyphens (-) instead of underscores (_) in new URLs.")
def _(ctx):
    for p, s in _paths(ctx):
        if "_" in s.path:
            yield p["url"], ""


@audit("u_space", C, "URLs with spaces", "warning",
       "Spaces get encoded as %20, which is error-prone when shared or linked.",
       "Replace spaces with hyphens and redirect the old URLs.")
def _(ctx):
    for p, s in _paths(ctx):
        if "%20" in s.path or " " in s.path or "+" in s.path:
            yield p["url"], ""


@audit("u_non_ascii", C, "URLs with non-ASCII characters", "opportunity",
       "Non-ASCII URLs work, but must be consistently percent-encoded or they can break when shared.",
       "Make sure links use one consistent (encoded) form; consider transliterated slugs.")
def _(ctx):
    for p, s in _paths(ctx):
        if any(ord(ch) > 127 for ch in s.path) or re.search(r"%[89A-Fa-f][0-9A-Fa-f]", s.path):
            yield p["url"], ""


audit("u_long", C, "Overly long URLs (>115 characters)", "opportunity",
      "Long URLs are harder to read, share and may get truncated in results.",
      "Use short, descriptive slugs.",
      sql=f"SELECT url, LENGTH(url) || ' chars' FROM pages WHERE {H} AND LENGTH(url)>115")


@audit("u_params", C, "URLs with many parameters (>3)", "opportunity",
       "Parameter-heavy URLs create crawl traps and duplicates.",
       "Limit parameters, use canonical tags, and block useless combinations.")
def _(ctx):
    for p, s in _paths(ctx):
        n = len(parse_qsl(s.query, keep_blank_values=True))
        if n > 3:
            yield p["url"], f"{n} parameters"


@audit("u_slash", C, "Trailing-slash inconsistency", "warning",
       "Both /page and /page/ return 200, so the same content lives at two URLs.",
       "Pick one form and 301-redirect the other (or canonicalise).")
def _(ctx):
    ok = {p["url"] for p in ctx.html}
    for u in ok:
        s = urlsplit(u)
        if s.path.endswith("/") and len(s.path) > 1:
            other = u.replace(s.path, s.path.rstrip("/"), 1)
            if other in ok:
                yield u, f"also 200: {other}"


@audit("u_param_dup", C, "Duplicate URLs through parameters", "warning",
       "The same content is reachable with different query strings.",
       "Canonicalise parameter URLs to the clean version, and avoid linking to them.")
def _(ctx):
    groups = defaultdict(list)
    for p, s in _paths(ctx):
        if p["content_hash"]:
            groups[(s.netloc, s.path, p["content_hash"])].append(p["url"])
    for urls in groups.values():
        if len(urls) > 1 and any("?" in u for u in urls):
            for u in urls:
                if "?" in u:
                    yield u, f"same content as {min(x for x in urls if x != u)}"


# =====================================================================================
# 11. Hreflang
# =====================================================================================
C = "Hreflang"


def _hreflang(ctx):
    rows = defaultdict(list)
    for src, lang, href in ctx.db.execute("SELECT src, lang, href FROM hreflang"):
        rows[src].append((lang, href))
    return rows


@audit("hl_invalid", C, "Invalid hreflang codes", "warning",
       "Invalid language/region codes are ignored by search engines.",
       "Use ISO 639-1 language codes and optional ISO 3166-1 region codes (e.g. en, en-GB, ar-SA, x-default).")
def _(ctx):
    for src, items in _hreflang(ctx).items():
        bad = [l for l, _ in items if not valid_hreflang(l)]
        if bad:
            yield src, ", ".join(bad[:10])


@audit("hl_return", C, "Missing hreflang return links", "warning",
       "hreflang must be reciprocal: if A points to B, B must point back to A, or the pair is ignored.",
       "Add the missing return annotation on the target page.")
def _(ctx):
    rows = _hreflang(ctx)
    for src, items in rows.items():
        for lang, href in items:
            if href == src or href not in rows:
                continue
            if not any(h == src for _, h in rows[href]):
                yield src, f"{lang} → {href} has no link back"


@audit("hl_xdefault", C, "Missing x-default", "opportunity",
       "x-default tells search engines which page to show users who don't match any listed language.",
       "Add <link rel=\"alternate\" hreflang=\"x-default\" href=\"…\"> to each set.")
def _(ctx):
    for src, items in _hreflang(ctx).items():
        if not any(l.lower() == "x-default" for l, _ in items):
            yield src, f"{len(items)} hreflang tags, no x-default"


@audit("hl_self", C, "Missing self-referencing hreflang", "opportunity",
       "Each page in an hreflang set should list itself.",
       "Add an hreflang entry pointing to the page's own URL.")
def _(ctx):
    for src, items in _hreflang(ctx).items():
        if not any(h == src for _, h in items):
            yield src, ""


@audit("hl_bad_target", C, "hreflang to non-200 or noindex URLs", "warning",
       "Alternates must be live, indexable pages.",
       "Point hreflang at the final 200, indexable version of each alternate.")
def _(ctx):
    by = ctx.by_url
    for src, items in _hreflang(ctx).items():
        for lang, href in items:
            t = by.get(href)
            if t and (t["status"] != 200 or t["indexability"] == "Non-Indexable: noindex"):
                yield src, f"{lang} → {href} ({t['status'] or t['indexability']})"


@audit("hl_lang", C, "Page language doesn't match hreflang", "opportunity",
       "The html lang attribute disagrees with the page's own hreflang code.",
       "Make <html lang> and the self-referencing hreflang use the same language.")
def _(ctx):
    rows = _hreflang(ctx)
    for src, items in rows.items():
        p = ctx.by_url.get(src)
        if not p or not p["lang"]:
            continue
        own = [l for l, h in items if h == src and l.lower() != "x-default"]
        if own and own[0].split("-")[0].lower() != p["lang"].split("-")[0].lower():
            yield src, f"lang={p['lang']} · hreflang={own[0]}"


# =====================================================================================
# 12. Structured data
# =====================================================================================
C = "Structured data"


@audit("sd_invalid", C, "Invalid JSON-LD", "critical",
       "Malformed JSON-LD is ignored entirely, so no rich results are possible.",
       "Fix the JSON syntax (validate with the Rich Results Test or a JSON linter).")
def _(ctx):
    for p in ctx.html:
        errs = ctx.data(p).get("schema", {}).get("errors", [])
        if errs:
            yield p["url"], errs[0]


@audit("sd_required", C, "Structured data missing required properties", "warning",
       "Without required properties the markup isn't eligible for rich results.",
       "Add the missing properties listed for each type.")
def _(ctx):
    for p in ctx.html:
        m = ctx.data(p).get("schema", {}).get("missing", [])
        if m:
            yield p["url"], "; ".join(m[:5])


@audit("sd_recommended", C, "Structured data missing recommended properties", "opportunity",
       "Recommended properties improve how rich results look.",
       "Add the recommended properties where you have the data.")
def _(ctx):
    for p in ctx.html:
        m = ctx.data(p).get("schema", {}).get("recommended", [])
        if m:
            yield p["url"], "; ".join(m[:5])


audit("sd_none", C, "Pages without structured data", "opportunity",
      "Structured data helps search engines and AI systems understand entities on the page.",
      "Add relevant schema.org markup (Organization, BreadcrumbList, Article, Product, FAQPage…).",
      sql=f"SELECT url, '' FROM pages WHERE {IDX} AND (schema_types IS NULL OR schema_types='')")

# =====================================================================================
# 13. Performance
# =====================================================================================
C = "Performance"
audit("p_slow", C, "Slow response (>1 s)", "warning",
      "Slow server responses delay everything else and hurt Core Web Vitals.",
      "Add caching (page cache/CDN), optimise database queries and upgrade hosting if needed.",
      sql=f"SELECT url, response_ms || ' ms' FROM pages WHERE {H} AND response_ms>1000")
audit("p_ttfb", C, "High TTFB (>600 ms)", "opportunity",
      "Time to first byte above ~600 ms leaves less budget for LCP.",
      "Use server-side caching and a CDN close to your users.",
      sql=f"SELECT url, ttfb_ms || ' ms' FROM pages WHERE {H} AND ttfb_ms>600")
audit("p_large", C, "Large HTML (>1 MB)", "warning",
      "Huge HTML documents are slow to download and parse, especially on mobile.",
      "Remove inline data/scripts, paginate long lists, and lazy-load below-the-fold content.",
      sql=f"SELECT url, (size/1024) || ' KB' FROM pages WHERE {H} AND size>1048576")
audit("p_resources", C, "Many resources (>80 scripts, styles and images)", "opportunity",
      "Each request has a cost; too many slow down loading.",
      "Bundle, remove unused scripts and lazy-load images.",
      sql=f"SELECT url, (COALESCE(scripts,0)+COALESCE(stylesheets,0)+COALESCE(images,0)) || ' resources' FROM pages "
          f"WHERE {H} AND (COALESCE(scripts,0)+COALESCE(stylesheets,0)+COALESCE(images,0))>80")
audit("p_blocking", C, "Render-blocking resources", "opportunity",
      "Synchronous scripts and stylesheets in <head> delay first paint.",
      "Add defer/async to scripts, inline critical CSS and load the rest asynchronously.",
      sql=f"SELECT url, render_blocking || ' blocking resources' FROM pages WHERE {H} AND render_blocking>2")
audit("p_compression", C, "No text compression", "warning",
      "Uncompressed HTML is typically 3–5× larger over the network.",
      "Enable Brotli or Gzip on the server/CDN for HTML, CSS and JS.",
      sql=f"SELECT url, (size/1024) || ' KB uncompressed' FROM pages WHERE {H} AND size>1024 AND (content_encoding IS NULL OR content_encoding='')")
audit("p_cache", C, "No caching headers", "opportunity",
      "Without Cache-Control/ETag, browsers and CDNs can't reuse responses.",
      "Send Cache-Control (and ETag/Last-Modified) with sensible lifetimes.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND (cache_control IS NULL OR cache_control='')")
audit("p_lcp", C, "Poor LCP (>4 s, PageSpeed Insights)", "warning",
      "Largest Contentful Paint measures loading; over 4 s is rated poor.",
      "Optimise the hero image/text, server response time and render-blocking resources.",
      sql="SELECT url, strategy || ': ' || ROUND(lcp/1000.0,1) || ' s' FROM psi WHERE lcp>4000")
audit("p_inp", C, "Poor INP (>500 ms, PageSpeed Insights)", "warning",
      "Interaction to Next Paint measures responsiveness; over 500 ms is rated poor.",
      "Break up long JavaScript tasks and reduce third-party scripts.",
      sql="SELECT url, strategy || ': ' || CAST(inp AS INT) || ' ms' FROM psi WHERE inp>500")
audit("p_cls", C, "Poor CLS (>0.25, PageSpeed Insights)", "warning",
      "Cumulative Layout Shift measures visual stability; over 0.25 is rated poor.",
      "Reserve space for images, ads and embeds; avoid inserting content above existing content.",
      sql="SELECT url, strategy || ': ' || ROUND(cls,2) FROM psi WHERE cls>0.25")
audit("p_score", C, "Low PageSpeed score (<50)", "opportunity",
      "Lighthouse performance score below 50 indicates significant speed problems.",
      "Open the page in PageSpeed Insights and work through the top opportunities.",
      sql="SELECT url, strategy || ': ' || CAST(score AS INT) FROM psi WHERE score<50")

# =====================================================================================
# 14. Mobile
# =====================================================================================
C = "Mobile"
audit("mb_viewport", C, "Missing viewport meta tag", "critical",
      "Without a viewport tag, mobile browsers render the desktop layout zoomed out.",
      "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND (viewport IS NULL OR viewport='')")
audit("mb_viewport_bad", C, "Viewport not mobile-friendly", "warning",
      "The viewport isn't set to device width, or zooming is disabled (an accessibility problem).",
      "Use width=device-width, initial-scale=1 and don't set user-scalable=no / maximum-scale=1.",
      sql=f"SELECT url, viewport FROM pages WHERE {H} AND viewport<>'' AND (viewport NOT LIKE '%device-width%' "
          "OR REPLACE(viewport,' ','') LIKE '%user-scalable=no%' OR REPLACE(viewport,' ','') LIKE '%maximum-scale=1%')")
audit("mb_parity", C, "Mobile content differs from desktop", "warning",
      "Google indexes the mobile version; content or links missing on mobile won't count.",
      "Serve the same main content and links to mobile users.",
      sql=f"SELECT url, 'desktop ' || word_count || ' words / ' || internal_links || ' links · mobile ' || "
          f"mobile_word_count || ' words / ' || mobile_links || ' links' FROM pages WHERE {H} AND mobile_word_count IS NOT NULL "
          "AND (mobile_word_count < word_count*0.8 OR mobile_links < (internal_links+external_links)*0.7)")
audit("mb_font", C, "Small font sizes (<12px inline)", "opportunity",
      "Text below 12px is hard to read on phones.",
      "Use a base font size of at least 16px and avoid tiny inline sizes.",
      sql=f"SELECT url, small_fonts || ' inline styles' FROM pages WHERE {H} AND small_fonts>0")

# =====================================================================================
# 15. Pagination & facets
# =====================================================================================
C = "Pagination"
audit("pg_canon_first", C, "Paginated pages canonicalised to page 1", "warning",
      "Canonicalising page 2+ to page 1 hides the items listed on deeper pages.",
      "Give each paginated page a self-referencing canonical.",
      sql=f"SELECT url, '→ ' || canonical FROM pages WHERE {H} AND rel_prev<>'' AND indexability='Non-Indexable: canonicalised'")
audit("pg_noindex", C, "Paginated pages set to noindex", "opportunity",
      "Noindexing pagination can, over time, stop links on those pages being followed.",
      "Keep paginated pages indexable with self-canonicals unless they're low value.",
      sql=f"SELECT url, '' FROM pages WHERE {H} AND (rel_prev<>'' OR rel_next<>'') AND indexability='Non-Indexable: noindex'")


@audit("pg_broken", C, "rel=next/prev pointing to non-200 URLs", "warning",
       "Pagination hints must point at live pages.",
       "Fix the rel=next/prev URLs.")
def _(ctx):
    by = ctx.by_url
    for p in ctx.html:
        for rel in ("rel_next", "rel_prev"):
            t = by.get(p[rel]) if p[rel] else None
            if t and t["status"] != 200:
                yield p["url"], f"{rel[4:]} → {p[rel]} ({t['status']})"


@audit("pg_trap", C, "Faceted navigation crawl trap", "warning",
       "Many parameter variations of the same path waste crawl budget.",
       "Block facet combinations in robots.txt, use canonical tags, or render filters without crawlable links.")
def _(ctx):
    groups = defaultdict(list)
    for p in ctx.pages:
        s = urlsplit(p["url"])
        if s.query:
            groups[(s.netloc, s.path)].append(p["url"])
    for (_, path), urls in groups.items():
        if len(urls) >= 25:
            yield urls[0].split("?")[0], f"{len(urls)} parameter variations of {path}"


# =====================================================================================
# 16. Sitemaps & robots.txt
# =====================================================================================
C = "Sitemaps & robots.txt"


@audit("sm_missing", C, "No XML sitemap found", "warning",
       "Sitemaps help search engines discover and prioritise your URLs.",
       "Create an XML sitemap, reference it in robots.txt and submit it in Search Console.", site_level=True)
def _(ctx):
    sm = ctx.meta("sitemaps")
    cfg = ctx.meta("config", {}) or {}
    if sm is not None and (cfg.get("use_sitemaps", True) or cfg.get("mode") == "sitemap") and not ctx.sitemap_urls:
        yield _site(ctx), "checked: " + ", ".join(s["url"] for s in sm)[:300]


@audit("sm_errors", C, "Sitemap errors", "critical",
       "Invalid sitemaps may be ignored completely.",
       "Fix the listed errors so the sitemap validates against the sitemaps.org protocol.", site_level=True)
def _(ctx):
    for s in ctx.meta("sitemaps") or []:
        if s.get("errors"):
            yield s["url"], "; ".join(s["errors"][:3])
        elif s.get("status") not in (200, 0) and s.get("url", "").endswith(".xml") and ctx.sitemap_urls:
            yield s["url"], f"HTTP {s['status']}"


@audit("sm_bad", C, "Sitemap URLs that redirect or error", "warning",
       "Sitemaps should only list final, 200-status URLs.",
       "Replace redirecting URLs with their targets and remove broken ones.")
def _(ctx):
    for u in ctx.sitemap_urls:
        p = ctx.by_url.get(u)
        if p and p["status"] != 200 and p["indexability"] != "Blocked by robots.txt":
            yield u, f"{p['status'] or p['error']}"


@audit("sm_nonindexable", C, "Non-indexable URLs in sitemap", "warning",
       "Listing noindex or canonicalised URLs sends mixed signals.",
       "Only include canonical, indexable URLs in sitemaps.")
def _(ctx):
    for u in ctx.sitemap_urls:
        p = ctx.by_url.get(u)
        if p and p["status"] == 200 and p["indexability"] and p["indexability"] != "Indexable":
            yield u, p["indexability"]


@audit("sm_not_in", C, "Indexable pages missing from sitemap", "opportunity",
       "Pages not in the sitemap may be discovered and recrawled more slowly.",
       "Add every indexable, canonical page to the XML sitemap.")
def _(ctx):
    if not ctx.sitemap_urls:
        return
    for p in ctx.indexable:
        if p["url"] not in ctx.sitemap_urls:
            yield p["url"], ""


@audit("rb_missing", C, "No robots.txt", "opportunity",
       "robots.txt isn't required, but it's where you declare sitemaps and crawl rules.",
       "Add /robots.txt with at least a Sitemap: line.", site_level=True)
def _(ctx):
    st = ctx.meta("robots_status")
    if st is not None and str(st) != "200":
        yield _site(ctx).rstrip("/") + "/robots.txt", f"HTTP {st}"


ROBOTS_OK = {"user-agent", "disallow", "allow", "sitemap", "crawl-delay", "host", "clean-param", "noindex", "request-rate",
             "visit-time", "content-signal"}


@audit("rb_syntax", C, "robots.txt syntax problems", "warning",
       "Unrecognised lines are ignored by crawlers, which may not be what you intended.",
       "Fix or remove the listed lines.", site_level=True)
def _(ctx):
    txt = ctx.meta("robots_txt") or ""
    if not isinstance(txt, str):
        return
    bad = []
    seen_ua = False
    for i, line in enumerate(txt.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            bad.append(f"line {i}: '{line[:40]}'")
            continue
        key = line.split(":", 1)[0].strip().lower()
        if key not in ROBOTS_OK:
            bad.append(f"line {i}: unknown '{key}'")
        if key == "user-agent":
            seen_ua = True
        elif key in ("disallow", "allow") and not seen_ua:
            bad.append(f"line {i}: rule before any User-agent")
    if bad:
        yield _site(ctx).rstrip("/") + "/robots.txt", "; ".join(bad[:5])


@audit("rb_resources", C, "CSS/JS blocked by robots.txt", "warning",
       "Google needs CSS and JavaScript to render pages; blocking them can hurt rankings.",
       "Allow crawling of CSS/JS files in robots.txt.")
def _(ctx):
    txt = ctx.meta("robots_txt") or ""
    if not isinstance(txt, str) or "disallow" not in txt.lower():
        return
    rp = robotparser.RobotFileParser()
    rp.parse(txt.splitlines())
    for p in ctx.html:
        blocked = [u for u in ctx.data(p).get("css_js", []) if urlsplit(u).netloc == urlsplit(p["url"]).netloc
                   and not rp.can_fetch("Googlebot", u)]
        if blocked:
            yield p["url"], f"{len(blocked)} blocked, e.g. {blocked[0]}"


# =====================================================================================
# 17. AI / GEO readiness
# =====================================================================================
C = "AI / GEO readiness"


@audit("ai_bots", C, "AI crawlers blocked in robots.txt", "opportunity",
       "Blocked AI crawlers (GPTBot, ClaudeBot, PerplexityBot…) can't read your content, so you won't be cited in AI answers.",
       "If you want AI visibility, allow these user-agents in robots.txt. Keep the block if it's a deliberate choice.",
       site_level=True)
def _(ctx):
    bots = ctx.meta("ai_bots") or {}
    blocked = [b for b, ok in bots.items() if not ok]
    if blocked:
        yield _site(ctx).rstrip("/") + "/robots.txt", "blocked: " + ", ".join(blocked)


@audit("ai_llms", C, "No llms.txt file", "opportunity",
       "llms.txt is an emerging convention that gives AI tools a curated map of your most useful content.",
       "Publish /llms.txt (Markdown) listing your key pages with one-line descriptions.", site_level=True)
def _(ctx):
    info = ctx.meta("llms_txt") or {}
    if info and not any(v.get("ok") for v in info.values()):
        yield _site(ctx).rstrip("/") + "/llms.txt", f"HTTP {info.get('llms.txt', {}).get('status')}"


audit("ai_structure", C, "Long content without answer-friendly structure", "opportunity",
      "AI systems quote content that's easy to extract: clear headings, lists, tables and short answers.",
      "Break long text into H2/H3 sections, add lists/tables and a short summary answer near the top.",
      sql=f"SELECT url, word_count || ' words, ' || h2_count || ' H2, ' || lists || ' lists' FROM pages WHERE {IDX} "
          "AND word_count>600 AND COALESCE(lists,0)=0 AND COALESCE(tables,0)=0 AND COALESCE(h2_count,0)<2")
audit("ai_faq", C, "Question headings without FAQ markup", "opportunity",
      "Q&A content marked up with FAQPage/QAPage schema is easier for search and AI to extract.",
      "Add FAQPage structured data for the questions and answers on the page.",
      sql=f"SELECT url, question_headings || ' question headings' FROM pages WHERE {IDX} AND question_headings>=2 "
          "AND COALESCE(schema_types,'') NOT LIKE '%FAQPage%' AND COALESCE(schema_types,'') NOT LIKE '%QAPage%'")


@audit("ai_entity", C, "No Organization / WebSite schema on the site", "opportunity",
       "Organization and WebSite markup define your brand entity for search engines and AI.",
       "Add Organization (name, logo, url, sameAs) and WebSite schema to the homepage.", site_level=True)
def _(ctx):
    types = " ".join(p["schema_types"] or "" for p in ctx.html)
    if ctx.html and not any(t in types for t in ("Organization", "LocalBusiness", "Corporation", "Person")):
        yield _site(ctx), "no Organization/LocalBusiness/Person schema found"


def _article_like(p):
    st = p["schema_types"] or ""
    return any(t in st for t in ("Article", "BlogPosting", "NewsArticle")) or (p["word_count"] or 0) >= 800


@audit("ai_author", C, "Articles without author information", "opportunity",
       "Clear authorship supports E-E-A-T (experience, expertise, authority, trust).",
       "Show a named author with a bio/profile page and add author to Article schema.")
def _(ctx):
    for p in ctx.indexable:
        if _article_like(p) and not p["author"]:
            yield p["url"], f"{p['word_count']} words"


@audit("ai_dates", C, "Articles without a published/updated date", "opportunity",
       "Dates help users and AI judge freshness.",
       "Show published and updated dates and add datePublished/dateModified to schema.")
def _(ctx):
    for p in ctx.indexable:
        if _article_like(p) and not (p["published"] or p["modified"]):
            yield p["url"], ""


@audit("ai_citations", C, "Long content without outbound citations", "opportunity",
       "Linking to authoritative sources signals trustworthiness.",
       "Cite and link to reputable sources that support key claims.")
def _(ctx):
    for p in ctx.indexable:
        if (p["word_count"] or 0) >= 800 and not p["external_links"]:
            yield p["url"], f"{p['word_count']} words, 0 external links"


@audit("ai_trust_pages", C, "No About or Contact page found", "opportunity",
       "About and Contact pages are basic trust signals for users, quality raters and AI.",
       "Create clear About and Contact pages and link them site-wide (e.g. footer).", site_level=True)
def _(ctx):
    urls = " ".join(p["url"].lower() for p in ctx.html)
    missing = [n for n, keys in (("About", ("about", "من-نحن", "%d9%85%d9%86-%d9%86%d8%ad%d9%86", "who-we-are")),
                                 ("Contact", ("contact", "اتصل", "%d8%a7%d8%aa%d8%b5%d9%84")))
               if not any(k in urls for k in keys)]
    if ctx.html and missing:
        yield _site(ctx), "not found: " + ", ".join(missing)


BUILTIN = B
