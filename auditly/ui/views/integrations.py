"""Integrations: PageSpeed Insights (Core Web Vitals) and IndexNow."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPlainTextEdit, QSpinBox

from ...audits import run_audits
from ...integrations import indexnow, pagespeed
from ..i18n import t
from ..widgets import Card, button, label, run_worker
from .base import View


def _psi_batch(db_path, urls, strategy, key, progress=None):
    done, errors = 0, []
    for u in urls:
        try:
            pagespeed.save(db_path, pagespeed.run(u, strategy, key))
            done += 1
        except Exception as e:
            errors.append(f"{u}: {e}")
    run_audits(db_path)
    return done, errors


class IntegrationsView(View):
    def __init__(self, main):
        super().__init__(main, scroll=True)
        self.header(t("Integrations"), "Connect external data to your crawl.")

        psi = Card(padding=20, spacing=10)
        psi.add(label("PageSpeed Insights · Core Web Vitals", "H2"))
        psi.add(label("Fetches LCP, INP and CLS (real-user CrUX data when available, otherwise Lighthouse lab data) for your "
                      "strongest pages and adds them to the Performance audits. Works without a key at low volume; add a "
                      "free API key in Settings for more.", "Muted", wrap=True))
        r = QHBoxLayout()
        r.addWidget(label(t("Number of pages")))
        self.psi_n = QSpinBox(minimum=1, maximum=500, value=10)
        r.addWidget(self.psi_n)
        r.addWidget(label(t("Strategy")))
        self.psi_strategy = QComboBox()
        self.psi_strategy.addItem(t("Mobile"), "mobile")
        self.psi_strategy.addItem(t("Desktop"), "desktop")
        r.addWidget(self.psi_strategy)
        self.psi_btn = button(t("Run on top pages"), "Primary", "zap", on=self.run_psi)
        r.addWidget(self.psi_btn)
        r.addStretch()
        psi.add(r)
        self.psi_status = label("", "Muted", wrap=True)
        psi.add(self.psi_status)
        self.body.addWidget(psi)

        inow = Card(padding=20, spacing=10)
        inow.add(label("IndexNow", "H2"))
        inow.add(label("Tell Bing, Yandex, Seznam and other IndexNow engines about new or updated URLs. Host your key at "
                       "https://yoursite/<key>.txt and add the key in Settings.", "Muted", wrap=True))
        self.inow_urls = QPlainTextEdit()
        self.inow_urls.setPlaceholderText("One URL per line (leave empty to submit all indexable pages from this crawl)")
        self.inow_urls.setMaximumHeight(120)
        inow.add(self.inow_urls)
        r2 = QHBoxLayout()
        self.inow_btn = button(t("Submit URLs"), "Primary", "send", on=self.submit)
        r2.addWidget(self.inow_btn)
        self.inow_status = label("", "Muted", wrap=True)
        r2.addWidget(self.inow_status, 1)
        inow.add(r2)
        self.body.addWidget(inow)

        more = Card(padding=20, spacing=6)
        more.add(label("Coming next", "H2"))
        more.add(label("Google Search Console, GA4, Bing Webmaster Tools, CrUX history and backlink providers "
                       "(Ahrefs, Semrush, Majestic, Moz, DataForSEO) are on the roadmap — see CONTRIBUTING.md.", "Muted", wrap=True))
        self.body.addWidget(more)
        self.body.addStretch()

    def load(self, session):
        super().load(session)
        self.psi_btn.setEnabled(bool(session))
        self.inow_btn.setEnabled(bool(session))

    def run_psi(self):
        if not self.session:
            return
        n = self.psi_n.value()
        pages = sorted((p for p in self.session.pages if p.get("indexability") == "Indexable"),
                       key=lambda p: -(p.get("link_score") or 0))[:n]
        urls = [p["url"] for p in pages]
        if not urls:
            self.psi_status.setText("No indexable pages in this crawl.")
            return
        self.psi_btn.setEnabled(False)
        self.psi_status.setText(f"Testing {len(urls)} pages… this takes ~20 s per page.")
        run_worker(self, _psi_batch, self.session.db_path, urls, self.psi_strategy.currentData(),
                   self.main.settings.pagespeed_api_key, on_result=self._psi_done, on_error=self._psi_err)

    def _psi_done(self, res):
        done, errors = res
        self.psi_btn.setEnabled(True)
        msg = f"Done: {done} pages tested."
        if errors:
            msg += f" {len(errors)} failed — e.g. {errors[0][:200]}"
        self.psi_status.setText(msg)
        self.main.reload_session()

    def _psi_err(self, msg):
        self.psi_btn.setEnabled(True)
        self.psi_status.setText(msg)

    def submit(self):
        if not self.session:
            return
        urls = [u.strip() for u in self.inow_urls.toPlainText().splitlines() if u.strip()]
        if not urls:
            urls = [p["url"] for p in self.session.pages if p.get("indexability") == "Indexable"]
        self.inow_btn.setEnabled(False)
        run_worker(self, indexnow.submit, urls, self.main.settings.indexnow_key,
                   on_result=lambda r: (self.inow_status.setText(r[1]), self.inow_btn.setEnabled(True)),
                   on_error=lambda m: (self.inow_status.setText(m), self.inow_btn.setEnabled(True)))
