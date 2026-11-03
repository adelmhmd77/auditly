"""Auditly command line: crawl, audit and export without the desktop app (CI/CD, cron, Docker)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import APP_NAME, __version__
from . import settings as settings_mod
from .audits import all_audits, run_audits
from .compare import compare
from .crawl.config import USER_AGENTS, CrawlConfig
from .crawl.crawler import Crawler
from .crawl import db as dbm
from .export import FORMATS, export_bundle
from .sessions import list_sessions, new_session_dir


def _progress(stats: dict) -> None:
    print(f"\r  crawled {stats['crawled']:>8,}  queued {stats['queued']:>8,}  {stats['rate']:5.1f} pages/s",
          end="", file=sys.stderr, flush=True)


def cmd_crawl(a) -> int:
    cfg = CrawlConfig.load_yaml(a.profile) if a.profile else CrawlConfig()
    if a.url:
        cfg.url = a.url
    for k in ("mode", "threads", "delay", "max_urls", "max_depth", "user_agent", "sitemap_url"):
        v = getattr(a, k, None)
        if v is not None:
            setattr(cfg, k, v)
    if a.list_file:
        cfg.mode = "list"
        cfg.url_list = [ln.strip() for ln in Path(a.list_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if a.ignore_robots:
        cfg.respect_robots = False
    if a.render:
        cfg.render_js = True
    cfg.include += a.include
    cfg.exclude += a.exclude
    if not cfg.url and not cfg.url_list:
        print("Give a URL, a --profile with a url, or --list-file.", file=sys.stderr)
        return 2

    session = Path(a.resume) if a.resume else new_session_dir(cfg.url or cfg.url_list[0])
    crawler = Crawler(cfg, session, resume=bool(a.resume))
    crawler.on_progress = None if a.quiet else _progress
    crawler.on_message = None if a.quiet else (lambda m: print(f"\n{m}", file=sys.stderr))
    print(f"{APP_NAME} {__version__} · crawling {crawler.start} · session {session}", file=sys.stderr)
    try:
        asyncio.run(crawler.run())
    except KeyboardInterrupt:
        print(f"\nInterrupted. Resume later with: auditly crawl --resume \"{session}\"", file=sys.stderr)
    print("\nRunning audits…", file=sys.stderr)
    res = run_audits(session / "crawl.db")
    sev = {x.id: x.severity for x in all_audits()}
    totals = {"critical": 0, "warning": 0, "opportunity": 0}
    for aid, n in res["counts"].items():
        totals[sev[aid]] += n
    db = dbm.connect(session / "crawl.db", readonly=True)
    health = dbm.get_meta(db, "health", 0, as_json=True)
    db.close()
    print(f"Health {health}/100 · {totals['critical']} critical · {totals['warning']} warnings · "
          f"{totals['opportunity']} opportunities", file=sys.stderr)

    formats = set(a.format.split(",")) if a.format else {"master_csv", "html", "prompt"}
    bad = formats - set(FORMATS)
    if bad:
        print(f"Unknown format(s): {', '.join(bad)}. Choose from {', '.join(FORMATS)}", file=sys.stderr)
        return 2
    s = settings_mod.load()
    root = Path(a.output) if a.output else s.export_root
    dest, files = export_bundle(session, formats, root, s.brand_name, s.brand_color, s.brand_logo, a.language)
    print(f"Exported {len(files)} files to {dest}", file=sys.stderr)
    if a.json_summary:
        print(json.dumps({"session": str(session), "export": str(dest), "health": health, **totals}))
    if a.fail_on:
        limit = {"critical": totals["critical"], "warning": totals["critical"] + totals["warning"]}[a.fail_on]
        if limit:
            return 1
    if a.min_health and health < a.min_health:
        return 1
    return 0


def cmd_sessions(a) -> int:
    for s in list_sessions():
        print(f"{s['status']:<12} {s['pages']:>7,} pages  health {s['health'] or '-':>3}  {s['started'][:16]}  "
              f"{s['url']}\n             {s['path']}")
    return 0


def cmd_export(a) -> int:
    s = settings_mod.load()
    root = Path(a.output) if a.output else s.export_root
    dest, files = export_bundle(Path(a.session), set(a.format.split(",")), root, s.brand_name, s.brand_color,
                                s.brand_logo, a.language)
    print(f"Exported {len(files)} files to {dest}")
    return 0


def cmd_compare(a) -> int:
    r = compare(a.before, a.after)
    print(f"Health {r['before']['health']} → {r['after']['health']} · {len(r['added'])} new URLs · "
          f"{len(r['removed'])} removed · {r['fixed_total']} findings fixed · {r['new_total']} new findings")
    for row in r["issues"]:
        if row["before"] != row["after"]:
            print(f"  {row['before']:>6} → {row['after']:<6} [{row['severity']}] {row['title']}")
    return 0


def cmd_audits(a) -> int:
    for x in all_audits():
        print(f"{x.id:<18} {x.severity:<12} {x.category:<22} {x.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="auditly", description=f"{APP_NAME} — technical SEO crawler and auditor")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("crawl", help="crawl a site, run audits and export reports")
    c.add_argument("url", nargs="?")
    c.add_argument("--profile", help="YAML crawl profile")
    c.add_argument("--mode", choices=["spider", "list", "sitemap", "single"])
    c.add_argument("--list-file", help="text file with one URL per line (list mode)")
    c.add_argument("--sitemap-url", dest="sitemap_url")
    c.add_argument("--threads", type=int)
    c.add_argument("--delay", type=float)
    c.add_argument("--max-urls", dest="max_urls", type=int)
    c.add_argument("--max-depth", dest="max_depth", type=int)
    c.add_argument("--user-agent", dest="user_agent", help=f"preset ({', '.join(USER_AGENTS)}) or a custom string")
    c.add_argument("--include", action="append", default=[], metavar="REGEX")
    c.add_argument("--exclude", action="append", default=[], metavar="REGEX")
    c.add_argument("--ignore-robots", action="store_true")
    c.add_argument("--render", action="store_true", help="render JavaScript with Playwright")
    c.add_argument("--resume", metavar="SESSION_DIR", help="continue an interrupted crawl")
    c.add_argument("-f", "--format", help=f"comma list: {','.join(FORMATS)} (default master_csv,html,prompt)")
    c.add_argument("-o", "--output", help="export folder (default: Downloads/Auditly or the folder set in the app)")
    c.add_argument("--language", default="en", choices=["en", "ar"], help="language of the AI prompt")
    c.add_argument("--fail-on", choices=["critical", "warning"], help="exit 1 if findings of this severity exist (CI)")
    c.add_argument("--min-health", type=int, default=0, help="exit 1 if the health score is below this (CI)")
    c.add_argument("--json-summary", action="store_true", help="print a JSON summary to stdout")
    c.add_argument("-q", "--quiet", action="store_true")
    c.set_defaults(func=cmd_crawl)

    s = sub.add_parser("sessions", help="list saved crawl sessions")
    s.set_defaults(func=cmd_sessions)

    e = sub.add_parser("export", help="export a saved session")
    e.add_argument("session")
    e.add_argument("-f", "--format", default="master_csv,xlsx,html,prompt")
    e.add_argument("-o", "--output")
    e.add_argument("--language", default="en", choices=["en", "ar"])
    e.set_defaults(func=cmd_export)

    m = sub.add_parser("compare", help="compare two sessions (before → after)")
    m.add_argument("before")
    m.add_argument("after")
    m.set_defaults(func=cmd_compare)

    l = sub.add_parser("audits", help="list all available audits (including plugins)")
    l.set_defaults(func=cmd_audits)
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # never crash on characters the console can't show (Windows)
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "func", None):
        ap.print_help()
        return 0
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
