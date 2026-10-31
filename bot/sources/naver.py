"""네이버 증권 시세 (국내·미국 주식, 지수, 환율, 종목 검색).

네이버 증권 웹이 내부적으로 쓰는 공개 엔드포인트로, 공식 API가 아니므로 응답 형식이 바뀔 수 있다.
조회 실패 시 상위 계층(market_data)이 Yahoo로 대체한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from ..models import AssetType, Instrument, Quote, Session
from .http import Http

log = logging.getLogger(__name__)

REALTIME = "https://polling.finance.naver.com/api/realtime"
AUTOCOMPLETE = "https://ac.stock.naver.com/ac"
MARKET_INDEX = "https://m.stock.naver.com/front-api/marketIndex/productDetail"

BATCH = 20
_FALLING_CODES = {"4", "5"}  # 4: 하한, 5: 하락


def _num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _signed_change(raw: Any, direction: dict | None) -> float:
    """등락폭 부호를 방향 코드와 맞춘다 (일부 응답은 부호 없이 내려온다)."""
    change = _num(raw) or 0.0
    if direction and str(direction.get("code")) in _FALLING_CODES and change > 0:
        change = -change
    return change


def _zone(exchange: dict) -> ZoneInfo:
    try:
        return ZoneInfo(exchange.get("zoneId") or "Asia/Seoul")
    except Exception:  # noqa: BLE001 - 알 수 없는 zoneId
        return ZoneInfo("America/New_York" if exchange.get("nationType") == "USA" else "Asia/Seoul")


def _hhmm(value: Any, default: str) -> time:
    text = str(value or default)
    return time(int(text[:2]), int(text[2:4]))


def parse_quote(d: dict, currency: str, now: datetime | None = None) -> Quote:
    """realtime 응답의 datas 항목 하나를 Quote로 변환.

    정규장이 닫혀 있을 때 프리/애프터마켓(국내는 넥스트레이드) 체결이 더 최신이면 그 가격을 쓴다.
      - 프리마켓: 오늘 정규장 개장 전에만 유효. 등락 기준은 직전 정규장 종가.
      - 애프터마켓: 그 뒤로 정규장이 다시 열리지 않았을 때 유효. 등락 기준은 정규장의 전일 종가
        (즉 정규장+애프터를 합친 하루 전체 등락).
    """
    code = d.get("reutersCode") or d.get("itemCode") or d.get("symbolCode") or ""
    name = d.get("stockName") or d.get("indexName") or code
    exchange = d.get("stockExchangeType") or {}

    regular = _num(d.get("closePriceRaw")) or _num(d.get("closePrice"))
    if regular is None:
        raise ValueError(f"가격 없음: {code}")
    change = _signed_change(
        d.get("compareToPreviousClosePriceRaw") or d.get("compareToPreviousClosePrice"),
        d.get("compareToPreviousPrice"),
    )
    regular_prev = regular - change
    traded_at = _dt(d.get("localTradedAt"))
    is_open = d.get("marketStatus") == "OPEN"

    quote = Quote(
        code=code,
        name=name,
        price=regular,
        prev_close=regular_prev,
        currency=currency,
        session=Session.REGULAR if is_open else Session.CLOSED,
        regular_price=regular,
        regular_change_pct=(regular / regular_prev - 1) * 100 if regular_prev else 0.0,
        traded_at=traded_at,
        source="naver",
    )

    over = d.get("overMarketPriceInfo") or {}
    ext_price = _num(over.get("overPrice"))
    ext_at = _dt(over.get("localTradedAt"))
    if is_open or not ext_price or not ext_at:
        return quote

    tz = _zone(exchange)
    ext_local = ext_at.astimezone(tz)
    session_type = over.get("tradingSessionType")
    if session_type == "PRE_MARKET":
        now_local = (now or datetime.now(tz)).astimezone(tz)
        opens = _hhmm(exchange.get("startTime"), "0900")
        if ext_local.date() != now_local.date() or now_local.time() >= opens:
            return quote  # 정규장이 이미 열렸다 닫힌 뒤의 오래된 프리마켓 데이터
        quote.session, quote.prev_close = Session.PRE, regular
    elif session_type == "AFTER_MARKET":
        closes = _hhmm(exchange.get("endTime"), "1530")
        stale = traded_at is not None and traded_at.astimezone(tz).date() > ext_local.date()
        if ext_local.time() < closes or stale:
            return quote
        quote.session = Session.AFTER
    else:
        return quote
    quote.price = ext_price
    quote.traded_at = ext_at
    return quote


def parse_fx(result: dict) -> Quote:
    price = _num(result.get("calcPrice")) or _num(result.get("closePrice"))
    if price is None:
        raise ValueError("환율 없음")
    change = _signed_change(result.get("fluctuations"), result.get("fluctuationsType"))
    return Quote(
        code=result.get("reutersCode", "FX_USDKRW"),
        name="원/달러",
        price=price,
        prev_close=price - change,
        currency="KRW",
        session=Session.REGULAR,
        traded_at=_dt(result.get("localTradedAt")),
        source="naver",
    )


def parse_search(payload: dict) -> list[Instrument]:
    results: list[Instrument] = []
    for item in payload.get("items") or []:
        if item.get("category") != "stock":
            continue
        nation = item.get("nationCode")
        if nation == "KOR":
            results.append(
                Instrument(AssetType.KR, item["code"], item.get("name", item["code"]), item.get("typeCode", ""))
            )
        elif nation == "USA" and item.get("reutersCode"):
            results.append(
                Instrument(AssetType.US, item["reutersCode"], item.get("name", item["code"]), item.get("typeCode", ""))
            )
    return results


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Naver:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def _realtime(self, path: str, codes: list[str], currency: str) -> dict[str, Quote]:
        quotes: dict[str, Quote] = {}
        now = datetime.now().astimezone()
        for chunk in _chunks(sorted(set(codes)), BATCH):
            payload = await self.http.get_json(f"{REALTIME}/{path}/{','.join(chunk)}")
            for d in payload.get("datas") or []:
                try:
                    q = parse_quote(d, currency, now)
                except ValueError as exc:
                    log.warning("네이버 응답 해석 실패: %s", exc)
                    continue
                key = d.get("reutersCode") if path.startswith("worldstock") else d.get("itemCode")
                quotes[key or q.code] = q
        return quotes

    async def kr_stocks(self, codes: list[str]) -> dict[str, Quote]:
        return await self._realtime("domestic/stock", codes, "KRW") if codes else {}

    async def us_stocks(self, reuters_codes: list[str]) -> dict[str, Quote]:
        return await self._realtime("worldstock/stock", reuters_codes, "USD") if reuters_codes else {}

    async def kr_indices(self, codes: list[str]) -> dict[str, Quote]:
        return await self._realtime("domestic/index", codes, "KRW")

    async def us_indices(self, codes: list[str]) -> dict[str, Quote]:
        return await self._realtime("worldstock/index", codes, "USD")

    async def usdkrw(self) -> Quote:
        payload = await self.http.get_json(MARKET_INDEX, {"category": "exchange", "reutersCode": "FX_USDKRW"})
        return parse_fx(payload.get("result") or {})

    async def search(self, query: str) -> list[Instrument]:
        payload = await self.http.get_json(AUTOCOMPLETE, {"q": query, "target": "stock"})
        return parse_search(payload)
