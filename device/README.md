# device/

The device script. Runs on the Raspberry Pi 5 all the time, as a systemd service.

- Reads all sensors. Timed readings happen inside the script; the read interval per sensor comes from `.env` (set after Sprint 1 tests).
- SGP30 (VOC + eCO2, issue #30): read every 1 s, because the sensor needs this for its built-in baseline correction. The first ~15 s after start return fixed values (400 ppm / 0 ppb) and are discarded. The script sends the latest value at the interval set in `READ_INTERVAL_SGP30_SECONDS`.
- Sends each button press and the timed readings to the back end over REST (`POST /presses`, `POST /readings`).
- Publishes station status over MQTT (local Mosquitto broker).
- Receives commands from the back end over MQTT: set the LED bar level, unlock the latch. The servo locks the latch again after 60 s (`LATCH_RELOCK_SECONDS`).
- Drives the LED bar and the servo latch. No buzzer.

- `tests/`:  one small test script per sensor/actuator (Sprint 1)
- GPIO access via the Grove library / gpiozero (RPi.GPIO does not work on the Pi 5)

Messages and topics → [docs/data-model.md](../docs/data-model.md).

## Combined sensor test (#59)

`tests/test_combined.py` reads all sensors and drives all actuators in one loop, to check they work together (pins, I2C bus, ADC). Pins as in [docs/wiring.md](../docs/wiring.md).

Run it on the Pi, from the repo folder, with the venv on:

```bash
cd ~/IoT_final_project_2026
source .venv/bin/activate
pip install smbus2 gpiozero      # only if not installed yet
i2cdetect -y 1                   # should list 08 (HAT) and 76 or 77 (BME280)
python device/tests/test_combined.py
```

Expected output (one status line every ~2 s, events in between):

```text
Opening sensors and actuators...
  OK    button (D5)
  ...
  OK    servo (GPIO12)
        BME280 is a BME280 at 0x76
Running. Press the button, wave at the PIR. Ctrl+C to stop.

10:15:02 | light 45% bright | soil 12% dry | 21.3 C | 49 %RH | 1013.2 hPa | motion 0 | button up | bar 0/10
10:15:03  motion detected (#1)
10:15:04  pressed -> level 1/10
...
10:15:40  pressed -> level 10/10
Bar full!
10:15:40  servo -> OPEN (90°)
10:15:44  servo -> LOCKED (0°)
10:15:44  bar reset
```

- A missing I2C sensor shows `FAIL` at the start and `--` in the status lines; the rest keeps running.
- An unplugged analogue sensor (light, soil) gives no error, just a value near 0.
- Ctrl+C: LED bar and button LED off, servo back to LOCKED.
