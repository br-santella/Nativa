"""Soybean sanitary void and sowing calendar of Paraná by ADAPAR region (one of three windows per municipality).

Reads data/ref/vazio_sanitario_pr.json, built by ingest/vazio_sanitario_pr.py from the annual SDA/MAPA portaria. The windows change
every crop year: when the JSON is from an older crop, the response should say so (see `calendario_soja`'s `safra`).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REF = ROOT / "data/ref/vazio_sanitario_pr.json"
DEFAULT_REGION = 2  # Norte, Noroeste, Centro-Oeste e Oeste: the window the engine used before it became regional


@lru_cache(maxsize=1)
def _load() -> dict:
    ref = json.loads(REF.read_text())
    by_code = {c: r for r in ref["regioes"] for c in r["municipios"]}
    return dict(ref=ref, by_code=by_code, by_region={r["regiao"]: r for r in ref["regioes"]})


def _dm(ddmm: str) -> tuple[int, int]:
    d, m = map(int, ddmm.split("/"))
    return m, d


def in_window(ddmm: str, start: str, end: str) -> bool:
    """True if `ddmm` is inside [start, end]; the window may cross the new year (e.g. 20/09 to 20/01)."""
    x, a, b = _dm(ddmm), _dm(start), _dm(end)
    return a <= x <= b if a <= b else (x >= a or x <= b)


def calendario_soja(cod_ibge: int | str | None) -> dict:
    """Soybean calendar of the municipality: {regiao, nome, vazio, semeadura, safra, portaria, url, padrao}.

    `padrao` is True when the municipality is unknown (outside Paraná or no IBGE code) and the default region was used.
    """
    d = _load()
    reg = d["by_code"].get(int(cod_ibge)) if cod_ibge is not None else None
    padrao = reg is None
    reg = reg or d["by_region"][DEFAULT_REGION]
    ref = d["ref"]
    return dict(regiao=reg["regiao"], nome=reg["nome"], vazio=tuple(reg["vazio"]), semeadura=tuple(reg["semeadura"]),
                safra=ref["safra"], portaria=ref["portaria"], url=ref["url_adapar"], padrao=padrao)
