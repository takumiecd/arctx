"""Who the local servers answer to.

Binding to loopback is not a security model once a browser is involved: every
page the user visits can send requests to 127.0.0.1, and these servers have
write routes. These tests pin both halves of the defence — the Origin check
(cross-site requests) and the Host check (DNS rebinding) — and, just as
important, that ordinary local use still works.
"""

from __future__ import annotations

from arctx.serve.guard import RequestGuard, guard_from_cors_option, is_loopback


class TestLoopbackDetection:
    def test_the_names_that_mean_this_machine(self):
        for value in ("localhost", "127.0.0.1", "http://127.0.0.1:8787",
                      "http://localhost:5173", "[::1]", "http://[::1]:8787"):
            assert is_loopback(value), value

    def test_names_that_do_not(self):
        for value in ("evil.example", "https://evil.example",
                      "http://127.0.0.1.evil.example", "https://localhost.evil.example"):
            assert not is_loopback(value), value


class TestDefaultPolicy:
    """No --cors-origin: loopback only."""

    guard = RequestGuard()

    def test_a_website_is_refused(self):
        assert self.guard.reject(origin="https://evil.example", host="127.0.0.1:8787")

    def test_refusal_survives_a_simple_request(self):
        """A text/plain POST needs no preflight, so the check must be server-side.

        Withholding Access-Control-Allow-Origin only hides the response; the
        write would still land. This is why `reject` exists at all.
        """
        assert self.guard.reject(origin="https://evil.example", host="localhost:8787")

    def test_a_rebound_host_is_refused(self):
        """DNS rebinding sends no Origin at all — the page really is same-origin."""
        assert self.guard.reject(origin=None, host="attacker.example")

    def test_the_gui_itself_is_served(self):
        assert self.guard.reject(origin="http://127.0.0.1:8787", host="127.0.0.1:8787") is None

    def test_a_local_dev_server_is_served(self):
        assert self.guard.reject(origin="http://localhost:5173", host="localhost:8787") is None

    def test_a_request_with_no_origin_is_served(self):
        """curl, the CLI, anything that is not a browser."""
        assert self.guard.reject(origin=None, host="127.0.0.1:8787") is None

    def test_no_cors_header_for_a_same_origin_request(self):
        assert self.guard.acao(None) is None

    def test_cors_header_echoes_the_caller_not_a_star(self):
        assert self.guard.acao("http://localhost:5173") == "http://localhost:5173"

    def test_no_cors_header_for_a_refused_origin(self):
        assert self.guard.acao("https://evil.example") is None


class TestExplicitWidening:
    def test_a_named_origin_is_allowed(self):
        guard = guard_from_cors_option("https://ok.example")
        assert guard.reject(origin="https://ok.example", host="localhost") is None
        assert guard.acao("https://ok.example") == "https://ok.example"
        assert guard.reject(origin="https://evil.example", host="localhost")

    def test_several_origins(self):
        guard = guard_from_cors_option("https://a.example, https://b.example")
        assert guard.reject(origin="https://b.example", host="localhost") is None

    def test_star_still_opens_everything_when_asked_for(self):
        guard = guard_from_cors_option("*")
        assert guard.allow_any_origin
        assert guard.reject(origin="https://evil.example", host="whatever.example") is None
        assert guard.acao("https://evil.example") == "*"

    def test_the_default_is_not_star(self):
        assert not guard_from_cors_option(None).allow_any_origin
        assert not guard_from_cors_option("").allow_any_origin
