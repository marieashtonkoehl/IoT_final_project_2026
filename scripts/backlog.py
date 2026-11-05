"""backlog.py: the product backlog of the Pollinator Station as data.

Single source for labels, milestones (sprints), user stories and tasks.
Used by setup_github.py to create everything on GitHub.
"""

REPO = "marieashtonkoehl/IoT_final_project_2026"

# name: (colour, description)
LABELS = {
    "user-story":      ("5319e7", "Feature from a user's point of view; split into tasks"),
    "device":          ("1d76db", "Raspberry Pi code: sensors and actuators (device/)"),
    "backend":         ("0e8a16", "API, rules, storage, external APIs (backend/)"),
    "frontend":        ("fbca04", "Web page and map (frontend/)"),
    "data":            ("c5def5", "Database, Grafana dashboards, analytics"),
    "infra":           ("bfd4f2", "Repo, board, Docker, systemd, release"),
    "documentation":   ("0075ca", "README, wiki, diagrams, reports"),
    "test":            ("d4c5f9", "Hardware tests and checks"),
    "stretch":         ("ededed", "Nice extra, only after planned work"),
    "priority:high":   ("b60205", "Needed for the next Sprint Review"),
    "priority:med":    ("d93f0b", "Needed for the MVP"),
    "priority:low":    ("f9d0c4", "Improves the project; MVP works without it"),
    "good first issue": ("7057ff", "Small and self-contained"),
}

# title: (due date, description)
MILESTONES = {
    "Sprint 1": ("2026-11-17", "Sprint Review 1 (17 Nov): repo + board, prioritised backlog, architecture, sensors/actuators tested"),
    "Sprint 2": ("2026-12-03", "Sprint Review 2 (3 Dec): full flow sensor → storage → dashboard, live"),
    "Sprint 3": ("2026-12-11", "MVP via ALUD + release tag v1.0 (11 Dec)"),
}

# key: (title, story text, labels)
STORIES = {
    "US1": ("US1: Press the button and see progress",
            "As a visitor, I press the button when I see a pollinator and an LED lights up towards the target.",
            ["user-story", "priority:high"]),
    "US2": ("US2: Every press stored with its conditions",
            "As the team, each press is stored with temperature, humidity, light, UV, air pressure, soil moisture, "
            "gas, air quality and footfall, so we can see when and in what conditions pollinators are noticed.",
            ["user-story", "priority:high"]),
    "US3": ("US3: Fair use — cooldown and daily cap",
            "As the team, repeat presses within the cooldown and presses above the daily cap are ignored, "
            "so one person cannot empty the lockers.",
            ["user-story", "priority:high"]),
    "US4": ("US4: Locker opens at the target",
            "As a visitor, when the target is reached a locker opens and I take a plant to plant in the bed.",
            ["user-story", "priority:high"]),
    "US5": ("US5: Partner dashboard",
            "As a partner (Ayuntamiento), I see presses and all logged conditions on a dashboard in several views "
            "(over time, by hour, against each condition, current gauges, plants unlocked).",
            ["user-story", "priority:high"]),
    "US6": ("US6: Station web page with conditions level",
            "As a visitor or partner, I see on a web page how close the next plant is and whether today's "
            "conditions are good / fair / poor for pollinators and for being outdoors.",
            ["user-story", "priority:med"]),
    "US7": ("US7: Operator alerts",
            "As an operator, I get an alert when a locker opens, lockers are empty, the bed needs water, "
            "air quality is poor, or presses look suspicious.",
            ["user-story", "priority:med"]),
    "US8": ("US8: Analytics report",
            "As the team, I see a report with averages, medians and trends, incl. before vs after planting.",
            ["user-story", "priority:med"]),
    "US9": ("US9: Station runs on its own",
            "As an operator, the station starts by itself after a reboot, keeps logs, and reports the Pi's "
            "health (CPU temperature, load).",
            ["user-story", "priority:med"]),
    "US10": ("US10: Open data for context",
             "As the team, we combine our data with weather, air-quality and green-space open data to explain "
             "press numbers and choose sites.",
             ["user-story", "priority:med"]),
}

# (sprint or None for stretch, title, labels, story key or None, [done-when items])
TASKS = [
    # ---------------- Sprint 1 ----------------
    ("Sprint 1", "Set up repo structure, .gitignore and .env.example", ["infra", "priority:high"], None,
     ["Folders device/, backend/, frontend/, dashboards/, deploy/, docs/, scripts/ exist", ".env is ignored by git"]),
    ("Sprint 1", "Set up the GitHub Project board", ["infra", "priority:high"], None,
     ["Columns Backlog / To do / In progress / In review / Done", "All issues added", "Board linked in README"]),
    ("Sprint 1", "Add collaborators (all members + dieguich) and make a first commit each", ["infra", "priority:high", "good first issue"], None,
     ["dieguich added as collaborator", "Every member has at least one commit from their own account"]),
    ("Sprint 1", "Architecture diagram and data model", ["documentation", "backend", "priority:high"], "US2",
     ["Diagram of device / back end / front end / database in docs/", "JSON press message and InfluxDB measurements defined"]),
    ("Sprint 1", "Wiring plan for every sensor and actuator", ["device", "documentation", "priority:high"], None,
     ["Table: component → port/pin → interface (GPIO / analogue / I2C)", "Photo of the setup in the wiki"]),
    ("Sprint 1", "Test button and LED bar", ["device", "test", "priority:high", "good first issue"], "US1",
     ["Test script in device/tests/", "Output pasted in the issue"]),
    ("Sprint 1", "Test PIR motion sensor", ["device", "test", "priority:high", "good first issue"], "US2",
     ["Test script in device/tests/", "Motion detected and counted"]),
    ("Sprint 1", "Test temperature & humidity sensor", ["device", "test", "priority:high", "good first issue"], "US2",
     ["Test script in device/tests/", "Interface (I2C/digital) noted in wiring plan"]),
    ("Sprint 1", "Test light and UV sensors", ["device", "test", "priority:high", "good first issue"], "US2",
     ["Test scripts in device/tests/", "Values converted to % / UV index"]),
    ("Sprint 1", "Test soil moisture sensor", ["device", "test", "priority:high", "good first issue"], "US2",
     ["Test script in device/tests/", "Dry vs wet soil values noted"]),
    ("Sprint 1", "Test barometer", ["device", "test", "priority:high", "good first issue"], "US2",
     ["Test script in device/tests/", "Pressure in hPa"]),
    ("Sprint 1", "Test servo latch", ["device", "test", "priority:med"], "US4",
     ["Open/closed angles chosen", "Test script in device/tests/"]),
    ("Sprint 1", "FastAPI skeleton: GET /health and POST /presses", ["backend", "priority:high"], "US2",
     ["Runs on the Pi", "/docs shows the OpenAPI page"]),
    ("Sprint 1", "InfluxDB + Grafana running", ["data", "infra", "priority:high"], "US5",
     ["Test data point visible in Grafana", "Setup steps in README / wiki"]),
    ("Sprint 1", "Plan Sprint 2 and prepare Sprint Review 1", ["documentation", "priority:high"], None,
     ["Sprint 2 issues in To do", "5-min run-through: board, repo, tested hardware"]),
    # ---------------- Sprint 2 ----------------
    ("Sprint 2", "Device script: on press, read all sensors and POST JSON", ["device", "priority:high"], "US2",
     ["One press → one JSON message with all readings", "Press visible on the server"]),
    ("Sprint 2", "Cooldown and daily cap on the server", ["backend", "priority:high"], "US3",
     ["Values from .env", "Rejected presses get a clear response", "Short cooldown for demos"]),
    ("Sprint 2", "LED bar shows progress from the server", ["device", "priority:high"], "US1",
     ["LED bar matches accepted presses", "Resets after a plant is unlocked"]),
    ("Sprint 2", "Store presses and periodic readings in InfluxDB", ["backend", "data", "priority:high"], "US2",
     ["Presses + conditions in InfluxDB", "Background readings every few minutes (for comparison)"]),
    ("Sprint 2", "Integrate gas sensor", ["device", "priority:med"], "US2",
     ["Test script + reading included in the press message"]),
    ("Sprint 2", "Integrate air quality sensor", ["device", "priority:med"], "US2",
     ["Test script + reading included in the press message"]),
    ("Sprint 2", "Qualitative levels: good / fair / poor", ["backend", "priority:med"], "US6",
     ["Pollinator conditions level (temp, light, UV, humidity)", "Air quality level", "GET /conditions returns both"]),
    ("Sprint 2", "Grafana dashboard v1", ["data", "frontend", "priority:high"], "US5",
     ["Presses per day", "Every condition over time", "Live gauges", "Dashboard JSON exported to dashboards/grafana/"]),
    ("Sprint 2", "MQTT: station status and Pi health", ["device", "priority:med"], "US9",
     ["Local Mosquitto broker", "Messages visible with mosquitto_sub"]),
    ("Sprint 2", "Web page v1: progress and conditions", ["frontend", "priority:high"], "US6",
     ["Served from the Pi", "Shows progress, today's presses, conditions level"]),
    ("Sprint 2", "Weather from an external API", ["backend", "priority:med"], "US10",
     ["Euskalmet (or Open-Meteo fallback) data stored with presses", "API key in .env"]),
    ("Sprint 2", "systemd services and log files", ["infra", "priority:med"], "US9",
     ["Device script and API start after reboot", "Logs written to file / journal"]),
    ("Sprint 2", "Report Pi health (CPU temperature, load)", ["device", "data", "priority:med"], "US9",
     ["Values in InfluxDB", "Panel in Grafana"]),
    ("Sprint 2", "Wiki pages: hardware, setup, API", ["documentation", "priority:med"], None,
     ["At least 3 wiki pages", "Linked from README"]),
    ("Sprint 2", "Prepare Sprint Review 2 (live full flow)", ["documentation", "priority:high"], None,
     ["Press → database → dashboard shown live in under 5 min"]),
    # ---------------- Sprint 3 ----------------
    ("Sprint 3", "Locker unlock cycle at the target", ["device", "backend", "priority:high"], "US4",
     ["Target reached → servo opens, buzzer, LED bar resets", "Works 3 times in a row"]),
    ("Sprint 3", "Alerts via Telegram or ntfy", ["backend", "priority:med"], "US7",
     ["Locker opened, lockers empty, Pi too hot", "Phone receives the notification"]),
    ("Sprint 3", "Soil moisture: 'please water the plants' reminder", ["device", "backend", "priority:med"], "US7",
     ["Threshold for dry soil", "LED signal and/or alert"]),
    ("Sprint 3", "Analytics report endpoint", ["backend", "data", "priority:med"], "US8",
     ["GET /report: daily averages, median presses per hour, weekly trend", "Shown on the web page"]),
    ("Sprint 3", "Grafana dashboard v2: comparisons and patterns", ["data", "frontend", "priority:med"], "US5",
     ["Presses vs temperature / UV / humidity / air quality", "Presses by hour of day", "Before vs after planting"]),
    ("Sprint 3", "Map of the station and Bilbao green spaces (Leaflet)", ["frontend", "priority:med"], "US10",
     ["OpenStreetMap + Leaflet on the web page", "Green spaces from Bilbao open data"]),
    ("Sprint 3", "Air quality open data (Open Data Euskadi)", ["backend", "priority:low"], "US10",
     ["Official air quality shown next to our sensor's value"]),
    ("Sprint 3", "Edge AI: flag suspicious press bursts", ["device", "data", "priority:low"], "US7",
     ["Model from Lab 6 approach (presses vs motion)", "Anomaly logged + alert"]),
    ("Sprint 3", "Full-cycle test and bug fixing", ["test", "priority:high"], None,
     ["Test checklist in the wiki", "All found bugs have issues"]),
    ("Sprint 3", "Final README", ["documentation", "priority:high"], None,
     ["Purpose, sensors/actuators, wiring, how to run, code structure", "A teammate can reproduce from it"]),
    ("Sprint 3", "Export OpenAPI docs", ["documentation", "backend", "priority:med"], None,
     ["docs/openapi.json in the repo", "Linked from README"]),
    ("Sprint 3", "Release v1.0", ["infra", "priority:high"], None,
     ["Tag v1.0 on 11 Dec", "GitHub release with short notes"]),
    ("Sprint 3", "ALUD submission: links, reflection, self-assessment", ["documentation", "priority:high"], None,
     ["TXT with repo + board links", "Half-page reflection + self-assessment", "groupXX_Final_Project_IoT.zip uploaded"]),
    ("Sprint 3", "Rehearse the 15-min demo", ["documentation", "priority:high"], None,
     ["Everyone presents a part", "Everyone can explain every part"]),
    # ---------------- Stretch ----------------
    (None, "Bluetooth: read station status from a phone", ["device", "stretch"], None,
     ["Status sent via BLE or serial Bluetooth", "Visible in a phone app"]),
    (None, "Text-to-speech 'thank you' when a plant unlocks", ["device", "stretch"], "US4",
     ["espeak-ng plays a short message"]),
    (None, "LEDs off at night (light sensor)", ["device", "stretch", "good first issue"], None,
     ["LEDs dim/off below a light threshold"]),
]
