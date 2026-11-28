"""Sensor drivers for the device script (#26).

Copied from the Sprint 1 tests (device/tests/test_combined.py and the single
tests), so station.py only has to call small functions. Pins and addresses:
docs/wiring.md.

Every read function returns a number in the unit from docs/data-model.md,
or raises an exception if the sensor does not answer. station.py turns a
failed read into `null` (never 0).
"""

import struct
import time

from smbus2 import i2c_msg

# Pins and addresses (see docs/wiring.md)
BTN_LED_PIN = 5        # D5: LED inside the button
BTN_PIN = 6            # D5 second pin: button
PIR_PIN = 16           # D16: PIR motion sensor
LIGHT_CH = 0           # A0
SOIL_CH = 2            # A2
I2C_BUS = 1
ADC_ADDR = 0x08        # Grove Base HAT ADC
BME_ADDRS = (0x76, 0x77)

PRESSED = 0            # button reads 0 when pressed

# Calibration (from light-sensor.py / soil_moisture_sensor.py)
SAMPLES = 5            # ADC readings averaged
MAX_LIGHT_RAW = 2870   # light sensor ceiling
SOIL_DRY_RAW = 0       # soil probe in air
SOIL_WET_RAW = 1900    # soil probe in water


# Analogue sensors (light, soil moisture) via the Base HAT ADC

def read_adc(adc, channel):
    """Average a few raw ADC readings of one channel."""
    total = 0
    for _ in range(SAMPLES):
        total += adc.read_raw(channel)
        time.sleep(0.005)
    return total / SAMPLES


def read_light_pct(adc):
    """Light in % of the sensor range (0 = dark, 100 = full sun)."""
    raw = read_adc(adc, LIGHT_CH)
    return min(100.0, raw / MAX_LIGHT_RAW * 100)


def read_soil_moisture_pct(adc):
    """Soil moisture in % (0 = dry, 100 = wet)."""
    raw = read_adc(adc, SOIL_CH)
    pct = (SOIL_DRY_RAW - raw) / (SOIL_DRY_RAW - SOIL_WET_RAW) * 100
    return max(0.0, min(100.0, pct))


# BME280: temperature, humidity, air pressure (I2C)

class BME280:
    """BME280 / BMP280 driver (copied from barometer-sensor.py)."""

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
        """Return (temperature_c, pressure_hpa, humidity_pct or None)."""
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


# SGP30: TVOC + eCO2 (I2C 0x58), from device/tests/test_sgp30.py (#30)

SGP30_ADDR = 0x58
SGP30_IAQ_INIT = (0x20, 0x03)        # start the air-quality algorithm
SGP30_MEASURE_IAQ = (0x20, 0x08)     # one measurement: eCO2 + TVOC


def _crc8(data):
    """CRC from the SGP30 datasheet: polynomial 0x31, start value 0xFF."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _sgp30_command(bus, cmd, wait_s, words=0):
    """Send a 2-byte command, wait, read `words` 16-bit values (each with CRC).

    Raises OSError if the sensor does not answer, ValueError on a CRC error.
    """
    bus.i2c_rdwr(i2c_msg.write(SGP30_ADDR, list(cmd)))
    time.sleep(wait_s)
    if words == 0:
        return []
    msg = i2c_msg.read(SGP30_ADDR, words * 3)
    bus.i2c_rdwr(msg)
    raw = list(msg)
    values = []
    for i in range(0, len(raw), 3):
        high, low, crc = raw[i], raw[i + 1], raw[i + 2]
        if _crc8([high, low]) != crc:
            raise ValueError("SGP30 CRC error")
        values.append((high << 8) | low)
    return values


def init_sgp30(bus):
    """Start the SGP30 measurement. After this, call read_sgp30() every 1 s."""
    _sgp30_command(bus, SGP30_IAQ_INIT, 0.01)


def read_sgp30(bus):
    """One SGP30 measurement. Returns (tvoc_ppb, eco2_ppm).

    The first ~15 readings after init_sgp30() are fixed warm-up values
    (0 ppb / 400 ppm); station.py discards them.
    """
    eco2_ppm, tvoc_ppb = _sgp30_command(bus, SGP30_MEASURE_IAQ, 0.012, words=2)
    return tvoc_ppb, eco2_ppm