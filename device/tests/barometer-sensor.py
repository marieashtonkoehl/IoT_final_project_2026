"""Barometer test (BME280)
Finds the sensor on the I2C bus, reads temperature and air pressure every
second and prints them with a qualitative pressure level.
"""
import time
import struct
from smbus2 import SMBus

# --- Settings (see port plan) ---
I2C_BUS = 1          # /dev/i2c-1 on the Raspberry Pi
ADDRESS = 0x77       # change to 0x76 if i2cdetect shows 0x76
REG_ID = 0xD0
REG_CALIBRATION = 0x88
REG_CTRL_MEAS = 0xF4
REG_CONFIG = 0xF5
REG_DATA = 0xF7
CHIP_IDS = {0x56: "BMP280", 0x57: "BMP280", 0x58: "BMP280", 0x60: "BME280"}


# --- Barometer driver (Bosch BMP280 formulas from the datasheet) ---
def read_calibration(bus):
    """Read the 12 factory calibration values of the chip."""
    data = bus.read_i2c_block_data(ADDRESS, REG_CALIBRATION, 24)
    return struct.unpack("<HhhHhhhhhhhh", bytes(data))

def read_raw(bus):
    """Raw 20 bit temperature and pressure values."""
    d = bus.read_i2c_block_data(ADDRESS, REG_DATA, 6)
    raw_pressure = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
    raw_temperature = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
    return raw_temperature, raw_pressure

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

def level(hpa):
    """Rough qualitative level of the air pressure."""
    if hpa < 1000:
        return "low (unsettled weather)"
    if hpa <= 1020:
        return "normal"
    return "high (settled weather)"


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

calibration = read_calibration(bus)
bus.write_byte_data(ADDRESS, REG_CONFIG, 0x00)
bus.write_byte_data(ADDRESS, REG_CTRL_MEAS, 0x57)   # normal mode, oversampling
time.sleep(0.1)

print(f"{CHIP_IDS[chip_id]} found at 0x{ADDRESS:02x}. Ctrl+C to stop.")
print(f"{'temp (C)':>10} {'pressure (hPa)':>15}  level")
try:
    while True:
        raw_t, raw_p = read_raw(bus)
        temperature, hpa = compensate(raw_t, raw_p, calibration)
        print(f"{temperature:10.2f} {hpa:15.2f}  {level(hpa)}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
