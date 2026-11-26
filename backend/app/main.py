"""The FastAPI app: creates the app and defines the endpoints.

Start it (from the backend/ folder):  uvicorn app.main:app --port 8000
Then open http://localhost:8000/docs for the interactive API docs.

This file only connects the pieces:
- models.py : shape of the JSON in and out
- rules.py  : cooldown / daily cap / presses-per-plant decisions
- storage.py: reading and writing the database (InfluxDB)
- config.py : settings from .env
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import rules, storage
from app.config import REPO_ROOT, settings
from app.models import HealthOut, PressIn, PressOut, ReadingIn, ReadingOut, StatusOut
from app.conditions import air_quality_level, pollinator_level

FRONTEND_DIR: Path = REPO_ROOT / "frontend"

# TODO: fake "latest values" until storage has a "latest reading" query
# (newest `environment` point from InfluxDB).
# Key names = fields of `environment` in docs/data-model.md.
LATEST_READING = {
    "temperature_c": 24.0,
    "humidity_pct": 50.0,
    "light_pct": 80.0,
    "pressure_hpa": 1013.0,
    "soil_moisture_pct": 40.0,
    "tvoc_ppb": 100,
    "eco2_ppm": 600,
}


def get_latest_reading():
    """Return the latest sensor reading from storage, falling back to sample values."""
    try:
        latest = storage.get_latest_environment(settings.station_id)
        if latest:
            return latest
    except storage.StorageUnavailable:
        pass
    return LATEST_READING


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs around the whole life of the server: close the database at the end.

    No database work at start-up on purpose: the progress count is restored
    on the first request (see storage.get_progress_count).
    """
    yield
    storage.close()


app = FastAPI(
    title="Pollinator Station API",
    description=(
        "Back end of the Pollinator Station. The device script sends button "
        "presses and sensor readings here; the web page reads data from here.\n\n"
        "Message formats: `docs/data-model.md`. Endpoints: `docs/architecture.md`."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(storage.StorageUnavailable)
async def database_unavailable(request: Request, error: storage.StorageUnavailable):
    """InfluxDB is down or refused the request: answer 503 instead of crashing (500).

    503 = "try again later". The device script can keep the message and send it again.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(error)},
    )


def now_utc() -> datetime:
    """The server's current time in UTC.

    A separate function so the tests can replace it with a fixed time.
    """
    return datetime.now(timezone.utc)


def check_station_id(station_id: str) -> None:
    """Refuse messages from another station (answer 400 Bad Request)."""
    if station_id != settings.station_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown station_id '{station_id}'. "
            f"This back end serves '{settings.station_id}'.",
        )


def _format_duration(seconds: float) -> str:
    """Seconds as short text, e.g. 11520 -> '3h12m', 360 -> '6m0s'."""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes}m"
    if minutes:
        return f"{minutes}m{secs}s"
    return f"{secs}s"


def check_not_in_future(timestamp: datetime) -> None:
    """Refuse a timestamp too far ahead of the server clock (answer 422).

    Why: the rules use the timestamp in the message. One accepted press dated
    in the future would put every later press into cooldown, and because the
    press is stored in the database, a restart would not fix it.

    Timestamps in the past are normal. When the back
    end is down, the device script keeps presses and sends them later (oldest
    first) with their original time. A small margin
    (MAX_FUTURE_SKEW_SECONDS) allows for clocks that are slightly apart.
    """
    seconds_ahead = (timestamp - now_utc()).total_seconds()
    if seconds_ahead > settings.max_future_skew_seconds:
        raise HTTPException(
            # 422 = "the message is well-formed but its content can't be used".
            # (The name of this constant differs between FastAPI versions, so a plain number.)
            status_code=422,
            detail=f"timestamp {timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')} is "
            f"{_format_duration(seconds_ahead)} ahead of server time "
            f"(max {settings.max_future_skew_seconds} s)",
        )


# Shown on /docs for endpoints that can answer 400.
UNKNOWN_STATION_RESPONSE = {
    400: {
        "description": "The station_id is not the one in STATION_ID (.env).",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Unknown station_id 'other-01'. "
                    "This back end serves 'deusto-ria-01'."
                }
            }
        },
    }
}

# Shown on /docs for endpoints that use the database.
DATABASE_DOWN_RESPONSE = {
    503: {
        "description": "InfluxDB is not reachable (or refused the request). Nothing was stored.",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Database not available (InfluxDB at http://localhost:8086): "
                    "NewConnectionError. Is Docker running (deploy/compose.yaml) "
                    "and are DB_* set in .env?"
                }
            }
        },
    }
}

# Text for /docs, shared by /presses and /readings.
TIMESTAMP_CHECK_TEXT = (
    "A `timestamp` more than `MAX_FUTURE_SKEW_SECONDS` (default 300 s) ahead of "
    "the server clock is refused with 422 and nothing is stored. Timestamps in "
    "the past are always allowed (buffered messages). "
    "**Try it out:** replace the example timestamp with the current UTC time."
)



# Endpoints

@app.get(
    "/health",
    response_model=HealthOut,
    tags=["system"],
    summary="Check that the back end is running",
    description="Always answers `{\"status\": \"ok\"}` while the server is up. "
    "No login needed.",
)
def health() -> HealthOut:
    return HealthOut(status="ok")


@app.post(
    "/presses",
    response_model=PressOut,
    tags=["device"],
    summary="Send one button press",
    description=(
        "Sent by the device script on every press, with all sensor readings.\n\n"
        "The back end decides if the press counts. Checks, in this order:\n"
        "1. less than `PRESS_COOLDOWN_SECONDS` since the last accepted press "
        "→ `cooldown`\n"
        "2. `DAILY_PRESS_CAP` accepted presses already today (day = midnight to "
        "midnight Europe/Madrid) → `daily_cap`\n"
        "3. otherwise → `accepted`, and `count` goes up by 1\n\n"
        "Every press (accepted or not) is stored in InfluxDB, measurement `presses`.\n\n"
        "When `count` reaches `presses_per_plant`, the answer shows the full count "
        "(e.g. 10 of 10) and the count then starts again at 0.\n\n"
        "The rules use the `timestamp` in the message, not the server clock. "
        + TIMESTAMP_CHECK_TEXT
    ),
    responses={**UNKNOWN_STATION_RESPONSE, **DATABASE_DOWN_RESPONSE},
)
def post_press(press: PressIn) -> PressOut:
    check_station_id(press.station_id)
    check_not_in_future(press.timestamp)
    station_id = press.station_id

    # 1. Gather what the rules need.
    # TODO(InfluxDB): read the current settings from the newest `settings` point
    #   instead of the start values from .env.
    start_of_today = rules.start_of_local_day_utc(press.timestamp)
    result = rules.decide_press(
        press_time=press.timestamp,
        last_accepted_time=storage.get_last_accepted_time(station_id),
        accepted_today=storage.count_accepted_since(station_id, start_of_today),
        cooldown_seconds=settings.press_cooldown_seconds,
        daily_cap=settings.daily_press_cap,
    )

    # 2. New progress count (only accepted presses count).
    count = storage.get_progress_count(station_id, settings.presses_per_plant)
    if result == "accepted":
        count += 1

    # 3. Save the press, accepted or rejected. FIRST save, THEN remember the
    #    new count: if the database is down, this raises (-> 503) and the
    #    count stays as it was.
    storage.save_press(press, result, count)
    storage.set_progress_count(station_id, count)

    if result == "accepted":
        # TODO(MQTT): publish an LED command (cmd/led, QoS 1) with level=count.
        pass

    # 4. Answer, so it still shows the full count (e.g. 10 of 10).
    answer = PressOut(
        result=result,
        count=count,
        presses_per_plant=settings.presses_per_plant,
    )

    # 5. Plant reached, then cycle starts again at 0 (after the answer above).
    #    The database keeps progress_count=10 for this press; storage turns
    #    that into 0 when it restores the count after a restart.
    if rules.is_plant_earned(count, settings.presses_per_plant):
        # TODO(MQTT): publish an unlock command (cmd/unlock, QoS 1, trigger=target).
        # TODO(InfluxDB): write a `rewards` point (trigger=target).
        storage.set_progress_count(station_id, 0)
        # TODO(MQTT): publish an LED command with level=0.

    return answer


@app.post(
    "/readings",
    response_model=ReadingOut,
    tags=["device"],
    summary="Send a timed sensor reading",
    description=(
        "Sent by the device script on a timer. Contains only the sensors read at "
        "that moment; all sensor fields are optional and may be `null` "
        "(a failed sensor sends `null`, not 0).\n\n"
        "Stored in InfluxDB: sensor values in `environment`, `motion_count` and "
        "`interval_s` in `footfall` (only if `motion_count` is present). "
        "`null` fields are left out.\n\n"
        + TIMESTAMP_CHECK_TEXT
    ),
    responses={**UNKNOWN_STATION_RESPONSE, **DATABASE_DOWN_RESPONSE},
)
def post_reading(reading: ReadingIn) -> ReadingOut:
    check_station_id(reading.station_id)
    check_not_in_future(reading.timestamp)

    storage.save_reading(reading)

    return ReadingOut(status="received")


@app.get(
    "/status",
    response_model=StatusOut,
    tags=["web page"],
    summary="Progress toward the next plant",
    description=(
        "Current `count` (accepted presses since the last unlock), "
        "`presses_per_plant`, and `last_press` (time of the newest accepted "
        "press, or `null`). Correct after a restart too: read from InfluxDB.\n\n"
        "Station online / locker state come later (MQTT, issue #34). "
        "No login yet (issue #60)."
    ),
    responses=DATABASE_DOWN_RESPONSE,
)
def get_status() -> StatusOut:
    # Same storage functions as POST /presses, so both always agree.
    station_id = settings.station_id
    return StatusOut(
        count=storage.get_progress_count(station_id, settings.presses_per_plant),
        presses_per_plant=settings.presses_per_plant,
        last_press=storage.get_last_accepted_time(station_id),
    )


@app.get(
    "/conditions",
    tags=["web page"],
    summary="Latest sensor values and good / fair / poor levels",
    description=(
        "`readings`: latest value of every sensor. Plus two levels: "
        "`pollinator_conditions` (temperature, light, humidity) and "
        "`air_quality` (TVOC, eCO2). Each level is `good`, `fair`, `poor` "
        "or `unknown`.\n\n"
        "For now the values are fake (fixed numbers). No login yet (issue #60)."
    ),
)
def get_conditions() -> dict:
    r = get_latest_reading() or {}
    return {
        "readings": r,
        "pollinator_conditions": pollinator_level(
            r.get("temperature_c"), r.get("light_pct"), r.get("humidity_pct")
        ),
        "air_quality": air_quality_level(r.get("tvoc_ppb"), r.get("eco2_ppm")),
    }

@app.get(
    "/api/dashboard",
    tags=["web page"],
    summary="Dashboard data: live readings, presses per day, and conditions over time",
    description=(
        "Returns `latest` sensor readings for live gauges, `presses_per_day`, "
        "and `conditions` time series for the selected `range` (`24h`, `7d`, `30d`)."
    ),
    responses=DATABASE_DOWN_RESPONSE,
)
def get_dashboard(range: str = "24h") -> dict:
    if range not in {"24h", "7d", "30d"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid range. Use one of: 24h, 7d, 30d.",
        )

    latest = get_latest_reading() or {}
    try:
        presses_per_day = storage.get_presses_per_day(settings.station_id, range)
        conditions = storage.get_environment_series(settings.station_id, range)
    except storage.StorageUnavailable:
        presses_per_day = []
        conditions = {}

    return {
        "range": range,
        "latest": latest,
        "presses_per_day": presses_per_day,
        "conditions": conditions,
    }


# Web page

# Serve the files in frontend/ at "/" (html=True: "/" shows index.html).
# AFTER endpoints above: FastAPI checks routes in order,
# and a mount at "/" would otherwise catch every request.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
