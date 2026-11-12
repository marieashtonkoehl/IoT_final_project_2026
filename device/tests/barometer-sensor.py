"""Barometer test (BME280)
Finds the sensor on the I2C bus, reads temperature and air pressure every
second and prints them with a qualitative pressure level.
"""

import argparse
import struct
import time
 
from smbus2 import SMBus
 
I2C_BUS = 1                        # /dev/i2c-1 on the Raspberry Pi
CANDIDATE_ADDRESSES = (0x77, 0x76)  # the Grove module uses 0x77 by default
CHIP_IDS = {0x60: "BME280"}
 
REG_ID = 0xD0
REG_CALIBRATION = 0x88   # 24 bytes of calibration data
REG_CTRL_MEAS = 0xF4
REG_CONFIG = 0xF5
REG_DATA = 0xF7          # 6 bytes: pressure (3) then temperature (3)
 
# Typical range of sea-level pressure on Earth, used as a sanity check.
PRESSURE_MIN_HPA = 300
PRESSURE_MAX_HPA = 1100
 
def find_sensor(bus, forced_address=None):
    """Return (address, chip name) of the first BMP280/BME280 found."""
    addresses = (forced_address,) if forced_address else CANDIDATE_ADDRESSES
    for address in addresses:
        try:
            chip_id = bus.read_byte_data(address, REG_ID)
        except OSError:
            continue  # nobody answers at this address
        if chip_id in CHIP_IDS:
            return address, CHIP_IDS[chip_id]
    return None, None
 
 
def read_calibration(bus, address):
    """Read the 12 factory calibration values: T1-T3 and P1-P9."""
    data = bus.read_i2c_block_data(address, REG_CALIBRATION, 24)
    # T1 and P1 are unsigned 16 bit, all the others signed 16 bit, little endian
    return struct.unpack("<HhhHhhhhhhhh", bytes(data))
 
 
def start_measuring(bus, address):
    """Put the chip in normal mode (temperature x2, pressure x16 oversampling)."""
    bus.write_byte_data(address, REG_CONFIG, 0x00)
    bus.write_byte_data(address, REG_CTRL_MEAS, 0x57)
    time.sleep(0.1)  # let the first measurement finish
 
 
def read_raw(bus, address):
    """Return the raw 20 bit (temperature, pressure) values."""
    d = bus.read_i2c_block_data(address, REG_DATA, 6)
    raw_pressure = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
    raw_temperature = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
    return raw_temperature, raw_pressure
 
 
def compensate(raw_temperature, raw_pressure, calibration):
    """Convert raw values to (temperature in deg C, pressure in hPa).
 
    Floating point formulas from the BMP280 datasheet (section 3.11.3).
    """
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = calibration
 
    # temperature
    var1 = (raw_temperature / 16384.0 - t1 / 1024.0) * t2
    var2 = (raw_temperature / 131072.0 - t1 / 8192.0) ** 2 * t3
    t_fine = var1 + var2
    temperature_c = t_fine / 5120.0
 
    # pressure (in Pa)
    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * p6 / 32768.0
    var2 = var2 + var1 * p5 * 2.0
    var2 = var2 / 4.0 + p4 * 65536.0
    var1 = (p3 * var1 * var1 / 524288.0 + p2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * p1
    if var1 == 0:
        return temperature_c, 0.0  # avoid a division by zero
    pressure = 1048576.0 - raw_pressure
    pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
    var1 = p9 * pressure * pressure / 2147483648.0
    var2 = pressure * p8 / 32768.0
    pressure = pressure + (var1 + var2 + p7) / 16.0
 
    return temperature_c, pressure / 100.0
 
 
def pressure_level(hpa):
    """Rough qualitative level of the air pressure."""
    if hpa < 1000:
        return "low (unsettled weather)"
    if hpa <= 1020:
        return "normal"
    return "high (settled weather)"
 
 
def main():
    parser = argparse.ArgumentParser(description="Barometer (BMP280/BME280) test")
    parser.add_argument("--address", type=lambda s: int(s, 0), default=None,
                        help="I2C address, e.g. 0x76 (default: try 0x77 and 0x76)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between readings")
    args = parser.parse_args()
 
    with SMBus(I2C_BUS) as bus:
        address, chip = find_sensor(bus, args.address)
        if address is None:
            print("No BMP280/BME280 found on I2C bus 1. Check the cable, the "
                  "I2C port and run: i2cdetect -y 1")
            return
 
        calibration = read_calibration(bus, address)
        start_measuring(bus, address)
        print(f"{chip} found at address 0x{address:02x}. Ctrl+C to stop.")
        print(f"{'temperature (C)':>16} {'pressure (hPa)':>15}  level")
 
        try:
            while True:
                raw_t, raw_p = read_raw(bus, address)
                temperature, hpa = compensate(raw_t, raw_p, calibration)
                line = f"{temperature:16.2f} {hpa:15.2f}  {pressure_level(hpa)}"
                if not PRESSURE_MIN_HPA <= hpa <= PRESSURE_MAX_HPA:
                    line += "   <- out of range: check the sensor"
                print(line)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nBye.")
 
 
if __name__ == "__main__":
    main()
 
