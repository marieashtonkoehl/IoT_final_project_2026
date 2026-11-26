"""Tests for the endpoints.

Settings in these tests (see conftest.py):
cooldown 10 s, daily cap 5, presses per plant 3.

Run from the backend/ folder:  pytest
"""

from dataclasses import replace

import pytest

from app import main, storage
from conftest import make_press, stored, utc


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_first_press_is_accepted(client):
    response = client.post("/presses", json=make_press("2026-11-20T11:42:05Z"))
    assert response.status_code == 200
    assert response.json() == {"result": "accepted", "count": 1, "presses_per_plant": 3}


def test_press_inside_cooldown(client):
    client.post("/presses", json=make_press("2026-11-20T11:42:00Z"))

    # 5 s later: inside the 10 s cooldown -> does not count
    response = client.post("/presses", json=make_press("2026-11-20T11:42:05Z"))
    assert response.json() == {"result": "cooldown", "count": 1, "presses_per_plant": 3}

    # 10 s after the first (accepted) press: cooldown is over
    response = client.post("/presses", json=make_press("2026-11-20T11:42:10Z"))
    assert response.json()["result"] == "accepted"
    assert response.json()["count"] == 2


def test_daily_cap(client):
    # 5 accepted presses, 1 minute apart (cap = 5)
    for minute in range(5):
        response = client.post("/presses", json=make_press(f"2026-11-20T10:0{minute}:00Z"))
        assert response.json()["result"] == "accepted"

    # 6th press the same day -> daily cap
    response = client.post("/presses", json=make_press("2026-11-20T12:00:00Z"))
    assert response.json()["result"] == "daily_cap"

    # 23:30Z on 20 Nov is 00:30 on 21 Nov in Madrid (UTC+1): a new day
    response = client.post("/presses", json=make_press("2026-11-20T23:30:00Z"))
    assert response.json()["result"] == "accepted"


def test_count_resets_after_presses_per_plant(client):
    # 3 presses per plant: the answers show 1, 2, 3 ...
    counts = []
    for second in ["00", "20", "40"]:
        response = client.post("/presses", json=make_press(f"2026-11-20T11:00:{second}Z"))
        counts.append(response.json()["count"])
    assert counts == [1, 2, 3]

    # ... and the next accepted press starts a new cycle at 1
    response = client.post("/presses", json=make_press("2026-11-20T11:01:00Z"))
    assert response.json() == {"result": "accepted", "count": 1, "presses_per_plant": 3}


def test_reading_with_nulls_and_missing_fields(client):
    body = {
        "station_id": "deusto-ria-01",
        "timestamp": "2026-11-20T11:45:00Z",
        "temperature_c": None,  # failed sensor
        "light_pct": 69.8,
        # the other sensors were not read this time: left out
    }
    response = client.post("/readings", json=body)
    assert response.status_code == 200
    assert response.json() == {"status": "received"}


def test_reading_with_wrong_type_is_rejected(client):
    body = {
        "station_id": "deusto-ria-01",
        "timestamp": "2026-11-20T11:45:00Z",
        "temperature_c": "warm",
    }
    response = client.post("/readings", json=body)
    assert response.status_code == 422  # Pydantic validation error


def test_unknown_station_is_rejected(client):
    body = make_press("2026-11-20T11:42:05Z")
    body["station_id"] = "other-01"
    response = client.post("/presses", json=body)
    assert response.status_code == 400


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Pollinator Station" in response.text


# What is stored (InfluxDB is replaced by the MemoryStore, see conftest.py)


def test_every_press_is_stored_with_its_result(client, store):
    client.post("/presses", json=make_press("2026-11-20T11:42:00Z"))  # accepted
    client.post("/presses", json=make_press("2026-11-20T11:42:05Z"))  # cooldown

    presses = stored(store, "presses")
    assert [p["tags"]["result"] for p in presses] == ["accepted", "cooldown"]
    assert all(p["tags"]["station_id"] == "deusto-ria-01" for p in presses)
    # The rejected press keeps the current progress (1), it does not add to it.
    assert [p["fields"]["progress_count"] for p in presses] == [1, 1]
    assert all(p["fields"]["count"] == 1 for p in presses)
    # Point time = the timestamp from the message.
    assert presses[1]["time"] == utc("2026-11-20T11:42:05Z")


def test_daily_cap_press_is_stored(client, store):
    for minute in range(5):
        client.post("/presses", json=make_press(f"2026-11-20T10:0{minute}:00Z"))
    client.post("/presses", json=make_press("2026-11-20T12:00:00Z"))

    assert stored(store, "presses")[-1]["tags"]["result"] == "daily_cap"


def test_press_with_null_sensor_is_stored_without_it(client, store):
    body = make_press("2026-11-20T11:42:05Z")
    body["temperature_c"] = None  # failed sensor
    response = client.post("/presses", json=body)
    assert response.json()["result"] == "accepted"

    fields = stored(store, "presses")[0]["fields"]
    assert "temperature_c" not in fields
    assert fields["humidity_pct"] == 62.0


def test_reading_is_split_into_environment_and_footfall(client, store):
    body = {
        "station_id": "deusto-ria-01",
        "timestamp": "2026-11-20T11:45:00Z",
        "temperature_c": None,  # failed sensor: left out
        "humidity_pct": 61,  # sent as a whole number: must be stored as a float
        "tvoc_ppb": 115,
        "motion_count": 9,
        "interval_s": 600,
    }
    client.post("/readings", json=body)

    environment = stored(store, "environment")
    footfall = stored(store, "footfall")
    assert len(environment) == 1 and len(footfall) == 1
    assert environment[0]["fields"] == {"humidity_pct": 61.0, "tvoc_ppb": 115}
    assert isinstance(environment[0]["fields"]["humidity_pct"], float)
    assert footfall[0]["fields"] == {"motion_count": 9, "interval_s": 600}
    assert footfall[0]["tags"] == {"station_id": "deusto-ria-01"}


def test_reading_without_pir_count_writes_no_footfall(client, store):
    body = {"station_id": "deusto-ria-01", "timestamp": "2026-11-20T11:45:00Z", "light_pct": 69.8}
    client.post("/readings", json=body)
    assert len(stored(store, "environment")) == 1
    assert stored(store, "footfall") == []


def test_reading_with_only_pir_count_writes_no_environment(client, store):
    body = {"station_id": "deusto-ria-01", "timestamp": "2026-11-20T11:45:00Z", "motion_count": 3}
    client.post("/readings", json=body)
    assert stored(store, "environment") == []
    assert stored(store, "footfall")[0]["fields"] == {"motion_count": 3}



# Progress after a restart


def restart_back_end(store):
    """Like a restart: same database, but the progress count in memory is gone."""
    storage.use_store(store)


def test_progress_is_restored_after_restart(client, store):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    client.post("/presses", json=make_press("2026-11-20T11:00:20Z"))
    restart_back_end(store)

    response = client.post("/presses", json=make_press("2026-11-20T11:00:40Z"))
    assert response.json() == {"result": "accepted", "count": 3, "presses_per_plant": 3}


def test_progress_starts_at_zero_after_restart_right_after_a_plant(client, store):
    # 3 of 3: plant earned, stored with progress_count=3
    for second in ["00", "20", "40"]:
        client.post("/presses", json=make_press(f"2026-11-20T11:00:{second}Z"))
    assert stored(store, "presses")[-1]["fields"]["progress_count"] == 3
    restart_back_end(store)

    response = client.post("/presses", json=make_press("2026-11-20T11:01:00Z"))
    assert response.json()["count"] == 1


def test_cooldown_still_works_after_restart(client, store):
    client.post("/presses", json=make_press("2026-11-20T11:42:00Z"))
    restart_back_end(store)

    response = client.post("/presses", json=make_press("2026-11-20T11:42:05Z"))
    assert response.json()["result"] == "cooldown"



# Database down -> 503


@pytest.fixture
def database_down():
    """A real InfluxStore pointing at a port where nothing listens."""
    storage.use_store(
        storage.InfluxStore(
            url="http://127.0.0.1:9", token="test", org="test", bucket="test", timeout_ms=1000
        )
    )


def test_press_answers_503_when_database_is_down(client, database_down):
    response = client.post("/presses", json=make_press("2026-11-20T11:42:05Z"))
    assert response.status_code == 503
    assert "Database not available" in response.json()["detail"]


def test_reading_answers_503_when_database_is_down(client, database_down):
    body = {"station_id": "deusto-ria-01", "timestamp": "2026-11-20T11:45:00Z", "light_pct": 69.8}
    response = client.post("/readings", json=body)
    assert response.status_code == 503


def test_status_answers_503_when_database_is_down(client, database_down):
    assert client.get("/status").status_code == 503



# Timestamps in the future (TEST_NOW is replaced by the `clock` fixture)


def test_press_6_minutes_in_the_future_is_rejected(client, store, clock):
    clock["now"] = utc("2026-11-20T12:00:00Z")
    response = client.post("/presses", json=make_press("2026-11-20T12:06:00Z"))
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "timestamp 2026-11-20T12:06:00Z is 6m0s ahead of server time (max 300 s)"
    )
    assert store.records == []  # nothing stored


def test_press_4_minutes_in_the_future_is_accepted(client, clock):
    clock["now"] = utc("2026-11-20T12:00:00Z")
    response = client.post("/presses", json=make_press("2026-11-20T12:04:00Z"))
    assert response.status_code == 200
    assert response.json()["result"] == "accepted"


def test_press_2_hours_in_the_past_is_accepted(client, clock):
    # e.g. a press the device script kept while the back end was down
    clock["now"] = utc("2026-11-20T12:00:00Z")
    response = client.post("/presses", json=make_press("2026-11-20T10:00:00Z"))
    assert response.status_code == 200
    assert response.json()["result"] == "accepted"


def test_reading_in_the_future_is_rejected(client, store, clock):
    clock["now"] = utc("2026-11-20T12:00:00Z")
    body = {"station_id": "deusto-ria-01", "timestamp": "2026-11-20T15:12:00Z", "light_pct": 69.8}
    response = client.post("/readings", json=body)
    assert response.status_code == 422
    assert "3h12m ahead" in response.json()["detail"]
    assert store.records == []


def test_rules_use_message_time_not_arrival_time(client, monkeypatch):
    # Like buffered presses sent after an outage: they arrive at the same
    # moment, but their timestamps are 10 minutes apart (cooldown 300 s).
    monkeypatch.setattr(main, "settings", replace(main.settings, press_cooldown_seconds=300))

    first = client.post("/presses", json=make_press("2026-11-20T10:00:00Z"))
    second = client.post("/presses", json=make_press("2026-11-20T10:10:00Z"))
    assert first.json()["result"] == "accepted"
    assert second.json()["result"] == "accepted"
    assert second.json()["count"] == 2



# GET /status


def test_status_with_no_presses(client):
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "presses_per_plant": 3,
        "last_press": None,
        # no MQTT status received yet (see test_mqtt.py)
        "online": None,
        "locker": None,
        "status_time": None,
    }


def test_status_after_presses(client):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))  # accepted
    client.post("/presses", json=make_press("2026-11-20T11:00:20Z"))  # accepted
    client.post("/presses", json=make_press("2026-11-20T11:00:25Z"))  # cooldown

    assert client.get("/status").json() == {
        "count": 2,
        "presses_per_plant": 3,
        "last_press": "2026-11-20T11:00:20Z",  # newest ACCEPTED press
        "online": None,
        "locker": None,
        "status_time": None,
    }


def test_status_after_restart(client, store):
    client.post("/presses", json=make_press("2026-11-20T11:00:00Z"))
    client.post("/presses", json=make_press("2026-11-20T11:00:20Z"))
    restart_back_end(store)
    assert client.get("/status").json()["count"] == 2


def test_status_is_zero_after_a_plant_also_after_restart(client, store):
    for second in ["00", "20", "40"]:
        client.post("/presses", json=make_press(f"2026-11-20T11:00:{second}Z"))
    assert client.get("/status").json()["count"] == 0

    restart_back_end(store)
    assert client.get("/status").json()["count"] == 0
