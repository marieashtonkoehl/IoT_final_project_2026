# deploy/

Setup files and instructions for running the station **on the Raspberry Pi**. Everything runs on the Pi.

| File | What it is |
|---|---|
| `compose.yaml` | Docker Compose file with two services: **InfluxDB 2** (bucket `pollinator`, retention "never", port `127.0.0.1:8086`) and **Mosquitto** (MQTT broker, port `127.0.0.1:1883`). Both restart automatically |
| `mosquitto/mosquitto.conf` | Mosquitto config: `listener 1883`, no login (safe: port bound to `127.0.0.1`), persistence on |
| `data/` | Created on the Pi. Database and broker data + logs. Ignored by git |
| `pollinator-backend.service` | systemd unit for the back end (FastAPI, `python -m app`): starts at boot, restarts on crash. See [Start everything after reboot](#start-everything-after-reboot-issue-37) |
| `pollinator-device.service` | systemd unit for the device script (`device/station.py`): starts at boot after the clock is synced, restarts on crash |
| crontab line *(added by #38)* | Runs the Pi status script in `scripts/` every 5 min with the project's `.venv` Python. See [Pi status script](#pi-status-script-cron-38) |

Secrets (token, passwords) come only from `.env` in the repo root (template: `.env.example`), never from files in this folder.

**How compose finds `.env`:** Docker Compose only reads a `.env` next to `compose.yaml`. So `deploy/.env` is a link to the root `.env` (step 3). One `.env` for the whole project, and every `docker compose` command works without extra options. The link is ignored by git.

---

## InfluxDB + Mosquitto in Docker (issue #24)

Run everything on the Pi, over SSH: `ssh haem@HAEM-Raspi5.local`.

- Every `docker compose` command runs inside `~/IoT_final_project_2026/deploy` (that is where `compose.yaml` is).
- `docker exec <container> …` commands work from any folder.

### 0. Docker

Check if Docker is installed:

```bash
docker --version          # what this does: prints the version if Docker is installed
docker compose version    # what this does: checks the Compose plugin
```

Both print a version → skip to "Start at boot" below. Otherwise install it (official script, supports 64-bit Raspberry Pi OS):

```bash
curl -fsSL https://get.docker.com -o get-docker.sh   # downloads Docker's install script
sudo sh get-docker.sh                                # installs Docker + Compose plugin
sudo usermod -aG docker $USER                        # lets you run docker without sudo
exit                                                 # log out; then ssh in again so the group change applies
```

Start at boot (do this even if Docker was already installed):

```bash
sudo systemctl enable --now docker   # starts Docker now and at every boot
systemctl is-enabled docker          # expected: enabled
docker ps                            # expected: an empty table, no "permission denied"
```

### 1. Port 1883 free?

An old Mosquitto installed directly on the Pi (Lab 5) would block port 1883.

```bash
sudo ss -tlnp | grep -E ':(1883|8086)\b'   # shows programs using these ports
```

- No output → ports are free, go on.
- A line with `mosquitto` → stop the old broker and keep it off after reboots:

```bash
sudo systemctl disable --now mosquitto   # stops it now and at boot
```

### 2. Get the code

First time:

```bash
cd ~
git clone https://github.com/marieashtonkoehl/IoT_final_project_2026.git   # copies repo to ~/IoT_final_project_2026
cd ~/IoT_final_project_2026
```

Already cloned:

```bash
cd ~/IoT_final_project_2026
git pull                          # gets latest version
```

Until #24 is merged, also run `git switch chore/24-influxdb-mosquitto-docker` (after `git pull`).

### 3. `.env` and the link

```bash
cd ~/IoT_final_project_2026
cp .env.example .env     # creates your own .env from the template (skip if .env exists)
openssl rand -hex 32     # prints a random value. Run twice: one for DB_TOKEN, one for DB_ADMIN_PASSWORD
nano .env                # fill in DB_TOKEN and DB_ADMIN_PASSWORD; check DB_ORG=pollinator-station, DB_BUCKET=pollinator, DB_ADMIN_USER=admin
```

Save in nano: `Ctrl+O`, `Enter`, `Ctrl+X`.

```bash
ln -s ../.env deploy/.env   # lets compose (in deploy/) read the root .env
ls -l deploy/.env           # expected: ... deploy/.env -> ../.env
```

!! InfluxDB reads these values **only on its very first start**. Changing the token or password in `.env` later does nothing, unless you start fresh (step 7)!! 

### 4. Data folders

```bash
cd ~/IoT_final_project_2026/deploy
mkdir -p data/influxdb/data data/influxdb/config data/mosquitto/data data/mosquitto/log   # creates the folders the containers store data in
sudo chown -R 1883:1883 data/mosquitto   # gives the Mosquitto folders to the container's user (id 1883), so it can write data and logs
```

Without the `chown`, Mosquitto stops with `Unable to open log file /mosquitto/log/mosquitto.log for writing`. InfluxDB needs no extra step. Because of this, deleting `data/` later needs `sudo`.

### 5. Start

```bash
cd ~/IoT_final_project_2026/deploy
docker compose up -d   # downloads the images (first time only) and starts both containers in the background
docker compose ps      # lists the containers
```

Expected: two lines, `influxdb` and `mosquitto`, both with STATUS `Up …`.

Check the logs:

```bash
docker compose logs influxdb --tail 20    # expected (first start): setup messages, then "Listening" … 8086
docker compose logs mosquitto --tail 20   # expected: "mosquitto version 2.x running"
```

An error like `required variable DB_TOKEN is missing` → that value is empty in `.env`, or the link from step 3 is missing.

### 6. Tests

**6.1 InfluxDB: bucket and retention**

```bash
docker exec influxdb influx bucket list   # lists the buckets
```

Expected: a line with name `pollinator` and retention `infinite`.

**6.2 InfluxDB: write and read a test point**

```bash
docker exec influxdb influx write --bucket pollinator "readme_test,station_id=test value=1"   # writes one point
docker exec influxdb influx query 'from(bucket: "pollinator") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "readme_test")'   # reads it back
```

Expected: a small table with `_measurement readme_test`, `_field value`, `_value 1`. No output from `write` means it worked.

**6.3 MQTT: publish and receive**

```bash
docker exec mosquitto mosquitto_pub -t pollinator/test -m "hello" -r   # publishes "hello", retained (the broker keeps it)
docker exec mosquitto mosquitto_sub -t pollinator/test -C 1 -W 5       # subscribes, prints 1 message, gives up after 5 s
```

Expected: `hello`.

Live version (optional, two SSH windows): in window 1 run `docker exec mosquitto mosquitto_sub -t pollinator/test -v`, in window 2 run `docker exec mosquitto mosquitto_pub -t pollinator/test -m "live"`. Window 1 prints `pollinator/test live`. Stop with `Ctrl+C`.

**6.4 Ports only reachable from the Pi**

```bash
sudo ss -tlnp | grep -E ':(1883|8086)\b'   # shows on which address each port listens
```

Expected: `127.0.0.1:8086` and `127.0.0.1:1883` (program `docker-proxy`). **Not** `0.0.0.0:…` or `*:…`.

**6.5 Reboot**

```bash
sudo reboot
```

Wait ~1 min, SSH in again, then:

```bash
cd ~/IoT_final_project_2026/deploy
docker compose ps                                                  # expected: influxdb and mosquitto, both "Up"
docker exec mosquitto mosquitto_sub -t pollinator/test -C 1 -W 5  # expected: hello (retained message survived = persistence works)
docker exec influxdb influx query 'from(bucket: "pollinator") |> range(start: -1d) |> filter(fn: (r) => r._measurement == "readme_test")'   # expected: the test point is still there
```

Clean up the test data:

```bash
docker exec mosquitto mosquitto_pub -t pollinator/test -r -n   # deletes the retained test message
docker exec influxdb influx delete --bucket pollinator --start 1970-01-01T00:00:00Z --stop 2100-01-01T00:00:00Z --predicate '_measurement="readme_test"'   # deletes the test point
```

### 7. Useful commands

Run inside `~/IoT_final_project_2026/deploy`:

| Command | What it does |
|---|---|
| `docker compose ps` | Show the containers and their state |
| `docker compose logs -f` | Follow the logs of both (`Ctrl+C` to stop watching) |
| `docker compose logs mosquitto --tail 50` | Last 50 log lines of one service |
| `docker compose restart` | Restart both containers |
| `docker compose stop` | Stop both. ! They stay stopped after a reboot until `docker compose up -d` |
| `docker compose up -d` | Start (again). Also applies changes to `compose.yaml` |
| `docker compose down` | Stop and remove the containers. Data in `data/` stays |

**Start fresh** **deletes all data: every press, reading and setting in InfluxDB, and all retained MQTT messages.** Only needed e.g. to change the InfluxDB token or password.

```bash
cd ~/IoT_final_project_2026/deploy
docker compose down   # stops and removes the containers
sudo rm -rf data      # deletes all database and broker data (sudo: the folders belong to the containers' users)
```

Then repeat steps 4 and 5.

---

## Start everything after reboot (issue #37)

What starts what:

| Program | Started by | Restarts on crash |
|---|---|---|
| InfluxDB, Mosquitto | Docker (`restart: unless-stopped` in `compose.yaml`), Docker itself starts at boot (step 0) | yes |
| Back end (FastAPI) | systemd: `pollinator-backend.service` | yes, after 5 s |
| Device script | systemd: `pollinator-device.service` | yes, after 5 s |
| Pi status script | cron, every 5 min (#38) | (runs again 5 min later) |

Both unit files assume user `haem` and the repo in `/home/haem/IoT_final_project_2026`. Different user or folder → change `User=`, `WorkingDirectory=` and `ExecStart=` in the file before copying it.

Before you start: steps 0–5 above are done, `.venv` exists with the packages of `backend/requirements.txt` and `device/requirements.txt`, and both programs work when started by hand (see `backend/README.md` and `device/README.md`). Stop any copy you started by hand (`Ctrl+C`), otherwise port 8000 is already in use.

### 1. Wait for the clock (once)

```bash
sudo systemctl enable systemd-time-wait-sync   # lets the device service wait until the clock is synced
```

Why: the Pi has no battery clock. Right after boot the time can be wrong, and presses sent with a wrong timestamp would break the cooldown rules.

### 2. Install the two services

```bash
cd ~/IoT_final_project_2026
sudo cp deploy/pollinator-backend.service deploy/pollinator-device.service /etc/systemd/system/   # systemd reads unit files from here
sudo systemctl daemon-reload                     # tells systemd to read the new files
sudo systemctl enable --now pollinator-backend   # starts it now and at every boot
sudo systemctl enable --now pollinator-device
```

After changing a unit file in `deploy/`: copy it again, `sudo systemctl daemon-reload`, then `sudo systemctl restart <service>`.

After `git pull` with new code: `sudo systemctl restart pollinator-backend pollinator-device` (the services keep running the old code until they restart).

### 3. Check

```bash
systemctl status pollinator-backend   # expected: "active (running)"; q to quit
systemctl status pollinator-device
curl http://localhost:8000/health     # expected: {"status":"ok"}
```

`activating (auto-restart)` or `failed` → the program crashed. The reason is in the log (next step).

### 4. Log files

Both programs write their log to the console (→ systemd journal) and to a file:

| File | Written by |
|---|---|
| `logs/backend.log` | back end, incl. uvicorn's start-up and access lines |
| `logs/device.log` | device script |
| `logs/pi_status.log` | Pi status script (#38) |

`logs/` is in the repo root (change it with `LOG_DIR` in `.env`), and is ignored by git. Each file is **rotated**: at 1 MB it is renamed to `.log.1` (up to `.log.5`) and the oldest is deleted, so the logs never take more than ~6 MB each and the SD card can't fill up.

```bash
tail -f ~/IoT_final_project_2026/logs/backend.log   # follow the file live (Ctrl+C to stop watching)
tail -n 50 ~/IoT_final_project_2026/logs/device.log # last 50 lines
journalctl -u pollinator-backend -f                 # follow the journal (also shows crashes before logging started)
journalctl -u pollinator-device --since "1 hour ago"
journalctl -u pollinator-device -b                  # everything since the last boot
```

If a service does not start at all, look in `journalctl`: the file is only written once the program runs (e.g. a wrong path in `ExecStart=` only appears in the journal).

### 5. Stop / turn off

```bash
sudo systemctl stop pollinator-device             # stop now; starts again at the next boot
sudo systemctl restart pollinator-backend         # stop and start again
sudo systemctl disable --now pollinator-device    # stop now AND don't start at boot any more
```

To start a program by hand for testing (e.g. `python device/station.py`), stop its service first. Two copies of the device script fight over the sensors, and two back ends over port 8000.

### 6. Reboot test

```bash
sudo reboot
```

Wait ~1 min, SSH in again, then:

```bash
systemctl is-active pollinator-backend pollinator-device docker   # expected: active, three times
docker compose -f ~/IoT_final_project_2026/deploy/compose.yaml ps # expected: influxdb and mosquitto "Up"
curl http://localhost:8000/health                                 # expected: {"status":"ok"}
tail -n 20 ~/IoT_final_project_2026/logs/device.log               # expected: new "Running." and "MQTT connected" lines with today's time
docker exec mosquitto mosquitto_sub -t 'pollinator/+/status' -C 1 -W 5   # expected: status with "online": true
```

Then press the button once: `logs/device.log` shows `Press … -> accepted` (or `cooldown`) and `logs/backend.log` a `POST /presses` line.

---

## Pi status script (cron, #38)

*Added by #38: the script does not exist yet. This is only the plan.*

Planned crontab line (`crontab -e` as user `haem`; the script name is set in #38):

```cron
*/5 * * * * cd /home/haem/IoT_final_project_2026 && .venv/bin/python scripts/pi_status.py > /dev/null 2>&1
```

- `*/5 * * * *` = every 5 minutes. cron starts at boot by itself, so nothing else is needed after a reboot.
- `> /dev/null 2>&1` throws away the console output: cron never rotates output files, so `>> file.log` would grow forever on the SD card.
- Note for #38: the script writes its own rotating log to `<LOG_DIR>/pi_status.log`, same setup as the back end and device (`RotatingFileHandler`, 1 MB, 5 backups).
