"""Soil moisture sensor test
 
Reads the sensor every second and prints the raw ADC value, the voltage,
the moisture in % and a qualitative level (dry / moist / wet).
 
Calibrate DRY_RAW and WET_RAW first: run once with the probe in air and
once in a glass of water, and write the two raw values below.
"""
import time
from grove.adc import ADC

# --- Settings (see port plan) ---
CHANNEL = 2        # A2: soil moisture sensor (change to your port)
DRY_RAW = 0        # raw value with the probe in air (measured)
WET_RAW = 1900     # raw value with the probe in water (measured)
DRY_BELOW = 30     # % under which the soil is dry
MOIST_BELOW = 60   # % under which the soil is moist
ADC_MAX = 4095     # the HAT ADC is 12 bit
VREF_MV = 3300     # ADC reference voltage in mV
SAMPLES = 5        # readings averaged per line (less noise)

adc = ADC(address=0x08)  


# --- Helpers ---
def read_raw():
    """Average of a few raw readings."""
    total = 0
    for _ in range(SAMPLES):
        total += adc.read_raw(CHANNEL)
        time.sleep(0.02)
    return total / SAMPLES

def to_percent(raw):
    """Map the raw value to 0-100 % using the dry and wet points."""
    pct = (DRY_RAW - raw) / (DRY_RAW - WET_RAW) * 100
    return max(0, min(100, pct))

def level(pct):
    """Qualitative level of the planting bed."""
    if pct < DRY_BELOW:
        return "dry"
    if pct < MOIST_BELOW:
        return "moist"
    return "wet"


# --- Test ---
print(f"Soil moisture on A{CHANNEL}. Ctrl+C to stop.")
print(f"{'raw':>8} {'mV':>8} {'moisture %':>11}  level")
try:
    while True:
        raw = read_raw()
        pct = to_percent(raw)
        mv = raw / ADC_MAX * VREF_MV
        print(f"{raw:8.0f} {mv:8.0f} {pct:11.1f}  {level(pct)}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
