"""Where the back end keeps its state. FOR NOW: IN MEMORY ONLY.

Everything here is lost when the back end restarts. Later these functions will query and write InfluxDB instead.
main.py and rules.py only call the functions below, so swapping the inside
of this file is enough: they won't need to change.

What we keep:
- the time of the last accepted press (for the cooldown)
- the times of today's accepted presses (for the daily cap)
- the progress count (accepted presses since the last unlock)
"""

from datetime import datetime
from typing import List, Optional

# Module-level variables = the in-memory "database".
_last_accepted_time: Optional[datetime] = None
_accepted_times: List[datetime] = []
_progress_count: int = 0


def get_last_accepted_time() -> Optional[datetime]:
    """Time of the last accepted press, or None if there is none yet."""
    # TODO(InfluxDB): newest point in `presses` with tag result=accepted.
    return _last_accepted_time


def count_accepted_since(since_utc: datetime) -> int:
    """How many presses were accepted at or after `since_utc`.

    main.py passes local midnight (converted to UTC), so this is
    "accepted presses today".
    """
    # TODO(InfluxDB): count points in `presses` with result=accepted since `since_utc`.
    global _accepted_times
    # Forget presses from earlier days, so the list doesn't grow forever.
    _accepted_times = [t for t in _accepted_times if t >= since_utc]
    return len(_accepted_times)


def record_accepted_press(press_time: datetime) -> None:
    """Remember an accepted press (for the cooldown and the daily cap)."""
    global _last_accepted_time
    _last_accepted_time = press_time
    _accepted_times.append(press_time)


def get_progress_count() -> int:
    """Accepted presses since the last unlock."""
    # TODO(InfluxDB): on start, restore from `progress_count` of the newest `presses` point.
    return _progress_count


def set_progress_count(count: int) -> None:
    """Store a new progress count (e.g. +1, or 0 after an unlock)."""
    global _progress_count
    _progress_count = count


def reset() -> None:
    """Forget everything. Used by the tests to start each test from zero."""
    global _last_accepted_time, _accepted_times, _progress_count
    _last_accepted_time = None
    _accepted_times = []
    _progress_count = 0
