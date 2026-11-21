"""Qualitative levels (good / fair / poor) for GET /conditions 

pollinator_level:  conditions for pollinators from temperature, light, humidity.
air_quality_level: air quality from TVOC and eCO2 (SGP30 sensor).
"""

GOOD, FAIR, POOR, UNKNOWN = "good", "fair", "poor", "unknown"

# Each range: (good_min, good_max, fair_min, fair_max); outside fair -> poor
# Insect monitoring schemes do not count below 13 C and accept 17 C and above
# The upper limits (30 / 35) are our own choice: the sources give no maximum
TEMP_C = (17, 30, 13, 35)
HUMIDITY_PCT = (30, 80, 20, 90) #only very dry air or fog/rain (> 90 %) is poor (okay?)

# (good_min, fair_min): below 10 % it is dark (poor), below 40 % it is shade (fair).
# PLACEHOLDER until the light sensor is calibrated (issue #76).
LIGHT_PCT = (40, 10)

# Upper limits: (good_max, fair_max).
# TVOC: German UBA scale as used by Sensirion (good up to 220 ppb, moderate up to 660)
TVOC_PPB = (220, 660)
# eCO2: 600-800 ppm acceptable, about 1000 ppm tolerable (indoor reference)
ECO2_PPM = (800, 1000)

_RANK = {POOR: 0, FAIR: 1, GOOD: 2}


def _range_level(value, limits):
    """Level of a value that must stay inside a range (not too low, not too high)."""
    good_min, good_max, fair_min, fair_max = limits
    if good_min <= value <= good_max:
        return GOOD
    if fair_min <= value <= fair_max:
        return FAIR
    return POOR


def _max_level(value, limits):
    """Level of a value where lower is better """
    good_max, fair_max = limits
    if value <= good_max:
        return GOOD
    if value <= fair_max:
        return FAIR
    return POOR

def _min_level(value, limits):
    """Level of a value where higher is better"""
    good_min, fair_min = limits
    if value >= good_min:
        return GOOD
    if value >= fair_min:
        return FAIR
    return POOR

def _worst(levels):
    """The worst parameter decides; None values are ignored."""
    levels = [lv for lv in levels if lv is not None]
    if not levels:
        return UNKNOWN
    return min(levels, key=_RANK.get)


def pollinator_level(temp_c=None, light_pct=None, humidity_pct=None):
    """Level for pollinators. Light and humidity may be missing (None) """
    if temp_c is None:
        return UNKNOWN
    return _worst([
        _range_level(temp_c, TEMP_C),
        None if light_pct is None else _min_level(light_pct, LIGHT_PCT),
        None if humidity_pct is None else _range_level(humidity_pct, HUMIDITY_PCT),
    ])


def air_quality_level(tvoc_ppb=None, eco2_ppm=None):
    """Air quality from TVOC (ppb) and eCO2 (ppm); None values are ignored.

    Note: the first 10-20 readings of the SGP30 after power-on are always
    0 ppb / 400 ppm (warm-up). The device should skip them.
    """
    return _worst([
        None if tvoc_ppb is None else _max_level(tvoc_ppb, TVOC_PPB),
        None if eco2_ppm is None else _max_level(eco2_ppm, ECO2_PPM),
    ])
