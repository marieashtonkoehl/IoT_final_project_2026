"""Pydantic models: the shape of the JSON the API receives and sends.

The fields follow docs/data-model.md exactly (snake_case, unit in the name).

FastAPI checks every request body against these classes.
If a field has the wrong type (e.g. "temperature_c": "warm"), FastAPI answers
with 422 Unprocessable Entity and a message saying which field is wrong,
before code runs. The same classes also build the /docs page.

Sensor fields are all optional and may be `null`: a sensor that fails sends
`null` (not 0), and a timed reading only contains the sensors read at that moment.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Example messages, copied from docs/data-model.md. Shown on the /docs page.
PRESS_EXAMPLE = {
    "station_id": "deusto-ria-01",
    "timestamp": "2026-11-20T11:42:05Z",
    "temperature_c": 17.4,
    "humidity_pct": 62.0,
    "light_pct": 71.3,
    "pressure_hpa": 1016.8,
    "soil_moisture_pct": 38.5,
    "tvoc_ppb": 120,
    "eco2_ppm": 450,
    "motion_count_10min": 14,
}

READING_EXAMPLE = {
    "station_id": "deusto-ria-01",
    "timestamp": "2026-11-20T11:45:00Z",
    "temperature_c": 17.6,
    "humidity_pct": 61.5,
    "light_pct": 69.8,
    "pressure_hpa": 1016.7,
    "soil_moisture_pct": 38.4,
    "tvoc_ppb": 115,
    "eco2_ppm": 445,
    "motion_count": 9,
    "interval_s": 600,
}



# Messages in (device / Pi to back end, over REST or MQTT)


class StationMessage(BaseModel):
    """Fields EVERY incoming message has: station_id and timestamp.

    Not used on its own: the REST and MQTT messages below build on it, so the
    timestamp is turned into UTC in one place only.
    """

    # extra="forbid": an unknown field (e.g. a typo like "temp_c") is an error
    # instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")

    station_id: str = Field(description="Station that sent the message.")
    timestamp: datetime = Field(
        description="When it happened. ISO 8601, UTC, with Z, e.g. 2026-11-20T11:42:05Z."
    )

    @field_validator("timestamp")
    @classmethod
    def timestamp_in_utc(cls, value: datetime) -> datetime:
        """Make every timestamp a UTC time.

        "...Z" already is UTC. A timestamp without a time zone is taken as UTC.
        One with another offset (e.g. +01:00) is converted to UTC.
        This way the rules can always compare timestamps safely.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class SensorMessage(StationMessage):
    """Fields shared by a press and a timed reading.

    Not used as a request body on its own: PressIn and ReadingIn build on it.
    """

    # Optional[float] = None means: a number, or null, or left out.
    temperature_c: Optional[float] = Field(None, description="Temperature, °C.")
    humidity_pct: Optional[float] = Field(None, description="Relative humidity, %.")
    light_pct: Optional[float] = Field(
        None, description="Light, % of sensor range (0 = dark, 100 = full sun)."
    )
    pressure_hpa: Optional[float] = Field(None, description="Air pressure, hPa.")
    soil_moisture_pct: Optional[float] = Field(
        None, description="Soil moisture, % (0 = dry, 100 = wet)."
    )
    tvoc_ppb: Optional[int] = Field(None, description="TVOC from the SGP30, ppb.")
    eco2_ppm: Optional[int] = Field(
        None, description="Estimated CO2 (eCO2) from the SGP30, ppm."
    )


class PressIn(SensorMessage):
    """Body of `POST /presses`: one button press with all readings."""

    model_config = ConfigDict(json_schema_extra={"examples": [PRESS_EXAMPLE]})

    motion_count_10min: Optional[int] = Field(
        None, ge=0, description="PIR triggers in the last 10 minutes."
    )


class ReadingIn(SensorMessage):
    """Body of `POST /readings`: a timed sensor reading."""

    model_config = ConfigDict(json_schema_extra={"examples": [READING_EXAMPLE]})

    motion_count: Optional[int] = Field(
        None, ge=0, description="PIR triggers during the interval."
    )
    interval_s: Optional[int] = Field(
        None, ge=0, description="Length of the PIR counting interval, seconds."
    )


# MQTT messages (checked by mqtt.py, not by FastAPI). Formats: docs/data-model.md.

LockerValue = Literal["locked", "open"]


class StationStatusIn(StationMessage):
    """Topic pollinator/<station_id>/status: device script online? locker open?

    Also the device script's MQTT last will (then "online": false).
    """

    online: bool
    locker: LockerValue


class PiHealthIn(StationMessage):
    """Topic pollinator/<station_id>/pi_health: sent by the Pi status script (cron)."""

    # Required numbers: a Pi health message without them is useless.
    cpu_temp_c: float
    cpu_load_1m: float
    disk_used_pct: float



# Responses (back end to device script / web page)


# The three possible results of a press. Literal = only exact strings.
PressResultValue = Literal["accepted", "cooldown", "daily_cap"]


class PressOut(BaseModel):
    """Answer to `POST /presses`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"result": "accepted", "count": 7, "presses_per_plant": 10}]
        }
    )

    result: PressResultValue = Field(
        description="accepted, or why the press did not count (cooldown / daily_cap)."
    )
    count: int = Field(
        description="Accepted presses in the current cycle, after this press. "
        "Equal to presses_per_plant on the press that unlocks a plant."
    )
    presses_per_plant: int = Field(description="Accepted presses needed for one plant.")


class ReadingOut(BaseModel):
    """Answer to `POST /readings`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "received"}]})

    status: Literal["received"]


class StatusOut(BaseModel):
    """Answer to `GET /status`: progress toward the next plant, and station status.

    online / locker / status_time come from the newest MQTT status message.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "count": 7,
                    "presses_per_plant": 10,
                    "last_press": "2026-11-20T11:42:05Z",
                    "online": True,
                    "locker": "locked",
                    "status_time": "2026-11-20T11:58:13Z",
                }
            ]
        }
    )

    count: int = Field(description="Accepted presses in the current cycle.")
    presses_per_plant: int = Field(description="Accepted presses needed for one plant.")
    last_press: Optional[datetime] = Field(
        description="Time of the newest accepted press (UTC), or null if there is none yet."
    )
    online: Optional[bool] = Field(
        description="Device script online (from MQTT status), or null if no status "
        "has arrived yet since the back end started."
    )
    locker: Optional[LockerValue] = Field(
        description="Plant cupboard: locked / open, or null if no status yet."
    )
    status_time: Optional[datetime] = Field(
        description="Timestamp of the newest status message (UTC), or null if none yet."
    )


class HealthOut(BaseModel):
    """Answer to `GET /health`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"]
