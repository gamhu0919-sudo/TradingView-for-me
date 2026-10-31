"""평가금액·손익 계산. 모든 합계는 원화 기준."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import AssetType, Holding, Quote
from .market_data import Snapshot


@dataclass
class Position:
    holding: Holding
    quote: Quote | None
    fx: float  # 원화 환산 환율 (원화 자산은 1)
    value_krw: float
    cost_krw: float
    day_change_krw: float
    fx_pnl_krw: float | None = None  # 매수환율을 입력한 미국 주식만

    @property
    def pnl_krw(self) -> float:
        return self.value_krw - self.cost_krw

    @property
    def pnl_pct(self) -> float:
        return self.pnl_krw / self.cost_krw * 100 if self.cost_krw else 0.0

    @property
    def priced(self) -> bool:
        return self.quote is not None


@dataclass
class ClassTotal:
    value: float = 0.0
    cost: float = 0.0
    day_change: float = 0.0

    @property
    def pnl(self) -> float:
        return self.value - self.cost

    @property
    def pnl_pct(self) -> float:
        return self.pnl / self.cost * 100 if self.cost else 0.0

    @property
    def day_pct(self) -> float:
        base = self.value - self.day_change
        return self.day_change / base * 100 if base else 0.0


@dataclass
class Valuation:
    positions: list[Position]
    cash_krw: float
    usdkrw: float | None
    by_class: dict[AssetType, ClassTotal] = field(default_factory=dict)

    @property
    def invested(self) -> ClassTotal:
        total = ClassTotal()
        for c in self.by_class.values():
            total.value += c.value
            total.cost += c.cost
            total.day_change += c.day_change
        return total

    @property
    def total_value(self) -> float:
        return self.invested.value + self.cash_krw

    @property
    def missing(self) -> list[Position]:
        return [p for p in self.positions if not p.priced]

    def weight(self, value: float) -> float:
        return value / self.total_value * 100 if self.total_value else 0.0


def value_portfolio(holdings: list[Holding], snap: Snapshot, cash: dict[str, float]) -> Valuation:
    usdkrw = snap.usdkrw.price if snap.usdkrw else None
    positions: list[Position] = []
    by_class: dict[AssetType, ClassTotal] = {}

    for h in holdings:
        quote = snap.quote(h.instrument)
        is_usd = h.asset_type is AssetType.US
        fx = (usdkrw or h.buy_fx or 0.0) if is_usd else 1.0
        cost_fx = (h.buy_fx or fx) if is_usd else 1.0
        cost = h.qty * h.avg_price * cost_fx
        if quote is None:
            # 시세 조회 실패: 매입가로 대신 계산해 총액이 크게 왜곡되지 않게 한다
            pos = Position(h, None, fx, value_krw=h.qty * h.avg_price * fx, cost_krw=cost, day_change_krw=0.0)
        else:
            pos = Position(
                h, quote, fx,
                value_krw=h.qty * quote.price * fx,
                cost_krw=cost,
                day_change_krw=h.qty * quote.change * fx,
                fx_pnl_krw=h.qty * h.avg_price * (fx - h.buy_fx) if is_usd and h.buy_fx else None,
            )
        positions.append(pos)
        total = by_class.setdefault(h.asset_type, ClassTotal())
        total.value += pos.value_krw
        total.cost += pos.cost_krw
        total.day_change += pos.day_change_krw

    cash_krw = cash.get("KRW", 0.0) + cash.get("USD", 0.0) * (usdkrw or 0.0)
    return Valuation(positions, cash_krw, usdkrw, by_class)
