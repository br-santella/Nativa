"""Alertas INMET: NÃO implementado.

Verificado em 14/11/2026: alertas2.inmet.gov.br, alerts.inmet.gov.br, apiprevmet3.inmet.gov.br e portal.inmet.gov.br
encerram a conexão (Recv failure) a partir do ambiente de desenvolvimento, então o formato real do feed (CAP/RSS/JSON)
não pôde ser verificado. Sem verificação não há parser: devolve sempre indisponível. Reavaliar com acesso à rede do INMET.
"""
from __future__ import annotations

from typing import Any

from . import _base as B

FONTE = B.fonte("INMET — Avisos meteorológicos", "https://alertas2.inmet.gov.br/")
MOTIVO = ("Fonte não implementada: o feed de avisos do INMET não respondeu (conexão encerrada pelo servidor) a partir do "
          "ambiente de desenvolvimento e o formato não foi verificado.")


def consultar(*_, **__) -> dict[str, Any]:
    return B.indisponivel(MOTIVO, FONTE)
