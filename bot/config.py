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
    for raw in p.read_text(encoding="utf-8-sig").splitlines():  # 메모장이 붙이는 BOM 허용
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env_value(path: str | Path, key: str, value: str) -> bool:
    """.env 의 key 값을 바꾸거나 추가한다. 다른 줄은 그대로 둔다. 쓰기 실패 시 False."""
    p = Path(path)
    try:
        lines = p.read_text(encoding="utf-8-sig").splitlines() if p.is_file() else []
        out, found = [], False
        for line in lines:
            if line.strip().startswith(f"{key}="):
                out.append(f"{key}={value}")
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f"{key}={value}")
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError:
        return False
    os.environ[key] = value
    return True


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
    log_file: Path | None = None

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
            log_file=Path(os.environ["LOG_FILE"]) if os.environ.get("LOG_FILE") else None,
        )
