"""MQTT: the back end's connection to the Mosquitto broker (issue #34).

Topics and message formats: docs/data-model.md (section MQTT).

Receives (subscribes):
- pollinator/<station_id>/status    : device script online? locker open?
                                      Kept in memory for GET /status.
- pollinator/<station_id>/pi_health : CPU temperature, load, disk.
                                      Stored in InfluxDB (`pi_status`).
Sends (publishes), QoS 1, never retained:
- pollinator/<station_id>/cmd/led    : LED bar level
- pollinator/<station_id>/cmd/unlock : open the plant cupboard

paho-mqtt runs the network loop in its OWN background thread (loop_start).
So the callbacks below (on_connect, on_message, ...) do NOT run in the
thread of the web requests. That is why:
- the latest status is protected by a lock (_status_lock), and
- every incoming message is handled inside try/except: an error in the
  MQTT thread would otherwise stop all further messages, silently.
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Type, TypeVar

import paho.mqtt.client as paho
from pydantic import ValidationError

from app import rules, storage
from app.config import settings
from app.models import PiHealthIn, StationMessage, StationStatusIn

log = logging.getLogger(__name__)

# Each program on the Pi has its own client ID. The broker allows only one
# connection per ID: a second client with the same ID kicks out the first.
CLIENT_ID = "pollinator-backend"

# Wait time before trying to reconnect: starts at 1 s, doubles up to 30 s.
RECONNECT_MIN_DELAY_S = 1
RECONNECT_MAX_DELAY_S = 30

# The paho client. None = not started (e.g. in the tests, which put a fake here).
_client: Optional[paho.Client] = None

# Newest station status, or None if none has arrived since the back end started.
# Written by the MQTT thread, read by GET /status, so always use the lock.
_status_lock = threading.Lock()
_status: Optional[dict] = None


def topic(kind: str) -> str:
    """Full topic name, e.g. topic("status") -> "pollinator/deusto-ria-01/status"."""
    return f"pollinator/{settings.station_id}/{kind}"


def now_utc() -> datetime:
    """The server's current time in UTC. A separate function so the tests can fix it."""
    return datetime.now(timezone.utc)



# Start and stop (called from the FastAPI lifespan in main.py)


def start() -> None:
    """Connect to the broker in the background. Never blocks, never crashes.

    connect_async() only remembers where to connect. The real connection is
    made by paho's background thread (loop_start). If the broker is down,
    that thread keeps trying (1 s, 2 s, 4 s ... max 30 s), also for the very
    first connection. So the back end starts even without the broker, like
    it starts without InfluxDB.
    """
    global _client
    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(RECONNECT_MIN_DELAY_S, RECONNECT_MAX_DELAY_S)
    try:
        client.connect_async(settings.broker_host, settings.broker_port, keepalive=30)
    except ValueError as error:  # e.g. empty BROKER_HOST in .env
        log.error("MQTT not started, check BROKER_HOST / BROKER_PORT in .env: %s", error)
        return
    client.loop_start()
    _client = client
    log.info("MQTT: connecting to %s:%s", settings.broker_host, settings.broker_port)


def stop() -> None:
    """Disconnect cleanly and stop the background thread (when the back end stops)."""
    global _client
    if _client is None:
        return
    _client.disconnect()
    _client.loop_stop()  # waits until paho's thread has ended
    _client = None



# Callbacks (run in paho's background thread)


def on_connect(client, userdata, flags, reason_code, properties) -> None:
    """Connected (first time or after a reconnect): subscribe.

    Subscribing here, and not once in start(), matters: the broker forgets
    our subscriptions when the connection drops (clean session), so after
    every reconnect we must subscribe again, or we would receive nothing.
    """
    if reason_code.is_failure:
        log.warning("MQTT: broker refused the connection: %s", reason_code)
        return
    log.info("MQTT: connected, subscribing to status and pi_health")
    client.subscribe([(topic("status"), 0), (topic("pi_health"), 0)])


def on_disconnect(client, userdata, flags, reason_code, properties) -> None:
    """Connection lost. paho reconnects on its own, we only log it."""
    if reason_code.is_failure:
        log.warning("MQTT: connection to broker lost (%s), reconnecting", reason_code)


def on_message(client, userdata, message) -> None:
    handle_message(message.topic, message.payload)


def handle_message(message_topic: str, payload: bytes) -> None:
    """Handle one incoming message. A plain function, so the tests can call it.

    Bad messages are logged and ignored. Nothing in here may raise: an error
    would end up in paho's thread and could stop all further messages.
    """
    try:
        if message_topic == topic("status"):
            _handle_status(payload)
        elif message_topic == topic("pi_health"):
            _handle_pi_health(payload)
        else:
            log.warning("MQTT: ignored message on unexpected topic %s", message_topic)
    except Exception:
        # Last safety net for a bug in our own code: log it with the full
        # error (traceback), but keep the MQTT thread alive.
        log.exception("MQTT: error while handling a message on %s, ignored", message_topic)


Message = TypeVar("Message", bound=StationMessage)


def _parse(model: Type[Message], message_topic: str, payload: bytes) -> Optional[Message]:
    """Check one message with its Pydantic model. None (and a warning) if it is bad.

    Same checks as the REST endpoints: valid JSON with exactly the right
    fields, our own station_id, timestamp not too far in the future.
    """
    try:
        message = model.model_validate_json(payload)
    except ValidationError as error:
        # One short line per problem, e.g. "online: Field required".
        problems = "; ".join(
            f"{'.'.join(str(part) for part in e['loc']) or 'message'}: {e['msg']}"
            for e in error.errors()
        )
        log.warning("MQTT: ignored bad message on %s: %s", message_topic, problems)
        return None

    if message.station_id != settings.station_id:
        log.warning(
            "MQTT: ignored message on %s from unknown station_id '%s' (this back end serves '%s')",
            message_topic, message.station_id, settings.station_id,
        )
        return None

    # No timestamp (status last will): nothing to check, receive time is used.
    if message.timestamp is None:
        return message

    ahead = rules.seconds_ahead(message.timestamp, now_utc())
    if ahead > settings.max_future_skew_seconds:
        log.warning(
            "MQTT: ignored message on %s: timestamp %s is %d s ahead of server time (max %d s)",
            message_topic, message.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ahead, settings.max_future_skew_seconds,
        )
        return None

    return message


def _handle_status(payload: bytes) -> None:
    global _status
    status = _parse(StationStatusIn, topic("status"), payload)
    if status is None:
        return

    # The last will is fixed when the device connects: only station_id and
    # "online": false, no timestamp, no locker. Fill the gaps here.
    if status.timestamp is None or status.locker is None:
        log.info("MQTT: station status without timestamp/locker (last will?), using receive time")
    # Whole seconds, like the timestamps the device sends.
    received = now_utc().replace(microsecond=0)

    # The message that ARRIVED last wins, even if its timestamp is older.
    with _status_lock:
        last_locker = _status["locker"] if _status is not None else None
        _status = {
            "online": status.online,
            "locker": status.locker if status.locker is not None else last_locker,
            "timestamp": status.timestamp if status.timestamp is not None else received,
        }
        locker = _status["locker"]
    log.info("MQTT: station status online=%s locker=%s", status.online, locker)

    if status.online:
        # Device script just started or reconnected. Commands are not
        # retained, so it does not know the level: send it again.
        resend_led()


def _handle_pi_health(payload: bytes) -> None:
    health = _parse(PiHealthIn, topic("pi_health"), payload)
    if health is None:
        return
    try:
        storage.save_pi_health(health)
    except storage.StorageUnavailable as error:
        # The next message comes in 5 min anyway, so dropping one is OK.
        log.warning("MQTT: Pi health message dropped: %s", error)


def resend_led() -> None:
    """Send the current progress as LED level (e.g. after the device came online)."""
    try:
        level = storage.get_progress_count(settings.station_id, settings.presses_per_plant)
    except storage.StorageUnavailable as error:
        log.warning("MQTT: LED level not sent again, count unknown: %s", error)
        return
    send_led(level, settings.presses_per_plant)


def get_station_status() -> dict:
    """Newest status as {"online", "locker", "timestamp"}; all None if none yet."""
    with _status_lock:
        if _status is None:
            return {"online": None, "locker": None, "timestamp": None}
        return dict(_status)  # a copy, so nobody changes ours by accident


def forget_station_status() -> None:
    """Back to "no status received yet" (used by the tests)."""
    global _status
    with _status_lock:
        _status = None



# Sending commands (called by main.py, and by resend_led above)


def new_command_id() -> str:
    """A unique command ID, e.g. "c-3f2b9c...".

    The device ignores an ID it has already handled (QoS 1 may deliver a
    command twice). A counter would start again at 1 after a back end
    restart, and the device would then ignore the new commands. A random
    UUID is unique without remembering anything.
    """
    return "c-" + uuid.uuid4().hex


def _publish(kind: str, body: dict) -> bool:
    """Send one command. True if handed to the broker, False if not sent.

    If the broker is down, the command is SKIPPED, not queued. paho would
    otherwise keep it and send it after the reconnect, maybe minutes later:
    an old LED level, or the cupboard opening when nobody is there.
    """
    client = _client
    if client is None or not client.is_connected():
        log.warning("MQTT: command cmd/%s not sent: broker not connected", kind)
        return False
    body = {"command_id": new_command_id(), "timestamp": _timestamp_now(), **body}
    # (If the connection drops in the tiny moment between the check above and
    # this line, paho still queues the command. Rare enough to accept.)
    info = client.publish(topic(f"cmd/{kind}"), json.dumps(body), qos=1, retain=False)
    if info.rc != paho.MQTT_ERR_SUCCESS:
        log.warning("MQTT: command cmd/%s not sent: %s", kind, paho.error_string(info.rc))
        return False
    return True


def _timestamp_now() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def send_led(level: int, maximum: int) -> bool:
    """LED bar shows `level` of `maximum` (absolute, so a repeat does no harm)."""
    return _publish("led", {"level": level, "max": maximum})


def send_unlock(trigger: str) -> bool:
    """Open the plant cupboard. trigger: "target" (count reached) or "manual"."""
    return _publish("unlock", {"trigger": trigger})
