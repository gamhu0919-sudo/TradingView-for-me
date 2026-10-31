"""업비트 공개 시세 API (인증키 불필요). 원화(KRW) 마켓만 사용한다.

업비트의 '전일 대비'는 매일 오전 9시(KST)에 초기화된다.
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone

from ..models import AssetType, Instrument, Quote, Session
from .http import Http

BASE = "https://api.upbit.com/v1"
MARKETS_TTL = 6 * 3600


def parse_ticker(d: dict, name: str | None = None) -> Quote:
    price = float(d["trade_price"])
    prev = float(d.get("prev_closing_price") or price)
    ts = d.get("trade_timestamp") or d.get("timestamp")
    return Quote(
        code=d["market"],
        name=name or d["market"].split("-", 1)[-1],
        price=price,
        prev_close=prev,
        currency="KRW",
        session=Session.REGULAR,
        traded_at=datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else None,
        source="upbit",
    )


class Upbit:
    def __init__(self, http: Http) -> None:
        self.http = http
        self._markets: list[Instrument] = []
        self._markets_at = 0.0

    async def markets(self) -> list[Instrument]:
        if not self._markets or _time.monotonic() - self._markets_at > MARKETS_TTL:
            payload = await self.http.get_json(f"{BASE}/market/all", {"isDetails": "false"})
            self._markets = [
                Instrument(AssetType.COIN, m["market"], m.get("korean_name") or m["market"], "UPBIT")
                for m in payload
                if m["market"].startswith("KRW-")
            ]
            self._markets_at = _time.monotonic()
        return self._markets

    async def tickers(self, markets: list[str]) -> dict[str, Quote]:
        if not markets:
            return {}
        names = {m.code: m.name for m in await self.markets()}
        payload = await self.http.get_json(f"{BASE}/ticker", {"markets": ",".join(sorted(set(markets)))})
        return {d["market"]: parse_ticker(d, names.get(d["market"])) for d in payload}

    async def search(self, query: str) -> list[Instrument]:
        q = query.strip().upper()
        markets = await self.markets()
        exact = [m for m in markets if m.symbol == q or m.name == query.strip() or m.code == q]
        if exact:
            return exact
        return [m for m in markets if q in m.symbol or query.strip() in m.name][:8]
