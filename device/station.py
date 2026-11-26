"""Pollinator Station device script (#26).

Runs on the Raspberry Pi all the time (systemd service, see
device/pollinator-device.service). It:

- sends every button press to the back end: POST /presses with all current
  sensor values. The timestamp is taken at the moment of the press.
- sends timed readings: POST /readings. Each sensor has its own interval
  (READ_INTERVAL_*_SECONDS in .env). A reading only contains the sensors
  that are due at that moment.
- reads the SGP30 every 1 s in the background and ignores the first ~15 s
  (warm-up).
- ignores the PIR for the first 60 s after start (warm-up: a freshly powered
  PIR can trigger falsely while it settles).
- publishes the station status on MQTT pollinator/<station_id>/status
  (retained), with a last will that says online = false.

The device script does NOT decide anything about cooldown, daily cap or
plants: the back end does (backend/app/rules.py) and later sends commands
over MQTT (LED bar: #28, unlock: #41).

Message formats: docs/data-model.md. Pins: docs/wiring.md.

Start by hand (from the repo folder, venv on):  python device/station.py
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv
from smbus2 import SMBus

import sensors

# Settings (.env)

# device/station.py -> parents[1] = repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=False)


def env_int(name, default):
    """Whole number from .env, or the default if missing or empty."""
    value = os.getenv(name, "").strip()
    return max(1, int(value)) if value else default


STATION_ID = os.getenv("STATION_ID", "").strip() or "deusto-ria-01"
API_URL = (os.getenv("API_URL", "").strip() or "http://localhost:8000").rstrip("/")
BROKER_HOST = os.getenv("BROKER_HOST", "").strip() or "localhost"
BROKER_PORT = env_int("BROKER_PORT", 1883)

# Seconds between two timed readings, per sensor. The defaults are only used
# while the team has not set the values in .env yet.
INTERVALS = {
    "temp_humidity": env_int("READ_INTERVAL_TEMP_HUMIDITY_SECONDS", 300),
    "light": env_int("READ_INTERVAL_LIGHT_SECONDS", 60),
    "pressure": env_int("READ_INTERVAL_PRESSURE_SECONDS", 600),
    "soil_moisture": env_int("READ_INTERVAL_SOIL_MOISTURE_SECONDS", 900),
    "sgp30": env_int("READ_INTERVAL_SGP30_SECONDS", 60),
    "pir_count": env_int("READ_INTERVAL_PIR_COUNT_SECONDS", 600),
}

# Sensors sent with every button press (PIR is added separately)
PRESS_GROUPS = {"temp_humidity", "light", "pressure", "soil_moisture", "sgp30"}

# Fixed values (not in .env)
SGP30_READ_EVERY = 1.0   # seconds; the SGP30 needs this for its baseline
SGP30_WARMUP = 15        # seconds after start whose values are ignored
PIR_WARMUP = 60          # seconds after start in which PIR triggers are ignored
MOTION_WINDOW = 600      # seconds for motion_count_10min
HTTP_TIMEOUT = 5         # seconds to wait for the back end
RETRY_DELAY = 5          # seconds between tries while the back end is down
BUFFER_MAX = 1000        # messages kept while the back end is down
DEBOUNCE = 0.05          # seconds: button changes closer together are contact bounce

STATUS_TOPIC = f"pollinator/{STATION_ID}/status"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("station")


def utc_now_iso():
    """Current time as ISO 8601 UTC with Z, e.g. 2026-11-20T11:42:05Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rounded(value, digits=1):
    return None if value is None else round(value, digits)


# Warnings: once per sensor, again only after it recovered
_failing = set()


def sensor_failed(name, err):
    if name not in _failing:
        _failing.add(name)
        log.warning("%s not working (%s). Sending null for it.", name, err)


def sensor_ok(name):
    if name in _failing:
        _failing.discard(name)
        log.info("%s works again.", name)


# Hardware

class Hardware:
    """Opens all sensors once at start. A part that fails stays None."""

    def __init__(self):
        from grove.adc import ADC
        from grove.gpio import GPIO

        log.info("Opening sensors...")
        self.i2c_lock = threading.Lock()   # main loop and SGP30 thread share the bus
        self.bus = self._try_open("I2C bus 1", lambda: SMBus(sensors.I2C_BUS))
        self.btn = self._try_open("button (D5)", lambda: GPIO(sensors.BTN_PIN, GPIO.IN))
        self.btn_led = self._try_open("button LED (D5)",
                                      lambda: GPIO(sensors.BTN_LED_PIN, GPIO.OUT))
        self.pir = self._try_open("PIR (D16)", lambda: GPIO(sensors.PIR_PIN, GPIO.IN))
        self.adc = self._try_open("HAT ADC (0x08)", lambda: ADC(address=sensors.ADC_ADDR))
        self.bme = None
        if self.bus:
            self.bme = self._try_open("BME280 (0x76/0x77)", lambda: sensors.BME280(self.bus))

    @staticmethod
    def _try_open(name, make):
        try:
            part = make()
            log.info("  OK    %s", name)
            return part
        except Exception as err:   # missing, unplugged, wrong address...
            log.warning("  FAIL  %s: %s", name, err)
            return None

    def close(self):
        if self.btn_led:
            self.btn_led.write(0)
        if self.bus:
            self.bus.close()


# SGP30 (background thread)

class Sgp30Reader:
    """Reads the SGP30 every 1 s and keeps the latest value.

    If the SGP30 does not answer at start, the thread does not start and
    tvoc_ppb / eco2_ppm are sent as null.
    """

    def __init__(self, hw):
        self.hw = hw
        self._lock = threading.Lock()
        self._latest = (None, None)        # (tvoc_ppb, eco2_ppm)
        self.available = False             # True once the SGP30 thread runs

    def start(self):
        if self.hw.bus is None:
            log.warning("  FAIL  SGP30 (0x58): no I2C bus. tvoc_ppb / eco2_ppm are sent as null.")
            return
        try:
            with self.hw.i2c_lock:
                sensors.init_sgp30(self.hw.bus)
        except Exception as err:   # missing, unplugged...
            log.warning("  FAIL  SGP30 (0x58): %s. tvoc_ppb / eco2_ppm are sent as null.", err)
            return
        log.info("  OK    SGP30 (0x58), warm-up %d s", SGP30_WARMUP)
        self.available = True
        threading.Thread(target=self._run, args=(sensors.read_sgp30,), daemon=True).start()

    def latest(self):
        with self._lock:
            return self._latest

    def _run(self, read_fn):
        started = time.monotonic()
        next_read = started
        while True:
            try:
                with self.hw.i2c_lock:
                    tvoc, eco2 = read_fn(self.hw.bus)
                sensor_ok("SGP30")
                if time.monotonic() - started >= SGP30_WARMUP:
                    with self._lock:
                        self._latest = (int(tvoc), int(eco2))
            except Exception as err:
                sensor_failed("SGP30", err)
                with self._lock:
                    self._latest = (None, None)
            next_read += SGP30_READ_EVERY
            time.sleep(max(0.0, next_read - time.monotonic()))


# Reading sensor values

def read_values(hw, sgp, groups):
    """Read the sensors in `groups` and return their JSON fields.

    A sensor that is missing or fails gives None (= null in JSON, never 0).
    """
    values = {}

    if groups & {"temp_humidity", "pressure"}:
        temp = hpa = hum = None
        if hw.bme:
            try:
                with hw.i2c_lock:
                    temp, hpa, hum = hw.bme.read()
                sensor_ok("BME280")
            except Exception as err:
                sensor_failed("BME280", err)
        if "temp_humidity" in groups:
            values["temperature_c"] = rounded(temp)
            values["humidity_pct"] = rounded(hum)
        if "pressure" in groups:
            values["pressure_hpa"] = rounded(hpa)

    if "light" in groups:
        values["light_pct"] = read_adc_value(hw, sensors.read_light_pct, "light sensor")

    if "soil_moisture" in groups:
        values["soil_moisture_pct"] = read_adc_value(
            hw, sensors.read_soil_moisture_pct, "soil moisture sensor")

    if "sgp30" in groups:
        values["tvoc_ppb"], values["eco2_ppm"] = sgp.latest()

    return values


def read_adc_value(hw, read_fn, name):
    if hw.adc is None:
        return None
    try:
        with hw.i2c_lock:
            value = read_fn(hw.adc)
        sensor_ok(name)
        return rounded(value)
    except Exception as err:
        sensor_failed(name, err)
        return None


# Sending to the back end (REST, with offline buffer)

class ApiSender:
    """Sends messages to the back end in a background thread, in order.

    If the back end is not reachable, messages wait in memory and are sent
    later (with their original timestamp). The buffer is lost on restart.
    """

    def __init__(self):
        self.buffer = deque()
        self.cond = threading.Condition()
        self.session = requests.Session()
        self.offline = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, path, body):
        with self.cond:
            if len(self.buffer) >= BUFFER_MAX:
                self.buffer.popleft()
                log.warning("Buffer full: dropped the oldest waiting message.")
            self.buffer.append((path, body))
            self.cond.notify()

    def _run(self):
        while True:
            with self.cond:
                while not self.buffer:
                    self.cond.wait()
                item = self.buffer[0]
            try:
                done = self._post(*item)
            except Exception:
                log.exception("Unexpected error while sending %s, retrying.", item[0])
                done = False
            if not done:
                time.sleep(RETRY_DELAY)
                continue
            with self.cond:
                if self.buffer and self.buffer[0] is item:
                    self.buffer.popleft()

    def _post(self, path, body):
        """True = done (sent or rejected for good), False = try again later."""
        try:
            response = self.session.post(API_URL + path, json=body, timeout=HTTP_TIMEOUT)
        except requests.RequestException as err:
            if not self.offline:
                self.offline = True
                log.warning("Back end not reachable (%s). Keeping messages, "
                            "retrying every %d s.", err.__class__.__name__, RETRY_DELAY)
            return False

        if self.offline:
            self.offline = False
            log.info("Back end reachable again. Sending %d waiting message(s).",
                     len(self.buffer))

        if response.status_code == 503:           # database down: try again later
            log.warning("%s: back end busy (503), retrying.", path)
            return False

        if response.status_code >= 500:           # back-end bug: retrying won't help
            log.error("%s failed (%d), dropping it: %s", path, response.status_code, response.text)
            return True

        if response.status_code != 200:           # 400 / 422: would never work
            log.error("%s rejected (%d): %s", path, response.status_code, response.text)
            return True

        if path == "/presses":
            try:
                answer = response.json()
                log.info("Press %s -> %s, count %s/%s", body["timestamp"], answer["result"],
                         answer["count"], answer["presses_per_plant"])
            except (ValueError, KeyError) as err:
                log.warning("Press %s sent, but the answer looked wrong (%s)", body["timestamp"], err)
        else:
            fields = [k for k in body if k not in ("station_id", "timestamp")]
            log.info("Reading sent: %s", ", ".join(fields))
        return True


# Station status (MQTT)

class StatusPublisher:
    """Publishes the station status (retained) and sets the last will."""

    def __init__(self):
        self.locker = "locked"   # TODO(#41): set from the servo state
        self.stopping = False    # True while we disconnect on purpose
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"device-{STATION_ID}")
        # Sent by the broker if the script disappears without saying goodbye
        self.client.will_set(STATUS_TOPIC,
                             json.dumps({"station_id": STATION_ID, "online": False}),
                             qos=0, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def start(self):
        # connect_async + loop_start: the script keeps running if the broker is
        # down, and paho reconnects by itself.
        self.client.connect_async(BROKER_HOST, BROKER_PORT, keepalive=30)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.warning("MQTT connect failed: %s", reason_code)
            return
        log.info("MQTT connected to %s:%d", BROKER_HOST, BROKER_PORT)
        self.publish(online=True)          # also after every reconnect

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if not self.stopping:
            log.warning("MQTT disconnected (%s), reconnecting...", reason_code)

    def publish(self, online):
        message = {"station_id": STATION_ID, "timestamp": utc_now_iso(),
                   "online": online, "locker": self.locker}
        return self.client.publish(STATUS_TOPIC, json.dumps(message), qos=0, retain=True)

    def stop(self):
        self.stopping = True
        # A clean disconnect does not trigger the last will, so say "offline" ourselves.
        try:
            self.publish(online=False).wait_for_publish(timeout=2)
        except Exception:
            pass
        self.client.disconnect()
        self.client.loop_stop()


# Main loop

def main():
    log.info("Station %s, back end %s, broker %s:%d",
             STATION_ID, API_URL, BROKER_HOST, BROKER_PORT)
    log.info("Intervals (s): %s", INTERVALS)

    hw = Hardware()
    sender = ApiSender()
    sender.start()
    status = StatusPublisher()
    status.start()
    sgp = Sgp30Reader(hw)
    sgp.start()
    if not sgp.available:
        INTERVALS.pop("sgp30")          # SGP30 missing: no timed SGP30 readings
    # TODO(#41): move the latch to "locked" here (docs/architecture.md: device script start)

    # systemd stops the service with SIGTERM: exit cleanly (finally block below)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    now = time.monotonic()
    # PIR warm-up: triggers before this moment are ignored
    pir_ready_at = now + PIR_WARMUP
    pir_ready = False
    if hw.pir:
        log.info("PIR warm-up: motion is counted from %d s after start.", PIR_WARMUP)

    # First timed reading right away, except SGP30 (warm-up) and PIR (warm-up + a full interval)
    next_due = {group: now for group in INTERVALS}
    if "sgp30" in next_due:
        next_due["sgp30"] = now + max(SGP30_WARMUP, INTERVALS["sgp30"])
    next_due["pir_count"] = pir_ready_at + INTERVALS["pir_count"]

    motion_times = deque()          # PIR triggers of the last 10 min (for presses)
    motion_since_sent = 0           # PIR triggers since the last timed reading
    last_pir_sent = pir_ready_at
    last_btn = hw.btn.read() if hw.btn else 1 - sensors.PRESSED
    last_btn_change = 0.0           # time of the last accepted button change (debounce)
    last_pir = 0

    log.info("Running. Ctrl+C to stop.")
    try:
        while True:
            now = time.monotonic()

            # Button: one press -> one POST /presses
            # Debounce: a change within DEBOUNCE of the last one is contact
            # bounce and is ignored, when pressing AND when releasing.
            if hw.btn:
                state = hw.btn.read()
                if state != last_btn and now - last_btn_change >= DEBOUNCE:
                    last_btn_change = now
                    last_btn = state
                    if state == sensors.PRESSED:
                        timestamp = utc_now_iso()      # moment of the press
                        if hw.btn_led:
                            hw.btn_led.write(1)
                        body = {"station_id": STATION_ID, "timestamp": timestamp}
                        body.update(read_values(hw, sgp, PRESS_GROUPS))
                        # null during the PIR warm-up: no reliable count yet
                        body["motion_count_10min"] = (
                            len(motion_times) if (hw.pir and pir_ready) else None)
                        sender.send("/presses", body)
                        log.info("Button pressed at %s", timestamp)
                    elif hw.btn_led:
                        hw.btn_led.write(0)

            # PIR: count rising edges (only after the warm-up)
            if hw.pir:
                if not pir_ready and now >= pir_ready_at:
                    pir_ready = True
                    log.info("PIR warm-up done: counting motion now.")
                state = hw.pir.read()
                if state == 1 and last_pir == 0 and pir_ready:
                    motion_times.append(now)
                    motion_since_sent += 1
                last_pir = state
            while motion_times and now - motion_times[0] > MOTION_WINDOW:
                motion_times.popleft()

            # Timed readings: one POST /readings with all sensors due now
            due = {group for group, t in next_due.items() if now >= t}
            if due:
                for group in due:
                    next_due[group] += INTERVALS[group]
                    if next_due[group] <= now:         # fell behind: don't catch up
                        next_due[group] = now + INTERVALS[group]

                body = {"station_id": STATION_ID, "timestamp": utc_now_iso()}
                body.update(read_values(hw, sgp, due - {"pir_count"}))
                if "pir_count" in due and hw.pir:
                    body["motion_count"] = motion_since_sent
                    body["interval_s"] = round(now - last_pir_sent)
                    motion_since_sent = 0
                    last_pir_sent = now
                if len(body) > 2:                      # more than station_id + timestamp
                    sender.send("/readings", body)

            time.sleep(0.01)
    except KeyboardInterrupt:
        log.info("Stopping (Ctrl+C)...")
    finally:
        status.stop()
        hw.close()
        waiting = len(sender.buffer)
        if waiting:
            log.warning("%d message(s) were not sent yet and are lost.", waiting)
        log.info("Stopped.")


if __name__ == "__main__":
    main()