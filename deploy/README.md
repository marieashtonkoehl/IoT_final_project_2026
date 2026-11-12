# deploy/

Setup files and instructions for running the station **on the Raspberry Pi** *(planned, files not added yet)*. Everything runs on the Pi.

- `compose.yaml`: one Docker Compose file with two services:
  - **InfluxDB 2**: bucket `pollinator`, retention "never"; data kept in a local volume (`deploy/data/`, ignored by git)
  - **Mosquitto**: MQTT broker, port 1883 bound to `127.0.0.1` only
- **systemd unit files**: one for the back end (FastAPI) and one for the device script, so both start when the Pi boots and restart if they crash. Logs go to the journal (`journalctl -u <service>`).
- **crontab line**: runs the Pi status script in `scripts/` every 5 minutes with the project's `.venv` Python. It publishes CPU temperature, load and disk to MQTT. Nothing else runs from cron.

Settings and secrets come from `.env` (template: `.env.example`), never from files in this folder.

Steps → main [README](../README.md#deployment-planned).
