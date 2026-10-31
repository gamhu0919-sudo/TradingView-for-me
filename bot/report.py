"""텔레그램 메시지(HTML) 생성. 국내 관례대로 빨강=상승, 파랑=하락."""

from __future__ import annotations

import html
from datetime import datetime, timedelta

from .market import KST
from .market_data import Snapshot
from .models import AssetType, Quote, Session
from .portfolio import Position, Valuation
from .storage import Store

MAX_LEN = 4000  # 텔레그램 한도 4096자보다 여유 있게
_WEEKDAY = "월화수목금토일"


# ── 숫자 포맷 ────────────────────────────────────────────────
def dot(pct: float) -> str:
    if pct > 0.005:
        return "🔴"
    if pct < -0.005:
        return "🔵"
    return "⚪"


def pct(value: float) -> str:
    return f"{value:+.2f}%"


def krw(value: float) -> str:
    return f"{value:,.0f}원"


def signed_krw(value: float) -> str:
    return f"{value:+,.0f}원"


def signed_money(value: float, currency: str) -> str:
    if currency == "USD":
        return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"
    return signed_krw(value)


def price(value: float, currency: str) -> str:
    if currency == "USD":
        return f"${value:,.2f}"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 1:
        return f"{value:,.2f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def qty(value: float, asset_type: AssetType) -> str:
    if asset_type is AssetType.COIN:
        return f"{value:,.8f}".rstrip("0").rstrip(".") + "개"
    return f"{value:,.4f}".rstrip("0").rstrip(".") + "주"


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def stamp(now: datetime) -> str:
    now = now.astimezone(KST)
    return f"{now:%m/%d}({_WEEKDAY[now.weekday()]}) {now:%H:%M}"


def session_tag(q: Quote, asset_type: AssetType | None = None) -> str:
    """프리/애프터 가격이면 표시하고, 정규장 가격을 같이 보여준다."""
    if q.session in (Session.PRE, Session.AFTER):
        name = ("NXT " if asset_type is AssetType.KR else "") + ("프리" if q.session is Session.PRE else "애프터")
        reg = ""
        if q.regular_price is not None and q.session is Session.AFTER:
            reg = f" · 정규 {price(q.regular_price, q.currency)} {pct(q.regular_change_pct or 0)}"
        return f" <i>{name}{reg}</i>"
    if q.session is Session.CLOSED and asset_type is None:
        return " <i>종가</i>"
    return ""


def split_messages(sections: list[str]) -> list[str]:
    messages: list[str] = []
    current = ""
    for section in sections:
        candidate = f"{current}\n\n{section}" if current else section
        if len(candidate) > MAX_LEN and current:
            messages.append(current)
            current = section
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


# ── 섹션 ─────────────────────────────────────────────────────
def summary_section(val: Valuation) -> str:
    inv = val.invested
    lines = [
        f"💰 <b>총자산 {krw(val.total_value)}</b>",
        f"   오늘 {dot(inv.day_pct)} {signed_krw(inv.day_change)} ({pct(inv.day_pct)})",
        f"   누적 {dot(inv.pnl_pct)} {signed_krw(inv.pnl)} ({pct(inv.pnl_pct)})",
    ]
    parts = [
        f"{t.flag}{t.label} {val.weight(c.value):.0f}%"
        for t, c in sorted(val.by_class.items(), key=lambda kv: list(AssetType).index(kv[0]))
    ]
    if val.cash_krw:
        parts.append(f"💵현금 {val.weight(val.cash_krw):.0f}%")
    if parts:
        lines.append("   " + " · ".join(parts))
    return "\n".join(lines)


def market_section(snap: Snapshot) -> str:
    lines = ["🌐 <b>시장</b>"]
    for q in snap.indices:
        lines.append(f"{dot(q.change_pct)} {esc(q.name)} {q.price:,.2f} ({pct(q.change_pct)}){session_tag(q)}")
    if snap.usdkrw:
        q = snap.usdkrw
        lines.append(f"💱 원/달러 {q.price:,.2f} ({pct(q.change_pct)})")
    if snap.btc:
        lines.append(f"{dot(snap.btc.change_pct)} 비트코인 {price(snap.btc.price, 'KRW')} ({pct(snap.btc.change_pct)})")
    extra = []
    if snap.fear_greed:
        fg = snap.fear_greed
        extra.append(f"{fg.emoji} 코인 공포탐욕 {fg.value} ({fg.label})")
    if (prem := snap.tether_premium) is not None:
        extra.append(f"김프(테더) {pct(prem)}")
    if extra:
        lines.append(" · ".join(extra))
    return "\n".join(lines)


def position_lines(p: Position) -> list[str]:
    h, q = p.holding, p.quote
    if q is None:
        return [f"⚠️ {esc(h.name)} 시세 조회 실패 (매입가로 계산)", f"   {qty(h.qty, h.asset_type)}"]
    src = " <i>(Yahoo)</i>" if q.source == "yahoo" else ""
    head = f"{dot(q.change_pct)} {esc(h.name)} {price(q.price, q.currency)} ({pct(q.change_pct)}){session_tag(q, h.asset_type)}{src}"
    detail = f"   {qty(h.qty, h.asset_type)} · 수익 {pct(p.pnl_pct)} ({signed_krw(p.pnl_krw)})"
    if p.fx_pnl_krw is not None:
        detail += f" · 환차 {signed_krw(p.fx_pnl_krw)}"
    return [head, detail]


def holdings_section(val: Valuation, asset_type: AssetType) -> str | None:
    positions = [p for p in val.positions if p.holding.asset_type is asset_type]
    if not positions:
        return None
    total = val.by_class[asset_type]
    lines = [
        f"{asset_type.flag} <b>{asset_type.label}</b> {krw(total.value)} · 오늘 {pct(total.day_pct)} · 누적 {pct(total.pnl_pct)}"
    ]
    for p in sorted(positions, key=lambda p: -p.value_krw):
        lines.extend(position_lines(p))
    return "\n".join(lines)


def notes_section(val: Valuation, snap: Snapshot, threshold: float | None) -> str | None:
    notes: list[str] = []
    if threshold:
        for p in val.positions:
            if p.quote and abs(p.quote.change_pct) >= threshold:
                word = "급등" if p.quote.change_pct > 0 else "급락"
                notes.append(f"• {esc(p.holding.name)} {pct(p.quote.change_pct)} ({word})")
    priced = [p for p in val.positions if p.priced and p.day_change_krw]
    if priced:
        best = max(priced, key=lambda p: p.day_change_krw)
        worst = min(priced, key=lambda p: p.day_change_krw)
        if best.day_change_krw > 0:
            notes.append(f"• 오늘 수익 기여 1위: {esc(best.holding.name)} ({signed_krw(best.day_change_krw)})")
        if worst.day_change_krw < 0:
            notes.append(f"• 오늘 손실 기여 1위: {esc(worst.holding.name)} ({signed_krw(worst.day_change_krw)})")
    if snap.fallbacks:
        notes.append(f"• 네이버 조회 실패 → Yahoo 시세 사용: {esc(', '.join(snap.fallbacks))}")
    for err in snap.errors:
        notes.append(f"• ⚠️ {esc(err)}")
    return "🚨 <b>특이사항</b>\n" + "\n".join(notes) if notes else None


# ── 리포트 ───────────────────────────────────────────────────
def full_report(val: Valuation, snap: Snapshot, now: datetime, threshold: float | None) -> list[str]:
    sections = [f"📊 <b>포트폴리오 브리핑</b> · {stamp(now)}"]
    if val.positions or val.cash_krw:
        sections.append(summary_section(val))
    sections.append(market_section(snap))
    for t in AssetType:
        if s := holdings_section(val, t):
            sections.append(s)
    if not val.positions:
        sections.append("보유 종목이 없습니다. /add 로 추가하세요.")
    if notes := notes_section(val, snap, threshold):
        sections.append(notes)
    return split_messages(sections)


def brief_report(val: Valuation, snap: Snapshot, now: datetime) -> list[str]:
    sections = [f"⚡ <b>간단 요약</b> · {stamp(now)}"]
    if val.positions or val.cash_krw:
        sections.append(summary_section(val))
    idx = [f"{dot(q.change_pct)}{esc(q.name)} {pct(q.change_pct)}" for q in snap.indices]
    if snap.usdkrw:
        idx.append(f"💱{snap.usdkrw.price:,.1f}")
    if snap.btc:
        idx.append(f"{dot(snap.btc.change_pct)}BTC {pct(snap.btc.change_pct)}")
    if idx:
        sections.append("  ".join(idx))
    movers = sorted((p for p in val.positions if p.quote), key=lambda p: -abs(p.quote.change_pct))[:3]
    if movers:
        sections.append("📈 <b>변동 큰 종목</b>\n" + "\n".join(
            f"{dot(p.quote.change_pct)} {esc(p.holding.name)} {pct(p.quote.change_pct)}{session_tag(p.quote, p.holding.asset_type)}"
            for p in movers
        ))
    if snap.errors:
        sections.append("⚠️ " + esc(", ".join(snap.errors)))
    return split_messages(sections)


def coin_report(val: Valuation, snap: Snapshot, now: datetime) -> list[str]:
    sections = [f"🪙 <b>코인 요약</b> · {stamp(now)}"]
    if s := holdings_section(val, AssetType.COIN):
        sections.append(s)
    lines = []
    held_btc = any(p.holding.code == snap.btc.code for p in val.positions) if snap.btc else False
    if snap.btc and not held_btc:
        lines.append(f"{dot(snap.btc.change_pct)} 비트코인 {price(snap.btc.price, 'KRW')} ({pct(snap.btc.change_pct)})")
    if snap.fear_greed:
        fg = snap.fear_greed
        lines.append(f"{fg.emoji} 공포탐욕 {fg.value} ({fg.label})")
    if (prem := snap.tether_premium) is not None:
        lines.append(f"김프(테더) {pct(prem)}")
    lines.append("<i>업비트 등락률은 매일 09:00 기준</i>")
    sections.append("\n".join(lines))
    return split_messages(sections)


def weekly_report(val: Valuation, snap: Snapshot, store: Store, now: datetime) -> list[str]:
    sections = [f"🗓 <b>주간 리포트</b> · {stamp(now)}"]
    if val.positions or val.cash_krw:
        sections.append(summary_section(val))
    prev = store.snapshot_on_or_before((now - timedelta(days=7)).astimezone(KST).date())
    if prev:
        diff = val.total_value - prev["total_krw"]
        base = prev["total_krw"] or 1
        sections.append(
            f"📅 <b>지난주 대비</b> ({prev['day']})\n"
            f"{dot(diff)} 총자산 {signed_krw(diff)} ({pct(diff / base * 100)})\n"
            f"<i>입출금·매매로 인한 변동 포함</i>"
        )
    else:
        sections.append("📅 지난주 기록이 아직 없습니다. (매일 아침 자동 기록)")
    realized = store.realized_since(now - timedelta(days=7))
    if realized:
        fx = val.usdkrw or 0
        total = realized.get("KRW", 0) + realized.get("USD", 0) * fx
        sections.append(f"💵 이번 주 실현손익 {signed_krw(total)}")
    ranked = sorted((p for p in val.positions if p.priced), key=lambda p: -p.pnl_pct)
    if ranked:
        top = "\n".join(f"🔴 {esc(p.holding.name)} {pct(p.pnl_pct)}" for p in ranked[:3] if p.pnl_pct > 0)
        bottom = "\n".join(f"🔵 {esc(p.holding.name)} {pct(p.pnl_pct)}" for p in ranked[::-1][:3] if p.pnl_pct < 0)
        body = "\n".join(x for x in (top, bottom) if x)
        if body:
            sections.append("🏆 <b>누적 수익률 상·하위</b>\n" + body)
    sections.append(market_section(snap))
    return split_messages(sections)


def holdings_list(val: Valuation) -> list[str]:
    """/pf: 보유 종목 상세 (번호는 /del, /sell에 사용)."""
    if not val.positions and not val.cash_krw:
        return ["보유 종목이 없습니다.\n예) <code>/add 삼성전자 10 58000</code>"]
    sections = []
    for t in AssetType:
        items = [p for p in val.positions if p.holding.asset_type is t]
        if not items:
            continue
        lines = [f"{t.flag} <b>{t.label}</b>"]
        for p in items:
            h = p.holding
            avg = price(h.avg_price, t.currency)
            now = price(p.quote.price, p.quote.currency) if p.quote else "?"
            fx = f" @{h.buy_fx:,.1f}" if h.buy_fx else ""
            lines.append(
                f"<code>#{h.id}</code> {esc(h.name)} ({esc(h.instrument.symbol)})\n"
                f"   {qty(h.qty, t)} · 평단 {avg}{fx} → 현재 {now}\n"
                f"   평가 {krw(p.value_krw)} · {dot(p.pnl_pct)} {pct(p.pnl_pct)} · 비중 {val.weight(p.value_krw):.1f}%"
            )
        sections.append("\n".join(lines))
    if val.cash_krw:
        sections.append(f"💵 <b>현금</b> {krw(val.cash_krw)} · 비중 {val.weight(val.cash_krw):.1f}%")
    return split_messages(sections)
