"""The FastAPI app: creates the app and defines the endpoints.

Start it (from the backend/ folder):  uvicorn app.main:app --port 8000
Then open http://localhost:8000/docs for the interactive API docs.

This file only connects the pieces:
- models.py : shape of the JSON in and out
- rules.py  : cooldown / daily cap / presses-per-plant decisions
- storage.py: state (in memory for now, InfluxDB later)
- config.py : settings from .env
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles

from app import rules, storage
from app.config import REPO_ROOT, settings
from app.models import HealthOut, PressIn, PressOut, ReadingIn, ReadingOut

FRONTEND_DIR: Path = REPO_ROOT / "frontend"

app = FastAPI(
    title="Pollinator Station API",
    description=(
        "Back end of the Pollinator Station. The device script sends button "
        "presses and sensor readings here; the web page reads data from here.\n\n"
        "Message formats: `docs/data-model.md`. Endpoints: `docs/architecture.md`."
    ),
    version="0.1.0",
)


def check_station_id(station_id: str) -> None:
    """Refuse messages from another station (answer 400 Bad Request)."""
    if station_id != settings.station_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown station_id '{station_id}'. "
            f"This back end serves '{settings.station_id}'.",
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
        "When `count` reaches `presses_per_plant`, the answer shows the full count "
        "(e.g. 10 of 10) and the count then starts again at 0.\n\n"
        "The rules use the `timestamp` in the message, not the server clock."
    ),
    responses=UNKNOWN_STATION_RESPONSE,
)
def post_press(press: PressIn) -> PressOut:
    check_station_id(press.station_id)

    # 1. Gather what the rules need.
    # TODO(InfluxDB): read the current settings from the newest `settings` point
    #   instead of the start values from .env.
    start_of_today = rules.start_of_local_day_utc(press.timestamp)
    result = rules.decide_press(
        press_time=press.timestamp,
        last_accepted_time=storage.get_last_accepted_time(),
        accepted_today=storage.count_accepted_since(start_of_today),
        cooldown_seconds=settings.press_cooldown_seconds,
        daily_cap=settings.daily_press_cap,
    )

    # 2. Update the progress count (only accepted presses count).
    count = storage.get_progress_count()
    if result == "accepted":
        storage.record_accepted_press(press.timestamp)
        count += 1
        storage.set_progress_count(count)

    # TODO(InfluxDB): save the press to `presses` (tag `result`, fields: sensor
    #   values + `progress_count`=count). Rejected presses are saved too.
    #   Leave out null sensor fields (InfluxDB can't store null).

    if result == "accepted":
        # TODO(MQTT): publish an LED command (cmd/led, QoS 1) with level=count.
        pass

    # 3. Answer, so it still shows the full count (e.g. 10 of 10).
    answer = PressOut(
        result=result,
        count=count,
        presses_per_plant=settings.presses_per_plant,
    )

    # 4. Plant reached, then cycle starts again at 0 (after the answer above).
    if rules.is_plant_earned(count, settings.presses_per_plant):
        # TODO(MQTT): publish an unlock command (cmd/unlock, QoS 1, trigger=target).
        # TODO(InfluxDB): write a `rewards` point (trigger=target).
        storage.set_progress_count(0)
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
        "For now the body is only checked, not stored."
    ),
    responses=UNKNOWN_STATION_RESPONSE,
)
def post_reading(reading: ReadingIn) -> ReadingOut:
    check_station_id(reading.station_id)

    # TODO(InfluxDB): write the sensor values to `environment`, and
    #   `motion_count` / `interval_s` to `footfall` (only if present).
    #   Leave out null fields.

    return ReadingOut(status="received")



# Web page

# Serve the files in frontend/ at "/" (html=True: "/" shows index.html).
# AFTER endpoints above: FastAPI checks routes in order,
# and a mount at "/" would otherwise catch every request.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
