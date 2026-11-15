"""MJO: current phase and amplitude (ROMI index, NOAA PSL; near-real-time OLR).

Source: https://psl.noaa.gov/mjo/mjoindex/romi.cpcolr.1x.txt (columns: year month day hour PC1 PC2 amplitude).
The BoM RMM blocks automated access (HTTP 403) and the PSL OMI has been stalled since Jun/2026, so
we use ROMI. To get the phase in the RMM standard (1–8): RMM1 = PC2 and RMM2 = -PC1 (PSL convention for
comparing OMI/ROMI with RMM). Amplitude < 1: weak/undefined MJO. Informational only.
"""
from __future__ import annotations

import math
from typing import Any

from . import _base as B

URL = "https://psl.noaa.gov/mjo/mjoindex/romi.cpcolr.1x.txt"
FONTE = B.fonte("NOAA PSL — ROMI (Real-time OLR MJO Index)", URL)
FRASE = ("The MJO modulates rainfall in southern Brazil on a scale of weeks, with a modest effect that depends on the phase and the season; "
         "it is context only, not a forecast for the field.")


def fase_rmm(pc1: float, pc2: float) -> tuple[int, float]:
    rmm1, rmm2 = pc2, -pc1
    ang = math.degrees(math.atan2(rmm2, rmm1)) % 360
    fase = int(((ang - 180) % 360) // 45) + 1
    return fase, math.hypot(pc1, pc2)


def parse(txt: str) -> list[dict[str, Any]]:
    linhas = []
    for ln in txt.splitlines()[-40:]:
        p = ln.split()
        if len(p) >= 7:
            try:
                linhas.append({"data": f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}", "pc1": float(p[4]),
                               "pc2": float(p[5]), "amp": float(p[6])})
            except ValueError:
                pass
    if not linhas:
        raise ValueError("ROMI file empty or in an unexpected format")
    return linhas


def consultar(cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        if cache_only:
            bruto = B.ler_cache("mjo", B.TTL_MJO)
            if bruto is None:
                raise LookupError("no cache; query GET /v1/contexto")
            cache = True
        else:
            bruto, cache = B.com_cache("mjo", B.TTL_MJO, lambda: parse(B.baixar_texto(URL)))
        u = bruto[-1]
        fase, amp = fase_rmm(u["pc1"], u["pc2"])
        forte = amp >= 1.0
        return {"do_cache": cache, "data_ultimo_dado": u["data"], "fase": fase if forte else None, "fase_calculada": fase,
                "amplitude": round(amp, 2), "ativa": forte,
                "texto": (f"NOAA PSL (ROMI) on {u['data']}: MJO {'active, phase ' + str(fase) if forte else 'weak or undefined'} "
                          f"(amplitude {amp:.2f}). " + FRASE)}

    return B.seguro("mjo", FONTE, _fn)
