"""Integration test against a REAL MQTT broker (e.g. Mosquitto on the Pi).

Skipped automatically when no broker is reachable at BROKER_HOST:BROKER_PORT
(.env), so `pytest` still passes on a laptop without the broker.

It never touches the real station's topics: it uses a random station_id
(test-<random>), so the retained status of the real device is not changed.

Run only this file, from backend/:  pytest -v tests/test_mqtt_integration.py
"""

import json
import secrets
import socket
import time
from dataclasses import replace
from datetime import datetime, timezone

import paho.mqtt.client as paho
import pytest

from app import mqtt
from app.config import settings
from conftest import stored


def _broker_reachable() -> bool:
    try:
        with socket.create_connection((settings.broker_host, settings.broker_port), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _broker_reachable(),
    reason=f"No MQTT broker at {settings.broker_host}:{settings.broker_port}",
)


def wait_until(check, timeout_s: float = 5.0) -> bool:
    """Wait until check() is true (messages take a moment to travel)."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.05)
    return check()


@pytest.fixture
def station(monkeypatch):
    """Start the REAL back end MQTT client for a random test station."""
    station_id = f"test-{secrets.token_hex(4)}"
    test_settings = replace(settings, station_id=station_id)
    monkeypatch.setattr(mqtt, "settings", test_settings)
    monkeypatch.setattr(mqtt, "_client", None)  # not the FakeBroker from conftest
    # Real clock here (conftest fixes it to TEST_NOW), because the messages
    # below carry the real current time.
    monkeypatch.setattr(mqtt, "now_utc", lambda: datetime.now(timezone.utc))
    mqtt.start()
    assert wait_until(lambda: mqtt._client.is_connected()), "back end did not connect"
    yield station_id
    mqtt.stop()


@pytest.fixture
def device(station):
    """A second client playing the device script: publishes and listens to commands."""
    received = []
    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=f"{station}-device")
    client.on_message = lambda c, u, m: received.append((m.topic, json.loads(m.payload)))
    client.connect(settings.broker_host, settings.broker_port)
    client.subscribe(f"pollinator/{station}/cmd/#", qos=1)
    client.loop_start()
    client.received = received
    time.sleep(0.3)  # let the subscription settle
    yield client
    client.loop_stop()
    client.disconnect()


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def test_status_arrives_and_led_is_sent_again(station, device):
    status = {"station_id": station, "timestamp": now_text(), "online": True, "locker": "locked"}
    device.publish(f"pollinator/{station}/status", json.dumps(status), qos=0)

    assert wait_until(lambda: mqtt.get_station_status()["online"] is True)
    assert mqtt.get_station_status()["locker"] == "locked"
    # online: true -> the back end sends the LED level (0, no presses) again
    assert wait_until(lambda: len(device.received) == 1)
    topic, payload = device.received[0]
    assert topic == f"pollinator/{station}/cmd/led"
    assert payload["level"] == 0


def test_pi_health_is_stored(station, device, store):
    health = {"station_id": station, "timestamp": now_text(),
              "cpu_temp_c": 52.3, "cpu_load_1m": 0.41, "disk_used_pct": 23.7}
    device.publish(f"pollinator/{station}/pi_health", json.dumps(health), qos=0)

    assert wait_until(lambda: len(stored(store, "pi_status")) == 1)


def test_unlock_command_reaches_the_device(station, device):
    assert mqtt.send_unlock("target") is True
    assert wait_until(lambda: len(device.received) == 1)
    topic, payload = device.received[0]
    assert topic == f"pollinator/{station}/cmd/unlock"
    assert payload["trigger"] == "target"
