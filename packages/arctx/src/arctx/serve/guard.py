"""Who is allowed to talk to a local arctx server.

Both local servers bind to loopback, and binding to loopback was treated as
the whole security model: only someone on this machine can reach the port.
A browser breaks that assumption. Every page the user visits can send requests
to ``http://127.0.0.1:8787`` — it cannot read the reply without CORS, but the
request still arrives, and these servers have write routes (``POST /step`` /
``/attach`` / ``/cut``). With ``Access-Control-Allow-Origin: *`` it could read
the replies too, which made the whole run readable by any site.

Two checks, because they stop two different attacks:

* **Origin** stops cross-site requests. It has to be enforced server-side, not
  by handing out CORS headers: a ``text/plain`` POST is a CORS *simple
  request*, so the browser sends it with no preflight to ask permission with.
  Withholding ``Access-Control-Allow-Origin`` hides the response; it does not
  stop the write.

* **Host** stops DNS rebinding. A site can point a name it controls at
  127.0.0.1, at which point its page *is* same-origin with this server and
  sends no ``Origin`` header at all. The defence is to notice that the request
  arrived addressed to a name that is not ours.

The browser sets both headers and a page cannot forge either, which is what
makes them worth checking.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

#: Names that mean "this machine" — the only ones a local server answers to.
LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}
)


def _hostname(value: str) -> str:
    """The host part of a Host header or an origin, lowercased, port removed."""
    host = value.strip().lower()
    if "//" in host:
        host = urlsplit(host).netloc or host
    if host.startswith("["):  # IPv6 literal: [::1]:8787
        end = host.find("]")
        if end != -1:
            return host[: end + 1]
    return host.split(":", 1)[0]


def is_loopback(value: str) -> bool:
    return _hostname(value) in LOOPBACK_HOSTS


@dataclass(frozen=True)
class RequestGuard:
    """Decide whether one request may be served.

    ``allowed_origins`` are extra origins named explicitly by the operator
    (``--cors-origin``). Loopback origins are always allowed, so the bundled
    GUI and a ``vite`` dev server pointed straight at the API keep working
    without anyone opting into anything.
    """

    allowed_origins: tuple[str, ...] = ()

    @property
    def allow_any_origin(self) -> bool:
        return "*" in self.allowed_origins

    def reject(self, *, origin: str | None, host: str | None) -> str | None:
        """Return why the request must be refused, or ``None`` to serve it."""
        if host and not is_loopback(host) and not self._origin_allowed(f"//{host}"):
            return (
                f"refusing a request addressed to {host!r}: this server answers "
                "only as localhost. A name that resolves to 127.0.0.1 from "
                "somewhere else is how a website reaches a local server."
            )
        if origin and not self._origin_allowed(origin):
            return (
                f"refusing a cross-origin request from {origin!r}. Pass "
                "--cors-origin to allow it explicitly."
            )
        return None

    def acao(self, origin: str | None) -> str | None:
        """The ``Access-Control-Allow-Origin`` value for this request, if any.

        Echoes the caller's own origin rather than ``*`` so the header grants
        exactly what was checked. ``None`` means: send no CORS header, which is
        the right answer for a same-origin request.
        """
        if self.allow_any_origin:
            return "*"
        if origin and self._origin_allowed(origin):
            return origin
        return None

    def _origin_allowed(self, origin: str) -> bool:
        if self.allow_any_origin:
            return True
        if origin in self.allowed_origins:
            return True
        if is_loopback(origin):
            return True
        return any(
            allowed != "*" and _hostname(allowed) == _hostname(origin)
            for allowed in self.allowed_origins
        )


def guard_from_cors_option(cors_origin: str | None) -> RequestGuard:
    """Build a guard from the CLI's ``--cors-origin`` value.

    ``None`` (the default) means loopback only. A value is an explicit
    widening, including the ``*`` that used to be the default.
    """
    if not cors_origin:
        return RequestGuard()
    origins = tuple(part.strip() for part in cors_origin.split(",") if part.strip())
    return RequestGuard(allowed_origins=origins)
