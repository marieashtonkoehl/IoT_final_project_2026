"""Tests for MQTT (issue #34): commands, station status, Pi health.

No broker needed: the `broker` fixture (conftest.py) replaces the paho
client with a FakeBroker that records what would be published. Incoming
messages are fed straight into mqtt.handle_message(), as paho would.

Settings in these tests (see conftest.py):
cooldown 10 s, daily cap 5, presses per plant 3.

Run from the backend/ folder:  pytest -v tests/test_mqtt.py
"""

import json
import logging
from dataclasses import replace

import pytest

from app import mqtt, storage
from conftest import make_press, stored

STATUS_TOPIC = "pollinator/deusto-ria-01/status"
PI_HEALTH_TOPIC = "pollinator/deusto-ria-01/pi_health"

STATUS = {
    "station_id": "deusto-ria-01",
    "timestamp": "2026-11-20T11:58:13Z",
    "online": True,
    "locker": "open",
}
PI_HEALTH = {
    "station_id": "deusto-ria-01",
    "timestamp": "2026-11-20T12:00:00Z",
    "cpu_temp_c": 52.3,
    "cpu_load_1m": 0.41,
    "disk_used_pct": 23.7,
}


def send(topic: str, message) -> None:
    """Deliver one MQTT message to the back end, like paho would (payload = bytes)."""
    payload = message if isinstance(message, bytes) else json.dumps(message).encode()
    mqtt.handle_message(topic, payload)



# Commands after a press


def test_accepted_press_sends_led_level(client, broker):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    client.post("/presses", json=make_press("2026-11-20T11:00:20Z"))

    commands = broker.commands()
    assert [c[0] for c in commands] == ["led", "led"]
    assert commands[0][1]["level"] == 1
    assert commands[1][1]["level"] == 2
    assert commands[1][1]["max"] == 3


def test_led_command_format(client, broker):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))

    topic, payload, qos, retain = broker.published[0]
    assert topic == "pollinator/deusto-ria-01/cmd/led"
    assert qos == 1
    assert retain is False
    assert set(payload) == {"command_id", "timestamp", "level", "max"}
    assert payload["command_id"].startswith("c-")
    assert payload["timestamp"] == "2026-12-01T12:00:00Z"  # server time (TEST_NOW)


def test_plant_earned_sends_unlock_then_led_zero(client, broker):
    for second in ["00", "20", "40"]:
        client.post("/presses", json=make_press(f"2026-11-20T11:00:{second}Z"))

    names = [c[0] for c in broker.commands()]
    # led 1, led 2, led 3 (the full bar), then unlock, then led 0 (new cycle)
    assert names == ["led", "led", "led", "unlock", "led"]
    topic, unlock, qos, retain = broker.published[3]
    assert topic == "pollinator/deusto-ria-01/cmd/unlock"
    assert set(unlock) == {"command_id", "timestamp", "trigger"}
    assert unlock["trigger"] == "target"
    assert (qos, retain) == (1, False)
    assert broker.commands()[-1][1]["level"] == 0


def test_rejected_presses_send_nothing(client, broker):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))  # accepted
    broker.published.clear()

    response = client.post("/presses", json=make_press("2026-11-20T11:00:05Z"))
    assert response.json()["result"] == "cooldown"
    assert broker.published == []


def test_daily_cap_press_sends_nothing(client, broker, monkeypatch):
    # Cap 1 so the 2nd press (after the cooldown) hits the daily cap.
    from app import main

    monkeypatch.setattr(main, "settings", replace(main.settings, daily_press_cap=1))
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    broker.published.clear()

    response = client.post("/presses", json=make_press("2026-11-20T11:05:00Z"))
    assert response.json()["result"] == "daily_cap"
    assert broker.published == []


def test_every_command_id_is_different(client, broker):
    for second in ["00", "20", "40"]:
        client.post("/presses", json=make_press(f"2026-11-20T11:00:{second}Z"))
    ids = [payload["command_id"] for _, payload in broker.commands()]
    assert len(ids) == len(set(ids)) == 5


def test_command_id_format():
    command_id = mqtt.new_command_id()
    assert command_id.startswith("c-")
    assert len(command_id) == 2 + 32  # "c-" + 32 hex characters (UUID4)
    int(command_id[2:], 16)  # only hex digits



# Broker down when a command should be sent


def test_press_still_works_when_broker_is_down(client, broker, store, caplog):
    broker.connected = False

    response = client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))

    assert response.status_code == 200  # the press itself worked
    assert response.json() == {"result": "accepted", "count": 1, "presses_per_plant": 3}
    assert len(stored(store, "presses")) == 1
    assert broker.published == []  # skipped, not queued
    assert "cmd/led not sent: broker not connected" in caplog.text


def test_plant_earned_while_broker_is_down_logs_an_error(client, broker, caplog):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    client.post("/presses", json=make_press("2026-11-20T11:00:20Z"))
    broker.connected = False

    with caplog.at_level(logging.WARNING):
        response = client.post("/presses", json=make_press("2026-11-20T11:00:40Z"))

    assert response.status_code == 200
    assert response.json()["count"] == 3
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "Plant earned but unlock not sent: broker not connected" in errors[0].getMessage()
    # The count still starts again at 0 (manual unlock will cover the lost plant, #60).
    assert client.get("/status").json()["count"] == 0


def test_no_client_at_all_is_like_broker_down(client, monkeypatch):
    # e.g. mqtt.start() failed because of a bad BROKER_HOST
    monkeypatch.setattr(mqtt, "_client", None)
    response = client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    assert response.status_code == 200



# Station status (incoming)


def test_status_is_shown_in_get_status(client):
    send(STATUS_TOPIC, STATUS)

    body = client.get("/status").json()
    assert body["online"] is True
    assert body["locker"] == "open"
    assert body["status_time"] == "2026-11-20T11:58:13Z"


def test_status_message_that_arrived_last_wins(client):
    send(STATUS_TOPIC, STATUS)
    # Last will: older timestamp (fixed when the device connected), arrives later.
    send(STATUS_TOPIC, {**STATUS, "timestamp": "2026-11-20T08:00:00Z", "online": False})

    body = client.get("/status").json()
    assert body["online"] is False
    assert body["status_time"] == "2026-11-20T08:00:00Z"


def test_online_true_sends_led_level_again(client, broker):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    client.post("/presses", json=make_press("2026-11-20T11:00:20Z"))
    broker.published.clear()

    send(STATUS_TOPIC, {**STATUS, "online": True, "locker": "locked"})

    assert broker.commands() == [("led", broker.published[0][1])]
    assert broker.published[0][1]["level"] == 2
    assert broker.published[0][1]["max"] == 3


def test_online_false_sends_nothing(broker):
    send(STATUS_TOPIC, {**STATUS, "online": False})
    assert broker.published == []


def test_led_resend_when_database_is_down_is_skipped(broker, caplog):
    storage.use_store(
        storage.InfluxStore(
            url="http://127.0.0.1:9", token="test", org="test", bucket="test", timeout_ms=1000
        )
    )
    send(STATUS_TOPIC, STATUS)

    assert broker.published == []
    assert "LED level not sent again" in caplog.text
    assert mqtt.get_station_status()["online"] is True  # status still kept



# Pi health (incoming)


def test_pi_health_is_stored_in_pi_status(store):
    send(PI_HEALTH_TOPIC, PI_HEALTH)

    [record] = stored(store, "pi_status")
    assert record["tags"] == {"station_id": "deusto-ria-01"}
    assert record["fields"] == {"cpu_temp_c": 52.3, "cpu_load_1m": 0.41, "disk_used_pct": 23.7}
    assert record["time"].isoformat() == "2026-11-20T12:00:00+00:00"


def test_pi_health_whole_numbers_are_stored_as_floats(store):
    # e.g. "cpu_temp_c": 52 from the script must not become an int field
    send(PI_HEALTH_TOPIC, {**PI_HEALTH, "cpu_temp_c": 52, "cpu_load_1m": 1, "disk_used_pct": 24})

    fields = stored(store, "pi_status")[0]["fields"]
    assert all(type(value) is float for value in fields.values())


def test_pi_health_when_database_is_down_is_dropped(caplog):
    storage.use_store(
        storage.InfluxStore(
            url="http://127.0.0.1:9", token="test", org="test", bucket="test", timeout_ms=1000
        )
    )
    send(PI_HEALTH_TOPIC, PI_HEALTH)  # must not raise
    assert "Pi health message dropped" in caplog.text



# Bad messages: logged as a warning, ignored, never raise


BAD_MESSAGES = [
    pytest.param(STATUS_TOPIC, b"not json {", id="status-bad-json"),
    pytest.param(STATUS_TOPIC, b"\xff\xfe", id="status-not-utf8"),
    pytest.param(STATUS_TOPIC, {**STATUS, "locker": "half-open"}, id="status-bad-locker"),
    pytest.param(STATUS_TOPIC, {k: v for k, v in STATUS.items() if k != "online"},
                 id="status-missing-field"),
    pytest.param(STATUS_TOPIC, {**STATUS, "battery": 3}, id="status-extra-field"),
    pytest.param(STATUS_TOPIC, {**STATUS, "station_id": "other-01"}, id="status-other-station"),
    pytest.param(STATUS_TOPIC, {**STATUS, "timestamp": "2026-12-01T12:06:00Z"},
                 id="status-6-min-in-future"),
    pytest.param(STATUS_TOPIC, [1, 2, 3], id="status-json-list"),
    pytest.param(PI_HEALTH_TOPIC, b"", id="health-empty"),
    pytest.param(PI_HEALTH_TOPIC, {**PI_HEALTH, "cpu_temp_c": "hot"}, id="health-wrong-type"),
    pytest.param(PI_HEALTH_TOPIC, {**PI_HEALTH, "cpu_temp_c": None}, id="health-null"),
    pytest.param(PI_HEALTH_TOPIC, {**PI_HEALTH, "station_id": "other-01"},
                 id="health-other-station"),
    pytest.param(PI_HEALTH_TOPIC, {**PI_HEALTH, "timestamp": "2026-12-01T12:06:00Z"},
                 id="health-6-min-in-future"),
]


@pytest.mark.parametrize("topic, message", BAD_MESSAGES)
def test_bad_message_is_logged_and_ignored(topic, message, store, broker, caplog):
    send(topic, message)  # must not raise

    assert store.records == []
    assert broker.published == []
    assert mqtt.get_station_status() == {"online": None, "locker": None, "timestamp": None}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ignored" in warnings[0].getMessage()


def test_timestamp_4_minutes_in_future_is_accepted(clock):
    send(STATUS_TOPIC, {**STATUS, "timestamp": "2026-12-01T12:04:00Z"})
    assert mqtt.get_station_status()["online"] is True


def test_bug_in_handler_does_not_escape(monkeypatch, caplog):
    # Even an unexpected error (a bug) must not reach paho's thread.
    def broken(payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(mqtt, "_handle_status", broken)
    send(STATUS_TOPIC, STATUS)  # must not raise
    assert "error while handling a message" in caplog.text


def test_unexpected_topic_is_ignored(store, caplog):
    send("pollinator/deusto-ria-01/something", {"a": 1})
    assert store.records == []
    assert "unexpected topic" in caplog.text



# Connecting


class FakeReasonCode:
    def __init__(self, failure: bool) -> None:
        self.is_failure = failure


class SubscribeRecorder:
    def __init__(self) -> None:
        self.subscriptions = []

    def subscribe(self, topics):
        self.subscriptions.append(topics)


def test_subscribes_again_after_every_reconnect():
    client = SubscribeRecorder()
    mqtt.on_connect(client, None, None, FakeReasonCode(False), None)
    mqtt.on_connect(client, None, None, FakeReasonCode(False), None)  # reconnect

    expected = [(STATUS_TOPIC, 0), (PI_HEALTH_TOPIC, 0)]
    assert client.subscriptions == [expected, expected]


def test_refused_connection_does_not_subscribe(caplog):
    client = SubscribeRecorder()
    mqtt.on_connect(client, None, None, FakeReasonCode(True), None)
    assert client.subscriptions == []
    assert "refused" in caplog.text


def test_start_and_stop_with_broker_down(monkeypatch):
    # Port 9: nothing listens there, like a broker that is not running.
    monkeypatch.setattr(mqtt, "settings", replace(mqtt.settings, broker_host="127.0.0.1",
                                                  broker_port=9))
    mqtt.start()  # must not raise or block
    try:
        assert mqtt._client is not None
        assert mqtt._client.is_connected() is False
        assert mqtt.send_led(1, 3) is False  # skipped, no crash
    finally:
        mqtt.stop()  # must return (stops paho's retry thread)
    assert mqtt._client is None


def test_app_starts_with_broker_down(monkeypatch):
    # The whole app with its lifespan (mqtt.start / mqtt.stop).
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(mqtt, "settings", replace(mqtt.settings, broker_host="127.0.0.1",
                                                  broker_port=9))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
