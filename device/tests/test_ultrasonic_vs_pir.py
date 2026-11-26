"""Compare the ultrasonic distance sensor with the PIR (#75).

Grove Ultrasonic Distance Sensor v2.0 on D22 (GPIO22, one SIG pin for trigger
and echo), PIR motion sensor on D16 (GPIO16). Both run at the same time, so
you can walk past and see which sensor counts what.

- Ultrasonic: measures the distance every 60 ms. A "person" is counted when
  something is closer than DETECT_CM for 2 readings in a row; the next person
  can only be counted after 5 "far" readings (so one person is not counted twice).
- PIR: every change from 0 to 1 is counted (like device/station.py).

Run on the Pi, from the repo folder, venv on:
    python device/tests/test_ultrasonic_vs_pir.py          # threshold 100 cm
    python device/tests/test_ultrasonic_vs_pir.py 150      # threshold 150 cm

First stand nobody in front of the sensor and look at the distance: the
threshold must be clearly SMALLER than this free distance (e.g. wall at 250 cm
-> threshold 150). Ctrl+C prints a summary.
"""

import sys
import time

from grove.gpio import GPIO

US_PIN = 22                  # D22: ultrasonic SIG
PIR_PIN = 16                 # D16: PIR

DETECT_CM = int(sys.argv[1]) if len(sys.argv) > 1 else 100
MEASURE_EVERY = 0.06         # s; the sensor needs ~60 ms between measurements
ENTER_READINGS = 2           # "close" readings in a row to count someone
LEAVE_READINGS = 5           # "far" readings in a row before the next count
STATUS_EVERY = 1.0           # s between status lines

ECHO_START_TIMEOUT = 0.002   # s: echo must start within 2 ms after the trigger
ECHO_MAX = 0.025             # s: echo longer than this = nothing in range (~4 m)


def measure_cm(sig):
    """One distance measurement in cm, or None (no echo / nothing in range)."""
    # Trigger: a short high pulse (>= 10 us) on the SIG pin
    sig.dir(GPIO.OUT)
    sig.write(0)
    time.sleep(0.000002)
    sig.write(1)
    time.sleep(0.00001)
    sig.write(0)

    # Echo: the same pin goes high; its length is the travel time of the sound
    sig.dir(GPIO.IN)
    t0 = time.perf_counter()
    while not sig.read():
        if time.perf_counter() - t0 > ECHO_START_TIMEOUT:
            return None
    start = time.perf_counter()
    while sig.read():
        if time.perf_counter() - start > ECHO_MAX:
            return None
    echo_us = (time.perf_counter() - start) * 1_000_000
    return echo_us / 29 / 2     # sound: ~29 us per cm, there and back


def main():
    sig = GPIO(US_PIN)
    pir = GPIO(PIR_PIN, GPIO.IN)

    print(f"Ultrasonic on D{US_PIN}, PIR on D{PIR_PIN}. "
          f"Counting someone closer than {DETECT_CM} cm. Ctrl+C for the summary.\n")

    us_count = pir_count = 0
    measurements = no_echo = 0
    close_streak = far_streak = 0
    someone_there = False
    last_pir = pir.read()
    min_cm = None
    last_cm = None
    started = time.monotonic()
    next_status = started

    try:
        while True:
            loop_start = time.monotonic()
            now_txt = time.strftime("%H:%M:%S")

            # Ultrasonic
            cm = measure_cm(sig)
            measurements += 1
            if cm is None:
                no_echo += 1
                close = False
            else:
                last_cm = cm
                min_cm = cm if min_cm is None else min(min_cm, cm)
                close = cm < DETECT_CM

            if close:
                close_streak += 1
                far_streak = 0
                if not someone_there and close_streak >= ENTER_READINGS:
                    someone_there = True
                    us_count += 1
                    print(f"{now_txt}  ULTRASONIC  #{us_count:3d}  at {cm:5.0f} cm")
            else:
                far_streak += 1
                close_streak = 0
                if someone_there and far_streak >= LEAVE_READINGS:
                    someone_there = False

            # PIR: count rising edges
            state = pir.read()
            if state == 1 and last_pir == 0:
                pir_count += 1
                print(f"{now_txt}  PIR         #{pir_count:3d}")
            last_pir = state

            # Status line once per second
            if loop_start >= next_status:
                dist = "  ---" if last_cm is None else f"{last_cm:5.0f}"
                print(f"{now_txt}  distance {dist} cm  PIR {state}  "
                      f"| counted: ultrasonic {us_count}, PIR {pir_count}")
                next_status += STATUS_EVERY

            time.sleep(max(0.0, MEASURE_EVERY - (time.monotonic() - loop_start)))

    except KeyboardInterrupt:
        minutes = (time.monotonic() - started) / 60
        print("\nSummary")
        print(f"  duration:            {minutes:.1f} min")
        print(f"  threshold:           {DETECT_CM} cm")
        print(f"  counted ultrasonic:  {us_count}")
        print(f"  counted PIR:         {pir_count}")
        print(f"  measurements:        {measurements}, without echo: {no_echo} "
              f"({100 * no_echo / max(1, measurements):.0f} %)")
        print(f"  closest distance:    {'-' if min_cm is None else f'{min_cm:.0f} cm'}")


if __name__ == "__main__":
    main()