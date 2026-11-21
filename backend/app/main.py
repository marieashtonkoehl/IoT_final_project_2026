"""Backend API (FastAPI). Run from the backend/ folder: uvicorn app.main:app --reload

Login: the web page and the data endpoints need the shared account (HTTP Basic).
User and password come from the environment (.env), never from the code:
    STATION_USER=...
    STATION_PASSWORD=...
"""
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from rules.conditions import pollinator_level, air_quality_level

try:                          # optional in development: read the .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(title="IoT backend")
security = HTTPBasic()

# The web page lives in <repo>/frontend (this file is <repo>/backend/app/main.py).
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# TODO: replace with the real storage when it is ready.
# For now these are fake "latest values" so we can try the endpoints.
# TODO: check that the key names match docs/data-model.md; a wrong name
# is not an error, the level would silently be "unknown".
LATEST_READING = {
    "temperature": 24.0,   # deg C
    "humidity": 50.0,      # %
    "light_pct": 80.0,     # % (light sensor)
    "tvoc": 100,           # ppb
    "eco2": 600,           # ppm
}
# TODO: agree the real format with whoever builds the press storage.
PROGRESS = {"count": 7, "target": 10, "presses_today": 23}


def require_login(credentials: HTTPBasicCredentials = Depends(security)):
    """Check the shared account; user and password come from .env."""
    user = os.environ.get("STATION_USER")
    password = os.environ.get("STATION_PASSWORD")
    if not user or not password:       # never let anyone in if login is not set up
        raise HTTPException(
            status_code=503,
            detail="Login not configured: set STATION_USER and STATION_PASSWORD in .env",
        )
    user_ok = secrets.compare_digest(credentials.username.encode(), user.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), password.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Wrong user or password",
            headers={"WWW-Authenticate": "Basic"},
        )


def get_latest_reading():
    """Return the latest sensor reading (fake for now)."""
    return LATEST_READING


def get_progress():
    """Return progress towards the next plant and today's presses (fake for now)."""
    return PROGRESS


@app.get("/", include_in_schema=False, dependencies=[Depends(require_login)])
def index():
    """The station web page (frontend/index.html)."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/conditions", dependencies=[Depends(require_login)])
def get_conditions():
    """Pollinator conditions and air quality levels (good / fair / poor / unknown)."""
    r = get_latest_reading() or {}
    return {
        "pollinator_conditions": pollinator_level(
            r.get("temperature"), r.get("light_pct"), r.get("humidity")
        ),
        "air_quality": air_quality_level(r.get("tvoc"), r.get("eco2")),
    }


@app.get("/progress", dependencies=[Depends(require_login)])
def read_progress():
    """Presses counted towards the next plant, the target and today's presses."""
    return get_progress()
