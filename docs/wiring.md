# Wiring plan

All sensors and actuators are connected to the **Grove Base HAT** on the Raspberry Pi 5.
The HAT has 6 digital ports, 4 analogue ports, 3 I2C ports, 1 PWM port and 1 UART port.

| Component | Type | Port | GPIO / I2C address | Purpose |
|---|---|---|---|---|
| Red LED Button v1.0 | Digital | D5 | GPIO5 (LED), GPIO6 (button) | Registers a pollinator sighting |
| LED bar v2.0 | Digital | D18 | GPIO18 (data), GPIO19 (clock) | Shows progress towards the next plant |
| Servo latch | PWM | PWM | GPIO12 | Unlocks the plant locker |
| Light sensor | Analogue | A0 | ADC channel 0 | Sun / shade at each press |
| Soil moisture sensor | Analogue | A2 | ADC channel 2 | Moisture of the planting bed |
| Barometer (BME280) | I2C | I2C 1 | 0x77 (or 0x76) | Air pressure, temperature and humidity at each press |
| VOC & eCO2 gas sensor (SGP30 v1.0) | I2C | I2C 2 | 0x58 | Air quality at each press |
| Ultrasonic distance sensor v2.0 | Digital | D22 | GPIO22 (trigger and echo on one pin) | Counts passers-by walking through its beam |
| *free* | Digital | D16 | – | Reserve (was PIR, replaced in #75) |
| *free* | Digital | D24 | – | Reserve |
| *free* | Digital | D26 | – | Reserve |
| *free* | Analogue | A4 | – | Reserve |
| *free* | Analogue | A6 | – | Reserve |
| *free* | I2C | I2C 3 | – | Reserve |
| *free* | UART | UART | – | Reserve |

## Notes

- The BME280 measures air pressure, temperature and humidity, so no separate temperature & humidity sensor is used.
- The light sensor's reading tops out at the same value (raw ~2870) for overcast daylight and a torch, so it can't tell a cloudy day from a sunny one. Good enough for the MVP demo (dark / shade / bright), but a real station would need a sensor that measures actual light intensity.
- Each digital Grove port carries two GPIO pins (e.g. D5 = GPIO5 + GPIO6). The LED button and the LED bar use both.
- The HAT's own ADC uses I2C address **0x08**. No other sensor may use this address.
- All I2C ports share the same bus. Check the addresses with `i2cdetect -y 1`.
- The servo uses the hardware PWM pin (GPIO12) to avoid jitter on the Pi 5.
- GPIO access via the Grove library / gpiozero (RPi.GPIO does not work on the Pi 5).
- Test scripts for each component: `device/tests/`.
- The PIR was replaced by the ultrasonic distance sensor (#75): in the test the PIR reported motion almost all the time and could not count passers-by. The ultrasonic sensor only sees a narrow beam (15°, 3–350 cm), so the station must be placed so that visitors walk through it. Device script change: #NEW.
- Plug Grove sensors in only while the Pi is off (hot-plugging can damage them).