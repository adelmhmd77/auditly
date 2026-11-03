"""Google PageSpeed Insights (Core Web Vitals: field data from CrUX when available, otherwise lab data)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..crawl import db as dbm

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def run(url: str, strategy: str = "mobile", api_key: str = "", timeout: int = 90) -> dict:
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if api_key:
        params["key"] = api_key
    r = httpx.get(API, params=params, timeout=timeout)
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(f"PageSpeed API {r.status_code}: {msg}")
    j = r.json()
    field = (j.get("loadingExperience") or {}).get("metrics") or {}
    lh = j.get("lighthouseResult") or {}
    audits = lh.get("audits") or {}

    def fm(key):
        m = field.get(key)
        return m.get("percentile") if m else None

    def lab(key):
        a = audits.get(key) or {}
        return a.get("numericValue")

    lcp, inp, cls = fm("LARGEST_CONTENTFUL_PAINT_MS"), fm("INTERACTION_TO_NEXT_PAINT"), fm("CUMULATIVE_LAYOUT_SHIFT_SCORE")
    source = "field (CrUX)" if lcp is not None else "lab (Lighthouse)"
    if cls is not None:
        cls = cls / 100.0
    if lcp is None:
        lcp = lab("largest-contentful-paint")
    if cls is None:
        cls = lab("cumulative-layout-shift")
    score = ((lh.get("categories") or {}).get("performance") or {}).get("score")
    return {"url": url, "strategy": strategy, "score": score * 100 if score is not None else None, "lcp": lcp, "inp": inp,
            "cls": cls, "fcp": fm("FIRST_CONTENTFUL_PAINT_MS") or lab("first-contentful-paint"),
            "ttfb": fm("EXPERIMENTAL_TIME_TO_FIRST_BYTE") or lab("server-response-time"), "source": source}


def save(db_path, result: dict) -> None:
    db = dbm.connect(db_path)
    db.execute("INSERT OR REPLACE INTO psi(url, strategy, score, lcp, inp, cls, fcp, ttfb, source, fetched_at) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)",
               (result["url"], result["strategy"], result["score"], result["lcp"], result["inp"], result["cls"],
                result["fcp"], result["ttfb"], result["source"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
    db.commit()
    db.close()
