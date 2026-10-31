"""alternative.me 코인 공포탐욕지수 (하루 1회 갱신)."""

from __future__ import annotations

from dataclasses import dataclass

from .http import Http

URL = "https://api.alternative.me/fng/"
LABELS = {
    "Extreme Fear": ("극단적 공포", "😱"),
    "Fear": ("공포", "😨"),
    "Neutral": ("중립", "😐"),
    "Greed": ("탐욕", "😏"),
    "Extreme Greed": ("극단적 탐욕", "🤑"),
}


@dataclass(frozen=True)
class FearGreed:
    value: int
    label: str
    emoji: str


async def fear_greed(http: Http) -> FearGreed:
    payload = await http.get_json(URL, {"limit": 1})
    item = payload["data"][0]
    label, emoji = LABELS.get(item.get("value_classification", ""), (item.get("value_classification", ""), "🧭"))
    return FearGreed(int(item["value"]), label, emoji)
