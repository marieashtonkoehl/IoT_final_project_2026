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

## Device script (#26)

`station.py` is the real device script (sensor drivers in `sensors.py`). It runs all the time and:

- sends every button press to `POST /presses` with all current sensor values (timestamp = moment of the press)
- sends timed readings to `POST /readings`; interval per sensor from `READ_INTERVAL_*_SECONDS` in `.env` (defaults are used while empty)
- publishes the station status on MQTT `pollinator/<station_id>/status` (retained), last will = `online: false`
- ignores the PIR for the first 60 s after start (warm-up), so `motion_count_10min` is `null` during that time
- does not decide anything itself: cooldown, daily cap and plants are decided by the back end

LED bar commands (#28) and the latch (#41) are not included yet.

### Run it by hand

On the Pi, from the repo folder, venv on, back end running:

```bash
pip install -r device/requirements.txt
python device/station.py
```

The device also imports the system-installed `grove` library; create the venv with `python3 -m venv --system-site-packages .venv` so it can access it.

Watch the status: `mosquitto_sub -h localhost -t 'pollinator/#' -v`

For tests, set short intervals in `.env` (e.g. `10`) and `PRESS_COOLDOWN_SECONDS=10`.
Don't run `device/tests/test_sgp30.py` while `station.py` is running: both talk to the SGP30 and restart its measurement.

Expected log:

```text
INFO      OK    BME280 (0x76/0x77)
INFO      OK    SGP30 (0x58), warm-up 15 s
INFO    PIR warm-up: motion is counted from 60 s after start.
INFO    Running. Ctrl+C to stop.
INFO    MQTT connected to localhost:1883
INFO    Reading sent: temperature_c, humidity_pct, pressure_hpa, light_pct, soil_moisture_pct
INFO    Button pressed at 2026-11-24T14:09:13Z
INFO    Press 2026-11-24T14:09:13Z -> accepted, count 1/10
INFO    PIR warm-up done: counting motion now.
```

### Run it as a service (starts after reboot)

`pollinator-device.service` assumes user `haem` and the repo in `/home/haem/IoT_final_project_2026`.

```bash
sudo systemctl enable systemd-time-wait-sync    # once: lets the service wait for the synced clock
sudo cp device/pollinator-device.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pollinator-device
journalctl -u pollinator-device -f              # live log
sudo systemctl disable --now pollinator-device  # turn off again
```