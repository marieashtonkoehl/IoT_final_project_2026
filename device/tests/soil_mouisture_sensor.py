"""Soil moisture sensor test
 
Reads the sensor every second and prints the raw ADC value, the voltage,
the moisture in % and a qualitative level (dry / moist / wet).
 
Calibration: run it once with the probe in the air (dry) and once in a
glass of water (wet), note the raw values and pass them with --dry / --wet,
or write them into DEFAULT_DRY / DEFAULT_WET below. The percentage formula
works whether the raw value goes up or down when the soil gets wetter.
"""
import argparse
import time
 
from grove.adc import ADC  # same library as in Lab 4 (HAT address fixed to 0x08)
 
DEFAULT_CHANNEL = 2   # analog port A2 on the Grove Base HAT (adjust to your wiring)
DEFAULT_DRY = 3000    # PLACEHOLDER: raw value with the probe in air -> calibrate
DEFAULT_WET = 1200    # PLACEHOLDER: raw value with the probe in water -> calibrate
ADC_MAX = 4095        # the HAT ADC is 12 bit (0-4095)
VREF_MV = 3300        # reference voltage of the ADC in mV
SAMPLES = 5           # readings averaged per output line to reduce noise
 
 
def read_raw_averaged(adc, channel, samples=SAMPLES):
    """Return the average of several raw readings of one ADC channel."""
    total = 0
    for _ in range(samples):
        total += adc.read_raw(channel)
        time.sleep(0.02)
    return total / samples
 
 
def raw_to_millivolts(raw):
    """Convert a raw 12-bit value to millivolts."""
    return raw / ADC_MAX * VREF_MV
 
 
def moisture_percent(raw, dry, wet):
    """Map a raw value to 0-100 % using the dry and wet calibration points."""
    if dry == wet:
        raise ValueError("dry and wet calibration values must be different")
    pct = (dry - raw) / (dry - wet) * 100
    return max(0.0, min(100.0, pct))
 
 
def moisture_level(pct):
    """Qualitative level for the planting bed."""
    if pct < 30:
        return "dry"
    if pct < 60:
        return "moist"
    return "wet"
 
 
def main():
    parser = argparse.ArgumentParser(description="Soil moisture sensor test")
    parser.add_argument("--channel", type=int, default=DEFAULT_CHANNEL,
                        help="ADC channel of the sensor (0, 2, 4, 6 ...)")
    parser.add_argument("--dry", type=float, default=DEFAULT_DRY,
                        help="raw value with the probe in air")
    parser.add_argument("--wet", type=float, default=DEFAULT_WET,
                        help="raw value with the probe in water")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between readings")
    args = parser.parse_args()
 
    adc = ADC()
    print(f"Soil moisture on channel A{args.channel} "
          f"(dry={args.dry:.0f}, wet={args.wet:.0f}). Ctrl+C to stop.")
    print(f"{'raw (0-4095)':>13} {'voltage (mV)':>13} {'moisture (%)':>13}  level")
 
    try:
        while True:
            raw = read_raw_averaged(adc, args.channel)
            pct = moisture_percent(raw, args.dry, args.wet)
            line = (f"{raw:13.0f} {raw_to_millivolts(raw):13.0f} "
                    f"{pct:13.1f}  {moisture_level(pct)}")
            # A reading stuck at the extremes usually means a wiring problem.
            if raw < 5 or raw > ADC_MAX - 5:
                line += "   <- check the wiring / channel"
            print(line)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nBye.")
 
 
if __name__ == "__main__":
    main()
 