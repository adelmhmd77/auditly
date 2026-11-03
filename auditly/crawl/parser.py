"""HTML parsing and data extraction. Pure functions; run in worker threads."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from urllib.parse import urldefrag, urljoin, urlsplit

from lxml import etree, html as lhtml

from .urls import normalize

LOWER = "translate({},'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "ftp:", "file:", "whatsapp:", "skype:")
CHROME_TAGS = {"nav", "header", "footer", "aside"}
STOPWORDS = set("""a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has have having he
her here hers him his how i if in into is it its just me more most my no nor not now of off on once only or other our
out over own same she should so some such than that the their them then there these they this those through to too
under until up very was we were what when where which while who whom why will with you your yours يمكن هذا هذه التي
الذي على إلى من في عن مع أن إن كان كانت هو هي ثم أو لا ما كل بعد قبل بين عند غير حتى لم لن قد ذلك تلك""".split())

# Required properties for common rich-result types (subset of Google's documentation).
SCHEMA_REQUIRED = {
    "Article": ["headline"], "NewsArticle": ["headline"], "BlogPosting": ["headline"],
    "Product": ["name"], "Offer": ["price", "priceCurrency"],
    "FAQPage": ["mainEntity"], "QAPage": ["mainEntity"], "HowTo": ["name", "step"],
    "BreadcrumbList": ["itemListElement"], "Organization": ["name"], "LocalBusiness": ["name", "address"],
    "Event": ["name", "startDate", "location"], "Recipe": ["name", "image"], "VideoObject": ["name", "thumbnailUrl", "uploadDate"],
    "JobPosting": ["title", "datePosted", "description", "hiringOrganization"], "Review": ["itemReviewed", "author"],
    "SoftwareApplication": ["name"], "Course": ["name", "description"],
}
SCHEMA_RECOMMENDED = {
    "Article": ["author", "datePublished", "image"], "NewsArticle": ["author", "datePublished", "image"],
    "BlogPosting": ["author", "datePublished", "image"],
    "Product": ["image", "offers"], "Organization": ["logo", "url"], "LocalBusiness": ["telephone", "openingHours"],
    "Event": ["image", "offers"], "Recipe": ["recipeIngredient", "recipeInstructions"],
}
# A type is "rich result eligible" when all required props are present (plus one of these for Product).
PRODUCT_ANY = ("offers", "review", "aggregateRating")

# Approximate Arial 20px glyph widths, used by Google for desktop titles (limit ~580px).
_NARROW = set("ijlt.,:;|!'`fI ()[]{}/-\"r")
_WIDE = set("mwMW@%")


def pixel_width(text: str) -> int:
    w = 0.0
    for ch in text:
        if ch in _NARROW:
            w += 5.6
        elif ch in _WIDE:
            w += 16.7
        elif ch.isupper():
            w += 13.3
        elif ch.isdigit():
            w += 11.1
        else:
            w += 10.6
    return int(w)


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def flesch(text: str) -> float | None:
    """Flesch reading ease (0-100, higher = easier). Only meaningful for Latin-script text."""
    words = re.findall(r"[A-Za-z]+", text)
    if len(words) < 100 or len(words) < len(text.split()) * 0.6:
        return None
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    syl = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syl / len(words))
    return round(max(0.0, min(100.0, score)), 1)


def simhash(words: list[str]) -> str:
    if len(words) < 3:
        return ""
    v = [0] * 64
    for i in range(len(words) - 2):
        h = int.from_bytes(hashlib.md5(" ".join(words[i:i + 3]).encode()).digest()[:8], "big")
        for b in range(64):
            v[b] += 1 if h >> b & 1 else -1
    out = 0
    for b in range(64):
        if v[b] > 0:
            out |= 1 << b
    return f"{out:016x}"


def _iter_schema(node, out: list):
    if isinstance(node, list):
        for n in node:
            _iter_schema(n, out)
    elif isinstance(node, dict):
        if "@graph" in node:
            _iter_schema(node["@graph"], out)
        if "@type" in node:
            out.append(node)
        for k, v in node.items():
            if k not in ("@graph",) and isinstance(v, (dict, list)):
                _iter_schema(v, out)


def analyse_jsonld(blocks: list[str]) -> dict:
    types, errors, missing, recommended, eligible = [], [], [], [], []
    for raw in blocks:
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError as e:
            errors.append(f"Invalid JSON-LD: {e}"[:200])
            continue
        nodes: list = []
        _iter_schema(data, nodes)
        for n in nodes:
            ts = n.get("@type")
            for t in ts if isinstance(ts, list) else [ts]:
                if not isinstance(t, str):
                    continue
                types.append(t)
                req = SCHEMA_REQUIRED.get(t, [])
                miss = [p for p in req if p not in n]
                if t == "Product" and not any(p in n for p in PRODUCT_ANY):
                    miss.append("offers|review|aggregateRating")
                if miss:
                    missing.append(f"{t}: {', '.join(miss)}")
                elif req:
                    eligible.append(t)
                rec = [p for p in SCHEMA_RECOMMENDED.get(t, []) if p not in n]
                if rec:
                    recommended.append(f"{t}: {', '.join(rec)}")
    return {"types": sorted(set(types)), "errors": errors, "missing": missing,
            "recommended": recommended, "eligible": sorted(set(eligible)), "nodes": len(types)}


def _ancestor_tags(el) -> set:
    return {a.tag for a in el.iterancestors() if isinstance(a.tag, str)}


def parse_html(url: str, body: bytes, enc: str | None, strip_params: frozenset, extractions: list | None = None) -> tuple[dict, list, list]:
    """Returns (row_data, links, hreflang). links = [(dst, anchor, nofollow, kind, in_body)]."""
    doc = None
    for encoding in (enc, None):
        try:
            parser = lhtml.HTMLParser(encoding=encoding) if encoding else lhtml.HTMLParser()
            doc = lhtml.fromstring(body, parser=parser)
            break
        except (etree.ParserError, ValueError, LookupError):
            continue
    if doc is None:
        return {}, [], []

    def text(el) -> str:
        return " ".join(el.text_content().split())

    d: dict = {}
    extra: dict = {}
    https = url.startswith("https://")

    base = url
    base_href = doc.xpath("//base/@href")
    if base_href:
        base = urljoin(url, base_href[0].strip())

    titles = doc.xpath("//head//title | //title")
    titles = list(dict.fromkeys(titles))
    d["title"] = text(titles[0]) if titles else ""
    d["title_count"] = len(titles)
    d["title_len"] = len(d["title"])
    d["title_px"] = pixel_width(d["title"])

    name_l = LOWER.format("@name")
    prop_l = LOWER.format("@property")
    rel_l = LOWER.format("normalize-space(@rel)")
    descs = doc.xpath(f"//meta[{name_l}='description']/@content")
    d["meta_description"] = " ".join(descs[0].split()) if descs else ""
    d["meta_description_count"] = len(descs)
    d["meta_description_len"] = len(d["meta_description"])
    robots = doc.xpath(f"//meta[{name_l}='robots' or {name_l}='googlebot']/@content")
    d["meta_robots"] = ", ".join(r.strip().lower() for r in robots)
    canon = doc.xpath(f"//link[contains(concat(' ', {rel_l}, ' '), ' canonical ')]/@href")
    d["canonical"] = normalize(urljoin(base, canon[0].strip()), strip_params) or "" if canon else ""
    d["canonical_count"] = len(canon)
    vp = doc.xpath(f"//meta[{name_l}='viewport']/@content")
    d["viewport"] = vp[0].strip() if vp else ""
    d["lang"] = (doc.xpath("//html/@lang") or [""])[0].strip()
    nxt = doc.xpath(f"//link[{rel_l}='next']/@href")
    prv = doc.xpath(f"//link[{rel_l}='prev' or {rel_l}='previous']/@href")
    d["rel_next"] = urljoin(base, nxt[0].strip()) if nxt else ""
    d["rel_prev"] = urljoin(base, prv[0].strip()) if prv else ""

    # hreflang
    hreflang = []
    for el in doc.xpath(f"//link[{rel_l}='alternate'][@hreflang]"):
        href = normalize(urljoin(base, (el.get("href") or "").strip()), strip_params)
        if href:
            hreflang.append(((el.get("hreflang") or "").strip(), href))
    d["hreflang_count"] = len(hreflang)

    # headings
    headings = []
    for h in doc.xpath("//h1|//h2|//h3|//h4|//h5|//h6"):
        headings.append((int(h.tag[1]), text(h)[:200]))
    h1s = [t for lvl, t in headings if lvl == 1]
    d["h1"] = h1s[0] if h1s else ""
    d["h1_count"] = len(h1s)
    d["h2_count"] = sum(1 for lvl, _ in headings if lvl == 2)
    extra["headings"] = headings[:300]
    d["question_headings"] = sum(1 for lvl, t in headings if lvl >= 2 and t.rstrip().endswith(("?", "؟")))

    # dates / authorship (E-E-A-T)
    author = doc.xpath(f"//meta[{name_l}='author']/@content") or doc.xpath(f"//*[{rel_l}='author']//text()")
    pub = doc.xpath(f"//meta[{prop_l}='article:published_time']/@content")
    mod = doc.xpath(f"//meta[{prop_l}='article:modified_time' or {prop_l}='og:updated_time']/@content")
    times = doc.xpath("//time/@datetime")

    # structured data
    jsonld_blocks = doc.xpath(f"//script[{LOWER.format('@type')}='application/ld+json']/text()")
    sd = analyse_jsonld(jsonld_blocks)
    sd["microdata"] = sorted({t.rstrip("/").rsplit("/", 1)[-1] for t in doc.xpath("//*/@itemtype")})
    sd["rdfa"] = sorted({t.split(":")[-1] for t in doc.xpath("//*/@typeof")})
    extra["schema"] = sd
    all_types = sd["types"] + sd["microdata"] + sd["rdfa"]
    d["schema_types"] = ", ".join(sorted(set(all_types)))
    # pull author/dates out of JSON-LD too
    for raw in jsonld_blocks:
        if not author and '"author"' in raw:
            author = ["schema"]
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw)
        if m and not pub:
            pub = [m.group(1)]
        m = re.search(r'"dateModified"\s*:\s*"([^"]+)"', raw)
        if m and not mod:
            mod = [m.group(1)]
    if not author and doc.xpath("//*[contains(@class,'author') or contains(@class,'byline')]"):
        author = ["byline"]
    d["author"] = (author[0].strip() if author else "")[:120]
    d["published"] = (pub[0] if pub else (times[0] if times else ""))[:40]
    d["modified"] = (mod[0] if mod else "")[:40]

    # resources: images, scripts, styles
    images = []
    for i, img in enumerate(doc.iter("img")):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        absu = urljoin(base, src)
        images.append({"src": absu, "alt": img.get("alt"), "w": img.get("width"), "h": img.get("height"),
                       "loading": (img.get("loading") or "").lower(), "i": i})
    d["images"] = len(images)
    d["images_missing_alt"] = sum(1 for im in images if im["alt"] is None)
    d["images_empty_alt"] = sum(1 for im in images if im["alt"] is not None and not im["alt"].strip())
    extra["images"] = images[:500]

    head = doc.find(".//head")
    blocking = []
    if head is not None:
        for s in head.iter("script"):
            if s.get("src") and s.get("async") is None and s.get("defer") is None and (s.get("type") or "") != "module":
                blocking.append(urljoin(base, s.get("src")))
        for ln in head.iter("link"):
            if "stylesheet" in (ln.get("rel") or "").lower() and (ln.get("media") or "all") in ("all", "screen", ""):
                if ln.get("href"):
                    blocking.append(urljoin(base, ln.get("href")))
    d["render_blocking"] = len(blocking)
    extra["render_blocking"] = blocking[:50]
    scripts = [urljoin(base, s) for s in doc.xpath("//script/@src")]
    styles = [urljoin(base, s) for s in doc.xpath(f"//link[contains({rel_l},'stylesheet')]/@href")]
    d["scripts"] = len(scripts)
    d["stylesheets"] = len(styles)
    extra["css_js"] = (scripts + styles)[:100]

    # security signals
    mixed = []
    if https:
        for attr_url in doc.xpath("//img/@src|//script/@src|//iframe/@src|//video/@src|//audio/@src|//source/@src"
                                  f"|//link[contains({rel_l},'stylesheet')]/@href"):
            if attr_url.strip().lower().startswith("http://"):
                mixed.append(attr_url.strip())
    d["mixed_content"] = len(mixed)
    extra["mixed"] = mixed[:50]
    insecure = 0
    for form in doc.iter("form"):
        action = (form.get("action") or "").strip().lower()
        if action.startswith("http://") or (not https and form.xpath(".//input[@type='password']")):
            insecure += 1
    d["insecure_forms"] = insecure
    d["protocol_relative"] = len([u for u in doc.xpath("//a/@href|//img/@src|//script/@src|//link/@href")
                                  if u.strip().startswith("//")])
    small_fonts = re.findall(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", " ".join(doc.xpath("//@style")))
    d["small_fonts"] = sum(1 for f in small_fonts if float(f) < 12)

    # links
    links, seen = [], set()
    for a in doc.iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith(SKIP_SCHEMES):
            continue
        dst = normalize(urljoin(base, href), strip_params)
        if not dst:
            continue
        anchor = text(a)
        if not anchor:
            alts = a.xpath(".//img/@alt")
            anchor = f"[img] {alts[0].strip()}" if alts else (a.get("aria-label") or a.get("title") or "")
        anchor = anchor[:200]
        key = (dst, anchor)
        if key in seen:
            continue
        seen.add(key)
        nofollow = int("nofollow" in (a.get("rel") or "").lower().split())
        in_body = int(not (_ancestor_tags(a) & CHROME_TAGS))
        links.append((dst, anchor, nofollow, "a", in_body))
    for im in images:
        n = normalize(im["src"], frozenset())
        if n:
            links.append((n, (im["alt"] or "")[:200], 0, "img", 1))

    d["lists"] = len(doc.xpath("//ul|//ol"))
    d["tables"] = len(doc.xpath("//table"))

    # custom extraction (before scripts are stripped)
    if extractions:
        res = {}
        raw_html = None
        for ex in extractions:
            try:
                if ex.kind == "regex":
                    if raw_html is None:
                        raw_html = body.decode(enc or "utf-8", "ignore")
                    vals = [m if isinstance(m, str) else m[0] for m in re.findall(ex.expr, raw_html)]
                else:
                    els = doc.cssselect(ex.expr) if ex.kind == "css" else doc.xpath(ex.expr)
                    vals = []
                    for el in els:
                        if isinstance(el, str):
                            vals.append(el.strip())
                        elif ex.attr:
                            vals.append((el.get(ex.attr) or "").strip())
                        else:
                            vals.append(text(el))
                res[ex.name] = " | ".join(v for v in vals if v)[:2000]
            except Exception as e:
                res[ex.name] = f"[error] {e}"[:200]
        extra["extract"] = res

    # content
    container = doc.find(".//body")
    container = container if container is not None else doc
    etree.strip_elements(container, "script", "style", "noscript", "template", with_tail=False)
    # Main content only: prefer <main>/<article>, and drop navigation, header, footer and sidebars.
    mains = container.xpath(".//main|.//*[@role='main']") or container.xpath(".//article")
    if mains:
        container = max(mains, key=lambda e: len(e.text_content()))
    for el in container.xpath(".//nav|.//header|.//footer|.//aside|.//*[@role='navigation']"):
        if el.getparent() is not None:
            el.drop_tree()
    words_text = " ".join(container.text_content().split())
    words = words_text.split()
    d["word_count"] = len(words)
    d["text_ratio"] = round(100 * len(words_text.encode("utf-8")) / max(1, len(body)), 1)
    d["readability"] = flesch(words_text)
    low = [w.lower().strip(".,;:!?()[]\"'«»،؛") for w in words]
    d["content_hash"] = hashlib.sha1(" ".join(low).encode("utf-8", "ignore")).hexdigest() if words else ""
    d["simhash"] = simhash(low)
    content_words = [w for w in low if len(w) > 3 and w not in STOPWORDS and not w.isdigit()]
    if content_words:
        word, cnt = Counter(content_words).most_common(1)[0]
        d["top_keyword"] = word[:60]
        d["top_keyword_density"] = round(100 * cnt / max(1, len(words)), 2)
    d["internal_links"] = 0  # filled by the crawler (needs domain knowledge)
    d["data"] = json.dumps(extra, ensure_ascii=False)
    return d, links, hreflang


def parse_mobile(body: bytes, enc: str | None) -> tuple[int, int]:
    """(word_count, link_count) for a mobile-UA fetch of the same page."""
    try:
        doc = lhtml.fromstring(body, parser=lhtml.HTMLParser(encoding=enc) if enc else None)
    except Exception:
        return 0, 0
    nlinks = len(doc.xpath("//a[@href]"))
    body_el = doc.find(".//body")
    body_el = body_el if body_el is not None else doc
    etree.strip_elements(body_el, "script", "style", "noscript", "template", with_tail=False)
    return len(body_el.text_content().split()), nlinks


def strip_fragment(u: str) -> str:
    return urldefrag(u)[0]


def host_of(u: str) -> str:
    return (urlsplit(u).hostname or "").lower()
