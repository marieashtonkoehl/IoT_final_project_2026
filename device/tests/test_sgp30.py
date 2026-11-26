"""Test the SGP30 gas sensor (#30): TVOC and eCO2, read every 1 s.

The SGP30 (Grove "VOC and eCO2 Gas Sensor v1.0") sits on the I2C 2 port of the
HAT, address 0x58 (docs/wiring.md). This script talks to it directly with
smbus2, using the commands from the Sensirion SGP30 datasheet:

- the sensor must be measured every 1 s: its built-in baseline correction
  needs this rhythm
- the first 15 readings after start are fixed values (400 ppm / 0 ppb) while
  the sensor warms up: they are printed but marked as discarded
- every 2-byte value comes with a CRC byte; a wrong CRC means a bad reading

Run on the Pi, from the repo folder, venv on:
    i2cdetect -y 1                   # should list 58 (and 08, 76/77)
    python device/tests/test_sgp30.py

Breathe on the sensor or hold hand sanitiser near it: TVOC and eCO2 go up.
Ctrl+C to stop.
"""

import time

from smbus2 import SMBus, i2c_msg

I2C_BUS = 1
SGP30_ADDR = 0x58

# Commands (datasheet, table "Measurement commands")
CMD_IAQ_INIT = (0x20, 0x03)          # start the air-quality algorithm
CMD_MEASURE_IAQ = (0x20, 0x08)       # one measurement: eCO2 + TVOC
CMD_GET_SERIAL_ID = (0x36, 0x82)     # 48-bit serial number
CMD_GET_FEATURE_SET = (0x20, 0x2F)   # product type + version
CMD_MEASURE_TEST = (0x20, 0x32)      # self-test, answers 0xD400 if OK

READ_EVERY = 1.0                     # seconds, required by the sensor
WARMUP_READINGS = 15                 # first readings are fixed values


def crc8(data):
    """CRC from the datasheet: polynomial 0x31, start value 0xFF.

    Example from the datasheet: crc8([0xBE, 0xEF]) == 0x92.
    """
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def command(bus, cmd, wait_s, words=0):
    """Send a 2-byte command, wait, and read `words` 16-bit values.

    The answer comes as [high, low, crc] per word. Raises OSError if the
    sensor does not answer, ValueError if a CRC is wrong.
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
        if crc8([high, low]) != crc:
            raise ValueError(f"CRC error in answer to command 0x{cmd[0]:02x}{cmd[1]:02x}")
        values.append((high << 8) | low)
    return values


def init_sgp30(bus):
    """Start the measurement. After this, measure exactly every 1 s."""
    command(bus, CMD_IAQ_INIT, 0.01)


def read_sgp30(bus):
    """One measurement. Returns (tvoc_ppb, eco2_ppm)."""
    eco2_ppm, tvoc_ppb = command(bus, CMD_MEASURE_IAQ, 0.012, words=2)
    return tvoc_ppb, eco2_ppm


def main():
    with SMBus(I2C_BUS) as bus:
        # 1. Is the sensor there? Serial number + feature set
        try:
            serial = command(bus, CMD_GET_SERIAL_ID, 0.01, words=3)
        except OSError as err:
            print(f"FAIL: no answer at 0x{SGP30_ADDR:02x} ({err}).")
            print("Check the cable (I2C 2 port) and run: i2cdetect -y 1")
            return
        serial_hex = "".join(f"{word:04x}" for word in serial)
        feature = command(bus, CMD_GET_FEATURE_SET, 0.01, words=1)[0]
        print(f"SGP30 found at 0x{SGP30_ADDR:02x}, serial {serial_hex}, "
              f"feature set 0x{feature:04x}")

        # 2. Self-test (takes ~220 ms)
        result = command(bus, CMD_MEASURE_TEST, 0.22, words=1)[0]
        print("Self-test:", "OK" if result == 0xD400 else f"FAILED (0x{result:04x})")

        # 3. Start the algorithm and measure every 1 s
        init_sgp30(bus)
        print(f"Measuring every {READ_EVERY:.0f} s. "
              f"First {WARMUP_READINGS} readings are warm-up and discarded. Ctrl+C to stop.\n")

        count = 0
        next_read = time.monotonic()
        try:
            while True:
                count += 1
                try:
                    tvoc, eco2 = read_sgp30(bus)
                    note = "  (warm-up, discarded)" if count <= WARMUP_READINGS else ""
                    print(f"{time.strftime('%H:%M:%S')}  #{count:3d}  "
                          f"TVOC {tvoc:5d} ppb  eCO2 {eco2:5d} ppm{note}")
                except (OSError, ValueError) as err:
                    print(f"{time.strftime('%H:%M:%S')}  #{count:3d}  read failed: {err}")

                # keep an exact 1 s rhythm, even if a read takes a bit longer
                next_read += READ_EVERY
                time.sleep(max(0.0, next_read - time.monotonic()))
        except KeyboardInterrupt:
            print(f"\nStopped after {count} readings.")


if __name__ == "__main__":
    main()