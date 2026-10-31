"""텔레그램 명령어 처리와 정기 작업(일정·알림·스냅샷)."""

from __future__ import annotations

import csv
import io
import logging
import secrets
import time as _time
from datetime import datetime, time
from typing import Any

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    LinkPreviewOptions,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import schedules
from .config import Settings
from .market import KST, now_kst
from .market_data import MarketData
from .models import AssetType, Holding, Instrument
from .report import esc, krw, pct, price, qty, signed_money
from .service import Service
from .storage import Store

log = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
SNAPSHOT_AT = time(7, 10)
ERROR_NOTIFY_INTERVAL = 600

HELP = """<b>📊 포트폴리오 알림 봇</b>

<b>조회</b>
/now [전체|간단|코인|주간] — 지금 바로 리포트
/pf — 보유 종목 상세 (#번호 표시)
/history — 최근 거래 기록

<b>보유 종목 입력</b>
/add 삼성전자 10 58000 — 매수 기록 (평단 자동 계산)
/add AAPL 5 185.5 @1380 — 미국 주식 (@매수환율 선택)
/add BTC 0.01 95000000 — 코인 (원화 가격)
/sell 삼성전자 5 70000 — 매도 (수량 대신 '전량' 가능)
/set 삼성전자 50 58000 — 수량·평단 직접 수정
/del 3 — #3 종목 삭제
/cash 3000000 · /cash USD 500 — 현금(예수금)
/export · CSV 파일 보내기 — 백업/일괄 입력

<b>알림</b>
/schedule — 알림 일정 목록·삭제
/schedule add 08:30 평일 전체
/schedule add 국장마감+10m 전체
/schedule add 미장개장+15m 간단
/schedule add 매시 09-15 간단
/schedule add 일 20:00 주간
/alert 삼성전자 250000 — 목표가 알림
/threshold 5 — 하루 ±5% 급등락 알림 (off로 끄기)

<i>기준점: 국장프리 국장개장 국장마감 NXT마감 미장프리 미장개장 미장마감
요일: 매일 평일 주말 월수금… / 개장일(국내 휴장일 제외)</i>"""

COMMANDS = [
    ("now", "지금 리포트 받기"),
    ("pf", "보유 종목 상세"),
    ("add", "매수 기록"),
    ("sell", "매도 기록"),
    ("set", "수량·평단 수정"),
    ("del", "종목 삭제"),
    ("cash", "현금 설정"),
    ("schedule", "알림 일정"),
    ("alert", "목표가 알림"),
    ("threshold", "급등락 알림 기준"),
    ("history", "거래 기록"),
    ("export", "CSV 내보내기"),
    ("help", "도움말"),
]


# ── 입력 파싱 ────────────────────────────────────────────────
def parse_number(text: str) -> float:
    cleaned = text.replace(",", "").replace("$", "").replace("원", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"숫자가 아닙니다: {text}") from None


def parse_trade(args: list[str], allow_all: bool = False) -> tuple[str, float | None, float, float | None]:
    """'<종목> <수량> <가격> [@환율]' → (종목, 수량, 가격, 환율). 수량 '전량'은 None."""
    tokens = list(args)
    fx = None
    if tokens and tokens[-1].startswith("@"):
        fx = parse_number(tokens.pop()[1:])
    if len(tokens) < 3:
        raise ValueError("형식: <종목> <수량> <가격>")
    price_ = parse_number(tokens.pop())
    raw_qty = tokens.pop()
    quantity = None if allow_all and raw_qty in ("전량", "all", "ALL") else parse_number(raw_qty)
    return " ".join(tokens), quantity, price_, fx


def match_holdings(holdings: list[Holding], query: str) -> list[Holding]:
    q = query.strip()
    ident = q.lstrip("#")
    if ident.isdigit() and (q.startswith("#") or len(ident) <= 4):
        return [h for h in holdings if h.id == int(ident)]
    up = q.upper()
    exact = [h for h in holdings if up in (h.code.upper(), h.instrument.symbol.upper(), h.name.upper())]
    if exact:
        return exact
    return [h for h in holdings if up in h.name.upper() or up in h.instrument.symbol.upper()]


def plain_number(value: float) -> str:
    """CSV용: 지수 표기(9.5e+07) 없이 소수점 아래 불필요한 0을 뗀다."""
    return f"{value:.8f}".rstrip("0").rstrip(".")


def in_quiet_hours(now: datetime, quiet: tuple[time, time] | None) -> bool:
    if not quiet:
        return False
    start, end = quiet
    t = now.astimezone(KST).time()
    return start <= t < end if start <= end else (t >= start or t < end)


def inst_label(inst: Instrument) -> str:
    return f"{inst.asset_type.flag} {inst.name} ({inst.symbol})"


# ── 봇 ──────────────────────────────────────────────────────
class PortfolioBot:
    def __init__(self, settings: Settings, service: Service) -> None:
        self.settings = settings
        self.svc = service
        self.store = service.store
        self._last_error_notice = 0.0
        self._fired: dict[int, datetime] = {}

    # 전송 도우미
    async def reply(self, message: Message, texts: list[str] | str, **kwargs: Any) -> None:
        for text in [texts] if isinstance(texts, str) else texts:
            await message.reply_text(text, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW, **kwargs)

    async def send(self, app: Application, texts: list[str], silent: bool = False) -> None:
        for text in texts:
            await app.bot.send_message(
                self.settings.chat_id, text, parse_mode=ParseMode.HTML,
                link_preview_options=NO_PREVIEW, disable_notification=silent,
            )

    def _stash(self, context: ContextTypes.DEFAULT_TYPE, payload: Any) -> str:
        pending = context.user_data.setdefault("pending", {})
        if len(pending) > 20:
            pending.clear()
        token = secrets.token_hex(3)
        pending[token] = payload
        return token

    # ── 조회 ────────────────────────────────────────────────
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.reply(update.effective_message, HELP)

    async def cmd_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        kind = schedules.REPORT_KINDS.get(context.args[0], "full") if context.args else "full"
        await self.reply(update.effective_message, await self.svc.report(kind))

    async def cmd_pf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.reply(update.effective_message, await self.svc.holdings_list())

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        limit = int(context.args[0]) if context.args and context.args[0].isdigit() else 10
        rows = self.store.trades(min(limit, 50))
        if not rows:
            await self.reply(update.effective_message, "거래 기록이 없습니다.")
            return
        side = {"BUY": "매수", "SELL": "매도", "SET": "수정"}
        lines = ["🧾 <b>최근 거래</b>"]
        for r in rows:
            line = (f"{r['ts'][:16].replace('T', ' ')} {side.get(r['side'], r['side'])} {esc(r['name'])} "
                    f"{plain_number(r['qty'])} @ {price(r['price'], r['currency'])}")
            if r["side"] == "SELL":
                line += f" (실현 {signed_money(r['realized'], r['currency'])})"
            lines.append(line)
        await self.reply(update.effective_message, "\n".join(lines))

    # ── 보유 종목 입력 ────────────────────────────────────────
    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE, op: str = "add") -> None:
        msg = update.effective_message
        try:
            query, quantity, price_, fx = parse_trade(context.args)
        except ValueError as exc:
            example = "/add 삼성전자 10 58000" if op == "add" else "/set 삼성전자 50 58000"
            await self.reply(msg, f"⚠️ {esc(str(exc))}\n예) <code>{example}</code>")
            return
        await self.resolve(msg, context, query, {"op": op, "qty": quantity, "price": price_, "fx": fx})

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.cmd_add(update, context, op="set")

    async def resolve(self, msg: Message, context: ContextTypes.DEFAULT_TYPE, query: str, action: dict) -> None:
        """종목명을 검색해 하나로 정해지면 바로 실행하고, 여러 개면 버튼으로 묻는다."""
        held = match_holdings(self.store.holdings(), query) if action["op"] in ("add", "set", "alert") else []
        exact_held = [h for h in held if query.strip().upper() in (h.code.upper(), h.instrument.symbol.upper(), h.name.upper())]
        if len(exact_held) == 1:
            await self.perform(msg, exact_held[0].instrument, action)
            return
        results = await self.svc.data.search(query)
        if not results:
            await self.reply(msg, f"⚠️ '{esc(query)}' 검색 결과가 없습니다. 종목코드(005930, AAPL, BTC)로도 시도해 보세요.")
            return
        if len(results) == 1:
            await self.perform(msg, results[0], action)
            return
        token = self._stash(context, (results, action))
        buttons = [
            [InlineKeyboardButton(inst_label(inst), callback_data=f"pick:{token}:{i}")]
            for i, inst in enumerate(results[:8])
        ]
        await self.reply(msg, f"'{esc(query)}' 중 어떤 종목인가요?", reply_markup=InlineKeyboardMarkup(buttons))

    async def perform(self, msg: Message, inst: Instrument, action: dict) -> None:
        op = action["op"]
        fx = action.get("fx") if inst.asset_type is AssetType.US else None
        try:
            if op == "add":
                before = self.store.holding(inst.asset_type, inst.code)
                h = self.store.buy(inst, action["qty"], action["price"], fx)
                text = (f"✅ {esc(inst_label(inst))} {qty(action['qty'], inst.asset_type)} 매수 기록\n"
                        f"보유 {qty(h.qty, h.asset_type)} · 평단 {price(h.avg_price, inst.asset_type.currency)}")
                if before:
                    text += f" (이전 {price(before.avg_price, inst.asset_type.currency)})"
                if before and fx and h.buy_fx is None:
                    text += "\n<i>기존 보유분에 매수환율이 없어 환차손익 분리는 꺼집니다. /set 으로 환율을 함께 입력하세요.</i>"
            elif op == "set":
                h = self.store.set_holding(inst, action["qty"], action["price"], fx)
                text = (f"✏️ {esc(inst_label(inst))} 보유 {qty(h.qty, h.asset_type)} · "
                        f"평단 {price(h.avg_price, inst.asset_type.currency)} 으로 설정")
            elif op == "alert":
                text = await self._add_target(inst, action["price"])
            else:
                text = "알 수 없는 동작"
        except ValueError as exc:
            text = f"⚠️ {esc(str(exc))}"
        await self.reply(msg, text)

    async def on_pick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        _, token, idx = query.data.split(":")
        pending = context.user_data.get("pending", {}).pop(token, None)
        if not pending:
            await query.edit_message_text("⌛ 만료된 선택입니다. 명령을 다시 입력해 주세요.")
            return
        results, action = pending
        inst = results[int(idx)]
        label = inst_label(inst.instrument if isinstance(inst, Holding) else inst)
        await query.edit_message_text(f"선택: {esc(label)}", parse_mode=ParseMode.HTML)
        if isinstance(inst, Holding):
            await self._sell(query.message, inst, action)
        else:
            await self.perform(query.message, inst, action)

    async def cmd_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        try:
            query, quantity, price_, _ = parse_trade(context.args, allow_all=True)
        except ValueError as exc:
            await self.reply(msg, f"⚠️ {esc(str(exc))}\n예) <code>/sell 삼성전자 5 70000</code> · <code>/sell AAPL 전량 230</code>")
            return
        matches = match_holdings(self.store.holdings(), query)
        action = {"qty": quantity, "price": price_}
        if not matches:
            await self.reply(msg, f"⚠️ 보유 종목 중 '{esc(query)}'를 찾지 못했습니다. /pf 로 확인하세요.")
        elif len(matches) == 1:
            await self._sell(msg, matches[0], action)
        else:
            token = self._stash(context, (matches, action))
            buttons = [[InlineKeyboardButton(inst_label(h.instrument), callback_data=f"pick:{token}:{i}")]
                       for i, h in enumerate(matches[:8])]
            await self.reply(msg, "어떤 종목을 매도할까요?", reply_markup=InlineKeyboardMarkup(buttons))

    async def _sell(self, msg: Message, h: Holding, action: dict) -> None:
        quantity = h.qty if action["qty"] is None else action["qty"]
        try:
            left, realized = self.store.sell(h, quantity, action["price"])
        except ValueError as exc:
            await self.reply(msg, f"⚠️ {esc(str(exc))}")
            return
        realized_text = signed_money(realized, h.asset_type.currency)
        remain = f"남은 수량 {qty(left.qty, h.asset_type)}" if left else "전량 매도 — 보유 목록에서 제거"
        await self.reply(msg, f"✅ {esc(h.name)} {qty(quantity, h.asset_type)} 매도 · 실현손익 {realized_text}\n{remain}")

    async def cmd_del(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not context.args:
            await self.reply(msg, "예) <code>/del 3</code> (번호는 /pf 에서 확인)")
            return
        matches = match_holdings(self.store.holdings(), " ".join(context.args))
        if len(matches) != 1:
            await self.reply(msg, "⚠️ 삭제할 종목을 하나로 특정할 수 없습니다. /pf 의 #번호를 사용하세요.")
            return
        h = self.store.delete_holding(matches[0].id)
        await self.reply(msg, f"🗑 {esc(h.name)} 삭제됨 (거래 기록은 남습니다)")

    async def cmd_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, args = update.effective_message, context.args
        if args:
            currency = "KRW"
            if args[0].upper() in ("KRW", "USD"):
                currency = args.pop(0).upper()
            try:
                amount = parse_number(args[0]) if args else 0.0
            except ValueError as exc:
                await self.reply(msg, f"⚠️ {esc(str(exc))}")
                return
            self.store.set_cash(currency, amount)
        cash = self.store.cash()
        text = "💵 <b>현금</b>\n" + ("\n".join(
            f"{c}: {krw(v) if c == 'KRW' else price(v, 'USD')}" for c, v in cash.items()
        ) or "없음")
        await self.reply(msg, text + "\n<i>예) /cash 3000000 · /cash USD 500 · /cash 0 (삭제)</i>")

    # ── CSV 백업/입력 ─────────────────────────────────────────
    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["type", "code", "name", "market", "qty", "avg_price", "buy_fx"])
        for h in self.store.holdings():
            i = h.instrument
            writer.writerow([i.asset_type.value, i.code, i.name, i.market, plain_number(h.qty), plain_number(h.avg_price),
                             "" if h.buy_fx is None else plain_number(h.buy_fx)])
        for currency, amount in self.store.cash().items():
            writer.writerow(["cash", currency, "현금", "", plain_number(amount), "", ""])
        data = buf.getvalue().encode("utf-8-sig")  # 엑셀에서 한글이 깨지지 않게 BOM 포함
        name = f"portfolio_{now_kst():%Y%m%d}.csv"
        await update.effective_message.reply_document(InputFile(data, filename=name),
                                                      caption="보유 종목 백업 (이 파일을 다시 보내면 일괄 입력됩니다)")

    async def on_csv(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        file = await context.bot.get_file(msg.document.file_id)
        raw = bytes(await file.download_as_bytearray()).decode("utf-8-sig")
        added, errors = 0, []
        for n, row in enumerate(csv.DictReader(io.StringIO(raw)), start=2):
            try:
                kind = (row.get("type") or "").strip().lower()
                if kind == "cash":
                    self.store.set_cash(row["code"].strip().upper(), parse_number(row["qty"]))
                else:
                    inst = Instrument(AssetType(kind), row["code"].strip(), row["name"].strip(),
                                      (row.get("market") or "").strip())
                    fx = (row.get("buy_fx") or "").strip()
                    self.store.set_holding(inst, parse_number(row["qty"]), parse_number(row["avg_price"]),
                                           parse_number(fx) if fx else None)
                added += 1
            except (KeyError, ValueError) as exc:
                errors.append(f"{n}행: {exc}")
        text = f"📥 {added}건 입력 완료"
        if errors:
            text += "\n⚠️ " + "\n⚠️ ".join(esc(e) for e in errors[:10])
        await self.reply(msg, text)

    # ── 알림 일정 ────────────────────────────────────────────
    def _schedule_view(self) -> tuple[str, InlineKeyboardMarkup | None]:
        rows = self.store.schedules()
        if not rows:
            return "등록된 알림 일정이 없습니다.\n예) <code>/schedule add 08:30 평일 전체</code>", None
        lines, buttons = ["⏰ <b>알림 일정</b>"], []
        for r in rows:
            try:
                desc = schedules.parse(r.spec).describe()
            except ValueError:
                desc = f"(해석 불가) {r.spec}"
            lines.append(f"{'🟢' if r.enabled else '⏸'} <code>#{r.id}</code> {esc(desc)}")
            buttons.append([
                InlineKeyboardButton(f"{'⏸ 끄기' if r.enabled else '▶️ 켜기'} #{r.id}", callback_data=f"sch:tog:{r.id}"),
                InlineKeyboardButton(f"🗑 삭제 #{r.id}", callback_data=f"sch:del:{r.id}"),
            ])
        lines.append("\n<i>추가: /schedule add 국장마감+10m 전체</i>")
        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    async def cmd_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, args = update.effective_message, context.args
        if args and args[0] in ("add", "추가"):
            spec_text = " ".join(args[1:])
            try:
                spec = schedules.parse(spec_text)
            except ValueError as exc:
                await self.reply(msg, f"⚠️ {esc(str(exc))}\n/help 에서 예시를 확인하세요.")
                return
            sid = self.store.add_schedule(spec_text)
            await self.reply(msg, f"✅ <code>#{sid}</code> {esc(spec.describe())} 추가")
            return
        if args and args[0] in ("del", "삭제", "on", "off", "켜기", "끄기") and len(args) > 1 and args[1].lstrip("#").isdigit():
            sid = int(args[1].lstrip("#"))
            if args[0] in ("del", "삭제"):
                ok = self.store.delete_schedule(sid)
            else:
                ok = self.store.set_schedule_enabled(sid, args[0] in ("on", "켜기"))
            await self.reply(msg, "✅ 변경했습니다." if ok else "⚠️ 해당 번호가 없습니다.")
            return
        text, markup = self._schedule_view()
        await self.reply(msg, text, reply_markup=markup)

    async def on_schedule_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        _, action, sid = query.data.split(":")
        if action == "del":
            self.store.delete_schedule(int(sid))
        else:
            row = next((r for r in self.store.schedules() if r.id == int(sid)), None)
            if row:
                self.store.set_schedule_enabled(row.id, not row.enabled)
        text, markup = self._schedule_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    # ── 목표가·급등락 ─────────────────────────────────────────
    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, args = update.effective_message, list(context.args)
        if args and args[0] in ("del", "삭제") and len(args) > 1:
            ok = self.store.deactivate_target(int(args[1].lstrip("#")))
            await self.reply(msg, "🗑 삭제했습니다." if ok else "⚠️ 해당 번호가 없습니다.")
            return
        if len(args) >= 2:
            try:
                target = parse_number(args[-1])
            except ValueError as exc:
                await self.reply(msg, f"⚠️ {esc(str(exc))}")
                return
            await self.resolve(msg, context, " ".join(args[:-1]), {"op": "alert", "price": target})
            return
        targets = self.store.targets()
        if not targets:
            await self.reply(msg, "등록된 목표가 알림이 없습니다.\n예) <code>/alert 삼성전자 250000</code>")
            return
        lines = ["🎯 <b>목표가 알림</b>"]
        for t in targets:
            word = "이상" if t.direction == "above" else "이하"
            lines.append(f"<code>#{t.id}</code> {esc(t.instrument.name)} {price(t.price, t.instrument.asset_type.currency)} {word}")
        lines.append("<i>삭제: /alert del 번호</i>")
        await self.reply(msg, "\n".join(lines))

    async def _add_target(self, inst: Instrument, target: float) -> str:
        snap = await self.svc.data.fetch([inst], market=False)
        q = snap.quote(inst)
        if q is None:
            return "⚠️ 현재가를 조회하지 못해 목표가를 등록하지 못했습니다."
        direction = "above" if target > q.price else "below"
        tid = self.store.add_target(inst, direction, target)
        word = "이상" if direction == "above" else "이하"
        return (f"🎯 <code>#{tid}</code> {esc(inst_label(inst))} {price(target, q.currency)} {word}이면 알림\n"
                f"현재 {price(q.price, q.currency)} ({pct(q.change_pct)})")

    async def cmd_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if context.args:
            arg = context.args[0].lower().rstrip("%")
            if arg in ("off", "끄기", "0"):
                self.svc.set_threshold(None)
            else:
                try:
                    value = parse_number(arg)
                except ValueError as exc:
                    await self.reply(msg, f"⚠️ {esc(str(exc))}")
                    return
                if not 0.5 <= value <= 50:
                    await self.reply(msg, "⚠️ 0.5~50 사이로 입력하세요.")
                    return
                self.svc.set_threshold(value)
        t = self.svc.threshold()
        text = "급등락 알림: 꺼짐" if t is None else f"급등락 알림: 하루 ±{t:g}% (±{t * 2:g}%, ±{t * 3:g}%… 단계마다 다시 알림)"
        await self.reply(msg, f"🚨 {text}\n<i>/threshold 5 · /threshold off</i>")

    # ── 정기 작업 ────────────────────────────────────────────
    async def tick(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        app = context.application
        now = now_kst().replace(second=0, microsecond=0)

        for row in self.store.schedules():
            if not row.enabled or self._fired.get(row.id) == now:
                continue
            try:
                spec = schedules.parse(row.spec)
                if spec.is_due(now):
                    self._fired[row.id] = now
                    await self.send(app, await self.svc.report(spec.report, now), silent=self.settings.report_silent)
            except Exception as exc:  # noqa: BLE001
                await self.notify_error(app, f"일정 #{row.id} 실행 실패", exc)

        if (now.hour * 60 + now.minute) % self.settings.alert_interval_min == 0:
            try:
                messages = await self.svc.check_alerts(now)
                await self.send(app, messages, silent=in_quiet_hours(now, self.settings.alert_quiet_hours))
            except Exception as exc:  # noqa: BLE001
                await self.notify_error(app, "급등락 알림 확인 실패", exc)

        if now.time() == SNAPSHOT_AT:
            try:
                await self.svc.save_daily_snapshot(now)
                backup_dir = self.settings.db_path.parent / "backups"
                self.store.backup(backup_dir / f"portfolio_{now:%a}.db")  # 요일별 7개 순환
            except Exception as exc:  # noqa: BLE001
                await self.notify_error(app, "일일 기록 실패", exc)

    async def notify_error(self, app: Application, what: str, exc: BaseException) -> None:
        log.exception("%s", what, exc_info=exc)
        if _time.monotonic() - self._last_error_notice < ERROR_NOTIFY_INTERVAL:
            return
        self._last_error_notice = _time.monotonic()
        try:
            await self.send(app, [f"⚠️ {esc(what)}: {esc(type(exc).__name__)} {esc(str(exc))[:200]}"])
        except Exception:  # noqa: BLE001
            log.exception("오류 알림 전송 실패")

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        if context.error:
            await self.notify_error(context.application, "명령 처리 중 오류", context.error)


async def _setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.effective_message.reply_text(
        f"설정 모드입니다.\n이 대화의 chat_id: <code>{chat_id}</code>\n\n"
        f".env 파일에 <code>TELEGRAM_CHAT_ID={chat_id}</code> 를 넣고 봇을 재시작하세요.",
        parse_mode=ParseMode.HTML,
    )


def build_application(settings: Settings) -> Application:
    store = Store(settings.db_path)
    data = MarketData()
    service = Service(store, data)

    async def post_init(app: Application) -> None:
        if settings.chat_id is None:
            return
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
        if store.get_setting("seeded") is None:
            for spec in schedules.DEFAULT_SCHEDULES:
                store.add_schedule(spec)
            store.set_setting("seeded", "1")
            await app.bot.send_message(settings.chat_id, "👋 처음 실행되었습니다. 기본 알림 일정을 등록했습니다.\n" + HELP,
                                       parse_mode=ParseMode.HTML)
        else:
            await app.bot.send_message(settings.chat_id, "✅ 봇이 시작되었습니다.", disable_notification=True)

    async def post_shutdown(app: Application) -> None:
        await data.aclose()
        store.close()

    # 기본 대기시간(5초)은 느린 가정용 회선에서 텔레그램 연결이 시간 초과로 끝날 수 있어 넉넉히 늘린다
    app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .connect_timeout(20).read_timeout(30).write_timeout(30).pool_timeout(10)
        .get_updates_connect_timeout(20).get_updates_read_timeout(40)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    if settings.chat_id is None:
        log.warning("TELEGRAM_CHAT_ID 미설정: 설정 모드로 실행합니다. 봇에게 /start 를 보내세요.")
        app.add_handler(CommandHandler("start", _setup_start))
        return app

    bot = PortfolioBot(settings, service)
    owner = filters.Chat(chat_id=settings.chat_id)
    handlers = {
        "start": bot.cmd_help, "help": bot.cmd_help, "now": bot.cmd_now, "pf": bot.cmd_pf,
        "history": bot.cmd_history, "add": bot.cmd_add, "set": bot.cmd_set, "sell": bot.cmd_sell,
        "del": bot.cmd_del, "cash": bot.cmd_cash, "export": bot.cmd_export, "schedule": bot.cmd_schedule,
        "alert": bot.cmd_alert, "threshold": bot.cmd_threshold,
    }
    for name, fn in handlers.items():
        app.add_handler(CommandHandler(name, fn, filters=owner))
    app.add_handler(MessageHandler(owner & filters.Document.FileExtension("csv"), bot.on_csv))

    def owner_only(callback):
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if update.effective_chat and update.effective_chat.id == settings.chat_id:
                await callback(update, context)
        return wrapped

    app.add_handler(CallbackQueryHandler(owner_only(bot.on_pick), pattern=r"^pick:"))
    app.add_handler(CallbackQueryHandler(owner_only(bot.on_schedule_button), pattern=r"^sch:"))
    app.add_error_handler(bot.on_error)

    now = datetime.now()
    first = 62 - now.second  # 매 분 2초에 실행
    app.job_queue.run_repeating(bot.tick, interval=60, first=first, name="tick",
                                job_kwargs={"misfire_grace_time": 30, "max_instances": 1})
    return app
