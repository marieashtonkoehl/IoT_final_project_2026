"""Test servo latch (#22).
Press Enter to toggle between LOCKED and OPEN, type q + Enter (or Ctrl+C) to quit."""
import time
from gpiozero import AngularServo

SERVO_PIN = 12       # PWM port on the Grove HAT (GPIO12)
LOCKED    = 0        # angle for "locker closed"  (adjust after testing)
OPEN      = 90       # angle for "locker open"    (adjust after testing)

# Typical hobby servo: 0.5 ms = 0°, 2.5 ms = 180°
servo = AngularServo(SERVO_PIN, min_angle=0, max_angle=180,
                     min_pulse_width=0.0005, max_pulse_width=0.0025)

def move_to(angle, name):
    """Move the servo, wait until it arrives, then release it."""
    servo.angle = angle
    print(f"{time.strftime('%H:%M:%S')}  -> {name} ({angle}°)")
    time.sleep(0.6)          # give the servo time to get there
    servo.detach()           # stop the signal -> no jitter while waiting

move_to(LOCKED, "LOCKED")
is_open = False
try:
    while True:
        cmd = input("Enter = toggle, q = quit: ").strip().lower()
        if cmd == "q":
            break
        is_open = not is_open
        move_to(OPEN if is_open else LOCKED, "OPEN" if is_open else "LOCKED")
except KeyboardInterrupt:
    print()                  # Ctrl+C: just exit cleanly
finally:
    move_to(LOCKED, "LOCKED")
    servo.close()
    print("Stopped, servo back to LOCKED.")