"""Test LED button + LED bar (#16).
Each press lights one more segment of the LED bar.
When all 10 are lit, the bar blinks and starts again."""
import time
from grove.gpio import GPIO

# --- Pins (see port plan) ---
BTN_LED_PIN = 5    # D5: LED inside the button (output)
BTN_PIN     = 6    # D5 second pin: button (input)
BAR_DATA    = 18   # D18: LED bar data
BAR_CLK     = 19   # D18 second pin: LED bar clock

PRESSED  = 0       # Red LED Button reads 0 when pressed (flip to 1 if inverted)
SEGMENTS = 10


# --- LED bar driver (Grove LED Bar v2.0, MY9221 chip) ---
data = GPIO(BAR_DATA, GPIO.OUT)
clk  = GPIO(BAR_CLK, GPIO.OUT)
clk_state = 0

def _send16(value):
    """Send 16 bits; the chip reads one bit on every clock edge."""
    global clk_state
    for _ in range(16):
        data.write(1 if value & 0x8000 else 0)
        clk_state ^= 1
        clk.write(clk_state)
        value <<= 1

def _latch():
    """Tell the chip to show the data it just received."""
    data.write(0)
    time.sleep(0.0005)
    for _ in range(4):
        data.write(1)
        data.write(0)

def bar_show(level):
    """Light the first `level` segments (0..10)."""
    _send16(0x0000)                       # command word
    for i in range(SEGMENTS):
        _send16(0xFF if i < level else 0x00)
    _send16(0x0000)                       # 2 unused channels
    _send16(0x0000)
    _latch()


# --- Button ---
btn_led = GPIO(BTN_LED_PIN, GPIO.OUT)
btn     = GPIO(BTN_PIN, GPIO.IN)


# --- Test ---
level = 0
bar_show(0)
print(f"Button raw value now (not pressed): {btn.read()}")
print("Press the button (Ctrl+C to stop)...")

last = btn.read()
try:
    while True:
        state = btn.read()
        if state != last and state == PRESSED:      # new press only
            level += 1
            btn_led.write(1)
            print(f"{time.strftime('%H:%M:%S')}  pressed -> level {level}/{SEGMENTS}")
            bar_show(level)
            if level >= SEGMENTS:
                print("Bar full! (here the locker would open)")
                for _ in range(3):                  # blink full bar
                    bar_show(0);        time.sleep(0.3)
                    bar_show(SEGMENTS); time.sleep(0.3)
                level = 0
                bar_show(0)
            time.sleep(0.05)                        # simple debounce
        elif state != last:
            btn_led.write(0)                        # released
        last = state
        time.sleep(0.01)
except KeyboardInterrupt:
    bar_show(0)
    btn_led.write(0)
    print("\nStopped, bar cleared.")