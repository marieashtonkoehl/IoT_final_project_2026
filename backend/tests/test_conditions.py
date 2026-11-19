from rules.conditions import pollinator_level, air_quality_level

def test_pollinator():
    assert pollinator_level(24, 80, 50) == "good"
    assert pollinator_level(24, 25, 50) == "fair"    # shade
    assert pollinator_level(24, 5, 50) == "poor"     # dark
    assert pollinator_level(24, 80, 35) == "fair"
    assert pollinator_level(24, 80, 20) == "poor"
    assert pollinator_level(None, None, None) == "unknown"

def test_air_quality():
    assert air_quality_level(100, 600) == "good"
    assert air_quality_level(100, 1000) == "fair"
    assert air_quality_level(1000, 600) == "poor"