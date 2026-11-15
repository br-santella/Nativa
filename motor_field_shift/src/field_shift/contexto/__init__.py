"""Contexto atual (informativo): consulta fontes oficiais sobre eventos climáticos/fitossanitários em curso.

NÃO prevê nada e NÃO altera ranking ou notas do motor. Cada fonte tem timeout, cache em disco e fallback
({"disponivel": False, "motivo": ...}); uma fonte que falha nunca derruba as outras.
"""
from __future__ import annotations

import concurrent.futures as cf
from typing import Any

from . import _base as B
from . import alertas_inmet, enso, mjo, pragas, smap

AVISO = ("Contexto informativo de fontes oficiais (NOAA, NASA, IDR-PR/ADAPAR). Não é previsão para o talhão e não "
         "altera o ranking nem a nota das rotações.")


def montar(lat: float, lon: float, semeadura: str = "01/02", cache_only: bool = False) -> dict[str, Any]:
    """Contexto para um ponto (centroide do talhão) dentro do Oeste do PR. Nunca levanta exceção por falha de fonte."""
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
            except Exception as exc:  # defesa extra: cada fonte já é "segura"
                out[k] = B.indisponivel(f"{type(exc).__name__}: {exc}"[:300], B.fonte(k, ""))
    return {"consultado_em": B.agora_iso(), "aviso": AVISO,
            "local": {"lat": lat, "lon": lon, "municipio": nome_mun, "celula_clima": celula, "semeadura_safrinha": semeadura},
            **out}
