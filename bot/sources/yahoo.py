"""Yahoo Finance 차트 API. 네이버 조회가 실패했을 때만 쓰는 예비 소스 (지연 시세일 수 있음)."""

from __future__ import annotations

from datetime import datetime, timezone

from ..models import AssetType, Instrument, Quote, Session
from .http import Http

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def yahoo_symbol(inst: Instrument) -> str | None:
    if inst.asset_type is AssetType.KR:
        return f"{inst.code}.KQ" if inst.market.upper() == "KOSDAQ" else f"{inst.code}.KS"
    if inst.asset_type is AssetType.US:
        return inst.symbol.replace(".", "-")
    return None


class Yahoo:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def quote(self, inst: Instrument) -> Quote:
        symbol = yahoo_symbol(inst)
        if not symbol:
            raise ValueError(f"Yahoo 미지원: {inst.code}")
        payload = await self.http.get_json(CHART.format(symbol=symbol), {"interval": "1d", "range": "5d"})
        meta = payload["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        ts = meta.get("regularMarketTime")
        return Quote(
            code=inst.code,
            name=inst.name,
            price=price,
            prev_close=prev,
            currency=inst.asset_type.currency,
            session=Session.CLOSED,
            traded_at=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
            source="yahoo",
        )
