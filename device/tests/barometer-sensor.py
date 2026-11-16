"""Barometer test (BME280)
Finds the sensor on the I2C bus, reads temperature and air pressure every
second and prints them with a qualitative pressure level.
"""
import time
import struct
from smbus2 import SMBus

# --- Settings ---
I2C_BUS = 1          # /dev/i2c-1 on the Raspberry Pi
ADDRESS = 0x76
REG_ID = 0xD0
REG_CALIBRATION = 0x88
REG_HUM_CALIB_1 = 0xA1   # dig_H1 (1 byte)
REG_HUM_CALIB_2 = 0xE1   # dig_H2..dig_H6 (7 bytes)
REG_CTRL_HUM = 0xF2      # humidity oversampling (BME280 only)
REG_CTRL_MEAS = 0xF4
REG_CONFIG = 0xF5
REG_DATA = 0xF7          # pressure (3), temperature (3), humidity (2)
CHIP_IDS = {0x56: "BMP280", 0x57: "BMP280", 0x58: "BMP280", 0x60: "BME280"}
BME280_ID = 0x60

# --- Barometer driver (Bosch BMP280 / BME280 formulas from the datasheet) ---
def read_calibration(bus):
    """Read the 12 factory calibration values of the chip."""
    data = bus.read_i2c_block_data(ADDRESS, REG_CALIBRATION, 24)
    return struct.unpack("<HhhHhhhhhhhh", bytes(data))

def read_humidity_calibration(bus):
    """Read the 6 humidity calibration values of the BME280 (H1..H6)."""
    h1 = bus.read_byte_data(ADDRESS, REG_HUM_CALIB_1)
    e = bus.read_i2c_block_data(ADDRESS, REG_HUM_CALIB_2, 7)
    # bytes 0xE1..0xE7: H2 (16 bit), H3, E4, E5, E6, H6 (signed bytes)
    h2, h3, e4, e5, e6, h6 = struct.unpack("<hBbBbb", bytes(e))
    h4 = (e4 << 4) | (e5 & 0x0F)    # H4 and H5 share the byte 0xE5
    h5 = (e6 << 4) | (e5 >> 4)
    return h1, h2, h3, h4, h5, h6

def read_raw(bus):
    """Raw temperature (20 bit), pressure (20 bit) and humidity (16 bit)."""
    d = bus.read_i2c_block_data(ADDRESS, REG_DATA, 8)
    raw_pressure = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
    raw_temperature = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
    raw_humidity = (d[6] << 8) | d[7]
    return raw_temperature, raw_pressure, raw_humidity

def compensate(raw_temperature, raw_pressure, calibration):
    """Convert raw values to (temperature in deg C, pressure in hPa)."""
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = calibration
    var1 = (raw_temperature / 16384.0 - t1 / 1024.0) * t2
    var2 = (raw_temperature / 131072.0 - t1 / 8192.0) ** 2 * t3
    t_fine = var1 + var2
    temperature = t_fine / 5120.0
    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * p6 / 32768.0
    var2 = var2 + var1 * p5 * 2.0
    var2 = var2 / 4.0 + p4 * 65536.0
    var1 = (p3 * var1 * var1 / 524288.0 + p2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * p1
    if var1 == 0:
        return temperature, 0.0
    pressure = 1048576.0 - raw_pressure
    pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
    var1 = p9 * pressure * pressure / 2147483648.0
    var2 = pressure * p8 / 32768.0
    pressure = pressure + (var1 + var2 + p7) / 16.0
    return temperature, pressure / 100.0

def compensate_humidity(raw_humidity, temperature, hum_calibration):
    """Convert the raw humidity to relative humidity in % (0-100).

    The formula needs the temperature value t_fine; it is recovered from the
    temperature in deg C (temperature = t_fine / 5120).
    """
    h1, h2, h3, h4, h5, h6 = hum_calibration
    t_fine = temperature * 5120.0
    var_h = t_fine - 76800.0
    var_h = (raw_humidity - (h4 * 64.0 + h5 / 16384.0 * var_h)) * (
        h2 / 65536.0 * (1.0 + h6 / 67108864.0 * var_h
                        * (1.0 + h3 / 67108864.0 * var_h)))
    var_h = var_h * (1.0 - h1 * var_h / 524288.0)
    return max(0.0, min(100.0, var_h))

def level(hpa):
    """Rough qualitative level of the air pressure."""
    if hpa < 1000:
        return "low (unsettled weather)"
    if hpa <= 1020:
        return "normal"
    return "high (settled weather)"

def humidity_level(pct):
    """Rough qualitative level of the air humidity."""
    if pct < 30:
        return "dry air"
    if pct <= 60:
        return "comfortable"
    return "humid air"


# --- Test ---
bus = SMBus(I2C_BUS)
try:
    chip_id = bus.read_byte_data(ADDRESS, REG_ID)
except OSError:
    raise SystemExit(f"Nothing answers at 0x{ADDRESS:02x}. Check the cable, "
                     "the I2C port and run: i2cdetect -y 1")
if chip_id not in CHIP_IDS:
    raise SystemExit(f"Unknown chip id 0x{chip_id:02x}: not a BMP280/BME280. "
                     "Tell the team the sensor model.")

has_humidity = chip_id == BME280_ID
calibration = read_calibration(bus)
if has_humidity:
    hum_calibration = read_humidity_calibration(bus)
    bus.write_byte_data(ADDRESS, REG_CTRL_HUM, 0x01)   # humidity x1 (before CTRL_MEAS)
bus.write_byte_data(ADDRESS, REG_CONFIG, 0x00)
bus.write_byte_data(ADDRESS, REG_CTRL_MEAS, 0x57)   # normal mode, oversampling
time.sleep(0.1)

print(f"{CHIP_IDS[chip_id]} found at 0x{ADDRESS:02x}. Ctrl+C to stop.")
print(f"{'temp (C)':>10} {'pressure (hPa)':>15} {'humidity (%)':>13}  level")
try:
    while True:
        raw_t, raw_p, raw_h = read_raw(bus)
        temperature, hpa = compensate(raw_t, raw_p, calibration)
        if has_humidity:
            humidity = compensate_humidity(raw_h, temperature, hum_calibration)
            hum_text = f"{humidity:13.1f}"
            extra = f"{level(hpa)}, {humidity_level(humidity)}"
        else:
            hum_text = f"{'n/a':>13}"
            extra = level(hpa)
        print(f"{temperature:10.2f} {hpa:15.2f} {hum_text}  {extra}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
