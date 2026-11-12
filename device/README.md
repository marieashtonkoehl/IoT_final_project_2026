# device/

The device script. Runs on the Raspberry Pi 5 all the time, as a systemd service.

- Reads all sensors. Timed readings happen inside the script; the read interval per sensor comes from `.env` (set after Sprint 1 tests).
- Sends each button press and the timed readings to the back end over REST (`POST /presses`, `POST /readings`).
- Publishes station status over MQTT (local Mosquitto broker).
- Receives commands from the back end over MQTT: set the LED bar level, unlock the latch. The servo locks the latch again after 60 s (`LATCH_RELOCK_SECONDS`).
- Drives the LED bar and the servo latch. No buzzer.

- `tests/`:  one small test script per sensor/actuator (Sprint 1)
- GPIO access via the Grove library / gpiozero (RPi.GPIO does not work on the Pi 5)

Messages and topics → [docs/data-model.md](../docs/data-model.md).
