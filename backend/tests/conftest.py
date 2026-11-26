"""Shared setup for all tests (pytest loads this file automatically).

We set small, fixed settings BEFORE the app is imported, so the tests
don't depend on what is in your own .env (config.py never overrides
values that are already in the environment).

The tests do NOT need InfluxDB: every test gets an empty MemoryStore
(see storage.py). Only test_influx_integration.py uses a real InfluxDB,
and it skips itself when none is reachable.

The tests do NOT need an MQTT broker either: every test gets a FakeBroker
that records the commands the back end sends (see `broker` below). Only
test_mqtt_integration.py uses a real Mosquitto, and it skips itself too.
"""

import os

os.environ["STATION_ID"] = "deusto-ria-01"
os.environ["PRESS_COOLDOWN_SECONDS"] = "10"
os.environ["DAILY_PRESS_CAP"] = "5"
os.environ["PRESSES_PER_PLANT"] = "3"
os.environ["MAX_FUTURE_SKEW_SECONDS"] = "300"

import json  # noqa: E402  (imports after the settings on purpose)
from datetime import datetime, timezone  # noqa: E402

import paho.mqtt.client as paho  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main, mqtt, storage  # noqa: E402
from app.main import app  # noqa: E402

# The "server time" in the tests. Later than every timestamp the tests use
# (2026-11-20 ...), so the future-timestamp check never gets in the way,
# however late you run the tests. Tests that need another time change it.
TEST_NOW = "2026-12-01T12:00:00Z"


def utc(text: str) -> datetime:
    """Turn '2026-11-20T11:42:05Z' into an aware UTC datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def store():
    """Every test starts with an empty in-memory store (autouse = runs for every test).

    Tests can look at `store.records` to see what would be written to InfluxDB.
    """
    memory = storage.MemoryStore()
    storage.use_store(memory)
    yield memory
    storage.use_store(None)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Replace the server clock with a fixed time (TEST_NOW).

    A test can move it:  clock["now"] = utc("2026-11-20T12:00:00Z")
    """
    fake = {"now": utc(TEST_NOW)}
    monkeypatch.setattr(main, "now_utc", lambda: fake["now"])
    monkeypatch.setattr(mqtt, "now_utc", lambda: fake["now"])  # MQTT checks the same clock
    return fake


class FakeBroker:
    """Stands in for the paho client: records what would be published.

    `connected = False` makes it behave like a broker that is down.
    """

    class _Info:  # what paho's publish() returns (only .rc is used)
        rc = paho.MQTT_ERR_SUCCESS

    def __init__(self) -> None:
        self.connected = True
        self.published = []  # list of (topic, payload dict, qos, retain)

    def is_connected(self) -> bool:
        return self.connected

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload), qos, retain))
        return self._Info()

    def commands(self) -> list:
        """Short form for asserts: [("led", payload), ("unlock", payload), ...]."""
        return [(topic.rsplit("/", 1)[-1], payload) for topic, payload, _, _ in self.published]


@pytest.fixture(autouse=True)
def broker(monkeypatch):
    """Every test gets a connected FakeBroker and no station status yet."""
    fake = FakeBroker()
    monkeypatch.setattr(mqtt, "_client", fake)
    mqtt.forget_station_status()
    yield fake
    mqtt.forget_station_status()


@pytest.fixture
def client():
    """A fake HTTP client that calls the app directly, no server needed.

    Not used as `with TestClient(app)`, so the lifespan (mqtt.start) does
    not run: the tests never connect to a real broker.
    """
    return TestClient(app)


def make_press(timestamp: str) -> dict:
    """A valid press body with the given timestamp (sensor values from data-model.md)."""
    return {
        "station_id": "deusto-ria-01",
        "timestamp": timestamp,
        "temperature_c": 17.4,
        "humidity_pct": 62.0,
        "light_pct": 71.3,
        "pressure_hpa": 1016.8,
        "soil_moisture_pct": 38.5,
        "tvoc_ppb": 120,
        "eco2_ppm": 450,
        "motion_count_10min": 14,
    }


def stored(store, measurement: str) -> list:
    """The records of one measurement in the store, oldest first."""
    return sorted(
        (r for r in store.records if r["measurement"] == measurement),
        key=lambda r: r["time"],
    )
