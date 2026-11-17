"""Combined sensor test (#59).

Reads ALL sensors and drives all actuators together in one loop, to prove
they work at the same time without conflicts (pins, I2C bus, ADC).

- Every ~2 s: one line output with light, soil, temperature, humidity, pressure,
  PIR motion count and button state.
- Button press: button LED on, one more LED bar segment, printed.
  Bar full: servo -> OPEN, wait 3 s, servo -> LOCKED, bar reset.
- missing or failing prints warning;others keep going.
- Ctrl+C: LEDs off, servo back to LOCKED.

Logic copied from the single tests (button + LED bar,
PIR, servo, light, soil moisture, barometer). Pins: docs/wiring.md.
"""
import struct
import time

from smbus2 import SMBus

# Pins and addresses (see docs/wiring.md)
BTN_LED_PIN = 5        # D5: LED inside the button
BTN_PIN     = 6        # D5 second pin: button
PIR_PIN     = 16       # D16: PIR motion sensor
BAR_DATA    = 18       # D18: LED bar data
BAR_CLK     = 19       # D18 second pin: LED bar clock
SERVO_PIN   = 12       # PWM port (GPIO12)
LIGHT_CH    = 0        # A0
SOIL_CH     = 2        # A2
I2C_BUS     = 1
ADC_ADDR    = 0x08     # Grove Base HAT ADC
BME_ADDRS   = (0x76, 0x77)

# Settings 
PRINT_EVERY = 2.0      # seconds between status lines
UNLOCK_TIME = 3.0      # seconds the servo stays OPEN
PRESSED     = 0        # button reads 0 when pressed (same in test_button_ledbar.py)
SEGMENTS    = 10
LOCKED      = 0        # servo angles, as in test_servo.py
OPEN        = 90
SERVO_MOVE  = 0.6      # seconds the servo needs to arrive, then signal off
SAMPLES     = 5        # ADC readings averaged
MAX_LIGHT_RAW = 2870   # light sensor ceiling (light-sensor.py)
SOIL_DRY_RAW  = 0      # soil probe in air (soil_moisture_sensor.py)
SOIL_WET_RAW  = 1900   # soil probe in water


# Warnings: print once per sensor, again only after it recovered
_failing = set()

def warn(name, err):
    if name not in _failing:
        _failing.add(name)
        print(f"WARNING: {name} not working ({err}). Continuing without it.")

def ok(name):
    if name in _failing:
        _failing.discard(name)
        print(f"{name} works again.")


# LED bar driver (copied from test_button_ledbar.py)
class LedBar:
    def __init__(self, gpio_cls):
        self.data = gpio_cls(BAR_DATA, gpio_cls.OUT)
        self.clk = gpio_cls(BAR_CLK, gpio_cls.OUT)
        self.clk_state = 0

    def _send16(self, value):
        for _ in range(16):
            self.data.write(1 if value & 0x8000 else 0)
            self.clk_state ^= 1
            self.clk.write(self.clk_state)
            value <<= 1

    def _latch(self):
        self.data.write(0)
        time.sleep(0.0005)
        for _ in range(4):
            self.data.write(1)
            self.data.write(0)

    def show(self, level):
        """Light the first `level` segments (0..10)."""
        self._send16(0x0000)
        for i in range(SEGMENTS):
            self._send16(0xFF if i < level else 0x00)
        self._send16(0x0000)
        self._send16(0x0000)
        self._latch()


# Analogue sensors (copied from light-sensor.py / soil_moisture_sensor.py)
def read_adc(adc, channel):
    total = 0
    for _ in range(SAMPLES):
        total += adc.read_raw(channel)
        time.sleep(0.005)      # shorter than the single tests, keeps the loop fast
    return total / SAMPLES

def light_percent(raw):
    return min(100, raw / MAX_LIGHT_RAW * 100)

def light_level(pct):
    return "dark" if pct < 10 else "shade" if pct < 40 else "bright"

def soil_percent(raw):
    pct = (SOIL_DRY_RAW - raw) / (SOIL_DRY_RAW - SOIL_WET_RAW) * 100
    return max(0, min(100, pct))

def soil_level(pct):
    return "dry" if pct < 30 else "moist" if pct < 60 else "wet"


# BME280 (copied from barometer-sensor.py, with the address as a parameter)
class BME280:
    CHIP_IDS = {0x56: "BMP280", 0x57: "BMP280", 0x58: "BMP280", 0x60: "BME280"}

    def __init__(self, bus):
        self.bus = bus
        self.addr = None
        for addr in BME_ADDRS:                        # 0x76 first, then 0x77
            try:
                chip_id = bus.read_byte_data(addr, 0xD0)
            except OSError:
                continue
            if chip_id in self.CHIP_IDS:
                self.addr, self.chip_id = addr, chip_id
                break
        if self.addr is None:
            raise OSError("nothing answers at 0x76 or 0x77")
        self.name = self.CHIP_IDS[self.chip_id]
        self.has_humidity = self.chip_id == 0x60
        d = bus.read_i2c_block_data(self.addr, 0x88, 24)
        self.cal = struct.unpack("<HhhHhhhhhhhh", bytes(d))
        if self.has_humidity:
            h1 = bus.read_byte_data(self.addr, 0xA1)
            e = bus.read_i2c_block_data(self.addr, 0xE1, 7)
            h2, h3, e4, e5, e6, h6 = struct.unpack("<hBbBbb", bytes(e))
            self.hcal = (h1, h2, h3, (e4 << 4) | (e5 & 0x0F), (e6 << 4) | (e5 >> 4), h6)
            bus.write_byte_data(self.addr, 0xF2, 0x01)
        bus.write_byte_data(self.addr, 0xF5, 0x00)
        bus.write_byte_data(self.addr, 0xF4, 0x57)
        time.sleep(0.1)

    def read(self):
        """Return (temperature C, pressure hPa, humidity % or None)."""
        d = self.bus.read_i2c_block_data(self.addr, 0xF7, 8)
        raw_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        raw_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        raw_h = (d[6] << 8) | d[7]
        t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = self.cal
        var1 = (raw_t / 16384.0 - t1 / 1024.0) * t2
        var2 = (raw_t / 131072.0 - t1 / 8192.0) ** 2 * t3
        t_fine = var1 + var2
        temp = t_fine / 5120.0
        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * p6 / 32768.0
        var2 = var2 + var1 * p5 * 2.0
        var2 = var2 / 4.0 + p4 * 65536.0
        var1 = (p3 * var1 * var1 / 524288.0 + p2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * p1
        if var1 == 0:
            hpa = 0.0
        else:
            p = 1048576.0 - raw_p
            p = (p - var2 / 4096.0) * 6250.0 / var1
            var1 = p9 * p * p / 2147483648.0
            var2 = p * p8 / 32768.0
            hpa = (p + (var1 + var2 + p7) / 16.0) / 100.0
        hum = None
        if self.has_humidity:
            h1, h2, h3, h4, h5, h6 = self.hcal
            v = t_fine - 76800.0
            v = (raw_h - (h4 * 64.0 + h5 / 16384.0 * v)) * (
                h2 / 65536.0 * (1.0 + h6 / 67108864.0 * v * (1.0 + h3 / 67108864.0 * v)))
            v = v * (1.0 - h1 * v / 524288.0)
            hum = max(0.0, min(100.0, v))
        return temp, hpa, hum


# TODO(#30): add the SGP30 gas sensor (I2C 0x58) here once it has its own test


# Setup helper: try to open a part, warn and return None if it fails
def try_open(name, make):
    try:
        part = make()
        print(f"  OK    {name}")
        return part
    except Exception as err:               # missing, unplugged, wrong address...
        print(f"  FAIL  {name}: {err}")
        _failing.add(name)
        return None


def status_line(v, motion, btn_down, level):
    """One line with all values; "--" for a sensor without a reading."""
    def show(value, pattern):
        return "--" if value is None else pattern.format(value)

    light = "--" if v["light"] is None else f"{v['light']:.0f}% {light_level(v['light'])}"
    soil = "--" if v["soil"] is None else f"{v['soil']:.0f}% {soil_level(v['soil'])}"
    button = "--" if btn_down is None else ("pressed" if btn_down else "up")
    return (f"{time.strftime('%H:%M:%S')}"
            f" | light {light}"
            f" | soil {soil}"
            f" | {show(v['temp'], '{:.1f} C')}"
            f" | {show(v['hum'], '{:.0f} %RH')}"
            f" | {show(v['hpa'], '{:.1f} hPa')}"
            f" | motion {show(motion, '{}')}"
            f" | button {button}"
            f" | bar {level}/{SEGMENTS}")


def main():
    from grove.gpio import GPIO
    from grove.adc import ADC

    print("Opening sensors and actuators...")
    bus = SMBus(I2C_BUS)
    btn     = try_open("button (D5)", lambda: GPIO(BTN_PIN, GPIO.IN))
    btn_led = try_open("button LED (D5)", lambda: GPIO(BTN_LED_PIN, GPIO.OUT))
    pir     = try_open("PIR (D16)", lambda: GPIO(PIR_PIN, GPIO.IN))
    bar     = try_open("LED bar (D18)", lambda: LedBar(GPIO))
    adc     = try_open("HAT ADC (0x08)", lambda: ADC(address=ADC_ADDR))
    bme     = try_open("BME280 (0x76/0x77)", lambda: BME280(bus))

    def make_servo():
        from gpiozero import AngularServo
        s = AngularServo(SERVO_PIN, min_angle=0, max_angle=180,
                         min_pulse_width=0.0005, max_pulse_width=0.0025)
        s.angle = LOCKED
        time.sleep(SERVO_MOVE)
        s.detach()
        return s
    servo = try_open("servo (GPIO12)", make_servo)
    if bme:
        print(f"        BME280 is a {bme.name} at 0x{bme.addr:02x}")

    # Latest values (None = no reading yet / sensor failing)
    v = dict(light=None, soil=None, temp=None, hum=None, hpa=None)
    level = 0
    motion_count = 0
    last_btn = btn.read() if btn else 1 - PRESSED
    last_pir = 0
    btn_down = False
    servo_detach_at = None      # when to stop the servo signal
    relock_at = None            # when to lock again (None = locked)
    next_print = time.monotonic()

    def servo_to(angle, name):
        nonlocal servo_detach_at
        print(f"{time.strftime('%H:%M:%S')}  servo -> {name} ({angle}°)")
        if servo:
            servo.angle = angle
            servo_detach_at = time.monotonic() + SERVO_MOVE

    if bar:
        bar.show(0)
    print("Running. Press the button, wave at the PIR. Ctrl+C to stop.\n")

    try:
        while True:
            now = time.monotonic()

            # Button (every loop, ~10 ms)
            if btn:
                state = btn.read()
                if state != last_btn and state == PRESSED:
                    btn_down = True
                    if btn_led:
                        btn_led.write(1)
                    if relock_at is not None:
                        print(f"{time.strftime('%H:%M:%S')}  pressed (locker open, not counted)")
                    else:
                        level += 1
                        print(f"{time.strftime('%H:%M:%S')}  pressed -> level {level}/{SEGMENTS}")
                        if bar:
                            bar.show(level)
                        if level >= SEGMENTS:
                            print("Bar full!")
                            servo_to(OPEN, "OPEN")
                            relock_at = now + SERVO_MOVE + UNLOCK_TIME
                    time.sleep(0.05)                    # debounce
                elif state != last_btn:
                    btn_down = False
                    if btn_led:
                        btn_led.write(0)
                last_btn = state

            # PIR (every loop): count rising edges
            if pir:
                state = pir.read()
                if state == 1 and last_pir == 0:
                    motion_count += 1
                    print(f"{time.strftime('%H:%M:%S')}  motion detected (#{motion_count})")
                last_pir = state

            # Servo timing (no sleep, so the other sensors keep running)
            if servo_detach_at and now >= servo_detach_at:
                servo.detach()
                servo_detach_at = None
            if relock_at and now >= relock_at:
                servo_to(LOCKED, "LOCKED")
                relock_at = None
                level = 0
                if bar:
                    bar.show(0)
                print(f"{time.strftime('%H:%M:%S')}  bar reset")

            # Other sensors + status line every 2 s
            if now >= next_print:
                next_print += PRINT_EVERY
                if adc:
                    try:
                        v["light"] = light_percent(read_adc(adc, LIGHT_CH))
                        v["soil"] = soil_percent(read_adc(adc, SOIL_CH))
                        ok("HAT ADC (0x08)")
                    except Exception as err:
                        v["light"] = v["soil"] = None
                        warn("HAT ADC (0x08)", err)
                if bme:
                    try:
                        v["temp"], v["hpa"], v["hum"] = bme.read()
                        ok("BME280 (0x76/0x77)")
                    except Exception as err:
                        v["temp"] = v["hpa"] = v["hum"] = None
                        warn("BME280 (0x76/0x77)", err)

                print(status_line(v, motion_count if pir else None,
                                  btn_down if btn else None, level))

            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if bar:
            bar.show(0)
        if btn_led:
            btn_led.write(0)
        if servo:
            servo.angle = LOCKED
            time.sleep(SERVO_MOVE)
            servo.detach()
            servo.close()
        bus.close()
        print(f"Stopped. LEDs off, servo LOCKED. {motion_count} motion events counted.")


if __name__ == "__main__":
    main()
