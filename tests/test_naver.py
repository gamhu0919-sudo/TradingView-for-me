import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from bot.models import AssetType, Session
from bot.sources.naver import parse_fx, parse_quote, parse_search

FIX = Path(__file__).parent / "fixtures"
KST_NOW_SAT = datetime.fromisoformat("2026-10-31T13:00:00+09:00")


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def samsung():
    return load("naver_kr_005930.json")["datas"][0]


def test_kr_after_market_uses_nxt_price(samsung):
    q = parse_quote(samsung, "KRW", KST_NOW_SAT)
    assert q.session is Session.AFTER
    assert q.price == 220_000  # 넥스트레이드 애프터마켓
    assert q.regular_price == 220_500  # KRX 정규장 종가
    assert q.prev_close == 232_000  # 전일 종가 기준 하루 전체 등락
    assert q.change_pct == pytest.approx(-5.17, abs=0.01)
    assert q.regular_change_pct == pytest.approx(-4.96, abs=0.01)


def test_us_after_market_change_vs_previous_close():
    d = load("naver_us_aapl.json")["datas"][0]
    q = parse_quote(d, "USD", KST_NOW_SAT)
    assert q.session is Session.AFTER
    assert q.price == pytest.approx(345.10)
    assert q.prev_close == pytest.approx(348.91)
    assert q.regular_price == pytest.approx(344.63)


def _with_pre_market(d, ext_at):
    d = copy.deepcopy(d)
    d["overMarketPriceInfo"].update(tradingSessionType="PRE_MARKET", overPrice="225,000", localTradedAt=ext_at)
    return d


def test_kr_pre_market_before_open(samsung):
    d = _with_pre_market(samsung, "2026-11-02T08:30:00+09:00")
    q = parse_quote(d, "KRW", datetime.fromisoformat("2026-11-02T08:35:00+09:00"))
    assert q.session is Session.PRE
    assert q.price == 225_000
    assert q.prev_close == 220_500  # 프리마켓은 직전 정규장 종가 대비


def test_kr_stale_pre_market_after_close_is_ignored(samsung):
    d = _with_pre_market(samsung, "2026-11-02T08:50:00+09:00")
    q = parse_quote(d, "KRW", datetime.fromisoformat("2026-11-02T15:35:00+09:00"))
    assert q.session is Session.CLOSED
    assert q.price == 220_500


def test_stale_after_market_is_ignored_once_new_session_traded(samsung):
    d = copy.deepcopy(samsung)
    d["localTradedAt"] = "2026-11-02T15:30:00+09:00"  # 정규장이 그 뒤 다시 열렸음
    q = parse_quote(d, "KRW", datetime.fromisoformat("2026-11-02T15:35:00+09:00"))
    assert q.session is Session.CLOSED


def test_regular_session_open_ignores_extended(samsung):
    d = copy.deepcopy(samsung)
    d["marketStatus"] = "OPEN"
    q = parse_quote(d, "KRW", KST_NOW_SAT)
    assert q.session is Session.REGULAR
    assert q.price == 220_500


def test_unsigned_falling_change_is_negated(samsung):
    d = copy.deepcopy(samsung)
    d.pop("overMarketPriceInfo")
    d["compareToPreviousClosePriceRaw"] = "11500"
    q = parse_quote(d, "KRW", KST_NOW_SAT)
    assert q.prev_close == 232_000


def test_indices_and_fx():
    kospi = parse_quote(load("naver_kr_index.json")["datas"][0], "KRW", KST_NOW_SAT)
    assert kospi.code == "KOSPI" and kospi.change_pct == pytest.approx(-3.48, abs=0.01)
    spx = parse_quote(load("naver_us_index.json")["datas"][0], "USD", KST_NOW_SAT)
    assert spx.name == "S&P 500" and spx.session is Session.CLOSED
    fx = parse_fx(load("naver_fx.json")["result"])
    assert fx.price == pytest.approx(1335.8)
    assert fx.prev_close == pytest.approx(1340.5)


def test_search_parsing():
    results = parse_search(load("naver_ac_samsung.json"))
    assert results[0].asset_type is AssetType.KR
    assert (results[0].code, results[0].name, results[0].market) == ("005930", "삼성전자", "KOSPI")
    us = parse_search({"items": [{"code": "TSLA", "name": "테슬라", "typeCode": "NASDAQ", "reutersCode": "TSLA.O",
                                  "nationCode": "USA", "category": "stock"}]})
    assert us[0].code == "TSLA.O" and us[0].symbol == "TSLA"
