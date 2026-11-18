"""Shared setup for all tests (pytest loads this file automatically).

We set small, fixed settings BEFORE the app is imported, so the tests
don't depend on what is in your own .env (config.py never overrides
values that are already in the environment).
"""

import os

os.environ["STATION_ID"] = "deusto-ria-01"
os.environ["PRESS_COOLDOWN_SECONDS"] = "10"
os.environ["DAILY_PRESS_CAP"] = "5"
os.environ["PRESSES_PER_PLANT"] = "3"

import pytest  # noqa: E402  (imports after the settings on purpose)
from fastapi.testclient import TestClient  # noqa: E402

from app import storage  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def empty_storage():
    """Start every test with no presses stored (autouse = runs for every test)."""
    storage.reset()
    yield
    storage.reset()


@pytest.fixture
def client():
    """A fake HTTP client that calls the app directly, no server needed."""
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
