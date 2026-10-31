import asyncio
from datetime import datetime, time

import pytest

from bot.market_data import Snapshot
from bot.models import AssetType, Holding, Instrument, Quote
from bot.report import full_report, split_messages
from bot.portfolio import value_portfolio
from bot.service import Service
from bot.storage import Store
from bot.telegram_bot import in_quiet_hours, match_holdings, parse_trade

BTC = Instrument(AssetType.COIN, "KRW-BTC", "비트코인", "UPBIT")
SAMSUNG = Instrument(AssetType.KR, "005930", "삼성전자", "KOSPI")
SAT_NOON = datetime.fromisoformat("2026-10-31T12:00:00+09:00")


class FakeData:
    def __init__(self):
        self.prices: dict[str, Quote] = {}

    async def fetch(self, instruments, market=True):
        return Snapshot(quotes={(i.asset_type, i.code): self.prices[i.code] for i in instruments if i.code in self.prices})


@pytest.fixture
def svc():
    store = Store(":memory:")
    yield Service(store, FakeData())
    store.close()


def test_move_alert_levels_and_dedupe(svc):
    svc.store.set_holding(BTC, 1, 90_000_000)
    svc.store.set_holding(SAMSUNG, 1, 50_000)  # 토요일: 국내 시장 닫힘 → 확인 안 함
    svc.data.prices["KRW-BTC"] = Quote("KRW-BTC", "비트코인", 105_000_000, 100_000_000, source="upbit")
    svc.data.prices["005930"] = Quote("005930", "삼성전자", 40_000, 50_000, source="naver")

    first = asyncio.run(svc.check_alerts(SAT_NOON))
    assert len(first) == 1 and "비트코인 급등" in first[0]
    assert asyncio.run(svc.check_alerts(SAT_NOON)) == []  # 같은 단계 재알림 없음

    svc.data.prices["KRW-BTC"].price = 110_000_000  # +10% → 다음 단계
    second = asyncio.run(svc.check_alerts(SAT_NOON))
    assert len(second) == 1 and "±10%" in second[0]


def test_threshold_off_and_target_once(svc):
    svc.set_threshold(None)
    svc.store.add_target(BTC, "above", 104_000_000)
    svc.data.prices["KRW-BTC"] = Quote("KRW-BTC", "비트코인", 105_000_000, 100_000_000, source="upbit")
    msgs = asyncio.run(svc.check_alerts(SAT_NOON))
    assert len(msgs) == 1 and "목표가" in msgs[0]
    assert asyncio.run(svc.check_alerts(SAT_NOON)) == []
    assert svc.store.targets() == []


def test_yahoo_fallback_quotes_do_not_alert(svc):
    svc.store.set_holding(BTC, 1, 1)
    svc.data.prices["KRW-BTC"] = Quote("KRW-BTC", "비트코인", 200, 100, source="yahoo")
    assert asyncio.run(svc.check_alerts(SAT_NOON)) == []


def test_full_report_contents():
    h = Holding(SAMSUNG, 10, 50_000, id=1)
    snap = Snapshot(quotes={(AssetType.KR, "005930"): Quote("005930", "삼성전자", 60_000, 55_000)},
                    errors=["미국 지수 조회 실패"])
    val = value_portfolio([h], snap, {})
    text = "\n".join(full_report(val, snap, SAT_NOON, threshold=5))
    assert "총자산 600,000원" in text
    assert "삼성전자 60,000 (+9.09%)" in text
    assert "급등" in text and "미국 지수 조회 실패" in text


def test_split_messages_respects_limit():
    parts = split_messages(["a" * 3000, "b" * 3000, "c" * 10])
    assert len(parts) == 2 and all(len(p) <= 4096 for p in parts)


def test_parse_trade_variants():
    assert parse_trade(["KODEX", "200", "10", "35,000"]) == ("KODEX 200", 10, 35000, None)
    assert parse_trade(["AAPL", "5", "$185.5", "@1,380"]) == ("AAPL", 5, 185.5, 1380)
    assert parse_trade(["AAPL", "전량", "230"], allow_all=True) == ("AAPL", None, 230, None)
    with pytest.raises(ValueError):
        parse_trade(["AAPL", "5"])


def test_match_holdings_by_id_code_and_name():
    hs = [Holding(SAMSUNG, 1, 1, id=3), Holding(BTC, 1, 1, id=7)]
    assert match_holdings(hs, "#7")[0].code == "KRW-BTC"
    assert match_holdings(hs, "3")[0].code == "005930"
    assert match_holdings(hs, "005930")[0].id == 3  # 6자리는 번호가 아닌 종목코드
    assert match_holdings(hs, "btc")[0].id == 7
    assert match_holdings(hs, "삼성")[0].id == 3


def test_quiet_hours_wraparound():
    q = (time(23, 0), time(7, 0))
    assert in_quiet_hours(datetime.fromisoformat("2026-11-02T02:00:00+09:00"), q)
    assert not in_quiet_hours(datetime.fromisoformat("2026-11-02T12:00:00+09:00"), q)
    assert not in_quiet_hours(SAT_NOON, None)
