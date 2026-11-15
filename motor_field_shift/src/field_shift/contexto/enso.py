"""ENSO: official NOAA CPC status, the ONI table and the per-phase history for the field's cell.

Sources:
- Status/synopsis: https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml
  (HTML; text after "ENSO Alert System Status:" and the "Synopsis:" block). There is no JSON; extraction from text.
- ONI: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt (columns SEAS YR TOTAL ANOM).

Agricultural-year convention (project): Y = Jul/Y to Jun/Y+1. The ENSO phase of agricultural year Y is the one of
the DJF quarter (Dec/Y, Jan/Y+1, Feb/Y+1), the peak of the austral summer, which falls mid soybean cycle
and before the off-season. Phase: ONI >= +0.5 El Niño; <= -0.5 La Niña; otherwise Neutro.
The years 1991–2024 are the same as the engine's (indicadores_anuais.parquet).
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from typing import Any

import pandas as pd

from . import _base as B

URL_STATUS = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
URL_ONI = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
FONTE = B.fonte("NOAA Climate Prediction Center (CPC) — ENSO Diagnostic Discussion and ONI", URL_STATUS)
LIMIAR = 0.5
FASES = ("El Niño", "La Niña", "Neutro")
INDICADORES = {  # friendly name -> (label, engine indicator; {tag} = sowing date without the slash)
    "veranico_safrinha": ("off-season dry spell", "veranico_safrinha_ge15"),
    "geada_safrinha": ("off-season frost", "geada_safrinha_semeadura_{tag}_le3"),
    "geada_trigo": ("wheat frost", "geada_trigo_le3"),
}


def classificar(oni: float) -> str:
    return "El Niño" if oni >= LIMIAR else "La Niña" if oni <= -LIMIAR else "Neutro"


def parse_oni(txt: str) -> list[dict[str, Any]]:
    out = []
    for ln in txt.splitlines():
        p = ln.split()
        if len(p) == 4 and p[0].isalpha() and p[1].isdigit():
            try:
                out.append({"trimestre": p[0], "ano": int(p[1]), "oni": float(p[3])})
            except ValueError:
                pass
    if not out:
        raise ValueError("ONI table empty or in an unexpected format")
    return out


def parse_status(htm: str) -> dict[str, Any]:
    txt = html.unescape(re.sub(r"<[^>]+>", " ", htm))
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"ENSO Alert System Status:\s*(.{3,40}?)\s+Synopsis:\s*(.+?)(?:\s{2,}|Compared to|$)", txt)
    if not m:
        raise ValueError("ENSO status not found on the CPC page")
    status = m.group(1).strip()
    sinopse = m.group(2).strip()
    emitido = re.search(r"issued by.*?(\d{1,2} [A-Z][a-z]+ \d{4})", txt)
    prox = re.search(r"next ENSO Diagnostics? Discussion is scheduled for (\d{1,2} [A-Z][a-z]+ \d{4})", txt)
    pct = re.findall(r"(?:greater than a |about |~)?(\d{2,3})% chance", sinopse)
    return {"status": status, "sinopse": sinopse, "emitido_em": emitido.group(1) if emitido else None,
            "proximo_boletim": prox.group(1) if prox else None, "percentuais_citados": [int(x) for x in pct]}


def fase_do_status(status: str, oni_recente: float | None) -> str:
    s = status.lower()
    if "el niño" in s and "advisory" in s:
        return "El Niño"
    if "la niña" in s and "advisory" in s:
        return "La Niña"
    return "Neutro"


def _busca() -> dict[str, Any]:
    return {"oni": parse_oni(B.baixar_texto(URL_ONI)), "status": parse_status(B.baixar_texto(URL_STATUS))}


def fase_por_ano_agricola(oni: list[dict]) -> dict[int, dict[str, Any]]:
    """{Y: {fase, oni}} using DJF, which the file labels as year Y+1."""
    djf = {r["ano"]: r["oni"] for r in oni if r["trimestre"] == "DJF"}
    return {y: {"fase": classificar(djf[y + 1]), "oni": djf[y + 1]} for y in range(1991, 2025) if (y + 1) in djf}


@lru_cache(maxsize=1)
def _anuais() -> pd.DataFrame:
    return pd.read_parquet(B.ROOT / "data/processed/clima/indicadores_anuais.parquet",
                           columns=["ponto_id", "ano", "indicador", "valor"])


def historico_por_fase(celula_id: str, semeadura: str, oni: list[dict], anuais: pd.DataFrame | None = None) -> dict[str, Any]:
    df = _anuais() if anuais is None else anuais
    fases = fase_por_ano_agricola(oni)
    tag = semeadura.replace("/", "")
    out: dict[str, Any] = {"convencao": "agricultural year Y = Jul/Y to Jun/Y+1; phase = ONI of the DJF quarter (Dec/Y to Feb/Y+1); "
                                        "El Niño ONI >= +0.5, La Niña <= -0.5, otherwise Neutro",
                           "anos_por_fase": {f: sorted(a for a, v in fases.items() if v["fase"] == f) for f in FASES},
                           "indicadores": {}}
    sub = df[df.ponto_id == celula_id]
    for chave, (rotulo, ind) in INDICADORES.items():
        s = sub[sub.indicador == ind.format(tag=tag)].dropna(subset=["valor"]).set_index("ano")["valor"]
        s = s[s.index.isin(fases)]
        if s.empty:
            out["indicadores"][chave] = {"rotulo": rotulo, "disponivel": False}
            continue
        por_fase = {}
        for f in FASES:
            anos = [a for a in s.index if fases[a]["fase"] == f]
            ev = int(round(s.loc[anos].sum())) if anos else 0
            por_fase[f] = {"n_anos": len(anos), "anos_com_evento": ev,
                           "frequencia": round(ev / len(anos), 3) if anos else None}
        out["indicadores"][chave] = {"rotulo": rotulo, "indicador_motor": ind.format(tag=tag),
                                     "n_anos_total": int(len(s)), "frequencia_media_geral": round(float(s.mean()), 3),
                                     "por_fase": por_fase}
    return out


def frase_historico(fase: str, hist: dict[str, Any], chave: str = "veranico_safrinha") -> str | None:
    ind = hist["indicadores"].get(chave)
    if not ind or "por_fase" not in ind:
        return None
    pf = ind["por_fase"][fase]
    if not pf["n_anos"]:
        return None
    return (f"In {fase} years in this field's series, there was {ind['rotulo']} in {pf['anos_com_evento']} of {pf['n_anos']} years "
            f"(vs {ind['frequencia_media_geral']:.0%} on average over {ind['n_anos_total']} years).")


def consultar(celula_id: str | None, semeadura: str = "01/02", cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        if cache_only:
            bruto = B.ler_cache("enso", B.TTL_ENSO)
            if bruto is None:
                raise LookupError("no cache; query GET /v1/contexto")
            cache = True
        else:
            bruto, cache = B.com_cache("enso", B.TTL_ENSO, _busca)
        oni, st = bruto["oni"], bruto["status"]
        ult = oni[-1]
        fase = fase_do_status(st["status"], ult["oni"])
        out: dict[str, Any] = {
            "do_cache": cache,
            "status_alerta": st["status"],
            "fase_atual": fase,
            "oni_ultimo": {"trimestre": ult["trimestre"], "ano": ult["ano"], "oni": ult["oni"],
                           "classe": classificar(ult["oni"])},
            "boletim": {"emitido_em": st["emitido_em"], "proximo": st["proximo_boletim"],
                        "sinopse_original_en": st["sinopse"], "percentuais_citados": st["percentuais_citados"]},
            "texto": (f"NOAA/CPC indicates {fase} under way (alert status: {st['status']}); latest ONI "
                      f"{ult['trimestre']} {ult['ano']} = {ult['oni']:+.2f}. Forecast and status are NOAA's; "
                      "ENSO does not forecast this field's climate."),
            "oni_historico_recente": oni[-12:],
        }
        if celula_id:
            try:
                hist = historico_por_fase(celula_id, semeadura, oni)
                out["historico_por_fase"] = hist
                frases = [frase_historico(fase, hist, k) for k in INDICADORES]
                out["frases_historico"] = [f for f in frases if f]
                out["frase_historico"] = out["frases_historico"][0] if out["frases_historico"] else None
                out["aviso_historico"] = ("About 10 years per phase: small differences between phases may be sampling "
                                          "noise; this is historical frequency, not a forecast.")
            except Exception as exc:
                out["historico_por_fase"] = {"disponivel": False, "motivo": f"{type(exc).__name__}: {exc}"[:200]}
        return out

    return B.seguro("enso", FONTE, _fn)
