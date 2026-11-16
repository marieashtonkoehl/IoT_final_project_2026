"""Light sensor test
Reads the sensor every second and prints the raw ADC value, the voltage,
the light level in % and a qualitative level (dark / shade / bright).
 
How to check it: uncover the sensor (room light was about 70 %),
cover it with your hand (about 1-4 %), then point it at a lamp or a window.

"""
import time
from grove.adc import ADC

# --- Settings (see port plan) ---
CHANNEL = 0        # A0: light sensor (as in Lab 4, change to your port)
ADC_MAX = 4095     # the HAT ADC is 12 bit
VREF_MV = 3300     # ADC reference voltage in mV
SAMPLES = 5        # readings averaged per line (less noise)
MAX_RAW = 2870     # maximum raw value 
DARK_BELOW = 10    # % under which it is dark
SHADE_BELOW = 40   # % under which it is shade

adc = ADC(address=0x08)  

# --- Helpers ---
def read_raw():
    """Average of a few raw readings."""
    total = 0
    for _ in range(SAMPLES):
        total += adc.read_raw(CHANNEL)
        time.sleep(0.02)
    return total / SAMPLES

def level(pct):
    """Qualitative level: dark / shade / bright."""
    if pct < DARK_BELOW:
        return "dark"
    if pct < SHADE_BELOW:
        return "shade"
    return "bright"


# --- Test ---
print(f"Light sensor on A{CHANNEL}. Ctrl+C to stop.")
print(f"{'raw':>8} {'mV':>8} {'light %':>9}  level")
try:
    while True:
        raw = read_raw()
        pct = min(100, raw / ADC_MAX * 100)
        mv = raw / ADC_MAX * VREF_MV
        print(f"{raw:8.0f} {mv:8.0f} {pct:9.1f}  {level(pct)}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
