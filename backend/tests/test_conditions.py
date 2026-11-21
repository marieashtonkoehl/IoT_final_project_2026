"""Tests for the good / fair / poor levels. Run from backend/:  python -m pytest -q"""

from rules.conditions import pollinator_level, air_quality_level

def test_pollinator():
    assert pollinator_level(24, 80, 50) == "good"
    assert pollinator_level(24, 25, 50) == "fair"    # shade
    assert pollinator_level(24, 5, 50) == "poor"     # dark
    assert pollinator_level(24, 80, 25) == "fair"    # dry air
    assert pollinator_level(24, 80, 10) == "poor"    # very dry air
    assert pollinator_level(None, None, None) == "unknown"


def test_pollinator_humidity_high():
    assert pollinator_level(24, 80, 75) == "good"    # normal humid day in Bilbao
    assert pollinator_level(24, 80, 85) == "fair"
    assert pollinator_level(24, 80, 95) == "poor"    # fog or rain


def test_pollinator_temperature():
    assert pollinator_level(15, 80, 50) == "fair"    # between 13 and 17 C
    assert pollinator_level(11, 80, 50) == "poor"    # too cold
    assert pollinator_level(40, 80, 50) == "poor"    # too hot


def test_pollinator_boundaries():
    assert pollinator_level(17, 80, 50) == "good"    # exactly at the limit
    assert pollinator_level(13, 80, 50) == "fair"
    assert pollinator_level(12.9, 80, 50) == "poor"


def test_pollinator_missing_values():
    assert pollinator_level(None, 80, 50) == "unknown"   # no temperature: cannot judge
    assert pollinator_level(24) == "good"                # light and humidity optional


def test_air_quality():
    assert air_quality_level(100, 600) == "good"
    assert air_quality_level(100, 900) == "fair"
    assert air_quality_level(100, 1200) == "poor"
    assert air_quality_level(1000, 600) == "poor"


def test_air_quality_missing_values():
    assert air_quality_level() == "unknown"
    assert air_quality_level(100, None) == "good"        # one value is enough
