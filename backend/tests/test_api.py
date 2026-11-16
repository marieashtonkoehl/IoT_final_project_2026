"""Tests for the endpoints.

Settings in these tests (see conftest.py):
cooldown 10 s, daily cap 5, presses per plant 3.

Run from the backend/ folder:  pytest
"""

from conftest import make_press


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
