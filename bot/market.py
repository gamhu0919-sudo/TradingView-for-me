"""시장 운영시간·휴장일. 서머타임은 zoneinfo가 자동 반영한다."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import holidays

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

_CALENDARS = {
    "KR": holidays.financial_holidays("XKRX"),
    "US": holidays.financial_holidays("XNYS"),
}
_TZ = {"KR": KST, "US": NY}

# 프리마켓 시작 ~ 애프터마켓 종료 (현지 시각). 국내는 넥스트레이드 기준.
_ACTIVE = {"KR": (time(8, 0), time(20, 0)), "US": (time(4, 0), time(20, 0))}

# 일정 기준점: 이름 → (시장, 현지 시각)
ANCHORS: dict[str, tuple[str, time]] = {
    "국장프리": ("KR", time(8, 0)),
    "국장개장": ("KR", time(9, 0)),
    "국장마감": ("KR", time(15, 30)),
    "NXT마감": ("KR", time(20, 0)),
    "미장프리": ("US", time(4, 0)),
    "미장개장": ("US", time(9, 30)),
    "미장마감": ("US", time(16, 0)),
}
ANCHOR_ALIASES = {"넥스트마감": "NXT마감", "nxt마감": "NXT마감", "애프터마감": "NXT마감"}


def tz_of(market: str) -> ZoneInfo:
    return _TZ[market]


def is_trading_day(market: str, d: date) -> bool:
    return d.weekday() < 5 and d not in _CALENDARS[market]


def is_active(market: str, now: datetime) -> bool:
    """프리·정규·애프터 중 하나라도 열려 있는 시간인지."""
    local = now.astimezone(_TZ[market])
    start, end = _ACTIVE[market]
    return is_trading_day(market, local.date()) and start <= local.time() <= end


def now_kst() -> datetime:
    return datetime.now(KST)
