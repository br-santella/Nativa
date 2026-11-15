"""MJO: current phase and amplitude (ROMI index, NOAA PSL; near-real-time OLR).

Source: https://psl.noaa.gov/mjo/mjoindex/romi.cpcolr.1x.txt (columns: year month day hour PC1 PC2 amplitude).
The BoM RMM blocks automated access (HTTP 403) and the PSL OMI has been stalled since Jun/2026, so
we use ROMI. To get the phase in the RMM convention (1–8): RMM1 = PC2 and RMM2 = -PC1 (PSL convention to
compare OMI/ROMI with RMM). Amplitude < 1: weak/undefined MJO. Informative only.
"""
from __future__ import annotations

import math
from typing import Any

from . import _base as B

URL = "https://psl.noaa.gov/mjo/mjoindex/romi.cpcolr.1x.txt"
SOURCE = B.source("NOAA PSL — ROMI (Real-time OLR MJO Index)", URL)
PHRASE = ("A MJO modula a chuva no Sul do Brasil em escala de semanas, com efeito modesto que depende da fase e da estação; "
         "é só contexto, não previsão para o talhão.")


def rmm_phase(pc1: float, pc2: float) -> tuple[int, float]:
    rmm1, rmm2 = pc2, -pc1
    ang = math.degrees(math.atan2(rmm2, rmm1)) % 360
    phase = int(((ang - 180) % 360) // 45) + 1
    return phase, math.hypot(pc1, pc2)


def parse(txt: str) -> list[dict[str, Any]]:
    lines = []
    for ln in txt.splitlines()[-40:]:
        p = ln.split()
        if len(p) >= 7:
            try:
                lines.append({"data": f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}", "pc1": float(p[4]),
                               "pc2": float(p[5]), "amp": float(p[6])})
            except ValueError:
                pass
    if not lines:
        raise ValueError("arquivo ROMI vazio ou em formato inesperado")
    return lines


def query_source(cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        if cache_only:
            raw = B.read_cache("mjo", B.TTL_MJO)
            if raw is None:
                raise LookupError("sem cache; consulte GET /v1/contexto")
            cache = True
        else:
            raw, cache = B.com_cache("mjo", B.TTL_MJO, lambda: parse(B.download_text(URL)))
        u = raw[-1]
        phase, amp = rmm_phase(u["pc1"], u["pc2"])
        forte = amp >= 1.0
        return {"do_cache": cache, "data_ultimo_dado": u["data"], "fase": phase if forte else None, "fase_calculada": phase,
                "amplitude": round(amp, 2), "ativa": forte,
                "texto": (f"NOAA PSL (ROMI) em {u['data']}: MJO {'ativa, fase ' + str(phase) if forte else 'fraca ou indefinida'} "
                          f"(amplitude {amp:.2f}). " + PHRASE)}

    return B.insurance("mjo", SOURCE, _fn)
