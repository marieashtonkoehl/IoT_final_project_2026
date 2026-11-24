"""The press rules: cooldown, daily cap and presses per plant.

Only small "pure" functions: they get everything they need as arguments
and return an answer. They do not read settings or storage themselves.
That makes them easy to test and means they don't change when the storage
moves from memory to InfluxDB.

All datetimes here are UTC and "aware" (they carry a time zone).
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# The daily cap follows the local calendar day in Bilbao.
LOCAL_TZ = ZoneInfo("Europe/Madrid")


def start_of_local_day_utc(moment_utc: datetime) -> datetime:
    """Return local midnight (Europe/Madrid) of the day `moment_utc` falls on, in UTC.

    Example (winter, Madrid = UTC+1):
        2026-11-20T11:42:05Z -> local 12:42 on 20 Nov
        -> local midnight 2026-11-20T00:00+01:00 -> 2026-11-19T23:00:00Z

    In summer (UTC+2) local midnight is 22:00Z the day before.
    zoneinfo knows the summer-time dates.
    """
    local = moment_utc.astimezone(LOCAL_TZ)
    local_midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc)


def is_in_cooldown(
    press_time: datetime,
    last_accepted_time: Optional[datetime],
    cooldown_seconds: int,
) -> bool:
    """True if the press comes too soon after the last *accepted* press.

    Rejected presses do not restart the cooldown.
    """
    if last_accepted_time is None:  # no accepted press yet
        return False
    seconds_since_last = (press_time - last_accepted_time).total_seconds()
    return seconds_since_last < cooldown_seconds


def is_daily_cap_reached(accepted_today: int, daily_cap: int) -> bool:
    """True if today's accepted presses already reached the cap."""
    return accepted_today >= daily_cap


def decide_press(
    press_time: datetime,
    last_accepted_time: Optional[datetime],
    accepted_today: int,
    cooldown_seconds: int,
    daily_cap: int,
) -> str:
    """Decide what happens to one press. The order of the checks matters:

    1. inside the cooldown  -> "cooldown"
    2. daily cap reached    -> "daily_cap"
    3. otherwise            -> "accepted"
    """
    if is_in_cooldown(press_time, last_accepted_time, cooldown_seconds):
        return "cooldown"
    if is_daily_cap_reached(accepted_today, daily_cap):
        return "daily_cap"
    return "accepted"


def is_plant_earned(count: int, presses_per_plant: int) -> bool:
    """True when the cycle is full and the cupboard should unlock."""
    return count >= presses_per_plant
