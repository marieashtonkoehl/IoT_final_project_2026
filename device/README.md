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
