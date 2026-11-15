"""Pest outbreaks: Asian soybean rust (automatic, IDR-PR) + plant-health alerts curated by hand.

AUTOMATIC — soybean rust monitoring (IDR-Paraná, formerly Emater), public WFS of the State GeoServer:
  https://geoserver.pr.gov.br/geoserver/ows  layer `emater:monitoramento_ferrugem_soja_pto_p4674`
  (GeoJSON; fields municipio, mesorregiao, regiao, safra, situacao "Sem esporos"/"Com esporos", dtpriespo, estfeno).
  The "Com esporos" status is spore capture in a collector, not confirmation of disease in the field. Point = municipal
  seat/collector. Counts in the field's municipality, in the Western mesoregion and within a 100 km radius.
  The Consórcio Antiferrugem (consorcioantiferrugem.net) did not respond from this network; not used.

CURATED — `data/contexto/pragas_alertas.json` (versioned, updated by hand): corn leafhopper/corn stunt and
other ADAPAR/IDR-PR alerts, which only exist in PDF bulletins/dashboards without a documented API (CigarrinhaWeb:
https://cigarrinhaweb.com.br/). No scraping. Expired alerts (data + validade_dias) are ignored.
Informational only; does not change the score.
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
CAMADA = "emater:monitoramento_ferrugem_soja_pto_p4674"
FONTE_FERRUGEM = B.fonte("IDR-Paraná — Asian soybean rust monitoring (GeoServer PR)", URL_WFS)
FONTE_CURADO = B.fonte("ADAPAR / IDR-Paraná (alerts curated by hand)", "https://cigarrinhaweb.com.br/")
RAIO_KM = 100.0
ARQ_CURADO = B.CURADO_DIR / "pragas_alertas.json"


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def safra_atual(hoje: date | None = None) -> str:
    h = hoje or date.today()
    y = h.year if h.month >= 7 else h.year - 1
    return f"{y}/{y + 1}"


def _km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def _buscar_ferrugem(safra: str) -> list[dict[str, Any]]:
    import requests

    r = requests.get(URL_WFS, timeout=B.TIMEOUT_HTTP, headers={"User-Agent": B.UA}, params={
        "service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": CAMADA,
        "outputFormat": "application/json", "cql_filter": f"safra='{safra}'"})
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


def resumir_ferrugem(pontos: list[dict], lat: float, lon: float, municipio: str | None, safra: str) -> dict[str, Any]:
    def stats(sel: list[dict]) -> dict[str, Any]:
        com = [p for p in sel if p["situacao"] == "Com esporos"]
        datas = [d for d in (_data_br(p["data_esporos"]) for p in com) if d]
        return {"coletores": len(sel), "com_esporos": len(com),
                "ultima_deteccao": max(datas).strftime("%d/%m/%Y") if datas else None}

    mun = [p for p in pontos if municipio and _norm(p["municipio"]) == _norm(municipio)]
    oeste = [p for p in pontos if p["mesorregiao"] == "Oeste"]
    raio = [p for p in pontos if _km(lat, lon, p["lat"], p["lon"]) <= RAIO_KM]
    out = {"safra": safra, "municipio": {"nome": municipio, **stats(mun)}, "mesorregiao_oeste": stats(oeste),
           f"raio_{int(RAIO_KM)}_km": stats(raio), "coletores_na_safra_no_estado": len(pontos)}
    r = out[f"raio_{int(RAIO_KM)}_km"]
    if not pontos:
        out["texto"] = f"IDR-PR has no rust collectors registered yet for the {safra} season."
    elif r["coletores"] == 0:
        out["texto"] = f"IDR-PR ({safra} season): no soybean rust collectors within {int(RAIO_KM)} km of the field."
    else:
        ult = f"; latest detection on {r['ultima_deteccao']}" if r["ultima_deteccao"] else ""
        out["texto"] = (f"IDR-PR reports Asian rust spores in {r['com_esporos']} of {r['coletores']} collectors within "
                        f"{int(RAIO_KM)} km ({safra} season{ult}). It affects the current soybean; it is context information only and does not "
                        "change the score of the rotations.")
    return out


def consultar_ferrugem(lat: float, lon: float, municipio: str | None, cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        safra = safra_atual()
        chave = f"ferrugem_{safra.replace('/', '_')}"
        if cache_only:
            pontos = B.ler_cache(chave, B.TTL_PRAGAS)
            if pontos is None:
                raise LookupError("no cache; query GET /v1/contexto")
            cache = True
        else:
            pontos, cache = B.com_cache(chave, B.TTL_PRAGAS, lambda: _buscar_ferrugem(safra))
        return {"do_cache": cache, **resumir_ferrugem(pontos, lat, lon, municipio, safra)}

    return B.seguro("pragas_ferrugem", FONTE_FERRUGEM, _fn)


# ------------------------------------------------------------------------------------ curated
TEXTOS = {
    "cigarrinha": "Watch the off-season corn: rotations with cover crops reduce the exposure.",
}
NIVEL_TXT = {"baixo": "a low population", "moderado": "a moderate population", "alto": "a high population"}


def _aplica(alerta: dict, municipio: str | None) -> bool:
    regs = [_norm(r) for r in alerta.get("regiao", [])]
    return any(r in ("pr", "parana", "oeste do pr", "oeste") or (municipio and r == _norm(municipio)) for r in regs)


def _texto_alerta(a: dict) -> str:
    d = datetime.strptime(a["data"], "%Y-%m-%d").strftime("%d/%m")
    reg = ", ".join(a.get("regiao", [])) or "Paraná"
    praga = a["praga"]
    ind = NIVEL_TXT.get(a.get("nivel", ""), "an occurrence")
    extra = next((v for k, v in TEXTOS.items() if k in _norm(praga)), f"Watch {a.get('cultura_afetada', 'the crop')}.")
    return f"{a['fonte']} report {ind} of {praga} in {reg} (bulletin of {d}). {extra}"


def consultar_curado(municipio: str | None, hoje: date | None = None, arquivo: Path | None = None) -> dict[str, Any]:
    def _fn():
        arq = arquivo or ARQ_CURADO
        dados = json.loads(arq.read_text(encoding="utf-8"))
        h = hoje or date.today()
        vigentes, vencidos = [], 0
        for a in dados.get("alertas", []):
            d = datetime.strptime(a["data"], "%Y-%m-%d").date()
            if h > d + timedelta(days=int(a.get("validade_dias", 30))):
                vencidos += 1
                continue
            if _aplica(a, municipio):
                vigentes.append({**a, "texto": _texto_alerta(a)})
        out = {"curado_manualmente": True, "alertas": vigentes, "alertas_vencidos_ignorados": vencidos,
               "como_consultar": dados.get("fontes_monitoramento", []),
               "atualizado_em": dados.get("atualizado_em")}
        out["texto"] = (" ".join(a["texto"] for a in vigentes) if vigentes else
                        "No curated plant-health alert in force for this region (file updated by hand; "
                        "check CigarrinhaWeb and ADAPAR).")
        return out

    return B.seguro("pragas_curado", FONTE_CURADO, _fn)


def consultar(lat: float, lon: float, municipio: str | None, cache_only: bool = False) -> dict[str, Any]:
    return {"ferrugem_soja": consultar_ferrugem(lat, lon, municipio, cache_only),
            "alertas_curados": consultar_curado(municipio),
            "consultado_em": B.agora_iso(), "disponivel": True,
            "fonte": B.fonte("IDR-PR (WFS) + ADAPAR/IDR-PR (curado)", URL_WFS)}
