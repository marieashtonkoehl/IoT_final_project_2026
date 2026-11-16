"""Tests for the time-zone logic in rules.py (no HTTP needed)."""

from datetime import datetime, timezone

from app.rules import start_of_local_day_utc


def utc(text: str) -> datetime:
    """Turn '2026-11-20T11:42:05' into an aware UTC datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_local_midnight_in_winter():
    # Madrid is UTC+1 in November: local midnight = 23:00Z the day before
    assert start_of_local_day_utc(utc("2026-11-20T11:42:05")) == utc("2026-11-19T23:00:00")


def test_local_midnight_in_summer():
    # Madrid is UTC+2 in July: local midnight = 22:00Z the day before
    assert start_of_local_day_utc(utc("2026-07-10T09:00:00")) == utc("2026-07-09T22:00:00")


def test_late_utc_evening_is_already_next_local_day():
    # 23:30Z on 20 Nov = 00:30 on 21 Nov in Madrid
    assert start_of_local_day_utc(utc("2026-11-20T23:30:00")) == utc("2026-11-20T23:00:00")
