"""Start the back end with host and port from .env (API_HOST, API_PORT).

Run it (from the backend/ folder):  python -m app
The systemd service (deploy/pollinator-backend.service) uses this too.

For development, `uvicorn app.main:app --reload` still works; it just
ignores API_HOST / API_PORT and uses the --host / --port options instead.
"""

import uvicorn

from app.config import settings

if __name__ == "__main__":
    # "app.main:app" as text (not the object) so uvicorn imports it itself,
    # the same way as the uvicorn command does.
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port)
