# backend/

The back end: a **FastAPI** app (REST over HTTP with JSON, documented with OpenAPI at `/docs`). Runs on the Pi as a systemd service.

What it does:

- receives presses and timed sensor readings from the device script (REST)
- applies the cooldown, daily cap and presses-per-plant rules (current values from the `settings` measurement)
- reads from and writes to InfluxDB 2 (bucket `pollinator`)
- subscribes to MQTT (station status, Pi health) and publishes commands to the device (unlock, LED)
- serves the web page (`frontend/`) and its REST endpoints, with one shared login
- external APIs (weather, air quality, green spaces), alerts and analytics

- `app/`: the server code itself
- this folder: things about the server: README, list of Python packages, tests

Endpoints, messages and measurements → [docs/architecture.md](../docs/architecture.md), [docs/data-model.md](../docs/data-model.md).

## Files

| File | What it does |
|---|---|
| `app/main.py` | Creates the FastAPI app, defines the endpoints, serves `frontend/` at `/` |
| `app/models.py` | Pydantic models: the JSON the API accepts and returns (as in `docs/data-model.md`) |
| `app/rules.py` | Cooldown, daily cap (Europe/Madrid day) and presses-per-plant decisions |
| `app/storage.py` | State: **in memory for now** (lost on restart); InfluxDB later |
| `app/config.py` | Reads `STATION_ID`, `PRESS_COOLDOWN_SECONDS`, `DAILY_PRESS_CAP`, `PRESSES_PER_PLANT` from the repo-root `.env` |
| `tests/` | pytest tests |

Endpoints so far: `GET /health`, `POST /presses`, `POST /readings`. No InfluxDB and no MQTT yet: look for `TODO(InfluxDB)` and `TODO(MQTT)` in `app/main.py` and `app/storage.py`.

## How to run

All commands start in the **repo root** (`IoT_final_project_2026/`).

1. Create the virtual environment (once) and activate it (every new terminal):

   ```bash
   python3 -m venv .venv          # once (on the Pi: add --system-site-packages, see main README)
   source .venv/bin/activate      # the prompt now starts with (.venv)
   ```

2. Install the packages (once, and again when `requirements.txt` changes):

   ```bash
   pip install -r backend/requirements.txt
   ```

3. Settings: make sure `.env` exists in the repo root (`cp .env.example .env`). Without it, the defaults are used (cooldown 300 s, daily cap 50, 10 presses per plant). For a demo, set e.g. `PRESS_COOLDOWN_SECONDS=10`.

4. Start the server by hand on port 8000:

   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   - `app.main:app` = "in the file `app/main.py`, use the object called `app`".
   - `--host 0.0.0.0` lets other computers on the network reach it (e.g. your laptop → the Pi). Use `--host 127.0.0.1` to allow only the same machine.
   - `--reload` restarts the server when you save a file. Only for development.
   - Stop it with `Ctrl+C`.

5. Open in a browser:

   - <http://localhost:8000/>: placeholder web page (`frontend/index.html`)
   - <http://localhost:8000/docs>: interactive API docs. Click an endpoint → **Try it out** → **Execute**
   - <http://localhost:8000/health>: should show `{"status":"ok"}`

   On the Pi, replace `localhost` with `<pi-hostname>.local`.

6. Try a press from the terminal:

   ```bash
   curl -X POST http://localhost:8000/presses \
     -H "Content-Type: application/json" \
     -d '{"station_id": "deusto-ria-01", "timestamp": "2026-11-20T11:42:05Z", "temperature_c": 17.4}'
   ```

   Answer: `{"result":"accepted","count":1,"presses_per_plant":10}`. Send it again → `"cooldown"`.

## Tests

```bash
cd backend          # with .venv active
pytest -v
```

The tests use their own settings (cooldown 10 s, daily cap 5, 3 presses per plant, set in `tests/conftest.py`), so your `.env` does not change the results.

## Good to know

- The rules use the `timestamp` in the message, not the server clock.
- The day for the daily cap runs from midnight to midnight Europe/Madrid. Timestamps stay in UTC.
- A press or reading with a different `station_id` than `STATION_ID` gets `400`. A wrong type (e.g. `"temperature_c": "warm"`) or an unknown field (e.g. a typo like `temp_c`) gets `422`.
- `count` in the answer shows the full cycle (e.g. 10 of 10) on the press that earns a plant; the next accepted press starts at 1.
