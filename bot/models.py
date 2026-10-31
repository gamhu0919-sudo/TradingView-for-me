"""공용 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AssetType(StrEnum):
    KR = "kr"
    US = "us"
    COIN = "coin"

    @property
    def label(self) -> str:
        return {"kr": "국내", "us": "미국", "coin": "코인"}[self.value]

    @property
    def flag(self) -> str:
        return {"kr": "🇰🇷", "us": "🇺🇸", "coin": "🪙"}[self.value]

    @property
    def currency(self) -> str:
        return "USD" if self is AssetType.US else "KRW"


class Session(StrEnum):
    """Quote.price가 어느 시장 구간의 가격인지."""

    REGULAR = "regular"  # 정규장 진행 중
    CLOSED = "closed"  # 정규장 종가가 최신
    PRE = "pre"  # 프리마켓(국내는 넥스트레이드 프리) 가격이 최신
    AFTER = "after"  # 애프터마켓(국내는 넥스트레이드 애프터) 가격이 최신


@dataclass
class Quote:
    code: str
    name: str
    price: float  # 가장 최근 체결가 (프리/애프터 포함)
    prev_close: float  # '오늘 등락' 계산 기준가
    currency: str = "KRW"
    session: Session = Session.REGULAR
    regular_price: float | None = None  # 정규장 가격 (프리/애프터가 최신일 때 함께 표시)
    regular_change_pct: float | None = None
    traded_at: datetime | None = None
    source: str = ""

    @property
    def change(self) -> float:
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float:
        return (self.price / self.prev_close - 1) * 100 if self.prev_close else 0.0


@dataclass(frozen=True)
class Instrument:
    """검색 결과 또는 보유 종목의 식별 정보."""

    asset_type: AssetType
    code: str  # 국내: 005930, 미국: AAPL.O(네이버 reutersCode), 코인: KRW-BTC
    name: str
    market: str = ""  # KOSPI / KOSDAQ / NASDAQ / NYSE / UPBIT

    @property
    def symbol(self) -> str:
        """사용자에게 보여줄 짧은 코드."""
        if self.asset_type is AssetType.US:
            return self.code.split(".")[0]
        if self.asset_type is AssetType.COIN:
            return self.code.split("-", 1)[-1]
        return self.code


@dataclass
class Holding:
    instrument: Instrument
    qty: float
    avg_price: float  # 종목 통화 기준 (미국 주식은 달러)
    buy_fx: float | None = None  # 미국 주식 평균 매수 환율 (입력 시 환차손익 분리)
    id: int | None = None

    @property
    def asset_type(self) -> AssetType:
        return self.instrument.asset_type

    @property
    def code(self) -> str:
        return self.instrument.code

    @property
    def name(self) -> str:
        return self.instrument.name
