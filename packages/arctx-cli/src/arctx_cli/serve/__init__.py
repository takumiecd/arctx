"""Local read/write HTTP API for a single run (``arctx serve``).

Two layers, mirroring the rest of the CLI:

- :mod:`arctx_cli.serve.api` — a pure, socket-free dispatcher
  ``dispatch(store, run_id, method, path, body, *, user_id, lane_id)``
  returning ``(status, body_dict)``. All routing and verb logic lives here so
  it is unit-testable without opening a socket.
- :mod:`arctx_cli.serve.server` — a thin ``http.server`` shell that feeds
  request bytes into :func:`dispatch` and writes JSON back, plus CORS handling
  so a separate frontend dev server can call it.

The API is intentionally stdlib-only: ``arctx-cli`` keeps its "depends only on
arctx" invariant, and ``arctx serve`` needs zero extra installs. The JSON shapes
are the same contract a FastAPI port would expose, so the backend can be swapped
without touching the frontend.
"""

from arctx_cli.serve.api import dispatch  # noqa: F401
from arctx_cli.serve.server import serve  # noqa: F401

__all__ = ["dispatch", "serve"]
