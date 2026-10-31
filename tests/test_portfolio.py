import pytest

from bot.market_data import Snapshot
from bot.models import AssetType, Instrument, Quote
from bot.portfolio import value_portfolio
from bot.storage import Store

SAMSUNG = Instrument(AssetType.KR, "005930", "삼성전자", "KOSPI")
AAPL = Instrument(AssetType.US, "AAPL.O", "애플", "NASDAQ")
BTC = Instrument(AssetType.COIN, "KRW-BTC", "비트코인", "UPBIT")


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_buy_recomputes_weighted_average(store):
    store.buy(SAMSUNG, 10, 50_000)
    h = store.buy(SAMSUNG, 30, 70_000)
    assert h.qty == 40
    assert h.avg_price == pytest.approx(65_000)


def test_buy_fx_weighted_and_dropped_when_mixed(store):
    store.buy(AAPL, 10, 100, buy_fx=1300)
    h = store.buy(AAPL, 10, 300, buy_fx=1400)
    assert h.buy_fx == pytest.approx((1000 * 1300 + 3000 * 1400) / 4000)
    h = store.buy(AAPL, 1, 200)  # 환율 없이 추가 매수 → 분리 불가
    assert h.buy_fx is None


def test_sell_records_realized_and_removes_when_empty(store):
    h = store.buy(SAMSUNG, 10, 50_000)
    left, realized = store.sell(h, 4, 60_000)
    assert realized == 40_000
    assert left.qty == 6 and left.avg_price == 50_000
    left, realized = store.sell(left, 6, 40_000)
    assert left is None and realized == -60_000
    assert store.holdings() == []
    assert store.realized_since(__import__("datetime").datetime(2000, 1, 1)) == {"KRW": -20_000}


def test_sell_more_than_held_rejected(store):
    h = store.buy(SAMSUNG, 1, 50_000)
    with pytest.raises(ValueError):
        store.sell(h, 2, 50_000)


def test_valuation_totals_with_fx_and_missing_quote(store):
    store.set_holding(SAMSUNG, 10, 50_000)
    store.set_holding(AAPL, 10, 100, buy_fx=1300)
    store.set_holding(BTC, 0.5, 80_000_000)
    store.set_cash("KRW", 1_000_000)
    snap = Snapshot(
        quotes={
            (AssetType.KR, "005930"): Quote("005930", "삼성전자", 60_000, 55_000),
            (AssetType.US, "AAPL.O"): Quote("AAPL.O", "애플", 110, 100, currency="USD"),
            # 코인 시세 없음 → 매입가로 계산
        },
        usdkrw=Quote("FX", "원/달러", 1400, 1400),
    )
    val = value_portfolio(store.holdings(), snap, store.cash())
    kr, us, coin = (val.by_class[t] for t in AssetType)
    assert kr.value == 600_000 and kr.cost == 500_000 and kr.day_change == 50_000
    assert us.value == 10 * 110 * 1400
    assert us.cost == 10 * 100 * 1300  # 매수 환율 기준 원가
    aapl = next(p for p in val.positions if p.holding.code == "AAPL.O")
    assert aapl.fx_pnl_krw == 10 * 100 * (1400 - 1300)
    assert coin.value == coin.cost == 40_000_000
    assert [p.holding.code for p in val.missing] == ["KRW-BTC"]
    assert val.total_value == 600_000 + 1_540_000 + 40_000_000 + 1_000_000


def test_snapshot_and_settings_roundtrip(store):
    from datetime import date
    store.save_snapshot(date(2026, 10, 23), 100.0, 90.0)
    store.save_snapshot(date(2026, 10, 30), 110.0, 90.0)
    assert store.snapshot_on_or_before(date(2026, 10, 24))["total_krw"] == 100.0
    assert store.mark_sent("k") is True
    assert store.mark_sent("k") is False
