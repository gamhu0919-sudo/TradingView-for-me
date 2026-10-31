from datetime import datetime, time

import pytest

from bot.schedules import DEFAULT_SCHEDULES, parse


def kst(text):
    return datetime.fromisoformat(f"{text}+09:00")


def test_fixed_time_defaults_to_weekdays():
    spec = parse("08:30")
    assert spec.at == time(8, 30) and spec.report == "full"
    assert spec.is_due(kst("2026-11-02T08:30:00"))  # 월
    assert not spec.is_due(kst("2026-10-31T08:30:00"))  # 토
    assert not spec.is_due(kst("2026-11-02T08:31:00"))


def test_coin_report_defaults_to_every_day():
    spec = parse("23:00 코인")
    assert spec.report == "coin"
    assert spec.is_due(kst("2026-10-31T23:00:00"))


def test_custom_weekdays_and_trading_days():
    spec = parse("일 20:00 주간")
    assert spec.report == "weekly" and spec.is_due(kst("2026-11-01T20:00:00"))
    spec = parse("09:05 개장일 간단")
    assert not spec.is_due(kst("2026-12-25T09:05:00"))  # 성탄절 휴장
    assert spec.is_due(kst("2026-12-24T09:05:00"))


def test_us_open_anchor_follows_daylight_saving():
    spec = parse("미장개장+10m 간단")
    assert spec.is_due(kst("2026-10-30T22:40:00"))  # 서머타임: 09:30 EDT = 22:30 KST
    assert spec.is_due(kst("2026-11-02T23:40:00"))  # 11/1 서머타임 종료: 09:30 EST = 23:30 KST
    assert not spec.is_due(kst("2026-11-02T22:40:00"))
    assert not spec.is_due(kst("2026-11-26T23:40:00"))  # 추수감사절 휴장


def test_us_close_anchor_lands_next_kst_morning():
    spec = parse("미장마감+5분")
    assert spec.is_due(kst("2026-11-03T06:05:00"))  # 11/2(월) 16:00 EST


def test_kr_anchors_and_offsets():
    assert parse("국장마감+10m").is_due(kst("2026-11-02T15:40:00"))
    assert parse("국장개장-1h").is_due(kst("2026-11-02T08:00:00"))
    assert parse("NXT마감").is_due(kst("2026-11-02T20:00:00"))
    assert parse("넥스트마감+30분").is_due(kst("2026-11-02T20:30:00"))
    assert not parse("국장마감+10m").is_due(kst("2026-10-31T15:40:00"))  # 토요일


def test_interval_window():
    spec = parse("매시 09-15 간단")
    assert spec.is_due(kst("2026-11-02T09:00:00"))
    assert spec.is_due(kst("2026-11-02T15:00:00"))
    assert not spec.is_due(kst("2026-11-02T10:30:00"))
    assert not spec.is_due(kst("2026-11-02T16:00:00"))
    spec = parse("매30분 09:00-15:30")
    assert spec.is_due(kst("2026-11-02T15:30:00"))
    assert not spec.is_due(kst("2026-11-02T15:45:00"))


@pytest.mark.parametrize("bad", ["", "25:00", "08:30 국장마감", "매시 15-09", "아무거나", "국장마감+800m"])
def test_invalid_specs(bad):
    with pytest.raises(ValueError):
        parse(bad)


def test_describe_and_defaults_parse():
    assert parse("국장마감+10m").describe() == "국장마감 +10분 (국내 개장일) · 전체"
    assert parse("월수금 07:00 코인").describe() == "월수금 07:00 · 코인"
    for spec in DEFAULT_SCHEDULES:
        parse(spec)
