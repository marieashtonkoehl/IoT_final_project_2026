# device/

Runs on the Raspberry Pi 5. Reads all sensors, drives the LED bar, servo latch and buzzer, sends each press to the API (REST/JSON) and publishes status over MQTT.

- `tests/` — one small test script per sensor/actuator (Sprint 1)
- GPIO access via the Grove library / gpiozero (RPi.GPIO does not work on the Pi 5)
