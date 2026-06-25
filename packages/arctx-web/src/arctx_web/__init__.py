"""arctx-web — web GUI surface for ARCTX runs.

A thin Python package that serves the built React frontend (``web/``) together
with the ``arctx serve`` HTTP API, then opens a browser. The API logic itself is
reused from :mod:`arctx_cli.serve` so the data contract has one source of truth;
this package only adds static-asset serving and browser launching.
"""

__version__ = "0.3.0b3"
