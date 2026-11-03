"""IndexNow: notify Bing, Yandex, Seznam, Naver… that URLs changed.

The key must also be hosted at https://<host>/<key>.txt (containing the key) for submissions to be accepted.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

ENDPOINT = "https://api.indexnow.org/indexnow"


def submit(urls: list[str], key: str) -> tuple[int, str]:
    if not urls:
        return 0, "No URLs to submit."
    if not key:
        return 0, "Add your IndexNow key in Settings first."
    host = urlsplit(urls[0]).hostname
    body = {"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt",
            "urlList": [u for u in urls if urlsplit(u).hostname == host][:10_000]}
    r = httpx.post(ENDPOINT, json=body, timeout=30)
    meaning = {200: "Submitted.", 202: "Accepted — key validation pending.", 400: "Bad request.",
               403: "Key not valid (is the key file hosted on the site?).", 422: "URLs don't match the host or key.",
               429: "Too many requests."}.get(r.status_code, r.text[:200])
    return r.status_code, f"{len(body['urlList'])} URLs · HTTP {r.status_code}: {meaning}"
