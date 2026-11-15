"""Current context (informational): queries official sources about ongoing climate/plant-health events.

It forecasts NOTHING and does NOT change the engine's ranking or scores. Each source has a timeout, disk cache and fallback
({"disponivel": False, "motivo": ...}); a failing source never brings down the others.
"""
from __future__ import annotations

import concurrent.futures as cf
from typing import Any

from . import _base as B
from . import alertas_inmet, enso, mjo, pragas, smap

AVISO = ("Informational context from official sources (NOAA, NASA, IDR-PR/ADAPAR). It is not a forecast for the field and does not "
         "change the ranking or the score of the rotations.")


def montar(lat: float, lon: float, semeadura: str = "01/02", cache_only: bool = False) -> dict[str, Any]:
    """Context for a point (field centroid) inside Western Paraná. Never raises because of a source failure."""
    from field_shift.clima.lookup import indicadores_para

    try:
        info = indicadores_para(lat, lon) or {}
    except Exception:
        info = {}
    celula = (info.get("celula") or {}).get("ponto_id")
    mun = info.get("municipio") or {}
    nome_mun = mun.get("nome")
    tarefas = {
        "enso": lambda: enso.consultar(celula, semeadura, cache_only),
        "smap": lambda: smap.consultar(lat, lon, cache_only),
        "mjo": lambda: mjo.consultar(cache_only),
        "pragas": lambda: pragas.consultar(lat, lon, nome_mun, cache_only),
        "alertas_inmet": lambda: alertas_inmet.consultar(),
    }
    out: dict[str, Any] = {}
    with cf.ThreadPoolExecutor(max_workers=len(tarefas)) as ex:
        futs = {k: ex.submit(fn) for k, fn in tarefas.items()}
        for k, fut in futs.items():
            try:
                out[k] = fut.result()
            except Exception as exc:  # extra safety: each source is already "safe"
                out[k] = B.indisponivel(f"{type(exc).__name__}: {exc}"[:300], B.fonte(k, ""))
    return {"consultado_em": B.agora_iso(), "aviso": AVISO,
            "local": {"lat": lat, "lon": lon, "municipio": nome_mun, "celula_clima": celula, "semeadura_safrinha": semeadura},
            **out}
