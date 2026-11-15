"""Pest outbreaks: Asian soybean rust (automatic, IDR-PR) + hand-curated plant-health alerts.

AUTOMATIC — soybean rust monitoring (IDR-Paraná, former Emater), public WFS of the State GeoServer:
  https://geoserver.pr.gov.br/geoserver/ows  layer `emater:monitoramento_ferrugem_soja_pto_p4674`
  (GeoJSON; fields municipio, mesorregiao, regiao, safra, situacao "Sem esporos"/"Com esporos", dtpriespo, estfeno).
  The "Com esporos" status is spore capture in a collector, not confirmation of disease in the field. Point = seat/collector
  of the municipality. Count in the field's municipality, in the Oeste mesoregion and within a 100 km radius.
  The Consórcio Antiferrugem (consorcioantiferrugem.net) did not respond from this network; not used.

CURATED — `data/contexto/pragas_alertas.json` (versioned, updated by hand): corn leafhopper/corn stunt and
other ADAPAR/IDR-PR alerts, which only exist in PDF bulletins/dashboards without a documented API (CigarrinhaWeb:
https://cigarrinhaweb.com.br/). No scraping. Expired alerts (data + validade_dias) are ignored.
Informative only; does not change the score.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import _base as B

URL_WFS = "https://geoserver.pr.gov.br/geoserver/ows"
LAYER = "emater:monitoramento_ferrugem_soja_pto_p4674"
RUST_SOURCE = B.source("IDR-Paraná — monitoramento da ferrugem asiática da soja (GeoServer PR)", URL_WFS)
CURATED_SOURCE = B.source("ADAPAR / IDR-Paraná (alertas curados manualmente)", "https://cigarrinhaweb.com.br/")
RADIUS_KM = 100.0
CURATED_FILE = B.CURATED_DIR / "pragas_alertas.json"


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def current_season(today: date | None = None) -> str:
    h = today or date.today()
    y = h.year if h.month >= 7 else h.year - 1
    return f"{y}/{y + 1}"


def _km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def _fetch_rust(season: str) -> list[dict[str, Any]]:
    import requests

    r = requests.get(URL_WFS, timeout=B.TIMEOUT_HTTP, headers={"User-Agent": B.UA}, params={
        "service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": LAYER,
        "outputFormat": "application/json", "cql_filter": f"safra='{season}'"})
    r.raise_for_status()
    feats = r.json()["features"]
    out = []
    for f in feats:
        p, (lon, lat) = f["properties"], f["geometry"]["coordinates"][:2]
        out.append({"municipio": p.get("municipio"), "mesorregiao": p.get("mesorregiao"), "regiao": p.get("regiao"),
                    "situacao": p.get("situacao"), "data_esporos": p.get("dtpriespo") or None,
                    "estadio": p.get("estfeno"), "lat": lat, "lon": lon})
    return out


def _data_br(s: str | None) -> date | None:
    try:
        return datetime.strptime(s, "%d/%m/%Y").date() if s else None
    except ValueError:
        return None


def summarize_rust(points: list[dict], lat: float, lon: float, municipality: str | None, season: str) -> dict[str, Any]:
    def stats(sel: list[dict]) -> dict[str, Any]:
        com = [p for p in sel if p["situacao"] == "Com esporos"]
        dates = [d for d in (_data_br(p["data_esporos"]) for p in com) if d]
        return {"coletores": len(sel), "com_esporos": len(com),
                "ultima_deteccao": max(dates).strftime("%d/%m/%Y") if dates else None}

    mun = [p for p in points if municipality and _norm(p["municipio"]) == _norm(municipality)]
    oeste = [p for p in points if p["mesorregiao"] == "Oeste"]
    radius = [p for p in points if _km(lat, lon, p["lat"], p["lon"]) <= RADIUS_KM]
    out = {"safra": season, "municipio": {"nome": municipality, **stats(mun)}, "mesorregiao_oeste": stats(oeste),
           f"raio_{int(RADIUS_KM)}_km": stats(radius), "coletores_na_safra_no_estado": len(points)}
    r = out[f"raio_{int(RADIUS_KM)}_km"]
    if not points:
        out["texto"] = f"IDR-PR ainda não tem coletores de ferrugem lançados para a safra {season}."
    elif r["coletores"] == 0:
        out["texto"] = f"IDR-PR (safra {season}): sem coletores de ferrugem da soja num raio de {int(RADIUS_KM)} km do talhão."
    else:
        last = f"; última detecção em {r['ultima_deteccao']}" if r["ultima_deteccao"] else ""
        out["texto"] = (f"IDR-PR registra esporos de ferrugem asiática em {r['com_esporos']} de {r['coletores']} coletores num raio de "
                        f"{int(RADIUS_KM)} km (safra {season}{last}). Afeta a soja em curso; é só informação de contexto e não "
                        "altera a nota das rotações.")
    return out


def query_rust(lat: float, lon: float, municipality: str | None, cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        season = current_season()
        key = f"ferrugem_{season.replace('/', '_')}"
        if cache_only:
            points = B.read_cache(key, B.TTL_PESTS)
            if points is None:
                raise LookupError("sem cache; consulte GET /v1/contexto")
            cache = True
        else:
            points, cache = B.com_cache(key, B.TTL_PESTS, lambda: _fetch_rust(season))
        return {"do_cache": cache, **summarize_rust(points, lat, lon, municipality, season)}

    return B.insurance("pragas_ferrugem", RUST_SOURCE, _fn)


# ------------------------------------------------------------------------------------ curado
TEXTS = {
    "cigarrinha": "Atenção ao milho safrinha: rotações com cobertura reduzem a exposição.",
}
LEVEL_TXT = {"baixo": "baixa população", "moderado": "população moderada", "alto": "alta população"}


def _apply(alert: dict, municipality: str | None) -> bool:
    regs = [_norm(r) for r in alert.get("regiao", [])]
    return any(r in ("pr", "parana", "oeste do pr", "oeste") or (municipality and r == _norm(municipality)) for r in regs)


def _alert_text(a: dict) -> str:
    d = datetime.strptime(a["data"], "%Y-%m-%d").strftime("%d/%m")
    reg = ", ".join(a.get("regiao", [])) or "Paraná"
    pest = a["praga"]
    ind = LEVEL_TXT.get(a.get("nivel", ""), "ocorrência")
    extra = next((v for k, v in TEXTS.items() if k in _norm(pest)), f"Atenção a {a.get('cultura_afetada', 'a lavoura')}.")
    return f"{a['fonte']} indicam {ind} de {pest} no {reg} (boletim de {d}). {extra}"


def query_curated(municipality: str | None, today: date | None = None, file_path: Path | None = None) -> dict[str, Any]:
    def _fn():
        path_ = file_path or CURATED_FILE
        dados = json.loads(path_.read_text(encoding="utf-8"))
        h = today or date.today()
        current_items, expired = [], 0
        for a in dados.get("alertas", []):
            d = datetime.strptime(a["data"], "%Y-%m-%d").date()
            if h > d + timedelta(days=int(a.get("validade_dias", 30))):
                expired += 1
                continue
            if _apply(a, municipality):
                current_items.append({**a, "texto": _alert_text(a)})
        out = {"curado_manualmente": True, "alertas": current_items, "alertas_vencidos_ignorados": expired,
               "como_consultar": dados.get("fontes_monitoramento", []),
               "atualizado_em": dados.get("atualizado_em")}
        out["texto"] = (" ".join(a["texto"] for a in current_items) if current_items else
                        "Nenhum alerta fitossanitário curado vigente para esta região (arquivo atualizado à mão; "
                        "consulte a CigarrinhaWeb e a ADAPAR).")
        return out

    return B.insurance("pragas_curado", CURATED_SOURCE, _fn)


def query_source(lat: float, lon: float, municipality: str | None, cache_only: bool = False) -> dict[str, Any]:
    return {"ferrugem_soja": query_rust(lat, lon, municipality, cache_only),
            "alertas_curados": query_curated(municipality),
            "consultado_em": B.now_iso(), "disponivel": True,
            "fonte": B.source("IDR-PR (WFS) + ADAPAR/IDR-PR (curado)", URL_WFS)}
