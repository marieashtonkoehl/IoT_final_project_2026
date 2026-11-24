"""Integration test against a REAL InfluxDB (e.g. on the Pi).

Skipped automatically when InfluxDB is not reachable or DB_TOKEN is not set
in .env, so `pytest` still passes on a laptop without the database.

It never touches the real `pollinator` bucket: it creates a temporary bucket
(pollinator_test_<random>), uses it, and deletes it at the end, also when a
test fails. That needs the admin token (DB_TOKEN in .env).

Run only this file, from backend/:  pytest -v tests/test_influx_integration.py
"""

import secrets

import pytest
from influxdb_client import InfluxDBClient

from app import storage
from app.config import settings
from app.storage import flux_string, flux_time
from conftest import make_press, utc

# The day all test timestamps fall on, as a Flux range (OSS has no query
# parameters, so the values are written into the query text).
ONE_DAY = (
    f"|> range(start: {flux_time(utc('2026-11-20T00:00:00Z'))}, "
    f"stop: {flux_time(utc('2026-11-21T00:00:00Z'))})"
)


def _influx_reachable() -> bool:
    if not settings.db_token:
        return False
    try:
        with InfluxDBClient(url=settings.db_url, token=settings.db_token, timeout=2000) as client:
            return client.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _influx_reachable(), reason="InfluxDB not reachable (or DB_TOKEN not set in .env)"
)


@pytest.fixture
def influx_store():
    """A real InfluxStore on a temporary bucket. The bucket is deleted at the end."""
    client = InfluxDBClient(url=settings.db_url, token=settings.db_token, org=settings.db_org)
    bucket = client.buckets_api().create_bucket(
        bucket_name=f"pollinator_test_{secrets.token_hex(4)}", org=settings.db_org
    )
    store = storage.InfluxStore(
        url=settings.db_url, token=settings.db_token, org=settings.db_org, bucket=bucket.name
    )
    storage.use_store(store)
    try:
        yield store
    finally:
        # finally: runs even when the test fails, so no test buckets are left behind.
        store.close()
        client.buckets_api().delete_bucket(bucket)
        client.close()


def test_presses_and_restart_with_real_influxdb(client, influx_store):
    def press(time: str) -> dict:
        return client.post("/presses", json=make_press(time)).json()

    # Settings in the tests: cooldown 10 s, daily cap 5, 3 presses per plant.
    assert press("2026-11-20T11:00:00Z")["result"] == "accepted"
    assert press("2026-11-20T11:00:05Z")["result"] == "cooldown"  # stored too
    assert press("2026-11-20T11:00:20Z")["count"] == 2

    # Restart in the middle of a cycle: progress comes back from InfluxDB.
    storage.use_store(storage.InfluxStore(
        url=settings.db_url, token=settings.db_token, org=settings.db_org, bucket=influx_store.bucket
    ))
    assert client.get("/status").json() == {
        "count": 2,
        "presses_per_plant": 3,
        "last_press": "2026-11-20T11:00:20Z",
    }
    # Cooldown still applies after the restart (last accepted press read from InfluxDB).
    assert press("2026-11-20T11:00:25Z")["result"] == "cooldown"

    # 3 of 3: plant earned. Stored with progress_count=3 -> restored as 0.
    assert press("2026-11-20T11:00:40Z")["count"] == 3
    storage.use_store(influx_store)  # restart again
    assert client.get("/status").json()["count"] == 0

    assert storage.count_accepted_since("deusto-ria-01", utc("2026-11-20T00:00:00Z")) == 3
    rows = influx_store.query(
        f"from(bucket: {flux_string(influx_store.bucket)}) {ONE_DAY}"
        ' |> filter(fn: (r) => r._measurement == "presses" and r.result == "cooldown"'
        ' and r._field == "count")'
    )
    assert len(rows) == 2  # both rejected presses were stored


def test_reading_with_real_influxdb(client, influx_store):
    body = {
        "station_id": "deusto-ria-01",
        "timestamp": "2026-11-20T11:45:00Z",
        "humidity_pct": 61,  # int in the JSON, must arrive as a float
        "temperature_c": None,
        "motion_count": 9,
        "interval_s": 600,
    }
    assert client.post("/readings", json=body).status_code == 200

    rows = influx_store.query(f"from(bucket: {flux_string(influx_store.bucket)}) {ONE_DAY}")
    values = {(r.get_measurement(), r.get_field()): r.get_value() for r in rows}
    assert values == {
        ("environment", "humidity_pct"): 61.0,
        ("footfall", "motion_count"): 9,
        ("footfall", "interval_s"): 600,
    }
    assert isinstance(values[("environment", "humidity_pct")], float)
