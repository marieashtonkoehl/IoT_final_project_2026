# 🐝 The Pollinator Station

**A sighting becomes a plant.**
IoT Final Project · ADIoT 2026-27 · University of Deusto · Theme: *IoT for Reconnecting with Nature*

Team: Elisa Caldini · Hannah Kleutgens · Marie Sophie Köhl

> Status: **Sprint 1 — in progress.** This README describes the planned system; sections marked *(planned)* will be filled in as the code lands.

---

## What it does

A passer-by sees a bee or butterfly and presses a big button on the station.
Each press lights one more segment of an LED bar. When the bar is full, a small locker opens and the visitor takes a native, pollinator-friendly plant and plants it in the bed next to the station.

Every press is stored together with the conditions at that moment — temperature, humidity, light, UV, air pressure, soil moisture, gas and air quality, and how many people walked past. Over time the data shows *when* and *in what conditions* people notice pollinators, and whether the planting helps.

- **No app, no account, no screen** — one button, LEDs and printed info panels.
- **Fair use** — a cooldown between presses and a daily cap stop one person from emptying the lockers.
- **Privacy** — no camera or microphone; the motion sensor only counts movements.

## System overview

```
 ┌──────────────── Raspberry Pi 5 (station) ────────────────┐
 │                                                          │
 │  Sensors ──► device/ (sensor script) ──REST/JSON──► backend/ (FastAPI)
 │  Actuators ◄──────────── progress / unlock ◄──────────────┤
 │                     │                                    │      │
 │                     └──MQTT (status, Pi health)──► Mosquitto    ▼
 │                                                          │  InfluxDB ──► Grafana (partners)
 │                                                          │      │
 │                                                          │      └────► frontend/ (web page + map)
 └──────────────────────────────────────────────────────────┘
          ▲ external data: weather (Euskalmet / Open-Meteo), air quality (Open Data Euskadi),
            Bilbao parks & green spaces (open data)
```

Three parts:

| Part | Folder | Role |
|---|---|---|
| **Device script** | `device/` | Reads all sensors, drives LED bar / servo / buzzer, sends each press to the API, publishes status over MQTT |
| **Back end** | `backend/` | REST API (FastAPI, auto-generated OpenAPI docs), cooldown + daily cap rules, storage in InfluxDB, external APIs, alerts, analytics |
| **Front end** | `frontend/` + `dashboards/` | Web page (progress, conditions, map of green spaces) and Grafana dashboards for partners |

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
| Actuator | Servo latch | PWM | Unlocks the plant locker |
| Actuator | Buzzer *(optional)* | Digital | Sound when a plant is unlocked |

Exact pin/port wiring → [wiki: Hardware & wiring](../../wiki) *(planned)*.

## Data

Each accepted press is sent as one JSON message, for example:

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

The dashboards show this data in several ways *(planned)*: presses per day and per hour, live gauges of current conditions, presses against temperature / UV / humidity, a "good / fair / poor for pollinators" level, plants unlocked, and the trend before and after planting.

## Repository structure

```
device/            Sensor + actuator script for the Raspberry Pi
  tests/           One small test script per sensor / actuator
backend/app/       FastAPI application (API, rules, storage, external APIs)
frontend/          Web page (status, progress, map)
dashboards/grafana Exported Grafana dashboards (JSON)
deploy/            systemd services, docker-compose, Mosquitto config
docs/              Architecture, data model, diagrams
scripts/           Helper scripts (e.g. GitHub setup, Pi status)
```

How we work with branches, issues, pull requests and the board → **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Deployment *(planned)*

Everything runs on one Raspberry Pi 5 for the MVP. At the university, run the MQTT broker locally (outbound MQTT ports are closed on the campus network).

### 1. Get the code onto the Pi

```bash
ssh <user>@<pi-hostname>.local
git clone https://github.com/marieashtonkoehl/IoT_final_project_2026.git
cd IoT_final_project_2026
```

### 2. Python environment

Uses the Grove library set up in Lab 4 (RPi.GPIO does not work on the Pi 5 — we use the Grove library / gpiozero).

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Secrets and settings

```bash
cp .env.example .env
nano .env        # fill in tokens, cooldown, daily cap, target
```

`.env` is in `.gitignore` and must **never** be committed — the repository is public.

### 4. Database, dashboard and MQTT broker

```bash
cd deploy
docker compose up -d     # InfluxDB, Grafana, Mosquitto
```

(Alternative without Docker: install InfluxDB, Grafana and Mosquitto with `apt` as in the final lab.)

### 5. Start the services

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pollinator-api pollinator-device
```

Both services restart automatically after a reboot. Logs:

```bash
journalctl -u pollinator-device -f
```

### 6. Open it

| What | Address |
|---|---|
| Web page | `http://<pi-hostname>.local:8000/` |
| API docs (OpenAPI) | `http://<pi-hostname>.local:8000/docs` |
| Grafana | `http://<pi-hostname>.local:3000/` |

### Scaling beyond the MVP

The outdoor version replaces the Pi with a low-power microcontroller, LoRaWAN, and a solar panel + battery. The LoRaWAN network server forwards each press to the **same** REST endpoint as a webhook, so the back end and dashboards stay unchanged.

## Project management

- **Board:** [GitHub Project — Pollinator Station](https://github.com/users/marieashtonkoehl/projects/5)
- **Sprints:** Sprint 1 (3–17 Nov) · Sprint 2 (17 Nov–3 Dec) · Sprint 3 (3–11 Dec) · release `v1.0` on 11 Dec
- **Method:** SCRUM up to the MVP; every task is an issue, every change goes through a pull request.

## License

*(to be decided)*
