"""여러 시세 소스를 묶어 한 번에 조회한다. 일부가 실패해도 나머지는 정상 반환한다."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, TypeVar

from .models import AssetType, Instrument, Quote
from .sources.http import Http
from .sources.naver import Naver
from .sources.sentiment import FearGreed, fear_greed
from .sources.upbit import Upbit
from .sources.yahoo import Yahoo

log = logging.getLogger(__name__)
T = TypeVar("T")

KR_INDICES = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}
US_INDICES = {".INX": "S&P500", ".IXIC": "나스닥", ".DJI": "다우"}
BTC, USDT = "KRW-BTC", "KRW-USDT"


@dataclass
class Snapshot:
    quotes: dict[tuple[AssetType, str], Quote] = field(default_factory=dict)
    indices: list[Quote] = field(default_factory=list)
    usdkrw: Quote | None = None
    btc: Quote | None = None
    usdt: Quote | None = None
    fear_greed: FearGreed | None = None
    errors: list[str] = field(default_factory=list)
    fallbacks: list[str] = field(default_factory=list)  # Yahoo로 대체 조회한 종목명

    def quote(self, inst: Instrument) -> Quote | None:
        return self.quotes.get((inst.asset_type, inst.code))

    @property
    def tether_premium(self) -> float | None:
        """업비트 USDT 원화가격 / 원달러 환율 - 1 (김치 프리미엄 근사치, %)."""
        if self.usdt and self.usdkrw and self.usdkrw.price:
            return (self.usdt.price / self.usdkrw.price - 1) * 100
        return None


class MarketData:
    def __init__(self, http: Http | None = None) -> None:
        self.http = http or Http()
        self.naver = Naver(self.http)
        self.upbit = Upbit(self.http)
        self.yahoo = Yahoo(self.http)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _safe(self, label: str, coro: Awaitable[T], errors: list[str]) -> T | None:
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001 - 소스 하나의 실패가 전체를 멈추지 않게
            log.warning("%s 조회 실패: %s", label, exc)
            errors.append(f"{label} 조회 실패")
            return None

    async def fetch(self, instruments: list[Instrument], market: bool = True) -> Snapshot:
        """보유/관심 종목 시세와 (market=True면) 지수·환율·코인 지표를 함께 조회."""
        snap = Snapshot()
        kr = [i.code for i in instruments if i.asset_type is AssetType.KR]
        us = [i.code for i in instruments if i.asset_type is AssetType.US]
        coins = {i.code for i in instruments if i.asset_type is AssetType.COIN}
        if market:
            coins |= {BTC, USDT}

        tasks = {
            "kr": self._safe("국내 주식", self.naver.kr_stocks(kr), snap.errors),
            "us": self._safe("미국 주식", self.naver.us_stocks(us), snap.errors),
            "coin": self._safe("업비트", self.upbit.tickers(sorted(coins)), snap.errors),
            "fx": self._safe("환율", self.naver.usdkrw(), snap.errors),
        }
        if market:
            tasks |= {
                "kr_idx": self._safe("국내 지수", self.naver.kr_indices(list(KR_INDICES)), snap.errors),
                "us_idx": self._safe("미국 지수", self.naver.us_indices(list(US_INDICES)), snap.errors),
                "fng": self._safe("공포탐욕지수", fear_greed(self.http), snap.errors),
            }
        results = dict(zip(tasks, await asyncio.gather(*tasks.values())))

        for asset_type, key in ((AssetType.KR, "kr"), (AssetType.US, "us"), (AssetType.COIN, "coin")):
            for code, quote in (results.get(key) or {}).items():
                snap.quotes[(asset_type, code)] = quote

        await self._fallback(instruments, snap)

        snap.usdkrw = results.get("fx")
        coin_quotes = results.get("coin") or {}
        snap.btc, snap.usdt = coin_quotes.get(BTC), coin_quotes.get(USDT)
        snap.fear_greed = results.get("fng")
        for table, names in ((results.get("kr_idx"), KR_INDICES), (results.get("us_idx"), US_INDICES)):
            for code, label in names.items():
                if table and code in table:
                    table[code].name = label
                    snap.indices.append(table[code])
        return snap

    async def _fallback(self, instruments: list[Instrument], snap: Snapshot) -> None:
        missing = [
            i for i in instruments
            if i.asset_type in (AssetType.KR, AssetType.US) and snap.quote(i) is None
        ]
        if not missing:
            return
        results = await asyncio.gather(
            *(self._safe(f"{i.name}(Yahoo)", self.yahoo.quote(i), snap.errors) for i in missing)
        )
        for inst, quote in zip(missing, results):
            if quote is not None:
                snap.quotes[(inst.asset_type, inst.code)] = quote
                snap.fallbacks.append(inst.name)

    async def search(self, query: str) -> list[Instrument]:
        """종목명/코드로 국내·미국 주식과 업비트 코인을 함께 검색."""
        errors: list[str] = []
        stocks, coins = await asyncio.gather(
            self._safe("종목 검색", self.naver.search(query), errors),
            self._safe("코인 검색", self.upbit.search(query), errors),
        )
        stocks, coins = stocks or [], coins or []
        q = query.strip().upper()
        exact = [i for i in stocks + coins if q in (i.code.upper(), i.symbol.upper(), i.name.upper())]
        if exact:
            return exact
        return (stocks + coins)[:8]

    async def quotes_for(self, instruments: list[Instrument]) -> Snapshot:
        return await self.fetch(instruments, market=False)
