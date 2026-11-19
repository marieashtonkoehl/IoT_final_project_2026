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



# Requests (device script to back end)


class SensorMessage(BaseModel):
    """Fields shared by a press and a timed reading.

    Not used as a request body on its own: PressIn and ReadingIn build on it.
    """

    # extra="forbid": an unknown field (e.g. a typo like "temp_c") is an error
    # instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")

    station_id: str = Field(description="Station that sent the message.")
    timestamp: datetime = Field(
        description="When it happened. ISO 8601, UTC, with Z, e.g. 2026-11-20T11:42:05Z."
    )

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
    """Answer to `GET /status`: progress toward the next plant.

    Station online / locker state come later (they need MQTT, issue #34).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"count": 7, "presses_per_plant": 10, "last_press": "2026-11-20T11:42:05Z"}
            ]
        }
    )

    count: int = Field(description="Accepted presses in the current cycle.")
    presses_per_plant: int = Field(description="Accepted presses needed for one plant.")
    last_press: Optional[datetime] = Field(
        description="Time of the newest accepted press (UTC), or null if there is none yet."
    )


class HealthOut(BaseModel):
    """Answer to `GET /health`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"]
