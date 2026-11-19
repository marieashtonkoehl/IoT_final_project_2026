"""Qualitative levels (good / fair / poor) for GET /conditions """

GOOD, FAIR, POOR, UNKNOWN = "good", "fair", "poor", "unknown"

# Each threshold: (good_min, good_max, fair_min, fair_max)
TEMP_C = (18, 30, 12, 35)
HUMIDITY_PCT = (40, 60, 30, 80)
LIGHT_PCT = (40, 10)   # (good_min, fair_min) -> DARK_BELOW (10) and SHADE_BELOW (40)

# Upper limits: (good_max, fair_max)
TVOC_PPB = (220, 660)
ECO2_PPM = (800, 1500)

_RANK = {POOR: 0, FAIR: 1, GOOD: 2}


def _range_level(value, limits):
    good_min, good_max, fair_min, fair_max = limits
    if good_min <= value <= good_max:
        return GOOD
    if fair_min <= value <= fair_max:
        return FAIR
    return POOR

def _max_level(value, limits):
    good_max, fair_max = limits
    if value <= good_max:
        return GOOD
    if value <= fair_max:
        return FAIR
    return POOR

def _min_level(value, limits):
    good_min, fair_min = limits
    if value >= good_min:
        return GOOD
    if value >= fair_min:
        return FAIR
    return POOR

def _worst(levels):
    levels = [lv for lv in levels if lv is not None]
    if not levels:
        return UNKNOWN
    return min(levels, key=_RANK.get)   # the worst parameter decides


def pollinator_level(temp_c=None, light_pct=None, humidity_pct=None):
    """Level for pollinators; missing values (None) are ignored."""
    return _worst([
        None if temp_c is None else _range_level(temp_c, TEMP_C),
        None if light_pct is None else _min_level(light_pct, LIGHT_PCT),
        None if humidity_pct is None else _range_level(humidity_pct, HUMIDITY_PCT),
    ])


def air_quality_level(tvoc_ppb=None, eco2_ppm=None):
    """Air quality from TVOC (ppb) and eCO2 (ppm); None values are ignored."""
    return _worst([
        None if tvoc_ppb is None else _max_level(tvoc_ppb, TVOC_PPB),
        None if eco2_ppm is None else _max_level(eco2_ppm, ECO2_PPM),
    ])
