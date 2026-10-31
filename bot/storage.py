"""SQLite 저장소: 보유 종목, 거래 기록, 현금, 알림 일정, 목표가, 자산 스냅샷."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import AssetType, Holding, Instrument

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY,
    asset_type TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT '',
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    buy_fx REAL,
    updated_at TEXT NOT NULL,
    UNIQUE (asset_type, code)
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL,          -- BUY / SELL / SET
    qty REAL NOT NULL,
    price REAL NOT NULL,
    realized REAL NOT NULL DEFAULT 0,  -- 종목 통화 기준 실현손익
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cash (
    currency TEXT PRIMARY KEY,
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY,
    spec TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY,
    asset_type TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL,     -- above / below
    price REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_state (
    key TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    day TEXT PRIMARY KEY,
    total_krw REAL NOT NULL,
    invested_krw REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

EPS = 1e-9


@dataclass
class ScheduleRow:
    id: int
    spec: str
    enabled: bool


@dataclass
class Target:
    id: int
    instrument: Instrument
    direction: str
    price: float


KST = ZoneInfo("Asia/Seoul")


def _now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ── 보유 종목 ──────────────────────────────────────────────
    @staticmethod
    def _holding(row: sqlite3.Row) -> Holding:
        inst = Instrument(AssetType(row["asset_type"]), row["code"], row["name"], row["market"])
        return Holding(inst, row["qty"], row["avg_price"], row["buy_fx"], row["id"])

    def holdings(self) -> list[Holding]:
        rows = self.db.execute("SELECT * FROM holdings ORDER BY asset_type, name").fetchall()
        return [self._holding(r) for r in rows]

    def holding(self, asset_type: AssetType, code: str) -> Holding | None:
        row = self.db.execute(
            "SELECT * FROM holdings WHERE asset_type=? AND code=?", (asset_type.value, code)
        ).fetchone()
        return self._holding(row) if row else None

    def holding_by_id(self, holding_id: int) -> Holding | None:
        row = self.db.execute("SELECT * FROM holdings WHERE id=?", (holding_id,)).fetchone()
        return self._holding(row) if row else None

    def _save_holding(self, inst: Instrument, qty: float, avg: float, buy_fx: float | None) -> Holding:
        self.db.execute(
            """INSERT INTO holdings (asset_type, code, name, market, qty, avg_price, buy_fx, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (asset_type, code) DO UPDATE SET
                 name=excluded.name, market=excluded.market, qty=excluded.qty,
                 avg_price=excluded.avg_price, buy_fx=excluded.buy_fx, updated_at=excluded.updated_at""",
            (inst.asset_type.value, inst.code, inst.name, inst.market, qty, avg, buy_fx, _now()),
        )
        self._record(inst, "SET", qty, avg)
        self.db.commit()
        held = self.holding(inst.asset_type, inst.code)
        assert held is not None
        return held

    def _record(self, inst: Instrument, side: str, qty: float, price: float, realized: float = 0.0) -> None:
        self.db.execute(
            """INSERT INTO trades (ts, asset_type, code, name, side, qty, price, realized, currency)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), inst.asset_type.value, inst.code, inst.name, side, qty, price, realized,
             inst.asset_type.currency),
        )

    def set_holding(self, inst: Instrument, qty: float, avg: float, buy_fx: float | None = None) -> Holding:
        """수량·평단가를 그대로 덮어쓴다."""
        if qty <= 0 or avg < 0:
            raise ValueError("수량은 0보다 크고 평단가는 0 이상이어야 합니다.")
        return self._save_holding(inst, qty, avg, buy_fx)

    def buy(self, inst: Instrument, qty: float, price: float, buy_fx: float | None = None) -> Holding:
        """매수: 가중평균으로 평단가(와 매수환율)를 다시 계산한다."""
        if qty <= 0 or price < 0:
            raise ValueError("수량은 0보다 크고 가격은 0 이상이어야 합니다.")
        cur = self.holding(inst.asset_type, inst.code)
        if cur is None:
            new_qty, new_avg, new_fx = qty, price, buy_fx
        else:
            new_qty = cur.qty + qty
            old_cost, add_cost = cur.qty * cur.avg_price, qty * price
            new_avg = (old_cost + add_cost) / new_qty
            if cur.buy_fx and buy_fx and old_cost + add_cost > 0:
                # 매수 환율도 매입금액 가중평균
                new_fx = (old_cost * cur.buy_fx + add_cost * buy_fx) / (old_cost + add_cost)
            else:
                # 한쪽만 환율이 있으면 평균을 낼 수 없으므로 환차손익 분리를 끈다
                new_fx = None
        self.db.execute(
            """INSERT INTO holdings (asset_type, code, name, market, qty, avg_price, buy_fx, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (asset_type, code) DO UPDATE SET
                 qty=excluded.qty, avg_price=excluded.avg_price, buy_fx=excluded.buy_fx,
                 updated_at=excluded.updated_at""",
            (inst.asset_type.value, inst.code, inst.name, inst.market, new_qty, new_avg, new_fx, _now()),
        )
        self._record(inst, "BUY", qty, price)
        self.db.commit()
        held = self.holding(inst.asset_type, inst.code)
        assert held is not None
        return held

    def sell(self, holding: Holding, qty: float, price: float) -> tuple[Holding | None, float]:
        """매도: 수량을 줄이고 실현손익(종목 통화 기준)을 돌려준다. 전량 매도 시 보유 목록에서 지운다."""
        if qty <= 0 or price < 0:
            raise ValueError("수량은 0보다 크고 가격은 0 이상이어야 합니다.")
        if qty > holding.qty + EPS:
            raise ValueError(f"보유 수량({holding.qty:g})보다 많이 팔 수 없습니다.")
        realized = (price - holding.avg_price) * qty
        remaining = holding.qty - qty
        if remaining <= EPS:
            self.db.execute("DELETE FROM holdings WHERE id=?", (holding.id,))
        else:
            self.db.execute(
                "UPDATE holdings SET qty=?, updated_at=? WHERE id=?", (remaining, _now(), holding.id)
            )
        self._record(holding.instrument, "SELL", qty, price, realized)
        self.db.commit()
        left = self.holding(holding.asset_type, holding.code)
        return left, realized

    def delete_holding(self, holding_id: int) -> Holding | None:
        held = self.holding_by_id(holding_id)
        if held:
            self.db.execute("DELETE FROM holdings WHERE id=?", (holding_id,))
            self.db.commit()
        return held

    # ── 거래 기록 ──────────────────────────────────────────────
    def trades(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def realized_since(self, since: datetime) -> dict[str, float]:
        """기간 내 실현손익 합계 (통화별)."""
        rows = self.db.execute(
            "SELECT currency, SUM(realized) AS s FROM trades WHERE side='SELL' AND ts >= ? GROUP BY currency",
            (since.isoformat(timespec="seconds"),),
        ).fetchall()
        return {r["currency"]: r["s"] or 0.0 for r in rows}

    # ── 현금 ──────────────────────────────────────────────────
    def cash(self) -> dict[str, float]:
        return {r["currency"]: r["amount"] for r in self.db.execute("SELECT * FROM cash")}

    def set_cash(self, currency: str, amount: float) -> None:
        if amount <= 0:
            self.db.execute("DELETE FROM cash WHERE currency=?", (currency,))
        else:
            self.db.execute(
                "INSERT INTO cash (currency, amount) VALUES (?, ?) "
                "ON CONFLICT (currency) DO UPDATE SET amount=excluded.amount",
                (currency, amount),
            )
        self.db.commit()

    # ── 알림 일정 ──────────────────────────────────────────────
    def schedules(self) -> list[ScheduleRow]:
        rows = self.db.execute("SELECT * FROM schedules ORDER BY id").fetchall()
        return [ScheduleRow(r["id"], r["spec"], bool(r["enabled"])) for r in rows]

    def add_schedule(self, spec: str) -> int:
        cur = self.db.execute("INSERT INTO schedules (spec, created_at) VALUES (?, ?)", (spec, _now()))
        self.db.commit()
        return int(cur.lastrowid)

    def delete_schedule(self, schedule_id: int) -> bool:
        cur = self.db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        self.db.commit()
        return cur.rowcount > 0

    def set_schedule_enabled(self, schedule_id: int, enabled: bool) -> bool:
        cur = self.db.execute("UPDATE schedules SET enabled=? WHERE id=?", (int(enabled), schedule_id))
        self.db.commit()
        return cur.rowcount > 0

    # ── 목표가 알림 ────────────────────────────────────────────
    def targets(self) -> list[Target]:
        rows = self.db.execute("SELECT * FROM targets WHERE active=1 ORDER BY id").fetchall()
        return [
            Target(r["id"], Instrument(AssetType(r["asset_type"]), r["code"], r["name"], r["market"]),
                   r["direction"], r["price"])
            for r in rows
        ]

    def add_target(self, inst: Instrument, direction: str, price: float) -> int:
        cur = self.db.execute(
            "INSERT INTO targets (asset_type, code, name, market, direction, price, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (inst.asset_type.value, inst.code, inst.name, inst.market, direction, price, _now()),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def deactivate_target(self, target_id: int) -> bool:
        cur = self.db.execute("UPDATE targets SET active=0 WHERE id=? AND active=1", (target_id,))
        self.db.commit()
        return cur.rowcount > 0

    # ── 알림 중복 방지 ──────────────────────────────────────────
    def mark_sent(self, key: str) -> bool:
        """처음 보내는 알림이면 기록하고 True, 이미 보냈으면 False."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO alert_state (key, sent_at) VALUES (?, ?)", (key, _now())
        )
        self.db.commit()
        return cur.rowcount > 0

    def prune_alert_state(self, before: datetime) -> None:
        self.db.execute("DELETE FROM alert_state WHERE sent_at < ?", (before.isoformat(timespec="seconds"),))
        self.db.commit()

    # ── 자산 스냅샷 ─────────────────────────────────────────────
    def save_snapshot(self, day: date, total_krw: float, invested_krw: float) -> None:
        self.db.execute(
            "INSERT INTO snapshots (day, total_krw, invested_krw) VALUES (?, ?, ?) "
            "ON CONFLICT (day) DO UPDATE SET total_krw=excluded.total_krw, invested_krw=excluded.invested_krw",
            (day.isoformat(), total_krw, invested_krw),
        )
        self.db.commit()

    def snapshot_on_or_before(self, day: date) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM snapshots WHERE day <= ? ORDER BY day DESC LIMIT 1", (day.isoformat(),)
        ).fetchone()

    # ── 설정 ─────────────────────────────────────────────────
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.db.commit()

    # ── 백업 ─────────────────────────────────────────────────
    def backup(self, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        with target:
            self.db.backup(target)
        target.close()
