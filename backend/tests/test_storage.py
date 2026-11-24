"""Tests for storage.py: how records are built, and the progress restore rule.

No database needed. The line-protocol tests use the real InfluxDB client
library (without a server), so they check the exact text sent to InfluxDB.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from influxdb_client import Point, WritePrecision

from app import storage
from app.models import PressIn, ReadingIn
from conftest import make_press, utc


def line_protocol(record: dict) -> str:
    """The text the InfluxDB client would send for this record."""
    return Point.from_dict(record, write_precision=WritePrecision.S).to_line_protocol()



# Field types


def test_floats_and_ints_are_cast():
    fields = storage.clean_fields({"humidity_pct": 62, "tvoc_ppb": 120.0})
    assert fields == {"humidity_pct": 62.0, "tvoc_ppb": 120}
    assert isinstance(fields["humidity_pct"], float)
    assert isinstance(fields["tvoc_ppb"], int)


def test_null_fields_are_left_out():
    assert storage.clean_fields({"temperature_c": None, "light_pct": 71.3}) == {"light_pct": 71.3}


def test_unknown_field_is_an_error():
    # Protects against a new field being added without a type.
    with pytest.raises(ValueError):
        storage.clean_fields({"temp": 17.4})


def test_press_line_protocol_has_the_right_types():
    body = make_press("2026-11-20T11:42:05Z")
    body["humidity_pct"] = 62  # a whole number in the JSON
    record = storage.press_record(PressIn(**body), "accepted", 7)
    line = line_protocol(record)

    # In line protocol, ints end with "i" and floats don't.
    assert line.startswith("presses,result=accepted,station_id=deusto-ria-01 ")
    assert "count=1i" in line
    assert "progress_count=7i" in line
    assert "tvoc_ppb=120i" in line
    assert "eco2_ppm=450i" in line
    assert "motion_count_10min=14i" in line
    assert "humidity_pct=62," in line  # float, not "62i"
    assert "temperature_c=17.4" in line
    # Time in seconds (precision S): 2026-11-20T11:42:05Z
    assert line.endswith(" 1795174925")


def test_rejected_press_record():
    record = storage.press_record(PressIn(**make_press("2026-11-20T11:42:05Z")), "daily_cap", 4)
    assert record["measurement"] == "presses"
    assert record["tags"] == {"station_id": "deusto-ria-01", "result": "daily_cap"}
    assert record["fields"]["count"] == 1
    assert record["fields"]["progress_count"] == 4
    assert record["time"] == utc("2026-11-20T11:42:05Z")


def test_press_record_without_sensors():
    # All sensors failed: the press is still stored (count + progress_count).
    press = PressIn(station_id="deusto-ria-01", timestamp="2026-11-20T11:42:05Z")
    assert storage.press_record(press, "accepted", 1)["fields"] == {"count": 1, "progress_count": 1}


def test_empty_reading_gives_no_records():
    reading = ReadingIn(station_id="deusto-ria-01", timestamp="2026-11-20T11:45:00Z", light_pct=None)
    assert storage.reading_records(reading) == []


def test_interval_without_motion_count_gives_no_footfall():
    reading = ReadingIn(station_id="deusto-ria-01", timestamp="2026-11-20T11:45:00Z", interval_s=600)
    assert storage.reading_records(reading) == []



# Progress restore rule (presses per plant = 10 here)


@pytest.mark.parametrize(
    "newest, expected",
    [
        (None, 0),  # no press stored yet
        (0, 0),
        (7, 7),  # in the middle of a cycle
        (9, 9),
        (10, 0),  # the press that earned a plant: next cycle starts at 0
        (12, 0),  # above presses_per_plant (e.g. setting was lowered): also 0
    ],
)
def test_restore_progress(newest, expected):
    assert storage.restore_progress(newest, presses_per_plant=10) == expected


def test_progress_is_restored_on_first_use_only(store):
    store.write([storage.press_record(PressIn(**make_press("2026-11-20T11:00:00Z")), "accepted", 2)])
    assert storage.get_progress_count("deusto-ria-01", presses_per_plant=3) == 2

    # Later changes come from set_progress_count, not from the database.
    storage.set_progress_count("deusto-ria-01", 0)
    assert storage.get_progress_count("deusto-ria-01", presses_per_plant=3) == 0


def test_restore_uses_newest_press_even_if_rejected(store):
    press = PressIn(**make_press("2026-11-20T11:00:00Z"))
    later = PressIn(**make_press("2026-11-20T11:00:05Z"))
    # Written in the wrong order on purpose: "newest" means newest timestamp.
    store.write([storage.press_record(later, "cooldown", 5), storage.press_record(press, "accepted", 4)])
    assert storage.get_progress_count("deusto-ria-01", presses_per_plant=10) == 5


def test_reads_are_per_station(store):
    other = make_press("2026-11-20T11:00:00Z")
    other["station_id"] = "other-01"
    store.write([storage.press_record(PressIn(**other), "accepted", 6)])

    assert storage.get_last_accepted_time("deusto-ria-01") is None
    assert storage.count_accepted_since("deusto-ria-01", utc("2026-11-20T00:00:00Z")) == 0
    assert storage.get_progress_count("deusto-ria-01", presses_per_plant=10) == 0
    assert storage.get_progress_count("other-01", presses_per_plant=10) == 6



# Flux query text (InfluxDB OSS has no query parameters, so values go into the text)


def test_flux_string_plain():
    assert storage.flux_string("deusto-ria-01") == '"deusto-ria-01"'


def test_flux_string_escapes_quote_and_backslash():
    # Python 'a"b\c'  ->  Flux "a\"b\\c"
    assert storage.flux_string('a"b\\c') == '"a\\"b\\\\c"'


def test_flux_string_backslash_before_quote():
    # A value ending in \" must not be able to close the string early:
    # \  -> \\   and   "  -> \"   gives  \\\"  (an escaped backslash + an escaped quote)
    assert storage.flux_string('x\\"') == '"x\\\\\\""'


def test_flux_string_escapes_interpolation():
    # In Flux, "${...}" inside a string would insert a value.
    assert storage.flux_string("${r._value}") == '"\\${r._value}"'


def test_flux_time_is_utc_with_z():
    madrid_midnight = datetime(2026, 11, 20, 0, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    assert storage.flux_time(madrid_midnight) == "2026-11-19T23:00:00Z"


def test_flux_time_needs_a_time_zone():
    with pytest.raises(ValueError):
        storage.flux_time(datetime(2026, 11, 20))


ALL_QUERIES = {
    "last_accepted": storage.last_accepted_query("pollinator", "deusto-ria-01"),
    "count_since": storage.count_accepted_since_query(
        "pollinator", "deusto-ria-01", utc("2026-11-19T23:00:00Z")
    ),
    "newest_progress": storage.newest_progress_query("pollinator", "deusto-ria-01"),
}


@pytest.mark.parametrize("name", sorted(ALL_QUERIES))
def test_queries_use_no_params(name):
    query = ALL_QUERIES[name]
    assert "params." not in query  # would fail on InfluxDB OSS
    assert 'from(bucket: "pollinator")' in query
    assert 'r.station_id == "deusto-ria-01"' in query


def test_count_query_starts_at_the_given_time():
    query = ALL_QUERIES["count_since"]
    assert "range(start: 2026-11-19T23:00:00Z, stop: 2100-01-01T00:00:00Z)" in query
    assert 'r.result == "accepted"' in query


def test_strange_station_id_stays_inside_the_string():
    query = storage.last_accepted_query("pollinator", 'x" or r._measurement != "')
    assert 'r.station_id == "x\\" or r._measurement != \\""' in query
