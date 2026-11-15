"""INMET alerts: NOT implemented.

Checked on 14/11/2026: alertas2.inmet.gov.br, alerts.inmet.gov.br, apiprevmet3.inmet.gov.br and portal.inmet.gov.br
close the connection (Recv failure) from the development environment, so the real feed format (CAP/RSS/JSON)
could not be checked. Without checking there is no parser: it always returns unavailable. Re-evaluate with access to the INMET network.
"""
from __future__ import annotations

from typing import Any

from . import _base as B

SOURCE = B.source("INMET — Avisos meteorológicos", "https://alertas2.inmet.gov.br/")
REASON = ("Fonte não implementada: o feed de avisos do INMET não respondeu (conexão encerrada pelo servidor) a partir do "
          "ambiente de desenvolvimento e o formato não foi verificado.")


def query_source(*_, **__) -> dict[str, Any]:
    return B.unavailable(REASON, SOURCE)
