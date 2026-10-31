"""환경변수(.env) 기반 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """의존성 없이 .env 파일을 읽어 os.environ에 채운다. 이미 설정된 값은 덮어쓰지 않는다."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def parse_time_range(value: str | None) -> tuple[time, time] | None:
    """'00:00-07:00' → (time(0,0), time(7,0)). 빈 값이면 None."""
    if not value:
        return None
    start, _, end = value.partition("-")
    return time.fromisoformat(start.strip()), time.fromisoformat(end.strip())


@dataclass(frozen=True)
class Settings:
    bot_token: str
    chat_id: int | None
    db_path: Path
    report_silent: bool
    alert_quiet_hours: tuple[time, time] | None
    alert_interval_min: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=int(chat) if chat else None,
            db_path=Path(os.environ.get("DB_PATH", "data/portfolio.db")),
            report_silent=_parse_bool(os.environ.get("REPORT_SILENT"), False),
            alert_quiet_hours=parse_time_range(os.environ.get("ALERT_QUIET_HOURS", "00:00-07:00")),
            alert_interval_min=max(1, int(os.environ.get("ALERT_INTERVAL_MIN", "5"))),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
