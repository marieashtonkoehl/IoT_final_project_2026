# Data model

REST messages from the device script, MQTT topics and messages, and the InfluxDB measurements. Diagram and components: see [architecture.md](architecture.md).

General rules:

- One station = one `station_id`. MVP station: `deusto-ria-01`.
- Timestamps: ISO 8601, UTC, with `Z`, to the second. Example: `2026-11-20T11:42:05Z`. The Pi clock is synced with NTP.
- The unit is part of the field name (`_c`, `_pct`, `_hpa`, `_s`). See the unit table below.
- JSON uses `snake_case`. A sensor that fails sends `null`, not `0`.

## Units

| Suffix / field | Unit |
|---|---|
| `_c` | degrees Celsius |
| `_pct` | percent, 0–100 |
| `_hpa` | hectopascal |
| `_s` | seconds |
| `uv_index` | UV index, 0–11+ (conversion from raw value to confirm, issue #19) |
| `light_pct` | percent of sensor range, 0 = dark, 100 = full sun (to confirm) |
| `soil_moisture_pct` | percent, 0 = dry, 100 = wet (calibration to confirm, issue #20) |
| `motion_count_10min` | number of PIR triggers in the last 10 minutes |
| `_raw` | raw sensor value, no unit (gas, air quality, until converted) |

## REST messages from the device script

### Button press: `POST /presses`

Sent on every press (issue #26).

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
  "motion_count_10min": 14
}
```

Response:

```json
{ "result": "accepted", "count": 7, "presses_per_plant": 10 }
```

- The device does not decide if the press counts. The back end applies cooldown and daily cap.
- `result` is one of `accepted`, `cooldown`, `daily_cap`.
- `gas_raw` and `air_quality_raw` are added once those sensors are integrated (issues #30, #31).

### Timed sensor reading: `POST /readings`

Sent by the device script on a timer. The read interval per sensor comes from `.env` (set after Sprint 1 tests). A message contains only the sensors read at that moment; the others are left out.

```json
{
  "station_id": "deusto-ria-01",
  "timestamp": "2026-11-20T11:45:00Z",
  "temperature_c": 17.6,
  "humidity_pct": 61.5,
  "light_pct": 69.8,
  "uv_index": 2.0,
  "pressure_hpa": 1016.7,
  "soil_moisture_pct": 38.4,
  "motion_count": 9,
  "interval_s": 600
}
```

The back end writes the sensor values to `environment` and `motion_count` / `interval_s` to `footfall`.

## MQTT

The broker (Mosquitto) runs in Docker on the Pi. Its port is bound to `127.0.0.1`. MQTT is used only for station status, Pi health and commands. Presses and readings use REST.

### Topics

Pattern: `pollinator/<station_id>/<type>`.

| Topic | From → to | Content | QoS | Retained |
|---|---|---|---|---|
| `pollinator/<station_id>/status` | device script → back end | Station status; also the MQTT last will | 0 | yes |
| `pollinator/<station_id>/pi_health` | Pi status script → back end | CPU temperature, load, disk | 0 | no |
| `pollinator/<station_id>/cmd/led` | back end → device script | Set LED bar level | 1 | never |
| `pollinator/<station_id>/cmd/unlock` | back end → device script | Unlock the cupboard | 1 | never |

### Messages

Station status (on start, on every change):

```json
{ "station_id": "deusto-ria-01", "timestamp": "2026-11-20T11:58:13Z", "online": true, "locker": "open" }
```

`locker` is `locked` or `open`. Last will (sent by the broker if the device script disconnects): same topic, `"online": false`.

Pi health (every 5 min, from cron):

```json
{ "station_id": "deusto-ria-01", "timestamp": "2026-11-20T12:00:00Z", "cpu_temp_c": 52.3, "cpu_load_1m": 0.41, "disk_used_pct": 23.7 }
```

LED command:

```json
{ "command_id": "c-000123", "timestamp": "2026-11-20T11:42:06Z", "level": 7, "max": 10 }
```

Unlock command:

```json
{ "command_id": "c-000124", "timestamp": "2026-11-20T11:58:12Z", "trigger": "target" }
```

- `trigger` is `target` or `manual`.
- `command_id` format (to confirm). The device ignores a `command_id` it has already handled, because QoS 1 can deliver a command twice.
- `level` is absolute, so a repeated LED command does no harm. An unlock command while the locker is already open does nothing.
- After an unlock, the device script locks the latch again after 60 s and publishes status `locker: locked`.

## InfluxDB measurements

InfluxDB 2, in Docker on the Pi. It is the only database.

- One bucket: `pollinator`. Retention: never (keep all data for now).
- Tags are short text values used for filtering. Fields are the values. Each point has the timestamp from the message (or the time of the action for `settings`, `operator_actions`, `rewards`).
- Only the FastAPI back end reads and writes these measurements. The web page gets the data as JSON from the back end (endpoints in [architecture.md](architecture.md#rest-endpoints)).

### `presses`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `presses` | `station_id`, `result` (`accepted` / `cooldown` / `daily_cap`) | `count` (int, always 1)<br/>`progress_count` (int, accepted presses in current cycle after this press)<br/>`temperature_c` (float, °C)<br/>`humidity_pct` (float, %)<br/>`light_pct` (float, %)<br/>`uv_index` (float, index)<br/>`pressure_hpa` (float, hPa)<br/>`soil_moisture_pct` (float, %)<br/>`motion_count_10min` (int, count)<br/>later: `gas_raw` (int, raw), `air_quality_raw` (int, raw) | Every press, accepted or rejected |

### `environment`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `environment` | `station_id` | `temperature_c` (float, °C)<br/>`humidity_pct` (float, %)<br/>`light_pct` (float, %)<br/>`uv_index` (float, index)<br/>`pressure_hpa` (float, hPa)<br/>`soil_moisture_pct` (float, %)<br/>later: `gas_raw`, `air_quality_raw` (int, raw) | Every `POST /readings`; interval per sensor from `.env` (set after Sprint 1 tests) |

### `footfall`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `footfall` | `station_id` | `motion_count` (int, count)<br/>`interval_s` (int, seconds) | Every `POST /readings` that includes a PIR count; interval from `.env` (set after Sprint 1 tests) |

### `rewards`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `rewards` | `station_id`, `trigger` (`target` / `manual`) | `presses_in_cycle` (int, count)<br/>`presses_per_plant` (int, count) | Each time the back end sends an unlock command |

### `pi_status`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `pi_status` | `station_id` | `cpu_temp_c` (float, °C)<br/>`cpu_load_1m` (float, load average)<br/>`disk_used_pct` (float, %) | Every Pi health message (every 5 min, from cron) |

### `settings`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `settings` | `station_id`, `source` (`env` / `web`) | `cooldown_s` (int, seconds)<br/>`daily_cap` (int, presses per day)<br/>`presses_per_plant` (int, count) | On first start (start values from `.env`, `source=env`) and on every change on the web page (`source=web`) |

- Each point holds all three values. The newest point is the current setting.
- Each change is also logged in `operator_actions`.

### `operator_actions`

| Measurement | Tags | Fields (type, unit) | Written when |
|---|---|---|---|
| `operator_actions` | `station_id`, `action` (`login` / `login_failed` / `settings_change` / `manual_unlock`) | `detail` (string, e.g. the changed values) | Every action on the web page |

- Records what and when only. There is one shared login, so there is no "who".
- Possible next step: separate accounts per person, then a `user` tag could be added.

Station status (online, locker state) is not stored in InfluxDB. The broker keeps the latest status (retained) and the back end keeps it in memory for `GET /status`.

Example in InfluxDB line protocol (one accepted press):

```
presses,station_id=deusto-ria-01,result=accepted count=1i,progress_count=7i,temperature_c=17.4,humidity_pct=62.0,light_pct=71.3,uv_index=2.1,pressure_hpa=1016.8,soil_moisture_pct=38.5,motion_count_10min=14i 1795174925000000000
```

Not yet defined: external weather and air quality data (issues #36, #47), edge AI anomaly flags (issue #48).

## Retention and privacy

- No personal data about visitors. No camera, no microphone, no names, no IP addresses, no phone IDs.
- The PIR sensor only gives counts. It cannot tell who walked past.
- A press stores only the time and the sensor values.
- No names or usernames are stored. The action log records what and when, not who.
- Retention: the bucket keeps all data ("never" expires) for now.
- The login password hash, the InfluxDB token and other secrets stay in `.env` on the Pi, never in the repo.
