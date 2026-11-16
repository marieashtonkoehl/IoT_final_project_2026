"""Test PIR motion sensor (#17): prints when motion starts and ends."""
import time
from grove.gpio import GPIO

PIN = 16

pir = GPIO(PIN, GPIO.IN)
last = 0
count = 0

print(f"PIR on D{PIN}. Wave your hand in front of it (Ctrl+C to stop)...")
try:
    while True:
        state = pir.read()
        if state != last:                    # only report changes
            if state == 1:
                count += 1
                print(f"{time.strftime('%H:%M:%S')}  motion detected  (#{count})")
            else:
                print(f"{time.strftime('%H:%M:%S')}  no motion")
            last = state
        time.sleep(0.1)
except KeyboardInterrupt:
    print(f"\nStopped. {count} motion events counted.")