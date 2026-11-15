"""INMET alerts: NOT implemented.

Checked on 14/11/2026: alertas2.inmet.gov.br, alerts.inmet.gov.br, apiprevmet3.inmet.gov.br and portal.inmet.gov.br
close the connection (Recv failure) from the development environment, so the real feed format (CAP/RSS/JSON)
could not be verified. Without verification there is no parser: it always returns unavailable. Re-evaluate with access to the INMET network.
"""
from __future__ import annotations

from typing import Any

from . import _base as B

FONTE = B.fonte("INMET — Avisos meteorológicos", "https://alertas2.inmet.gov.br/")
MOTIVO = ("Source not implemented: the INMET warnings feed did not respond (connection closed by the server) from the "
          "development environment and the format was not verified.")


def consultar(*_, **__) -> dict[str, Any]:
    return B.indisponivel(MOTIVO, FONTE)
