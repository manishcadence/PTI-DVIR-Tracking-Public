"""Read deployment settings with environment overrides."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mode: str
    url: str = field(repr=False)
    token: str = field(repr=False)
    timezone: str
    ttl: int
    timeout: float
    sqlite_path: str
    keys: tuple[str, str, str, str]
    local_json_path: str = ""
    training_path: str = str(ROOT / "data" / "training.sqlite3")
    history_path: str = str(ROOT / "data" / "dvir_history.sqlite3")
    history_backup_dir: str = str(ROOT / "data" / "backups")
    download_url: str = ''
    upload_only: bool = True


def settings() -> Settings:
    load_dotenv(ROOT / ".env")

    def value(key: str, default: str = "") -> str:
        if key in os.environ:
            return os.environ[key]
        try:
            return str(st.secrets.get(key, default))
        except FileNotFoundError:
            return default

    mode = value("PTI_MODE", "demo").lower()
    tz = value("PTI_TIMEZONE", "America/Chicago")
    ttl = int(value("PTI_CACHE_TTL", "300"))
    timeout = float(value("PTI_HTTP_TIMEOUT", "15"))
    ZoneInfo(tz)
    if mode not in {"demo", "live"} or ttl < 1 or not 0 < timeout <= 120:
        raise ValueError("Invalid dashboard settings.")
    return Settings(mode, value("N8N_WEBHOOK_URL"), value("N8N_WEBHOOK_TOKEN"), tz,
                    ttl, timeout, value("PTI_SQLITE_PATH"),
                    (value("PTI_INSPECTIONS_KEY", "inspections"), value("PTI_DRIVERS_KEY", "drivers"),
                     value("PTI_ASSIGNMENTS_KEY", "driverAssignments"), value("PTI_TEAMS_KEY", "teamAssignments")),
                    value("PTI_LOCAL_JSON_PATH"),
                    value("PTI_TRAINING_DB", str(ROOT / "data" / "training.sqlite3")),
                    value("PTI_HISTORY_DB", str(ROOT / "data" / "dvir_history.sqlite3")),
                    value("PTI_HISTORY_BACKUP_DIR", str(ROOT / "data" / "backups")),
                    value("PTI_DOWNLOAD_URL"),
                    value("PTI_UPLOAD_ONLY", "true").lower() in ("true", "1", "yes"))
