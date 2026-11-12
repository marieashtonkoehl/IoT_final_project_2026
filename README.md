# The Pollinator Station

**A sighting becomes a plant.**
IoT Final Project · ADIoT 2026-27 · University of Deusto · Theme: *IoT for Reconnecting with Nature*

Team: Elisa Caldini · Hannah Kleutgens · Marie Sophie Köhl

> Status: **Sprint 1: in progress.** This README describes the planned system; sections marked *(planned)* will be filled in as the code lands.

> **🔓 Still open:**
> - map library for the web page ([#46](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/46))
> - alert channel ([#42](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/42))
> - edge AI ([#48](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/48))
>
> Everything else is decided ([#58](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/58)) — see [docs/architecture.md](docs/architecture.md).

---

## What it does

A passer-by sees a bee or butterfly and presses a big button on the station.
Each press lights one more segment of an LED bar. When the bar is full, a small locker opens and the visitor takes a native, pollinator-friendly plant and plants it in the bed next to the station.

Every press is stored together with the conditions at that moment — temperature, humidity, light, UV, air pressure, soil moisture, gas and air quality, and how many people walked past. Over time the data shows *when* and *in what conditions* people notice pollinators, and whether the planting helps.

- **For visitors: no app, no account, no screen**: one button, the LED bar and a printed info panel.
- **For operators and partners (Ayuntamiento)**: a web page with login: charts, station status, map, settings and manual locker opening.
- **Fair use**: a cooldown between presses and a daily cap stop one person from emptying the lockers.
- **Privacy**: no camera or microphone; the motion sensor only counts movements.

## System overview

```
 ┌─────────────────────────────── Raspberry Pi 5 (station) ────────────────────────────────┐
 │                                                                                         │
 │              ┌───────────────┐   REST: presses, readings  ┌──────────────────┐          │
 │ Sensors ───► │ Device script │ ─────────────────────────► │ Back end         │          │
 │              │ (device/)     │                            │ FastAPI          │          │
 │ Actuators ◄─ │ systemd       │ ◄── MQTT: commands ─────── │ (backend/)       │          │
 │              │               │     (unlock, LED)          │ systemd          │          │
 │              │               │ ─── MQTT: status ────────► │                  │          │
 │              └───────────────┘                            │                  │          │
 │ Pi status script ──────────────── MQTT: Pi health ──────► │                  │          │
 │ (scripts/, cron, every 5 min)                             └───┬──────────┬───┘          │
 │                                                  write, query │          │ REST/JSON    │
 │                                                               ▼          ▼ + login      │
 │                                                  ┌──────────────┐ ┌──────────────────┐  │
 │ MQTT messages pass through Mosquitto             │ InfluxDB 2   │ │ Web page         │  │
 │ (Docker, port bound to 127.0.0.1).               │ (Docker)     │ │ (frontend/)      │  │
 │                                                  └──────────────┘ │ ECharts, served  │  │
 │                                                                   │ by FastAPI       │  │
 │                                                                   │ operators +      │  │
 │                                                                   │ partners only    │  │
 │                                                                   └──────────────────┘  │
 │                                                                                         │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
   ▲ external data: weather (Euskalmet / Open-Meteo), air quality (Open Data Euskadi),
     Bilbao parks & green spaces (open data) → fetched by the back end
```

Everything runs on the Raspberry Pi 5.

Three parts:

| Part | Folder | Role |
|---|---|---|
| **Device script** | `device/` | Reads all sensors, drives LED bar and servo latch, sends presses and readings to the back end (REST), publishes station status and receives commands (MQTT). Runs as a systemd service |
| **Back end** | `backend/` | FastAPI: REST API (documented with OpenAPI), cooldown + daily cap rules, storage in InfluxDB 2, commands to the device over MQTT, login, external APIs, alerts, analytics. Runs as a systemd service |
| **Front end** | `frontend/` | Web page for operators and partners, with login: charts and live gauges (Apache ECharts), status, progress, map, settings, manual unlock. Served by FastAPI |

## Hardware

| Type | Component | Interface | Used for |
|---|---|---|---|
| Sensor | Large LED push button | Digital GPIO | Registers a pollinator sighting |
| Sensor | PIR motion sensor | Digital GPIO | Counts passers-by (checks whether press numbers are realistic) |
| Sensor | Temperature & humidity | I2C / digital *(check model)* | Conditions at each press |
| Sensor | Light | Analogue (HAT ADC) | Sun / shade at each press |
| Sensor | UV | Analogue / I2C *(check model)* | UV level at each press |
| Sensor | Barometer | I2C | Air pressure → weather trend |
| Sensor | Soil moisture | Analogue (HAT ADC) | Moisture of the planting bed → "please water" reminder |
| Sensor | Gas *(to be added)* | Analogue / I2C | Air conditions near the station |
| Sensor | Air quality *(to be added)* | Analogue | Air quality level at each press |
| Actuator | LED bar | Digital | Progress towards the next plant |
| Actuator | Servo latch | PWM | Unlocks the plant locker; locks again after 60 s |

Exact pin/port wiring → [wiki: Hardware & wiring](../../wiki) *(planned)*.

## Data

The device script sends each press to the back end as one JSON message (`POST /presses`), for example:

```json
{
  "station_id": "deusto-ria-01",
  "timestamp": "2026-11-20T11:42:05Z",
  "temperature_c": 17.4,
  "humidity_pct": 62.0,
  "light_pct": 71.3,
  "uv_index": 2.1,
  "pressure_hpa": 1016.8,
  "soil_moisture_pct": 38.5,
  "gas_raw": 412,
  "air_quality_raw": 95,
  "motion_count_10min": 14
}
```

The back end decides if the press counts (cooldown, daily cap) and stores it either way. Full message formats and database measurements: [docs/data-model.md](docs/data-model.md).

The web page shows this data in several ways *(planned)*: presses per day and per hour, live gauges of current conditions, presses against temperature / UV / humidity, a "good / fair / poor for pollinators" level, plants unlocked, and the trend before and after planting.

## Repository structure

```
device/            Sensor + actuator script for the Raspberry Pi
  tests/           One small test script per sensor / actuator
backend/app/       API application (API, rules, storage, external APIs)
frontend/          Web page (charts, status, progress, map), served by FastAPI
deploy/            Setup files for running the station on the Pi (Docker Compose, systemd, cron)
docs/              Architecture, data model, diagrams
scripts/           Helper scripts around the project (e.g. Pi status report)
```

Architecture diagram and data model → **[docs/architecture.md](docs/architecture.md)**.

How we work with branches, issues, pull requests and the board → **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Deployment *(planned)*

Everything runs on one Raspberry Pi 5 for the MVP: InfluxDB 2 and Mosquitto in Docker, the back end and the device script as systemd services, the Pi status script from cron.

### 1. Get the code onto the Pi

```bash
ssh <user>@<pi-hostname>.local
git clone https://github.com/marieashtonkoehl/IoT_final_project_2026.git
cd IoT_final_project_2026
```

### 2. Python environment

Uses the Grove library set up in Lab 4 ( Grove library / gpiozero).

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt     # package list not added yet
```

### 3. Secrets and settings

```bash
cp .env.example .env
nano .env        # fill in InfluxDB token, login password hash, start values
```

`.env` is in `.gitignore` and must **never** be committed, the repository is public. More in [CONTRIBUTING.md § 8](CONTRIBUTING.md#8-secrets-and-settings).

### 4. Database and message broker (Docker)

InfluxDB 2 and Mosquitto run in Docker, from one file: `deploy/compose.yaml` *(not added yet)*.

```bash
cd deploy
docker compose up -d
```

- InfluxDB 2: one bucket `pollinator`, retention "never". Put its token in `.env`.
- Mosquitto: port 1883 bound to `127.0.0.1`, so only programs on the Pi can reach it. The campus network blocks some outbound ports, so the broker runs locally on the station.

### 5. Start the programs so they run after a reboot

- **Back end (FastAPI)** and **device script**: one systemd service each. Unit files go in `deploy/` *(not added yet)*. Copy them to `/etc/systemd/system/`, then `sudo systemctl enable --now <service>`.
- **Pi status script**: one crontab line (`crontab -e`) that runs the script in `scripts/` every 5 minutes with the project's `.venv` Python.

Details → [deploy/README.md](deploy/README.md).

### 6. Open it

| What | Address |
|---|---|
| Web page (login) | `http://<pi-hostname>.local:8000/` |
| API docs (OpenAPI) | `http://<pi-hostname>.local:8000/docs` |

Both are served by FastAPI. The port is `API_PORT` in `.env`.

### Scaling beyond the MVP

The outdoor version replaces the Pi with a low-power microcontroller, LoRaWAN, and a solar panel + battery. The LoRaWAN network server forwards each press to the **same** REST endpoint as a webhook, so the back end and web page stay unchanged.

## Project management

- **Board:** [GitHub Project — Pollinator Station](https://github.com/users/marieashtonkoehl/projects/5)
- **Sprints:** Sprint 1 (3–17 Nov) · Sprint 2 (17 Nov–3 Dec) · Sprint 3 (3–11 Dec) · release `v1.0` on 11 Dec
- **Method:** SCRUM up to the MVP; every task is an issue, every change goes through a pull request.

## License

*(to be decided)*
