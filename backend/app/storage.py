"""Backend keeps data in InfluxDB 2 (bucket `pollinator`).

Measurements, tags, fields and field types: docs/data-model.md.

main.py only calls the functions at the bottom of this file
(get_last_accepted_time, save_press, ...). Inside, they use a "store":

- InfluxStore: the real database. Used when the back end runs.
- MemoryStore: a list in memory. Used by the tests, so they run without
  InfluxDB. It answers the same questions in the same way.

Both stores get the same "records" (built by press_record / reading_records),
so the tests check exactly what is written to InfluxDB.

A record is a plain dict, the format the InfluxDB client understands:
    {"measurement": "presses",
     "tags": {"station_id": "deusto-ria-01", "result": "accepted"},
     "fields": {"count": 1, "progress_count": 7, "temperature_c": 17.4, ...},
     "time": datetime(2026, 11, 20, 11, 42, 5, tzinfo=timezone.utc)}
"""

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
from urllib3.exceptions import HTTPError

from app.config import settings
from app.models import PiHealthIn, PressIn, ReadingIn


class StorageUnavailable(Exception):
    """The database could not be reached, or refused the request.

    main.py turns this into a 503 answer instead of a crash (500).
    """



# Field types (from docs/data-model.md)

# InfluxDB fixes the type of a field the first time it is written. If the
# same field later arrives as another type (e.g. humidity 62 as an int after
# 61.5 as a float), the whole write is rejected. So we always cast.
FLOAT_FIELDS = {
    "temperature_c",
    "humidity_pct",
    "light_pct",
    "pressure_hpa",
    "soil_moisture_pct",
    "cpu_temp_c",
    "cpu_load_1m",
    "disk_used_pct",
}
INT_FIELDS = {
    "tvoc_ppb",
    "eco2_ppm",
    "motion_count_10min",
    "motion_count",
    "interval_s",
    "count",
    "progress_count",
}

# Sensor values that go to `environment` (from a timed reading).
ENVIRONMENT_FIELDS = [
    "temperature_c",
    "humidity_pct",
    "light_pct",
    "pressure_hpa",
    "soil_moisture_pct",
    "tvoc_ppb",
    "eco2_ppm",
]
FOOTFALL_FIELDS = ["motion_count", "interval_s"]

# Sensor values stored with every press (all environment ones + PIR count).
PRESS_SENSOR_FIELDS = ENVIRONMENT_FIELDS + ["motion_count_10min"]

# Pi health values (from MQTT) that go to `pi_status`.
PI_STATUS_FIELDS = ["cpu_temp_c", "cpu_load_1m", "disk_used_pct"]



# Building records (no database needed, easy to test)


def clean_fields(values: Dict[str, object]) -> Dict[str, object]:
    """Leave out null values and give every field its fixed type.

    InfluxDB can't store null, so a failed sensor (None) is simply missing
    from the point. The other fields are written as usual.
    """
    fields: Dict[str, object] = {}
    for name, value in values.items():
        if value is None:
            continue
        if name in FLOAT_FIELDS:
            fields[name] = float(value)  # 62 -> 62.0
        elif name in INT_FIELDS:
            fields[name] = int(value)
        else:
            # A field that is not in the tables above is a bug in this file.
            raise ValueError(f"No type known for field '{name}'")
    return fields


def press_record(press: PressIn, result: str, progress_count: int) -> dict:
    """The `presses` point for one press. Written for EVERY press,
    accepted or rejected (the `result` tag says which).

    progress_count = accepted presses in the cycle after this press. On the
    press that earns a plant this is presses_per_plant (e.g. 10).
    """
    values = {name: getattr(press, name) for name in PRESS_SENSOR_FIELDS}
    values["count"] = 1  # always 1, so InfluxDB can sum presses per hour/day
    values["progress_count"] = progress_count
    return {
        "measurement": "presses",
        "tags": {"station_id": press.station_id, "result": result},
        "fields": clean_fields(values),
        "time": press.timestamp,
    }


def reading_records(reading: ReadingIn) -> List[dict]:
    """The points for one timed reading: `environment` and/or `footfall`.

    A measurement is skipped when it would have no fields (e.g. a reading
    with only a PIR count gives no `environment` point). InfluxDB can't
    store a point without fields.
    """
    records = []
    for measurement, names in [
        ("environment", ENVIRONMENT_FIELDS),
        ("footfall", FOOTFALL_FIELDS),
    ]:
        fields = clean_fields({name: getattr(reading, name) for name in names})
        if measurement == "footfall" and "motion_count" not in fields:
            # interval_s alone means nothing without a count.
            continue
        if fields:
            records.append(
                {
                    "measurement": measurement,
                    "tags": {"station_id": reading.station_id},
                    "fields": fields,
                    "time": reading.timestamp,
                }
            )
    return records


def pi_status_record(health: PiHealthIn) -> dict:
    """The `pi_status` point for one Pi health message (MQTT, every 5 min)."""
    return {
        "measurement": "pi_status",
        "tags": {"station_id": health.station_id},
        "fields": clean_fields({name: getattr(health, name) for name in PI_STATUS_FIELDS}),
        "time": health.timestamp,
    }


def restore_progress(newest_progress_count: Optional[int], presses_per_plant: int) -> int:
    """Progress count to start with, from the newest stored press.

    The press that earns a plant is stored with progress_count =
    presses_per_plant (e.g. 10), and the cycle then starts again at 0.
    So a stored value >= presses_per_plant means "start at 0".
    """
    if newest_progress_count is None:  # no press stored yet
        return 0
    if newest_progress_count >= presses_per_plant:
        return 0
    return newest_progress_count



# Store 1: in memory (for the tests)


class MemoryStore:
    """Keeps the records in a list. Lost on restart, so only for the tests."""

    def __init__(self) -> None:
        self.records: List[dict] = []

    def write(self, records: List[dict]) -> None:
        self.records.extend(records)

    def _presses(self, station_id: str, result: Optional[str] = None) -> List[dict]:
        """Stored presses of one station (optionally only one result), oldest first."""
        presses = [
            r
            for r in self.records
            if r["measurement"] == "presses"
            and r["tags"]["station_id"] == station_id
            and (result is None or r["tags"]["result"] == result)
        ]
        return sorted(presses, key=lambda r: r["time"])

    def last_accepted_time(self, station_id: str) -> Optional[datetime]:
        accepted = self._presses(station_id, "accepted")
        return accepted[-1]["time"] if accepted else None

    def count_accepted_since(self, station_id: str, since_utc: datetime) -> int:
        return len([r for r in self._presses(station_id, "accepted") if r["time"] >= since_utc])

    def newest_progress_count(self, station_id: str) -> Optional[int]:
        presses = self._presses(station_id)
        return presses[-1]["fields"]["progress_count"] if presses else None



# Building Flux queries (plain text, no database needed, easy to test)

# InfluxDB OSS 2.x has no query parameters (`params.xxx` only works in
# InfluxDB Cloud). So values have to go INTO the query text. To keep a
# strange value (e.g. a station_id with a " in it) from changing the query
# itself ("injection"), every text value goes through flux_string(), and
# every time through flux_time().


def flux_string(value: str) -> str:
    """A Python string as a safe Flux string literal, with the quotes.

    Order matters: backslashes first (otherwise we would double the
    backslashes we add for the quotes), then double quotes. Flux also treats
    "${...}" inside a string as a placeholder, so "${" is escaped too.
        flux_string('a"b')  -> "a\"b"
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("${", "\\${")
    return f'"{escaped}"'


def flux_time(moment: datetime) -> str:
    """A datetime as a Flux time literal, e.g. 2026-11-19T23:00:00Z (no quotes).

    Built by our own code from a datetime object, never copied from input
    text, so only digits, "-", ":", "T" and "Z" can end up in the query.
    """
    if moment.tzinfo is None:
        raise ValueError("flux_time needs a datetime with a time zone (UTC)")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Flux's range() needs a start and stops at "now" by default. We use fixed,
# wide limits instead. The stop must be later than "now", because a message
# timestamp may be a little ahead of the Pi clock (up to MAX_FUTURE_SKEW_SECONDS).
RANGE_START = datetime(1970, 1, 1, tzinfo=timezone.utc)
RANGE_STOP = datetime(2100, 1, 1, tzinfo=timezone.utc)


# Careful with the `result` tag of `presses`: InfluxDB adds its own column
# called `result` (the name of the query result) to every answer. So a row
# has two columns named "result", the client warns "duplicated names", and
# record.values["result"] gives only one of them (not always ours).
# The queries below only FILTER on the tag, so this is no problem today.
# If you need the tag in Python: rename it in Flux first, e.g.
#   |> rename(columns: {result: "press_result"})
# or read it by position from record.row.
def _presses_filter(station_id: str, field: str, result: Optional[str] = None) -> str:
    """The filter for one field of `presses` of one station (optionally one result)."""
    condition = (
        f"r._measurement == {flux_string('presses')}"
        f" and r.station_id == {flux_string(station_id)}"
        f" and r._field == {flux_string(field)}"
    )
    if result is not None:
        condition += f" and r.result == {flux_string(result)}"
    return condition


def _newest_row_query(bucket: str, condition: str) -> str:
    """Query for the newest row that matches `condition`.

    last() gives the newest row of each series (one series per tag
    combination, e.g. result=accepted / result=cooldown). group() puts
    them into one table, and sort + last() picks the newest of those.
    """
    return f"""
from(bucket: {flux_string(bucket)})
  |> range(start: {flux_time(RANGE_START)}, stop: {flux_time(RANGE_STOP)})
  |> filter(fn: (r) => {condition})
  |> last()
  |> group()
  |> sort(columns: ["_time"])
  |> last()
"""


def last_accepted_query(bucket: str, station_id: str) -> str:
    """Query: newest accepted press of the station."""
    return _newest_row_query(bucket, _presses_filter(station_id, "count", "accepted"))


def count_accepted_since_query(bucket: str, station_id: str, since_utc: datetime) -> str:
    """Query: number of accepted presses of the station at or after `since_utc`."""
    return f"""
from(bucket: {flux_string(bucket)})
  |> range(start: {flux_time(since_utc)}, stop: {flux_time(RANGE_STOP)})
  |> filter(fn: (r) => {_presses_filter(station_id, "count", "accepted")})
  |> group()
  |> count()
"""


def newest_progress_query(bucket: str, station_id: str) -> str:
    """Query: progress_count of the newest press of the station.

    Newest press of ANY result: a rejected press also carries the
    current progress_count.
    """
    return _newest_row_query(bucket, _presses_filter(station_id, "progress_count"))



# Store 2: InfluxDB (main one)


class InfluxStore:
    """Writes to and reads from InfluxDB 2 with the official client."""

    def __init__(self, url: str, token: str, org: str, bucket: str, timeout_ms: int = 5000) -> None:
        self.url = url
        self.bucket = bucket
        # Creating the client does not connect yet. It connects on the first
        # write or query, so the back end can start before InfluxDB is up.
        self.client = InfluxDBClient(url=url, token=token, org=org, timeout=timeout_ms)
        # SYNCHRONOUS: write() waits for InfluxDB's answer, so a failed write
        # raises an error right away (and the press gets a 503, not a
        # silent "accepted" that was never saved).
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    def close(self) -> None:
        self.client.close()

    def _fail(self, error: Exception) -> StorageUnavailable:
        """Turn any client error into one StorageUnavailable with a short reason."""
        if isinstance(error, ApiException):
            reason = f"InfluxDB answered {error.status} {error.reason}"
            if error.status == 401:
                reason += " (check DB_TOKEN in .env)"
        else:
            reason = f"{type(error).__name__}"
        return StorageUnavailable(
            f"Database not available (InfluxDB at {self.url}): {reason}. "
            "Is Docker running (deploy/compose.yaml) and are DB_* set in .env?"
        )

    def write(self, records: List[dict]) -> None:
        if not records:
            return
        points = [Point.from_dict(r, write_precision=WritePrecision.S) for r in records]
        try:
            self.write_api.write(
                bucket=self.bucket, record=points, write_precision=WritePrecision.S
            )
        except (ApiException, InfluxDBError, HTTPError, OSError) as error:
            raise self._fail(error) from error

    def query(self, query: str) -> list:
        """Run a Flux query and return all rows (FluxRecords) in one list.

        Build `query` only with the functions above (flux_string, flux_time).
        """
        try:
            tables = self.query_api.query(query)
        except (ApiException, InfluxDBError, HTTPError, OSError) as error:
            raise self._fail(error) from error
        return [row for table in tables for row in table.records]

    def last_accepted_time(self, station_id: str) -> Optional[datetime]:
        rows = self.query(last_accepted_query(self.bucket, station_id))
        if not rows:
            return None
        return rows[-1].get_time().astimezone(timezone.utc)

    def count_accepted_since(self, station_id: str, since_utc: datetime) -> int:
        rows = self.query(count_accepted_since_query(self.bucket, station_id, since_utc))
        # No accepted press in that time = no rows at all.
        return int(rows[0].get_value()) if rows else 0

    def newest_progress_count(self, station_id: str) -> Optional[int]:
        rows = self.query(newest_progress_query(self.bucket, station_id))
        return int(rows[-1].get_value()) if rows else None



# The functions main.py uses

# The store in use. Created on first use (see _store()), or set by the tests.
_current_store = None

# Progress count per station, kept in memory while the back end runs.
# Missing = not restored from the database yet.
_progress: Dict[str, int] = {}

# Two threads use _progress: web requests (POST /presses, GET /status) and
# the MQTT thread (sends the LED level again when the device comes online).
# The lock makes sure only one of them reads or changes it at a time, so the
# count is never restored twice or read halfway through a change.
# RLock: the same thread may take it again (get inside a with-block is fine).
_progress_lock = threading.RLock()


def use_store(store) -> None:
    """Switch to another store (the tests use a fresh MemoryStore per test).

    Also forgets the progress counts, so they are restored from the new
    store. Like a restart of the back end.
    """
    global _current_store
    _current_store = store
    with _progress_lock:
        _progress.clear()


def _store():
    """The store in use. The first time: connect to InfluxDB with the .env values."""
    global _current_store
    if _current_store is None:
        _current_store = InfluxStore(
            url=settings.db_url,
            token=settings.db_token,
            org=settings.db_org,
            bucket=settings.db_bucket,
        )
    return _current_store


def close() -> None:
    """Close the database connection (when the back end stops)."""
    if isinstance(_current_store, InfluxStore):
        _current_store.close()


def get_last_accepted_time(station_id: str) -> Optional[datetime]:
    """Time of the last accepted press, or None if there is none yet."""
    return _store().last_accepted_time(station_id)


def count_accepted_since(station_id: str, since_utc: datetime) -> int:
    """How many presses were accepted at or after `since_utc`.

    main.py passes local midnight (converted to UTC), so this is
    "accepted presses today".
    """
    return _store().count_accepted_since(station_id, since_utc)


def get_progress_count(station_id: str, presses_per_plant: int) -> int:
    """Accepted presses since the last unlock.

    Restored from the newest stored press the first time it is needed (not at
    start-up): if the Pi starts the back end before InfluxDB is ready, the
    back end still starts, and the count is restored on the first request.
    """
    with _progress_lock:
        if station_id not in _progress:
            # If InfluxDB is down this raises, nothing is remembered, and the
            # next call tries again.
            newest = _store().newest_progress_count(station_id)
            _progress[station_id] = restore_progress(newest, presses_per_plant)
        return _progress[station_id]


def set_progress_count(station_id: str, count: int) -> None:
    """Remember a new progress count (e.g. +1, or 0 after an unlock).

    Only in memory: the database already has it as progress_count of the
    press that was just saved.
    """
    with _progress_lock:
        _progress[station_id] = count


def save_press(press: PressIn, result: str, progress_count: int) -> None:
    """Write one press (accepted or rejected) to `presses`."""
    _store().write([press_record(press, result, progress_count)])


def save_reading(reading: ReadingIn) -> None:
    """Write one timed reading to `environment` and/or `footfall`."""
    _store().write(reading_records(reading))


def save_pi_health(health: PiHealthIn) -> None:
    """Write one Pi health message to `pi_status`."""
    _store().write([pi_status_record(health)])
