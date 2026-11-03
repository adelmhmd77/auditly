"""Dashboard: health score, KPIs, top issues, status codes, site checks."""
from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ... import sessions as sessions_mod
from ...audits import CATEGORIES
from .. import theme
from ..i18n import t
from ..icons import logo_pixmap
from ..widgets import BarList, Card, HealthRing, KpiCard, StackBar, button, hline, label, pill, status_pill
from .base import View


class DashboardView(View):
    def __init__(self, main):
        super().__init__(main, scroll=True)
        self.load(None)

    def load(self, session):
        super().load(session)
        self.clear_layout(self.body)
        if session is None:
            self._empty()
        else:
            self._full(session)

    # ------------------------------------------------------------------ empty state
    def _empty(self):
        p = theme.palette()
        hero = Card(name="Hero", padding=36, spacing=14)
        row = QHBoxLayout()
        lg = label()
        lg.setPixmap(logo_pixmap(72))
        row.addWidget(lg, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(8)
        h = label(t("Audit any website"), "H1")
        h.setStyleSheet("font-size:28px;")
        col.addWidget(h)
        col.addWidget(label(t("Crawl a site to find technical SEO problems, see exactly which URLs are affected and how to fix them."),
                            "Muted", wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for txt in ("100+ checks", "Core Web Vitals", "Hreflang", "Structured data", "AI / GEO readiness", "Claude AI"):
            c = label(txt)
            c.setStyleSheet(f"background:{p['surface2']}; color:{p['muted']}; border-radius:10px; padding:4px 10px; font-size:12px;")
            chips.addWidget(c)
        chips.addStretch()
        col.addLayout(chips)
        b = button(t("Start audit"), "Primary", "play", on=self.main.focus_url)
        r2 = QHBoxLayout()
        r2.addWidget(b)
        r2.addWidget(button(t("Crawl settings"), icon_name="sliders", on=self.main.open_crawl_settings))
        r2.addStretch()
        col.addSpacing(6)
        col.addLayout(r2)
        row.addSpacing(18)
        row.addLayout(col, 1)
        hero.add(row)
        self.body.addWidget(hero)

        self.body.addWidget(label(t("Recent audits"), "H2"))
        recent = sessions_mod.list_sessions()[:6]
        if not recent:
            self.body.addWidget(label(t("No audits yet."), "Muted"))
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, s in enumerate(recent):
            c = Card(padding=14, spacing=4, clickable=True)
            c.add(label(s["url"].split("://")[-1].rstrip("/"), "H3"))
            c.add(label(f"{s['pages']:,} pages · {t(s['status'])} · {s['started'][:16].replace('T', ' ')}", "Faint"))
            if s["health"] is not None:
                c.add(label(f"{t('Health score')}: {s['health']}/100", "Muted"))
            c.clicked.connect(lambda path=s["path"]: self.main.open_session(path))
            grid.addWidget(c, i // 3, i % 3)
        for c_ in range(3):
            grid.setColumnStretch(c_, 1)
        self.body.addLayout(grid)
        self.body.addStretch()

    # ------------------------------------------------------------------ full dashboard
    def _full(self, s):
        p = theme.palette()
        sm = s.summary
        started = (s.meta.get("finished_at") or s.meta.get("started_at") or "")[:16].replace("T", " ")
        self.header(s.start_url, f"{sm['total']:,} {t('Pages crawled').lower()} · {started}",
                    [button(t("Export"), icon_name="export", on=lambda: self.main.goto("exports")),
                     button(t("AI assistant"), icon_name="ai", on=lambda: self.main.goto("ai"))])

        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        hc = Card(padding=14, spacing=2)
        hrow = QHBoxLayout()
        ring = HealthRing(104)
        ring.set_score(sm["health"])
        hrow.addWidget(ring)
        hcol = QVBoxLayout()
        hcol.addWidget(label(t("Health score"), "CardLabel"))
        verdict = "Good" if (sm["health"] or 0) >= 80 else "Needs work" if (sm["health"] or 0) >= 50 else "Poor"
        hcol.addWidget(label(t(verdict), "H2"))
        hcol.addWidget(label(f"{sm['indexable']:,} / {sm['total']:,} {t('Indexable').lower()}", "Faint"))
        hcol.addStretch()
        hrow.addLayout(hcol)
        hc.add(hrow)
        kpis.addWidget(hc, 2)
        share = f"{100 * sm['indexable'] / sm['total']:.0f}% {t('of pages')}" if sm["total"] else ""
        cards = [
            (t("Pages crawled"), f"{sm['total']:,}", "", None, "pages", "pages"),
            (t("Indexable"), f"{sm['indexable']:,}", share, None, "check", "pages"),
            (t("Critical"), f"{sm['sev_counts']['critical']:,}", t("URLs affected"), p["critical"], "issues", "critical"),
            (t("Warnings"), f"{sm['sev_counts']['warning']:,}", t("URLs affected"), p["warning"], "issues", "warning"),
            (t("Opportunities"), f"{sm['sev_counts']['opportunity']:,}", t("URLs affected"), p["opportunity"], "zap", "opportunity"),
            (t("Avg response"), f"{sm['avg_ms']:,} ms", "", None, "zap", "performance"),
        ]
        for title, val, cap, col, ic, target in cards:
            k = KpiCard(title, val, cap, col, ic)
            if target in ("critical", "warning", "opportunity"):
                k.clicked.connect(lambda sev=target: self.main.goto("issues", severity=sev))
            elif target == "pages":
                k.clicked.connect(lambda: self.main.goto("pages"))
            kpis.addWidget(k, 1)
        self.body.addLayout(kpis)

        grid = QGridLayout()
        grid.setSpacing(12)
        # top issues
        top = Card()
        hr = QHBoxLayout()
        hr.addWidget(label(t("Top issues"), "H2"))
        hr.addStretch()
        hr.addWidget(button(t("View all"), "Ghost", on=lambda: self.main.goto("issues")))
        top.add(hr)
        if not s.issues:
            top.add(label(t("No issues found"), "Muted"))
        for i in s.issues[:9]:
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(0, 4, 0, 4)
            rl.addWidget(pill(i["severity"]))
            tl = label(i["title"])
            rl.addWidget(tl, 1)
            rl.addWidget(label(f"{i['count']:,}", "Muted"))
            r.setCursor(Qt.PointingHandCursor)
            r.mouseReleaseEvent = lambda e, iid=i["id"]: self.main.goto("issues", issue=iid)
            top.add(r)
            top.add(hline())
        top.lay.addStretch()
        grid.addWidget(top, 0, 0, 2, 1)

        # status codes
        sc = Card()
        sc.add(label(t("Status codes"), "H2"))
        bars = BarList()
        rows = []
        for st, n in sm["status"]:
            st = st or 0
            col = p["ok"] if 200 <= st < 300 else p["warning"] if 300 <= st < 400 else p["critical"]
            name = {0: "No response / blocked"}.get(st, str(st))
            rows.append((name, n, col))
        bars.set_rows(rows)
        bars.clicked.connect(lambda lab: self.main.goto("pages", status=lab[:1] + "xx" if lab[:1].isdigit() else "All"))
        sc.add(bars)
        sc.lay.addStretch()
        grid.addWidget(sc, 0, 1)

        # site checks
        ck = Card()
        ck.add(label(t("Site checks"), "H2"))
        ssl = s.json_meta("ssl") or {}
        llms = s.json_meta("llms_txt") or {}
        bots = s.json_meta("ai_bots") or {}
        sitemaps = s.json_meta("sitemaps") or []
        checks = [
            ("HTTPS / SSL", (ssl.get("valid") and ssl.get("days_left", 0) >= 30) if ssl else (None if not s.start_url.startswith("https") else False),
             f"{ssl.get('days_left')} days left" if ssl.get("valid") else ("not HTTPS" if not ssl else "problem")),
            ("robots.txt", s.meta.get("robots_status") == "200", "found" if s.meta.get("robots_status") == "200" else "missing"),
            ("XML sitemap", any(x.get("urls") for x in sitemaps), f"{sum(x.get('urls', 0) for x in sitemaps if not x.get('index')):,} URLs"),
            ("llms.txt", any(v.get("ok") for v in llms.values()) if llms else None, "found" if any(v.get("ok") for v in llms.values()) else "missing"),
            ("AI crawlers", all(bots.values()) if bots else None,
             "all allowed" if bots and all(bots.values()) else f"{sum(1 for v in bots.values() if not v)} blocked" if bots else "—"),
        ]
        g = QGridLayout()
        g.setVerticalSpacing(8)
        for r_, (name, ok, txt) in enumerate(checks):
            g.addWidget(label(name), r_, 0)
            g.addWidget(status_pill(ok if ok is not None else None, txt), r_, 1, Qt.AlignRight)
        ck.add(g)
        ck.lay.addStretch()
        grid.addWidget(ck, 1, 1)

        # categories
        cat = Card()
        hr = QHBoxLayout()
        hr.addWidget(label(t("Issues by category"), "H2"))
        hr.addStretch()
        lg = QHBoxLayout()
        for sev in ("critical", "warning", "opportunity"):
            lg.addWidget(pill(sev))
        hr.addLayout(lg)
        cat.add(hr)
        agg = defaultdict(lambda: [0, 0, 0])
        for i in s.issues:
            agg[i["category"]][("critical", "warning", "opportunity").index(i["severity"])] += i["count"]
        cg = QGridLayout()
        cg.setHorizontalSpacing(20)
        cg.setVerticalSpacing(10)
        n = 0
        for c in CATEGORIES:
            if c not in agg:
                continue
            w = QWidget()
            w.setCursor(Qt.PointingHandCursor)
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(4)
            top_row = QHBoxLayout()
            top_row.addWidget(label(t(c)))
            top_row.addStretch()
            top_row.addWidget(label(f"{sum(agg[c]):,}", "Muted"))
            wl.addLayout(top_row)
            sb = StackBar()
            sb.set(*agg[c])
            wl.addWidget(sb)
            w.mouseReleaseEvent = lambda e, cc=c: self.main.goto("issues", category=cc)
            cg.addWidget(w, n // 3, n % 3)
            n += 1
        cat.add(cg)
        grid.addWidget(cat, 2, 0, 1, 2)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        self.body.addLayout(grid)
        self.body.addStretch()
