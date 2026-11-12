"""Light sensor test
Reads the sensor every second and prints the raw ADC value, the voltage,
the light level in % and a qualitative level (dark / shade / bright).
 
How to check it: uncover the sensor (room light was about 70 % in Lab 4),
cover it with your hand (about 1-4 %), then point it at a lamp or a window.

"""
import argparse
import time
 
from grove.adc import ADC  
 
DEFAULT_CHANNEL = 0   # analog port A0 on the Grove Base HAT (as in Lab 4)
ADC_MAX = 4095        # the HAT ADC is 12 bit (0-4095)
VREF_MV = 3300        # reference voltage of the ADC in mV
SAMPLES = 5           # readings averaged per output line to reduce noise
DARK_BELOW = 10       # % under which we call it dark
SHADE_BELOW = 40      # % under which we call it shade
 
 
def read_raw_averaged(adc, channel, samples=SAMPLES):
    """Return the average of several raw readings of one ADC channel."""
    total = 0
    for _ in range(samples):
        total += adc.read_raw(channel)
        time.sleep(0.02)
    return total / samples
 
 
def light_percent(raw):
    """Light level as a percentage of the ADC range (0-100)."""
    return raw / ADC_MAX * 100
 
 
def light_level(pct):
    """Qualitative level: dark / shade / bright."""
    if pct < DARK_BELOW:
        return "dark"
    if pct < SHADE_BELOW:
        return "shade"
    return "bright"
 
 
def main():
    parser = argparse.ArgumentParser(description="Light sensor test")
    parser.add_argument("--channel", type=int, default=DEFAULT_CHANNEL,
                        help="ADC channel of the sensor (0, 2, 4, 6 ...)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between readings")
    args = parser.parse_args()
 
    adc = ADC()
    print(f"Light sensor on channel A{args.channel}. Ctrl+C to stop.")
    print(f"{'raw (0-4095)':>13} {'voltage (mV)':>13} {'light (%)':>10}  level")
 
    try:
        while True:
            raw = read_raw_averaged(adc, args.channel)
            pct = light_percent(raw)
            line = (f"{raw:13.0f} {raw / ADC_MAX * VREF_MV:13.0f} "
                    f"{pct:10.1f}  {light_level(pct)}")
            if raw > ADC_MAX - 5:
                line += "   <- saturated: check the wiring / channel"
            print(line)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nBye.")
 
 
if __name__ == "__main__":
    main()