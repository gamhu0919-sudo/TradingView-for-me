"""실행 진입점.

  python -m bot                         텔레그램 봇 실행
  python -m bot preview [전체|간단|코인|주간] [--sample]
                                        텔레그램 없이 리포트를 콘솔에 출력 (--sample: 예시 포트폴리오)
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import sys

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


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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

    from .telegram_bot import build_application

    build_application(settings).run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
