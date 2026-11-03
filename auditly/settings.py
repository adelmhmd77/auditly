"""User settings, stored as JSON in the app data folder."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .paths import data_dir, default_export_root


@dataclass
class Settings:
    theme: str = "light"            # light | dark
    language: str = "en"            # en | ar
    export_dir: str = ""            # empty = Downloads/Auditly
    ask_export_folder: bool = False  # ask for a folder on every export
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    pagespeed_api_key: str = ""
    indexnow_key: str = ""
    brand_name: str = ""            # white-label reports
    brand_color: str = "#00E676"
    brand_logo: str = ""
    report_language: str = "en"     # language of AI output
    last_profile: dict = field(default_factory=dict)

    @property
    def export_root(self) -> Path:
        return Path(self.export_dir) if self.export_dir else default_export_root()

    @property
    def api_key(self) -> str:
        return self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")


_PATH = data_dir() / "settings.json"


def load() -> Settings:
    s = Settings()
    try:
        raw = json.loads(_PATH.read_text(encoding="utf-8"))
        names = {f.name for f in fields(Settings)}
        for k, v in raw.items():
            if k in names:
                setattr(s, k, v)
    except (OSError, ValueError):
        pass
    return s


def save(s: Settings) -> None:
    _PATH.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")
    try:
        os.chmod(_PATH, 0o600)  # holds API keys
    except OSError:
        pass
