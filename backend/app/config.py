"""Settings for the back end, read from the `.env` file in the repo root.

`.env` is never committed (see CONTRIBUTING.md § 8). Copy `.env.example`
to `.env` and fill it in. If a value is missing, the default below is used.

These are the *start* values. Later (InfluxDB) the current values will
come from the newest point in the `settings` measurement, and `.env` will only
be used on the very first start.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> parents[0] = app, [1] = backend, [2] = repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# Load the variables from .env into os.environ. Variables already set in the environment win (override=False).
# This lets the tests set their own values before the app is imported.
load_dotenv(REPO_ROOT / ".env", override=False)


def _get_int(name: str, default: int) -> int:
    """Read a whole number from the environment, or use the default.

    An empty value (e.g. `DAILY_PRESS_CAP=`) also uses the default.
    """
    value = os.getenv(name, "").strip()
    if value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    """All settings the back end needs, in one object."""

    station_id: str
    press_cooldown_seconds: int  # min. time between two accepted presses
    daily_press_cap: int  # max. accepted presses per day (Europe/Madrid)
    presses_per_plant: int  # accepted presses needed to unlock one plant


def load_settings() -> Settings:
    """Build a Settings object from the environment (and .env)."""
    return Settings(
        station_id=os.getenv("STATION_ID", "").strip() or "deusto-ria-01",
        press_cooldown_seconds=_get_int("PRESS_COOLDOWN_SECONDS", 300),
        daily_press_cap=_get_int("DAILY_PRESS_CAP", 50),
        presses_per_plant=_get_int("PRESSES_PER_PLANT", 10),
    )


# One shared Settings object, created once when the app starts.
settings = load_settings()
