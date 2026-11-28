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
| `app/storage.py` | Writes presses and readings to InfluxDB and reads them back (last accepted press, presses today, progress count). Also has a small in-memory store used by the tests |
| `app/config.py` | Reads `STATION_ID`, `PRESS_COOLDOWN_SECONDS`, `DAILY_PRESS_CAP`, `PRESSES_PER_PLANT`, `MAX_FUTURE_SKEW_SECONDS`, `DB_URL` / `DB_ORG` / `DB_BUCKET` / `DB_TOKEN`, `API_HOST` / `API_PORT` and `LOG_DIR` from the repo-root `.env` |
| `app/__main__.py` | `python -m app`: starts the server with `API_HOST` / `API_PORT` from `.env`. Used by the systemd service |
| `app/logging_setup.py` | Log to the console and to `logs/backend.log` (rotated at 1 MB, 5 old files). Runs once at start-up |
| `tests/` | pytest tests |

Endpoints so far: `GET /health`, `POST /presses`, `POST /readings`, `GET /status`. Presses and readings are stored in InfluxDB. Not done yet: settings from the database (#27), rewards (#41) and MQTT (#28, #34). Look for `TODO(InfluxDB)` and `TODO(MQTT)` in `app/main.py`.

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

   The back end needs **InfluxDB** for `/presses`, `/readings` and `/status` (see [Run on the Pi with InfluxDB](#run-on-the-pi-with-influxdb)). Without it, those endpoints answer `503`; `/health`, `/docs` and the web page still work.

4. Start the server by hand:

   ```bash
   cd backend
   python -m app
   ```

   - Host and port come from `API_HOST` and `API_PORT` in `.env` (default `0.0.0.0` and `8000`). This is the same command the systemd service uses.
   - `API_HOST=0.0.0.0` lets other computers on the network reach it (e.g. your laptop → the Pi). Use `127.0.0.1` to allow only the same machine.
   - Stop it with `Ctrl+C`.

   For development, with automatic restart when you save a file:

   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   - `app.main:app` = "in the file `app/main.py`, use the object called `app`".
   - Here `--host` / `--port` are used, not the values in `.env`.
   - `--reload`: only for development, not on the running station.

   Both ways also write the log to `logs/backend.log` in the repo root (`LOG_DIR` in `.env`).

   On the Pi the back end runs as a systemd service (starts at boot, restarts on crash): [deploy/README.md → Start everything after reboot](../deploy/README.md#start-everything-after-reboot-issue-37).

5. Open in a browser:

   - <http://localhost:8000/>: placeholder web page (`frontend/index.html`)
   - <http://localhost:8000/docs>: interactive API docs. Click an endpoint → **Try it out** → **Execute**
   - <http://localhost:8000/health>: should show `{"status":"ok"}`

   On the Pi, replace `localhost` with `<pi-hostname>.local`.

6. Try a press from the terminal:

   ```bash
   NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # current UTC time
   curl -X POST http://localhost:8000/presses \
     -H "Content-Type: application/json" \
     -d "{\"station_id\": \"deusto-ria-01\", \"timestamp\": \"$NOW\", \"temperature_c\": 17.4}"
   ```

   The timestamp must not be in the future: more than 5 min ahead of the server clock gets `422`.

   Answer: `{"result":"accepted","count":1,"presses_per_plant":10}`. Send it again → `"cooldown"`.

## Run on the Pi with InfluxDB

1. Start InfluxDB (and Mosquitto) in Docker: follow [deploy/README.md](../deploy/README.md) once. Check it runs:

   ```bash
   docker ps     # "influxdb" should be "Up"
   ```

2. Check the database values in the repo-root `.env`. They are the same ones Docker used on its first start:

   ```bash
   DB_URL=http://localhost:8086
   DB_ORG=pollinator-station
   DB_BUCKET=pollinator
   DB_TOKEN=<the token from deploy step 3>   # secret: only in .env, never in the repo
   ```

3. Install the packages again (`influxdb-client` is new) and start the server as in steps 2 and 4 above.

4. Send a press with the current time and check that it is in the database:

   ```bash
   NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   curl -X POST http://localhost:8000/presses -H "Content-Type: application/json" \
     -d "{\"station_id\": \"deusto-ria-01\", \"timestamp\": \"$NOW\", \"temperature_c\": 17.4}"

   docker exec influxdb influx query 'from(bucket: "pollinator") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "presses")'
   ```

5. Restart the back end (`Ctrl+C`, start again; as a service: `sudo systemctl restart pollinator-backend`) and open <http://localhost:8000/status>: `count` is the same as before the restart.

If something is wrong, the endpoints answer `503` with a message saying why:

- `NewConnectionError` / `ConnectTimeoutError`: InfluxDB is not running, or `DB_URL` is wrong. Check `docker ps`.
- `401 Unauthorized`: `DB_TOKEN` in `.env` is not the token InfluxDB was set up with.
- `404 Not Found`: `DB_ORG` or `DB_BUCKET` don't exist in InfluxDB.

The back end does not need InfluxDB to start: it connects on the first request. So the order in which the Pi starts Docker and the back end does not matter.

## Tests

```bash
cd backend          # with .venv active
pytest -v
```

The tests use their own settings (cooldown 10 s, daily cap 5, 3 presses per plant, set in `tests/conftest.py`), so your `.env` does not change the results.

They don't need InfluxDB: `conftest.py` gives every test an empty in-memory store, and fixes the server clock (so test timestamps like `2026-11-20` are never "in the future").

`tests/test_influx_integration.py` runs against a real InfluxDB (on the Pi). It is skipped automatically when InfluxDB is not reachable or `DB_TOKEN` is empty. It creates its own temporary bucket and deletes it afterwards, so the `pollinator` bucket is never touched:

```bash
pytest -v tests/test_influx_integration.py
```

## Good to know

- The rules use the `timestamp` in the message, not the server clock. A timestamp more than `MAX_FUTURE_SKEW_SECONDS` (default 300) ahead of the server clock gets `422` and is not stored, because one press dated in the future would block all later presses (cooldown). Past timestamps are always fine (the device script may send buffered presses later).
- Every press is stored in `presses`, also rejected ones (tag `result`). Readings go to `environment` and `footfall`. `null` sensor values are left out of the point.
- After a restart, the progress count comes back from `progress_count` of the newest stored press. The press that earned a plant is stored with `progress_count` = `presses_per_plant`, which means the next cycle starts at 0.
- The day for the daily cap runs from midnight to midnight Europe/Madrid. Timestamps stay in UTC.
- A press or reading with a different `station_id` than `STATION_ID` gets `400`. A wrong type (e.g. `"temperature_c": "warm"`) or an unknown field (e.g. a typo like `temp_c`) gets `422`.
- `count` in the answer shows the full cycle (e.g. 10 of 10) on the press that earns a plant; the next accepted press starts at 1.
