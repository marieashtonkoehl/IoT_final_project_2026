# device/

> 🔓 Some tools for this folder are still open decisions — see [#58](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/58). This README will be updated once the team decides.

Runs on the Raspberry Pi 5. Reads all sensors, drives the LED bar, servo latch and buzzer, sends each press to the API (REST/JSON) and sends status over a second communication protocol (to be decided).

- `tests/`:  one small test script per sensor/actuator (Sprint 1)
- GPIO access via the Grove library / gpiozero (RPi.GPIO does not work on the Pi 5)
