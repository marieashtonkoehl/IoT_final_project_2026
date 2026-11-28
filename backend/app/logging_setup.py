"""Log to the console AND to a file (<LOG_DIR>/backend.log).

Called once at start-up, from the lifespan in main.py. Not at import time,
so the tests never write log files (conftest.py also turns it off).

When backend.log reaches 1 MB it is renamed to backend.log.1 (and so on, up to
.5) and the oldest is deleted. So the logs never use more than ~6 MB.
"""

import logging
from logging.handlers import RotatingFileHandler

from app.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 1_000_000  # 1 MB per file
BACKUP_COUNT = 5  # keep backend.log.1 ... backend.log.5

_done = False  # with --reload or a second start-up, don't add the handlers twice


def setup_logging() -> None:
    global _done
    if _done:
        return
    _done = True

    settings.log_dir.mkdir(parents=True, exist_ok=True)  # create logs/ if missing
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    file_handler = RotatingFileHandler(
        settings.log_dir / "backend.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Root logger: our own loggers (e.g. logging.getLogger("app.mqtt"))
    # end up here. INFO, so their info lines are shown, not only warnings.
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # uvicorn's loggers don't pass their lines on to the root logger, and
    # they already print to the console in their own format. So only add
    # the file here: the console output of uvicorn stays as it was.
    for name in ("uvicorn", "uvicorn.access"):
        logging.getLogger(name).addHandler(file_handler)

    logging.getLogger(__name__).info("Logging to %s", settings.log_dir / "backend.log")
