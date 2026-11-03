"""Async crawler. Stores everything in SQLite so crawls can be paused, resumed and recovered after a crash.

Only crawl sites you own or have permission to crawl.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import httpx
from lxml import etree

from . import db as dbm
from .config import MOBILE_UA, CrawlConfig
from .parser import parse_html, parse_mobile
from .urls import has_skip_ext, normalize, strip_www

RETRY_STATUS = {429, 502, 503, 504}
AI_BOTS = ["GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-User", "anthropic-ai",
           "PerplexityBot", "Google-Extended", "CCBot", "Applebot-Extended", "Bytespider"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Crawler:
    def __init__(self, cfg: CrawlConfig, session_dir: str | Path, resume: bool = False):
        self.cfg = cfg
        self.resume = resume
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.session_dir / "crawl.db"
        self.strip_params = frozenset(p.strip().lower() for p in cfg.strip_params if p.strip())
        self.include = [re.compile(p) for p in cfg.include if p.strip()]
        self.exclude = [re.compile(p) for p in cfg.exclude if p.strip()]
        start = cfg.url.strip()
        if start and "://" not in start:
            start = "https://" + start
        if cfg.mode == "list" and not start and cfg.url_list:
            start = cfg.url_list[0]
        self.start = normalize(start, self.strip_params) or ""
        if not self.start:
            raise ValueError(f"Invalid start URL: {cfg.url!r}")
        self.root_host = strip_www(urlsplit(self.start).hostname or "")
        self.follow = cfg.mode == "spider"
        self.seen: set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.robots: dict[str, robotparser.RobotFileParser] = {}
        self.robots_locks: dict[str, asyncio.Lock] = {}
        self.sitemaps_found: list[str] = []
        self.crawled = 0
        self.started = 0
        self.errors = 0
        self.stop = False
        self.user_stopped = False
        self.limit_reached = False
        self.paused = False
        self.t0 = time.time()
        self.pending = 0
        self.on_page = None       # callback(row: dict)
        self.on_progress = None   # callback(stats: dict)
        self.on_message = None    # callback(text: str)

    # ---- control ----------------------------------------------------------
    def request_stop(self) -> None:
        self.stop = True
        self.user_stopped = True
        self.paused = False

    def pause(self) -> None:
        self.paused = True

    def unpause(self) -> None:
        self.paused = False

    def msg(self, text: str) -> None:
        if self.on_message:
            self.on_message(text)

    # ---- classification ---------------------------------------------------
    def is_internal(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        if self.cfg.subdomains:
            return host == self.root_host or host.endswith("." + self.root_host) or strip_www(host) == self.root_host
        return strip_www(host) == self.root_host

    def allowed(self, url: str) -> bool:
        if self.include and not any(r.search(url) for r in self.include):
            return False
        return not any(r.search(url) for r in self.exclude)

    def enqueue(self, url: str, depth: int, kind: str | None = None, force: bool = False) -> None:
        """kind: page (internal HTML), external, resource (image)."""
        if url in self.seen:
            return
        internal = self.is_internal(url)
        if kind is None:
            kind = "page" if internal else "external"
        if kind == "page":
            if not internal:
                kind = "external"
            elif not force:
                if has_skip_ext(url) or not self.allowed(url):
                    return
                if self.cfg.max_depth and depth > self.cfg.max_depth:
                    return
        if kind == "external" and not self.cfg.check_external:
            return
        if kind == "resource" and not self.cfg.check_images:
            return
        self.seen.add(url)
        self.db.execute("INSERT OR IGNORE INTO queue(url, depth, kind, done) VALUES (?,?,?,0)", (url, depth, kind))
        self.queue.put_nowait((url, depth, kind))

    # ---- robots / sitemaps / site checks ---------------------------------------
    async def get_robots(self, origin: str) -> robotparser.RobotFileParser:
        rp = self.robots.get(origin)
        if rp is not None:
            return rp
        lock = self.robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            rp = self.robots.get(origin)
            if rp is None:
                rp = robotparser.RobotFileParser()
                status, body = 0, ""
                try:
                    r = await self.client.get(origin + "/robots.txt", follow_redirects=True)
                    status, body = r.status_code, r.text if r.status_code == 200 else ""
                except httpx.HTTPError:
                    pass
                if status == 200:
                    rp.parse(body.splitlines())
                else:
                    rp.allow_all = True
                rp.modified()
                self.robots[origin] = rp
                self.sitemaps_found.extend(rp.site_maps() or [])
                if strip_www(urlsplit(origin).hostname or "") == self.root_host and dbm.get_meta(self.db, "robots_status") is None:
                    dbm.set_meta(self.db, "robots_status", str(status))
                    dbm.set_meta(self.db, "robots_txt", body[:200_000])
        return rp

    async def robots_ok(self, url: str) -> bool:
        p = urlsplit(url)
        rp = await self.get_robots(f"{p.scheme}://{p.netloc}")
        return rp.can_fetch(self.cfg.ua_token, url)

    async def site_checks(self) -> None:
        p = urlsplit(self.start)
        origin = f"{p.scheme}://{p.netloc}"
        rp = await self.get_robots(origin)
        bots = {b: rp.can_fetch(b, origin + "/") for b in AI_BOTS}
        dbm.set_meta(self.db, "ai_bots", bots)
        # llms.txt
        info = {}
        for name in ("llms.txt", "llms-full.txt"):
            try:
                r = await self.client.get(f"{origin}/{name}", follow_redirects=True)
                ok = r.status_code == 200 and "html" not in r.headers.get("content-type", "")
                info[name] = {"status": r.status_code, "ok": ok, "size": len(r.content)}
            except httpx.HTTPError as e:
                info[name] = {"status": 0, "ok": False, "error": str(e)[:100]}
        dbm.set_meta(self.db, "llms_txt", info)
        # http -> https
        if p.scheme == "https":
            try:
                r = await self.client.get(f"http://{p.netloc}/")
                dbm.set_meta(self.db, "http_redirect", {"status": r.status_code, "location": r.headers.get("location", "")})
            except httpx.HTTPError as e:
                dbm.set_meta(self.db, "http_redirect", {"status": 0, "error": str(e)[:100]})
            dbm.set_meta(self.db, "ssl", await asyncio.to_thread(self._ssl_info, p.hostname, p.port or 443))
        self.db.commit()

    @staticmethod
    def _ssl_info(host: str, port: int) -> dict:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as s:
                    cert = s.getpeercert()
            exp = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            issuer = dict(x[0] for x in cert.get("issuer", ()))
            return {"valid": True, "expires": exp.isoformat(), "days_left": (exp - datetime.now(timezone.utc)).days,
                    "issuer": issuer.get("organizationName", "")}
        except Exception as e:
            return {"valid": False, "error": f"{type(e).__name__}: {e}"[:200]}

    async def load_sitemaps(self, enqueue: bool = True) -> int:
        p = urlsplit(self.start)
        origin = f"{p.scheme}://{p.netloc}"
        await self.get_robots(origin)
        roots = [self.cfg.sitemap_url] if self.cfg.sitemap_url else self.sitemaps_found + [origin + "/sitemap.xml"]
        stack = [(u, 0) for u in dict.fromkeys(roots)]
        done: set[str] = set()
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
        found = 0
        report = []
        while stack:
            smap, d = stack.pop()
            if smap in done or d > 4:
                continue
            done.add(smap)
            entry = {"url": smap, "status": 0, "urls": 0, "bytes": 0, "errors": []}
            report.append(entry)
            try:
                r = await self.client.get(smap, follow_redirects=True)
            except httpx.HTTPError as e:
                entry["errors"].append(f"Fetch failed: {e}"[:150])
                continue
            entry["status"] = r.status_code
            if r.status_code != 200:
                continue
            data = r.content
            entry["bytes"] = len(data)
            if data[:2] == b"\x1f\x8b":
                try:
                    data = gzip.decompress(data)
                except OSError:
                    entry["errors"].append("Invalid gzip")
                    continue
            try:
                root = etree.fromstring(data, parser=parser)
            except etree.XMLSyntaxError as e:
                entry["errors"].append(f"XML error: {e}"[:150])
                continue
            kind = etree.QName(root).localname
            entries = []
            for el in root:
                if not isinstance(el.tag, str):
                    continue
                loc = lastmod = ""
                for child in el:
                    if not isinstance(child.tag, str):
                        continue
                    ln = etree.QName(child).localname
                    if ln == "loc":
                        loc = (child.text or "").strip()
                    elif ln == "lastmod":
                        lastmod = (child.text or "").strip()
                if loc:
                    entries.append((loc, lastmod))
            entry["urls"] = len(entries)
            if kind == "sitemapindex":
                entry["index"] = True
                stack.extend((u, d + 1) for u, _ in entries)
                continue
            if kind != "urlset":
                entry["errors"].append(f"Unexpected root element <{kind}>")
            if len(entries) > 50_000:
                entry["errors"].append("More than 50,000 URLs (limit)")
            if len(data) > 50 * 1024 * 1024:
                entry["errors"].append("Larger than 50 MB uncompressed (limit)")
            for loc, lastmod in entries:
                n = normalize(loc, self.strip_params)
                if not n:
                    entry["errors"].append(f"Invalid URL: {loc[:80]}")
                    continue
                if not self.is_internal(n):
                    continue
                self.db.execute("INSERT OR IGNORE INTO sitemap_urls(url, sitemap, lastmod) VALUES (?,?,?)", (n, smap, lastmod))
                if enqueue:
                    self.enqueue(n, 1, "page")
                found += 1
            entry["errors"] = entry["errors"][:20]
        dbm.set_meta(self.db, "sitemaps", report)
        return found

    # ---- fetching -------------------------------------------------------------
    async def _get(self, client: httpx.AsyncClient, url: str, read_body: bool) -> dict:
        t = time.perf_counter()
        async with client.stream("GET", url) as r:
            ttfb = int((time.perf_counter() - t) * 1000)
            headers = {k.lower(): v for k, v in r.headers.items()}
            ctype = headers.get("content-type", "")
            body = b""
            if read_body and 200 <= r.status_code < 300 and ("html" in ctype or not ctype):
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > self.cfg.max_bytes:
                        break
            ms = int((time.perf_counter() - t) * 1000)
            cl = headers.get("content-length", "")
            return {"status": r.status_code, "headers": headers, "body": body, "ms": ms, "ttfb": ttfb,
                    "enc": r.charset_encoding, "size": int(cl) if cl.isdigit() else len(body)}

    async def fetch(self, url: str, read_body: bool, client: httpx.AsyncClient | None = None) -> dict:
        client = client or self.client
        res: dict = {}
        for attempt in range(self.cfg.retries + 1):
            try:
                res = await self._get(client, url, read_body)
            except Exception as e:
                name = type(e).__name__
                res = {"status": 0, "headers": {}, "body": b"", "ms": 0, "ttfb": 0, "enc": None, "size": 0,
                       "error": f"{'Timeout' if 'Timeout' in name else name}: {e}"[:300]}
            retry = res["status"] == 0 or res["status"] in RETRY_STATUS
            if not retry or attempt == self.cfg.retries or self.stop:
                return res
            wait = 2 ** attempt
            ra = res["headers"].get("retry-after", "")
            if ra.isdigit():
                wait = min(int(ra), 30)
            await asyncio.sleep(wait)
        return res

    async def render(self, url: str) -> bytes | None:
        async with self.render_sem:
            page = await self.context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=self.cfg.timeout * 1000)
                return (await page.content()).encode("utf-8")
            except Exception:
                return None
            finally:
                await page.close()

    # ---- per-URL processing ---------------------------------------------------
    async def process_resource(self, url: str) -> None:
        status, size, ctype, err = 0, 0, "", None
        try:
            r = await self.client.head(url, follow_redirects=True)
            if r.status_code in (405, 501) or r.status_code >= 400:
                res = await self.fetch(url, read_body=False)
                status, err = res["status"], res.get("error")
                size, ctype = res["size"], res["headers"].get("content-type", "")
            else:
                status = r.status_code
                cl = r.headers.get("content-length", "")
                size = int(cl) if cl.isdigit() else 0
                ctype = r.headers.get("content-type", "")
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
        self.db.execute("INSERT OR REPLACE INTO resources(url, kind, status, size, content_type, error) VALUES (?,?,?,?,?,?)",
                        (url, "image", status, size, ctype.split(";")[0], err))

    async def process(self, url: str, depth: int, kind: str) -> None:
        internal = kind == "page"
        if kind == "resource":
            await self.process_resource(url)
            return
        now = now_iso()
        if internal and self.cfg.respect_robots and not await self.robots_ok(url):
            self.save_page({"url": url, "internal": 1, "depth": depth, "status": 0, "error": "Blocked by robots.txt",
                            "indexability": "Blocked by robots.txt", "crawled_at": now})
            return

        res = await self.fetch(url, read_body=internal)
        status, h = res["status"], res["headers"]
        ctype = h.get("content-type", "").split(";")[0].strip().lower()
        row = {"url": url, "internal": int(internal), "depth": depth, "status": status, "content_type": ctype,
               "size": res["size"], "response_ms": res["ms"], "ttfb_ms": res["ttfb"],
               "x_robots_tag": h.get("x-robots-tag", ""), "error": res.get("error"), "crawled_at": now,
               "last_modified": h.get("last-modified", ""), "content_encoding": h.get("content-encoding", ""),
               "cache_control": h.get("cache-control", "") or ("expires" if h.get("expires") else "") or
                                ("etag" if h.get("etag") else ""),
               "hsts": h.get("strict-transport-security", ""), "csp": h.get("content-security-policy", ""),
               "x_frame": h.get("x-frame-options", ""), "x_content_type": h.get("x-content-type-options", "")}
        links: list = []
        hreflang: list = []
        if status == 0:
            self.errors += 1

        if 300 <= status < 400 and h.get("location"):
            target = normalize(urljoin(url, h["location"]), self.strip_params)
            row["redirect_to"] = target
            row["indexability"] = f"Non-Indexable: redirect {status}"
            if target:
                links.append((target, "[redirect]", 0, "redirect", 1))
                self.enqueue(target, depth + 1, force=not self.follow)
        elif internal and status == 200 and res["body"] and ("html" in ctype or not ctype):
            body, enc = res["body"], res["enc"]
            if self.cfg.render_js and self.context is not None:
                rendered = await self.render(url)
                if rendered:
                    body, enc = rendered, "utf-8"
            data, links, hreflang = await asyncio.to_thread(parse_html, url, body, enc, self.strip_params,
                                                            self.cfg.extractions)
            row.update(data)
            blob = f"{data.get('meta_robots', '')} {row['x_robots_tag']}".lower()
            canon = data.get("canonical") or None
            if "noindex" in blob:
                row["indexability"] = "Non-Indexable: noindex"
            elif canon and canon != url:
                row["indexability"] = "Non-Indexable: canonicalised"
            else:
                row["indexability"] = "Indexable"
            a_links = [ln for ln in links if ln[3] == "a"]
            row["internal_links"] = sum(1 for ln in a_links if self.is_internal(ln[0]))
            row["external_links"] = len(a_links) - row["internal_links"]
            row["body_internal_links"] = sum(1 for ln in a_links if ln[4] and self.is_internal(ln[0]))
            for dst, _, _, k, _ in links:
                if k == "img":
                    self.enqueue(dst, depth + 1, "resource")
                elif self.follow or not self.is_internal(dst):
                    self.enqueue(dst, depth + 1)
            if self.cfg.mobile_parity:
                mres = await self.fetch(url, read_body=True, client=self.mobile_client)
                if mres["body"]:
                    row["mobile_word_count"], row["mobile_links"] = await asyncio.to_thread(parse_mobile, mres["body"], mres["enc"])
        elif status:
            row["indexability"] = "Indexable" if status == 200 else f"Non-Indexable: status {status}"

        if links:
            self.db.executemany(
                "INSERT INTO links(src, dst, anchor, internal, nofollow, kind, in_body) VALUES (?,?,?,?,?,?,?)",
                [(url, d, a, int(self.is_internal(d)), nf, k, ib) for d, a, nf, k, ib in links])
        if hreflang:
            self.db.executemany("INSERT INTO hreflang(src, lang, href) VALUES (?,?,?)", [(url, l, hr) for l, hr in hreflang])
        self.save_page(row)
        if internal:
            self.crawled += 1

    def save_page(self, row: dict) -> None:
        cols = ",".join(dbm.PAGE_COLS)
        marks = ",".join(":" + c for c in dbm.PAGE_COLS)
        self.db.execute(f"INSERT OR REPLACE INTO pages({cols}) VALUES ({marks})", {c: row.get(c) for c in dbm.PAGE_COLS})
        if self.on_page:
            self.on_page({k: v for k, v in row.items() if k != "data"})

    def mark_done(self, url: str) -> None:
        self.db.execute("UPDATE queue SET done=1 WHERE url=?", (url,))
        self.pending += 1
        if self.pending >= 100:
            self.db.commit()
            self.pending = 0

    async def worker(self) -> None:
        while True:
            url, depth, kind = await self.queue.get()
            try:
                while self.paused and not self.stop:
                    await asyncio.sleep(0.25)
                skip = False
                if kind == "page" and self.cfg.max_urls:
                    if self.started >= self.cfg.max_urls:
                        # Page limit reached: stop crawling new pages, but still check the links and images found.
                        self.limit_reached = True
                        skip = True
                    else:
                        self.started += 1
                if not self.stop and not skip:
                    try:
                        await self.process(url, depth, kind)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        if kind != "resource":
                            self.save_page({"url": url, "internal": int(kind == "page"), "depth": depth, "status": 0,
                                            "error": f"{type(e).__name__}: {e}"[:300], "crawled_at": now_iso()})
                    self.mark_done(url)
                    if self.cfg.delay:
                        await asyncio.sleep(self.cfg.delay)
            finally:
                self.queue.task_done()

    def stats(self) -> dict:
        el = max(time.time() - self.t0, 1)
        return {"crawled": self.crawled, "queued": self.queue.qsize(), "rate": self.crawled / el,
                "elapsed": el, "errors": self.errors, "paused": self.paused}

    async def progress(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            if self.on_progress:
                self.on_progress(self.stats())

    # ---- main --------------------------------------------------------------------
    async def run(self) -> None:
        cfg = self.cfg
        if self.db_path.exists() and not self.resume:
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(self.db_path) + suffix)
                if p.exists():
                    p.unlink()
        self.db = dbm.connect(self.db_path)
        dbm.set_meta(self.db, "config", cfg.to_dict())
        dbm.set_meta(self.db, "start_url", self.start)
        dbm.set_meta(self.db, "status", "running")
        if not self.resume or dbm.get_meta(self.db, "started_at") is None:
            dbm.set_meta(self.db, "started_at", now_iso())

        headers = {"User-Agent": cfg.ua_string, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                   "Accept-Encoding": "gzip, deflate, br" if _has_brotli() else "gzip, deflate"}
        headers.update({str(k): str(v) for k, v in (cfg.headers or {}).items()})
        if cfg.cookies.strip():
            headers["Cookie"] = cfg.cookies.strip()
        auth = httpx.BasicAuth(cfg.auth_user, cfg.auth_pass) if cfg.auth_user else None
        limits = httpx.Limits(max_connections=cfg.threads * 2, max_keepalive_connections=cfg.threads)
        self.client = httpx.AsyncClient(headers=headers, auth=auth, timeout=cfg.timeout, follow_redirects=False,
                                        verify=cfg.verify_tls, limits=limits)
        self.mobile_client = None
        if cfg.mobile_parity:
            self.mobile_client = httpx.AsyncClient(headers={**headers, "User-Agent": MOBILE_UA}, auth=auth,
                                                   timeout=cfg.timeout, follow_redirects=True, verify=cfg.verify_tls)

        self.pw = self.browser = self.context = None
        if cfg.render_js:
            try:
                from playwright.async_api import async_playwright
                self.pw = await async_playwright().start()
                self.browser = await self.pw.chromium.launch()
                self.context = await self.browser.new_context(user_agent=cfg.ua_string, ignore_https_errors=not cfg.verify_tls)

                async def _route(route):
                    if route.request.resource_type in ("image", "media", "font"):
                        await route.abort()
                    else:
                        await route.continue_()
                await self.context.route("**/*", _route)
                self.render_sem = asyncio.Semaphore(cfg.render_threads)
            except Exception as e:
                self.msg(f"JavaScript rendering unavailable ({e}). Crawling without it.")
                self.context = None

        tasks: list[asyncio.Task] = []
        finished = False
        try:
            resumed = False
            if self.resume:
                rows = self.db.execute("SELECT url, depth, kind, done FROM queue").fetchall()
                for r in rows:
                    self.seen.add(r["url"])
                    if not r["done"]:
                        self.queue.put_nowait((r["url"], r["depth"], r["kind"]))
                self.crawled = self.db.execute("SELECT COUNT(*) FROM pages WHERE internal=1").fetchone()[0]
                self.started = self.crawled
                resumed = bool(rows)
                if resumed:
                    self.msg(f"Resuming: {len(rows):,} known URLs, {self.queue.qsize():,} still to crawl.")
            if not resumed:
                self.msg("Checking robots.txt, SSL, llms.txt…")
                await self.site_checks()
                if cfg.mode == "list":
                    for u in cfg.url_list:
                        n = normalize(u if "://" in u else "https://" + u, self.strip_params)
                        if n:
                            self.enqueue(n, 0, "page", force=True)
                elif cfg.mode == "sitemap":
                    n = await self.load_sitemaps(enqueue=True)
                    self.msg(f"Sitemap: {n:,} URLs found.")
                else:
                    self.enqueue(self.start, 0, "page", force=True)
                    if cfg.use_sitemaps:
                        n = await self.load_sitemaps(enqueue=cfg.mode == "spider")
                        if n:
                            self.msg(f"Sitemap: {n:,} URLs found.")
            self.db.commit()
            self.msg(f"Crawling {self.start} …")
            tasks = [asyncio.create_task(self.worker()) for _ in range(max(1, cfg.threads))]
            tasks.append(asyncio.create_task(self.progress()))
            await self.queue.join()
            finished = True
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            left = self.db.execute("SELECT COUNT(*) FROM queue WHERE done=0").fetchone()[0]
            dbm.set_meta(self.db, "status", "complete" if finished and not left else "stopped")
            dbm.set_meta(self.db, "finished_at", now_iso())
            dbm.set_meta(self.db, "elapsed", round(time.time() - self.t0, 1))
            self.db.commit()
            self.db.close()
            await self.client.aclose()
            if self.mobile_client:
                await self.mobile_client.aclose()
            if self.browser:
                await self.browser.close()
            if self.pw:
                await self.pw.stop()


def _has_brotli() -> bool:
    try:
        import brotli  # noqa: F401
        return True
    except ImportError:
        try:
            import brotlicffi  # noqa: F401
            return True
        except ImportError:
            return False


def config_of(db) -> CrawlConfig:
    return CrawlConfig.from_dict(dbm.get_meta(db, "config", {}, as_json=True))


__all__ = ["Crawler", "config_of", "AI_BOTS", "json"]
