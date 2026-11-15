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
