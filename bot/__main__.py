"""실행 진입점.

  python -m bot                         텔레그램 봇 실행
  python -m bot preview [전체|간단|코인|주간] [--sample]
                                        텔레그램 없이 리포트를 콘솔에 출력 (--sample: 예시 포트폴리오)
"""

from __future__ import annotations

import asyncio
import dataclasses
import html
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import IO

from .config import Settings, load_dotenv
from .market_data import MarketData
from .models import AssetType, Instrument
from .schedules import REPORT_KINDS
from .service import Service
from .storage import Store

SAMPLE = [
    (Instrument(AssetType.KR, "005930", "삼성전자", "KOSPI"), 30, 180000, None),
    (Instrument(AssetType.KR, "069500", "KODEX 200", "KOSPI"), 20, 52000, None),
    (Instrument(AssetType.US, "AAPL.O", "애플", "NASDAQ"), 10, 300.0, 1380.0),
    (Instrument(AssetType.US, "TSLA.O", "테슬라", "NASDAQ"), 5, 420.0, None),
    (Instrument(AssetType.COIN, "KRW-BTC", "비트코인", "UPBIT"), 0.05, 95_000_000, None),
    (Instrument(AssetType.COIN, "KRW-ETH", "이더리움", "UPBIT"), 1.2, 5_000_000, None),
]


async def preview(kind: str, sample: bool, settings: Settings) -> None:
    store = Store(":memory:" if sample else settings.db_path)
    if sample:
        for inst, q, avg, fx in SAMPLE:
            store.set_holding(inst, q, avg, fx)
        store.set_cash("KRW", 2_000_000)
    data = MarketData()
    try:
        messages = await Service(store, data).report(kind)
    finally:
        await data.aclose()
        store.close()
    for m in messages:
        print(html.unescape(re.sub(r"<[^>]+>", "", m)))
        print("─" * 40)


def acquire_single_instance_lock(path: Path) -> IO[str]:
    """같은 데이터 폴더로 봇이 두 개 뜨지 않게 잠근다 (텔레그램은 동시 연결 시 409 오류).

    반환된 파일 객체가 살아 있는 동안 잠금이 유지된다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("봇이 이미 실행 중입니다. 기존 봇을 먼저 중지하세요.") from None
    return handle


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    if settings.log_file:
        # PC에서 창 없이 실행할 때 확인용 로그 (1MB × 4개 순환)
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(settings.log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers or None,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    args = sys.argv[1:]
    if args and args[0] == "preview":
        rest = [a for a in args[1:] if not a.startswith("--")]
        kind = REPORT_KINDS.get(rest[0], rest[0]) if rest else "full"
        asyncio.run(preview(kind, "--sample" in args, settings))
        return

    if not settings.bot_token:
        sys.exit("TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다. .env 파일을 확인하세요.")

    try:
        lock = acquire_single_instance_lock(settings.db_path.parent / "bot.lock")
    except RuntimeError as exc:
        sys.exit(str(exc))

    from .telegram_bot import build_application

    # bootstrap_retries=-1: 시작할 때 텔레그램 연결에 실패해도 종료하지 않고 계속 재시도
    polling = {"allowed_updates": ["message", "callback_query"], "bootstrap_retries": -1, "close_loop": False}
    try:
        app = build_application(settings)
        app.run_polling(**polling)
        registered = app.bot_data.get("registered_chat_id")
        if settings.chat_id is None and registered:
            # 설정 모드에서 주인이 등록되면 재시작 없이 바로 일반 모드로 전환
            build_application(dataclasses.replace(settings, chat_id=registered)).run_polling(**polling)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
