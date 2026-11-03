"""URL helpers."""
from __future__ import annotations

from urllib.parse import parse_qsl, urldefrag, urlencode, urlsplit, urlunsplit

SKIP_EXT = {
    "jpg", "jpeg", "png", "gif", "webp", "svg", "ico", "bmp", "avif", "tif", "tiff",
    "pdf", "zip", "gz", "rar", "7z", "tar", "exe", "dmg", "apk", "iso",
    "css", "js", "map", "json", "xml", "txt", "woff", "woff2", "ttf", "eot", "otf",
    "mp3", "mp4", "avi", "mov", "wmv", "webm", "ogg", "wav", "flv", "m4v",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv",
}


def normalize(url: str, strip_params: frozenset = frozenset()) -> str | None:
    """Canonical form used for de-duplication: no fragment, lowercase host, no default port."""
    try:
        url, _ = urldefrag(url.strip())
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return None
        host = p.hostname.lower()
        port = p.port
    except ValueError:
        return None
    netloc = host
    if port and not ((p.scheme == "http" and port == 80) or (p.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = p.query
    if strip_params and query:
        query = urlencode([(k, v) for k, v in parse_qsl(query, keep_blank_values=True)
                           if k.lower() not in strip_params])
    path = (p.path or "/").replace(" ", "%20")
    return urlunsplit((p.scheme, netloc, path, query, ""))


def has_skip_ext(url: str) -> bool:
    path = urlsplit(url).path
    last = path.rsplit("/", 1)[-1]
    if "." not in last:
        return False
    return last.rsplit(".", 1)[-1].lower() in SKIP_EXT


def strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host
