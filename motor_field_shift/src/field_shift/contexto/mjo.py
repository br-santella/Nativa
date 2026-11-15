"""MJO: fase e amplitude atuais (índice ROMI, NOAA PSL; OLR em tempo quase real).

Fonte: https://psl.noaa.gov/mjo/mjoindex/romi.cpcolr.1x.txt (colunas: ano mês dia hora PC1 PC2 amplitude).
O RMM da BoM bloqueia acesso automatizado (HTTP 403) e o OMI do PSL está parado desde jun/2026, então
usamos o ROMI. Para obter a fase no padrão RMM (1–8): RMM1 = PC2 e RMM2 = -PC1 (convenção do PSL para
comparar OMI/ROMI com RMM). Amplitude < 1: MJO fraca/indefinida. Só informativo.
"""
from __future__ import annotations

import math
from typing import Any

from . import _base as B

URL = "https://psl.noaa.gov/mjo/mjoindex/romi.cpcolr.1x.txt"
FONTE = B.fonte("NOAA PSL — ROMI (Real-time OLR MJO Index)", URL)
FRASE = ("A MJO modula a chuva no Sul do Brasil em escala de semanas, com efeito modesto que depende da fase e da estação; "
         "é só contexto, não previsão para o talhão.")


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
        raise ValueError("arquivo ROMI vazio ou em formato inesperado")
    return linhas


def consultar(cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        if cache_only:
            bruto = B.ler_cache("mjo", B.TTL_MJO)
            if bruto is None:
                raise LookupError("sem cache; consulte GET /v1/contexto")
            cache = True
        else:
            bruto, cache = B.com_cache("mjo", B.TTL_MJO, lambda: parse(B.baixar_texto(URL)))
        u = bruto[-1]
        fase, amp = fase_rmm(u["pc1"], u["pc2"])
        forte = amp >= 1.0
        return {"do_cache": cache, "data_ultimo_dado": u["data"], "fase": fase if forte else None, "fase_calculada": fase,
                "amplitude": round(amp, 2), "ativa": forte,
                "texto": (f"NOAA PSL (ROMI) em {u['data']}: MJO {'ativa, fase ' + str(fase) if forte else 'fraca ou indefinida'} "
                          f"(amplitude {amp:.2f}). " + FRASE)}

    return B.seguro("mjo", FONTE, _fn)
