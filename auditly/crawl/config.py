"""Crawl configuration. Can be saved/loaded as a YAML profile."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

USER_AGENTS = {
    "Auditly": "Mozilla/5.0 (compatible; Auditly/1.0; +https://github.com/auditly/auditly)",
    "Googlebot (desktop)": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; "
                           "+http://www.google.com/bot.html) Chrome/130.0.0.0 Safari/537.36",
    "Googlebot (smartphone)": "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36 "
                              "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; "
                     "+https://perplexity.ai/perplexitybot)",
    "Chrome (desktop)": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/130.0.0.0 Safari/537.36",
    "Chrome (mobile)": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/130.0.0.0 Mobile Safari/537.36",
}
MOBILE_UA = USER_AGENTS["Googlebot (smartphone)"]

MODES = ("spider", "list", "sitemap", "single")


@dataclass
class Extraction:
    name: str
    kind: str = "css"       # css | xpath | regex
    expr: str = ""
    attr: str = ""          # css/xpath: attribute to read instead of text


@dataclass
class CrawlConfig:
    url: str = ""
    mode: str = "spider"                    # spider | list | sitemap | single
    url_list: list[str] = field(default_factory=list)   # list mode
    sitemap_url: str = ""                   # sitemap mode (blank = auto)
    threads: int = 10
    delay: float = 0.0
    timeout: int = 20
    retries: int = 2
    max_urls: int = 0                       # 0 = unlimited
    max_depth: int = 0                      # 0 = unlimited
    respect_robots: bool = True
    use_sitemaps: bool = True
    subdomains: bool = False
    check_external: bool = True
    check_images: bool = True               # fetch images to find broken/oversized ones
    mobile_parity: bool = False             # re-fetch each page with a mobile UA
    render_js: bool = False
    render_threads: int = 3
    user_agent: str = "Auditly"             # preset name or a custom string
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    strip_params: list[str] = field(default_factory=lambda: ["utm_source", "utm_medium", "utm_campaign",
                                                              "utm_term", "utm_content", "gclid", "fbclid"])
    auth_user: str = ""
    auth_pass: str = ""
    cookies: str = ""                       # "name=value; name2=value2"
    headers: dict = field(default_factory=dict)
    verify_tls: bool = True
    max_bytes: int = 5_000_000
    extractions: list[Extraction] = field(default_factory=list)

    @property
    def ua_string(self) -> str:
        return USER_AGENTS.get(self.user_agent, self.user_agent or USER_AGENTS["Auditly"])

    @property
    def ua_token(self) -> str:
        """Token used to match robots.txt groups (e.g. 'Googlebot')."""
        ua = self.ua_string
        for tok in ("Googlebot", "bingbot", "GPTBot", "ClaudeBot", "PerplexityBot", "Auditly"):
            if tok.lower() in ua.lower():
                return tok
        return ua.split("/")[0].strip() or "*"

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("auth_pass", None)  # never persist passwords into profiles
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CrawlConfig":
        names = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in (d or {}).items() if k in names and k != "extractions"})
        cfg.extractions = [Extraction(**e) for e in (d or {}).get("extractions", []) if isinstance(e, dict)]
        return cfg

    def save_yaml(self, path: str | Path) -> None:
        import yaml
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")

    @classmethod
    def load_yaml(cls, path: str | Path) -> "CrawlConfig":
        import yaml
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
