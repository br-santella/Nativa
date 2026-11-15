"""Current context (informative): queries official sources about ongoing climate/plant-health events.

It does NOT forecast anything and does NOT change the engine ranking or scores. Each source has a timeout, a disk cache and a fallback
({"disponivel": False, "motivo": ...}); a failing source never brings down the others.
"""
from __future__ import annotations

import concurrent.futures as cf
from typing import Any

from . import _base as B
from . import inmet_alerts, enso, mjo, pests, smap

WARNING = ("Contexto informativo de fontes oficiais (NOAA, NASA, IDR-PR/ADAPAR). Não é previsão para o talhão e não "
         "altera o ranking nem a nota das rotações.")


def build(lat: float, lon: float, sowing: str = "01/02", cache_only: bool = False) -> dict[str, Any]:
    """Context for a point (field centroid) inside Paraná. Never raises because of a source failure."""
    from field_shift.climate.lookup import indicators_for

    try:
        info = indicators_for(lat, lon) or {}
    except Exception:
        info = {}
    cell = (info.get("celula") or {}).get("ponto_id")
    mun = info.get("municipio") or {}
    mun_name = mun.get("nome")
    tasks = {
        "enso": lambda: enso.query_source(cell, sowing, cache_only),
        "smap": lambda: smap.query_source(lat, lon, cache_only),
        "mjo": lambda: mjo.query_source(cache_only),
        "pragas": lambda: pests.query_source(lat, lon, mun_name, cache_only),
        "alertas_inmet": lambda: inmet_alerts.query_source(),
    }
    out: dict[str, Any] = {}
    with cf.ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        futs = {k: ex.submit(fn) for k, fn in tasks.items()}
        for k, fut in futs.items():
            try:
                out[k] = fut.result()
            except Exception as exc:  # extra safety: each source is already "safe"
                out[k] = B.unavailable(f"{type(exc).__name__}: {exc}"[:300], B.source(k, ""))
    return {"consultado_em": B.now_iso(), "aviso": WARNING,
            "local": {"lat": lat, "lon": lon, "municipio": mun_name, "celula_clima": cell, "semeadura_safrinha": sowing},
            **out}
