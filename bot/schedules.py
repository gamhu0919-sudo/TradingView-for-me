"""알림 일정 문법 해석과 실행 시각 판정.

예)
  08:30                     평일 08:30 전체 브리핑
  08:30 매일 코인            매일 08:30 코인 요약
  국장마감+10m              국내 개장일마다 15:40 전체 브리핑
  미장개장+15분 간단         미국 개장일마다 개장 15분 뒤 (서머타임 자동 반영)
  매시 09-15 간단            평일 09:00~15:00 매 정각
  매30분 09:00-15:30 간단    평일 30분 간격
  일 20:00 주간              일요일 20:00 주간 리포트
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .market import ANCHOR_ALIASES, ANCHORS, KST, is_trading_day, tz_of

REPORT_KINDS = {"전체": "full", "간단": "brief", "코인": "coin", "주간": "weekly"}
REPORT_LABELS = {v: k for k, v in REPORT_KINDS.items()}

_WEEKDAYS = "월화수목금토일"
_DAY_WORDS = {
    "매일": frozenset(range(7)),
    "평일": frozenset(range(5)),
    "주말": frozenset({5, 6}),
}
_ANCHOR_RE = re.compile(r"^(?P<name>[^\s+-]+?)(?:(?P<sign>[+-])(?P<num>\d+)(?P<unit>m|분|h|시간)?)?$", re.I)
_TIME_RE = re.compile(r"^(\d{1,2}):?(\d{2})$")
_EVERY_RE = re.compile(r"^(?:매(\d+)분|(\d+)분마다|매시|매시간)$")
_RANGE_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?$")


@dataclass(frozen=True)
class Spec:
    report: str = "full"
    at: time | None = None  # 고정 시각 (KST)
    anchor: str | None = None  # 시장 기준점 이름
    offset_min: int = 0
    every_min: int | None = None  # 반복 간격
    start: time | None = None
    end: time | None = None
    days: frozenset[int] = frozenset(range(5))
    trading_days_only: bool = False  # '개장일': 국내 휴장일 제외

    def describe(self) -> str:
        kind = REPORT_LABELS.get(self.report, self.report)
        if self.anchor:
            market = "국내" if ANCHORS[self.anchor][0] == "KR" else "미국"
            off = ""
            if self.offset_min:
                off = f" {'+' if self.offset_min > 0 else '-'}{abs(self.offset_min)}분"
            return f"{self.anchor}{off} ({market} 개장일) · {kind}"
        days = _describe_days(self.days) + (" 개장일" if self.trading_days_only else "")
        if self.every_min:
            return f"{days} {self.start:%H:%M}~{self.end:%H:%M} 매 {self.every_min}분 · {kind}"
        return f"{days} {self.at:%H:%M} · {kind}"

    def is_due(self, now: datetime) -> bool:
        """now(분 단위)에 실행해야 하는지."""
        now = now.astimezone(KST).replace(second=0, microsecond=0)
        if self.anchor:
            market, anchor_time = ANCHORS[self.anchor]
            local = (now - timedelta(minutes=self.offset_min)).astimezone(tz_of(market))
            return local.time() == anchor_time and is_trading_day(market, local.date())
        if now.weekday() not in self.days:
            return False
        if self.trading_days_only and not is_trading_day("KR", now.date()):
            return False
        if self.every_min:
            assert self.start and self.end
            if not (self.start <= now.time() <= self.end):
                return False
            minutes = (now.hour * 60 + now.minute) - (self.start.hour * 60 + self.start.minute)
            return minutes % self.every_min == 0
        return now.time() == self.at


def _describe_days(days: frozenset[int]) -> str:
    for word, value in _DAY_WORDS.items():
        if days == value:
            return word
    return "".join(_WEEKDAYS[d] for d in sorted(days))


def _parse_range(token: str) -> tuple[time, time] | None:
    m = _RANGE_RE.match(token)
    if not m:
        return None
    h1, m1, h2, m2 = m.groups()
    return time(int(h1), int(m1 or 0)), time(int(h2), int(m2 or 0))


def parse(text: str) -> Spec:
    """'국장마감+10m 전체' 같은 문자열을 Spec으로. 잘못된 입력은 ValueError."""
    tokens = text.split()
    if not tokens:
        raise ValueError("일정이 비어 있습니다.")

    report = "full"
    days: frozenset[int] | None = None
    trading_only = False
    at = anchor = every = rng = None
    offset = 0

    for tok in tokens:
        if tok in REPORT_KINDS:
            report = REPORT_KINDS[tok]
        elif tok in _DAY_WORDS:
            days = _DAY_WORDS[tok]
        elif tok == "개장일":
            trading_only = True
        elif tok and all(ch in _WEEKDAYS for ch in tok):
            days = frozenset(_WEEKDAYS.index(ch) for ch in tok)
        elif m := _TIME_RE.match(tok):
            hour, minute = int(m.group(1)), int(m.group(2))
            if hour > 23 or minute > 59:
                raise ValueError(f"시각 형식이 잘못됐습니다: {tok}")
            at = time(hour, minute)
        elif m := _EVERY_RE.match(tok):
            every = int(m.group(1) or m.group(2) or 60)
            if not 1 <= every <= 720:
                raise ValueError("반복 간격은 1~720분 사이여야 합니다.")
        elif (r := _parse_range(tok)) is not None:
            rng = r
        elif (m := _ANCHOR_RE.match(tok)) and (
            m.group("name") in ANCHORS or m.group("name").lower() in ANCHOR_ALIASES
        ):
            name = m.group("name")
            anchor = name if name in ANCHORS else ANCHOR_ALIASES[name.lower()]
            if m.group("num"):
                amount = int(m.group("num")) * (60 if (m.group("unit") or "").lower() in ("h", "시간") else 1)
                offset = amount if m.group("sign") == "+" else -amount
        else:
            raise ValueError(f"알 수 없는 항목: {tok}")

    if sum(x is not None for x in (at, anchor, every)) != 1:
        raise ValueError("시각(08:30), 시장 기준(국장마감+10m), 반복(매시) 중 하나만 지정하세요.")
    if abs(offset) > 12 * 60:
        raise ValueError("기준 시각 오프셋은 ±12시간 이내여야 합니다.")

    default_days = _DAY_WORDS["매일"] if report == "coin" else _DAY_WORDS["평일"]
    if anchor:
        return Spec(report=report, anchor=anchor, offset_min=offset)
    if every:
        start, end = rng or (time(0, 0), time(23, 59))
        if start > end:
            raise ValueError("반복 구간의 시작이 끝보다 늦습니다.")
        return Spec(report, every_min=every, start=start, end=end,
                    days=days or default_days, trading_days_only=trading_only)
    return Spec(report, at=at, days=days or default_days, trading_days_only=trading_only)


DEFAULT_SCHEDULES = [
    "08:30 평일 전체",
    "국장마감+10m 전체",
    "미장개장+10m 간단",
    "일 20:00 주간",
]
