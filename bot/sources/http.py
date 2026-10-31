"""재시도가 포함된 공용 HTTP 클라이언트."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class Http:
    def __init__(self, client: httpx.AsyncClient | None = None, retries: int = 2) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._retries = retries

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt == self._retries:
                    raise
                log.debug("GET %s 실패(%s), 재시도 %d", url, exc, attempt + 1)
                await asyncio.sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        await self._client.aclose()
