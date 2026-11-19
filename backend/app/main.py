from fastapi import FastAPI

from rules.conditions import pollinator_level, air_quality_level

app = FastAPI(title="IoT backend")

# TODO: replace with the real storage when it is ready.
# For now this is a fake "latest reading" so we can try the endpoint.
LATEST_READING = {
    "temperature": 24.0,   # deg C
    "humidity": 50.0,      # %
    "light_pct": 80.0,     # % (light sensor)
    "tvoc": 100,           # ppb
    "eco2": 600,           # ppm
}


def get_latest_reading():
    return LATEST_READING


@app.get("/conditions")
def get_conditions():
    r = get_latest_reading() or {}
    return {
        "pollinator_conditions": pollinator_level(
            r.get("temperature"), r.get("light_pct"), r.get("humidity")
        ),
        "air_quality": air_quality_level(r.get("tvoc"), r.get("eco2")),
    }