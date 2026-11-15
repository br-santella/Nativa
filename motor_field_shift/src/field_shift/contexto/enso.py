"""ENSO: status oficial da NOAA CPC, tabela ONI e histórico por fase para a célula do talhão.

Fontes:
- Status/sinopse: https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml
  (HTML; texto após "ENSO Alert System Status:" e bloco "Synopsis:"). Não há JSON; extração por texto.
- ONI: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt (colunas SEAS YR TOTAL ANOM).

Convenção do ano agrícola (projeto): Y = jul/Y a jun/Y+1. A fase do ENSO do ano agrícola Y é a do
trimestre DJF (dez/Y, jan/Y+1, fev/Y+1), o pico do verão austral, que cai no meio do ciclo da soja
e antes da safrinha. Fase: ONI >= +0,5 El Niño; <= -0,5 La Niña; senão Neutro.
Os anos 1991–2024 são os mesmos do motor (indicadores_anuais.parquet).
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
FONTE = B.fonte("NOAA Climate Prediction Center (CPC) — ENSO Diagnostic Discussion e ONI", URL_STATUS)
LIMIAR = 0.5
FASES = ("El Niño", "La Niña", "Neutro")
INDICADORES = {  # nome amigável -> (rótulo, indicador do motor; {tag} = semeadura sem barra)
    "veranico_safrinha": ("veranico no safrinha", "veranico_safrinha_ge15"),
    "geada_safrinha": ("geada no safrinha", "geada_safrinha_semeadura_{tag}_le3"),
    "geada_trigo": ("geada no trigo", "geada_trigo_le3"),
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
        raise ValueError("tabela ONI vazia ou em formato inesperado")
    return out


def parse_status(htm: str) -> dict[str, Any]:
    txt = html.unescape(re.sub(r"<[^>]+>", " ", htm))
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"ENSO Alert System Status:\s*(.{3,40}?)\s+Synopsis:\s*(.+?)(?:\s{2,}|Compared to|$)", txt)
    if not m:
        raise ValueError("status do ENSO não encontrado na página do CPC")
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
    """{Y: {fase, oni}} usando DJF cuja rotulagem no arquivo é o ano Y+1."""
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
    out: dict[str, Any] = {"convencao": "ano agrícola Y = jul/Y a jun/Y+1; fase = ONI do trimestre DJF (dez/Y a fev/Y+1); "
                                        "El Niño ONI >= +0,5, La Niña <= -0,5, senão Neutro",
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
    return (f"Em anos de {fase} na série deste talhão, houve {ind['rotulo']} em {pf['anos_com_evento']} de {pf['n_anos']} anos "
            f"(contra {ind['frequencia_media_geral']:.0%} na média de {ind['n_anos_total']} anos).")


def consultar(celula_id: str | None, semeadura: str = "01/02", cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        if cache_only:
            bruto = B.ler_cache("enso", B.TTL_ENSO)
            if bruto is None:
                raise LookupError("sem cache; consulte GET /v1/contexto")
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
            "texto": (f"NOAA/CPC indica {fase} em curso (status do alerta: {st['status']}); último ONI "
                      f"{ult['trimestre']} {ult['ano']} = {ult['oni']:+.2f}. Previsão e status são da NOAA; "
                      "o ENSO não prevê o clima deste talhão."),
            "oni_historico_recente": oni[-12:],
        }
        if celula_id:
            try:
                hist = historico_por_fase(celula_id, semeadura, oni)
                out["historico_por_fase"] = hist
                frases = [frase_historico(fase, hist, k) for k in INDICADORES]
                out["frases_historico"] = [f for f in frases if f]
                out["frase_historico"] = out["frases_historico"][0] if out["frases_historico"] else None
                out["aviso_historico"] = ("Cerca de 10 anos por fase: diferenças pequenas entre fases podem ser ruído "
                                          "amostral; é frequência histórica, não previsão.")
            except Exception as exc:
                out["historico_por_fase"] = {"disponivel": False, "motivo": f"{type(exc).__name__}: {exc}"[:200]}
        return out

    return B.seguro("enso", FONTE, _fn)
