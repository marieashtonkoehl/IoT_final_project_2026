# 🐝 The Pollinator Station

**A sighting becomes a plant.**
IoT Final Project · ADIoT 2026-27 · University of Deusto · Theme: *IoT for Reconnecting with Nature*

Team: Elisa Caldini · Hannah Kleutgens · Marie Sophie Köhl

> Status: **Sprint 1 — in progress.** This README describes the planned system; sections marked *(planned)* will be filled in as the code lands.

> **🔓 Open decisions — see [#58](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/58)**
> We have not yet chosen the final tools for these parts, so this README describes them in general terms:
> - web framework for the API
> - time-series database + dashboard tool
> - where the database and dashboard run (on the Pi, on a laptop, or a mix)
> - Docker containers or direct installation
> - second communication protocol besides REST/HTTP
> - how programs auto-start on the Pi
> - map library for the web page
> - alert channel
>
> This README will be updated once we decide.

---

## What it does

A passer-by sees a bee or butterfly and presses a big button on the station.
Each press lights one more segment of an LED bar. When the bar is full, a small locker opens and the visitor takes a native, pollinator-friendly plant and plants it in the bed next to the station.

Every press is stored together with the conditions at that moment — temperature, humidity, light, UV, air pressure, soil moisture, gas and air quality, and how many people walked past. Over time the data shows *when* and *in what conditions* people notice pollinators, and whether the planting helps.

- **No app, no account, no screen**: one button, LEDs and printed info panels.
- **Fair use**: a cooldown between presses and a daily cap stop one person from emptying the lockers.
- **Privacy**: no camera or microphone; the motion sensor only counts movements.

## System overview

```
 ┌──────────────────────── Raspberry Pi 5 (station) ────────────────────────┐
 │                                                                          │
 │  ┌─────────┐      ┌───────────────┐   REST/JSON   ┌───────────────────┐  │
 │  │ Sensors │ ───► │ Device script │ ────────────► │        API        │  │
 │  └─────────┘      │   (device/)   │               │    (backend/)     │  │
 │  ┌───────────┐    │               │ ◄──────────── │                   │  │
 │  │ Actuators │ ◄─ │               │ progress /    └─────────┬─────────┘  │
 │  └───────────┘    └───────┬───────┘ unlock                  │            │
 │                           │ status, Pi health               ▼            │
 │                           ▼                       ┌───────────────────┐  │
 │              ┌──────────────────────────┐         │     Database      │  │
 │              │ Message broker           │         └────┬─────────┬────┘  │
 │              │ (optional, 2nd protocol) │              │         │       │
 │              └──────────────────────────┘              ▼         ▼       │
 │                                              ┌───────────┐ ┌──────────┐  │
 │                                              │ Dashboard │ │ Web page │  │
 │                                              │(partners) │ │(frontend)│  │
 │                                              └───────────┘ └──────────┘  │
 └──────────────────────────────────────────────────────────────────────────┘
   ▲ external data: weather (Euskalmet / Open-Meteo), air quality (Open Data Euskadi),
     Bilbao parks & green spaces (open data)
```

Where the database and dashboard run (Pi or laptop) is still open — see [#58](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/58).

Three parts:

| Part | Folder | Role |
|---|---|---|
| **Device script** | `device/` | Reads all sensors, drives LED bar / servo / buzzer, sends each press to the API, sends status over a second communication protocol |
| **Back end** | `backend/` | REST API (documented with OpenAPI), cooldown + daily cap rules, storage in the time-series database, external APIs, alerts, analytics |
| **Front end** | `frontend/` + `dashboards/` | Web page (progress, conditions, map of green spaces) and dashboards for partners |

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
backend/app/       API application (API, rules, storage, external APIs)
frontend/          Web page (status, progress, map)
dashboards/        Exported dashboard files from the dashboard tool
deploy/            Setup files for running the station on the Pi (database, dashboard, auto-start)
docs/              Architecture, data model, diagrams
scripts/           Helper scripts around the project (e.g. Pi status report)
```

How we work with branches, issues, pull requests and the board → **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Deployment *(planned)*

Everything runs on one Raspberry Pi 5 for the MVP. Some steps depend on tools the team has not chosen yet; they say **(depends on #58)**.

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
nano .env        # fill in tokens, cooldown, daily cap, target
```

`.env` is in `.gitignore` and must **never** be committed, the repository is public. More in [CONTRIBUTING.md § 8](CONTRIBUTING.md#8-secrets-and-settings).

### 4. Database and dashboard

Set up the time-series database and the dashboard tool (and a message broker, if the second protocol needs one). **(depends on #58)** which tools, where they run, and whether with Docker or a direct install.

Note: the campus network blocks some outbound ports, so a message broker should run locally on the station.

### 5. Start the programs so they run after a reboot

Start the API and the device script, and set them up to start automatically when the Pi boots. **(depends on #58)**

### 6. Open it

| What | Address |
|---|---|
| Web page | `http://<pi-hostname>.local:8000/` *(port may change)* |
| API docs (OpenAPI) | address depends on the web framework **(depends on #58)** |
| Dashboard | address depends on the dashboard tool **(depends on #58)** |

### Scaling beyond the MVP

The outdoor version replaces the Pi with a low-power microcontroller, LoRaWAN, and a solar panel + battery. The LoRaWAN network server forwards each press to the **same** REST endpoint as a webhook, so the back end and dashboards stay unchanged.

## Project management

- **Board:** [GitHub Project — Pollinator Station](https://github.com/users/marieashtonkoehl/projects/5)
- **Sprints:** Sprint 1 (3–17 Nov) · Sprint 2 (17 Nov–3 Dec) · Sprint 3 (3–11 Dec) · release `v1.0` on 11 Dec
- **Method:** SCRUM up to the MVP; every task is an issue, every change goes through a pull request.

## License

*(to be decided)*
