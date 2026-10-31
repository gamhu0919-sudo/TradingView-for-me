"""저장소와 시세 조회를 묶어 리포트·알림을 만드는 계층 (텔레그램과 무관하게 테스트 가능)."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import report
from .market import KST, is_active, now_kst
from .market_data import MarketData, Snapshot
from .models import AssetType, Instrument
from .portfolio import Valuation, value_portfolio
from .report import dot, esc, pct, price, session_tag
from .storage import Store

DEFAULT_THRESHOLD = 5.0


class Service:
    def __init__(self, store: Store, data: MarketData) -> None:
        self.store = store
        self.data = data

    # ── 설정 ─────────────────────────────────────────────────
    def threshold(self) -> float | None:
        value = self.store.get_setting("move_threshold", str(DEFAULT_THRESHOLD))
        return None if value in (None, "off") else float(value)

    def set_threshold(self, value: float | None) -> None:
        self.store.set_setting("move_threshold", "off" if value is None else f"{value:g}")

    # ── 평가 ─────────────────────────────────────────────────
    async def valuation(self, market: bool = True) -> tuple[Valuation, Snapshot]:
        holdings = self.store.holdings()
        snap = await self.data.fetch([h.instrument for h in holdings], market=market)
        return value_portfolio(holdings, snap, self.store.cash()), snap

    async def report(self, kind: str, now: datetime | None = None) -> list[str]:
        now = now or now_kst()
        val, snap = await self.valuation(market=True)
        if kind == "brief":
            return report.brief_report(val, snap, now)
        if kind == "coin":
            return report.coin_report(val, snap, now)
        if kind == "weekly":
            return report.weekly_report(val, snap, self.store, now)
        return report.full_report(val, snap, now, self.threshold())

    async def holdings_list(self) -> list[str]:
        val, _ = await self.valuation(market=False)
        return report.holdings_list(val)

    async def save_daily_snapshot(self, now: datetime | None = None) -> None:
        now = now or now_kst()
        val, _ = await self.valuation(market=False)
        if val.positions or val.cash_krw:
            # 아침에 기록하므로 전날 장 마감(미국장·넥스트레이드 포함) 결과를 전날 날짜로 남긴다
            day = (now.astimezone(KST) - timedelta(days=1)).date()
            self.store.save_snapshot(day, val.total_value, val.invested.cost)

    # ── 급등락·목표가 알림 ──────────────────────────────────────
    async def check_alerts(self, now: datetime | None = None) -> list[str]:
        now = now or now_kst()
        active = {
            AssetType.KR: is_active("KR", now),
            AssetType.US: is_active("US", now),
            AssetType.COIN: True,
        }
        holdings = [h for h in self.store.holdings() if active[h.asset_type]]
        targets = [t for t in self.store.targets() if active[t.instrument.asset_type]]
        threshold = self.threshold()
        if not targets and (not holdings or threshold is None):
            return []

        instruments: dict[tuple[AssetType, str], Instrument] = {}
        for inst in [h.instrument for h in holdings] + [t.instrument for t in targets]:
            instruments[(inst.asset_type, inst.code)] = inst
        snap = await self.data.fetch(list(instruments.values()), market=False)

        messages: list[str] = []
        if threshold:
            for h in holdings:
                q = snap.quote(h.instrument)
                if q is None or q.source == "yahoo":
                    continue  # 예비 소스(지연 시세)로는 알림을 보내지 않는다
                level = int(abs(q.change_pct) // threshold)
                if level < 1:
                    continue
                sign = "+" if q.change_pct > 0 else "-"
                # 같은 거래일(기준가)·같은 단계에서는 한 번만 알린다. 단계가 올라가면 다시 알림.
                key = f"move:{h.asset_type}:{h.code}:{q.prev_close:g}:{sign}{level}"
                if self.store.mark_sent(key):
                    word = "급등" if q.change_pct > 0 else "급락"
                    messages.append(
                        f"🚨 <b>{esc(h.name)} {word}</b> {dot(q.change_pct)} {pct(q.change_pct)}\n"
                        f"현재 {price(q.price, q.currency)}{session_tag(q, h.asset_type)}\n"
                        f"<i>기준 ±{threshold * level:g}% 돌파</i>"
                    )

        for t in targets:
            q = snap.quote(t.instrument)
            if q is None or q.source == "yahoo":
                continue
            hit = q.price >= t.price if t.direction == "above" else q.price <= t.price
            if hit and self.store.deactivate_target(t.id):
                arrow = "이상 도달" if t.direction == "above" else "이하 도달"
                messages.append(
                    f"🎯 <b>{esc(t.instrument.name)} 목표가 {arrow}</b>\n"
                    f"목표 {price(t.price, q.currency)} → 현재 {price(q.price, q.currency)} ({pct(q.change_pct)})"
                    f"{session_tag(q, t.instrument.asset_type)}"
                )
        self.store.prune_alert_state(now - timedelta(days=7))
        return messages
