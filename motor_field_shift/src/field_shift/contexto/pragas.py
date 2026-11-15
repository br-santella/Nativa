"""Pragas em surto: ferrugem asiática (automático, IDR-PR) + alertas fitossanitários curados à mão.

AUTOMÁTICO — monitoramento da ferrugem da soja (IDR-Paraná, ex-Emater), WFS público do GeoServer do Estado:
  https://geoserver.pr.gov.br/geoserver/ows  camada `emater:monitoramento_ferrugem_soja_pto_p4674`
  (GeoJSON; campos municipio, mesorregiao, regiao, safra, situacao "Sem esporos"/"Com esporos", dtpriespo, estfeno).
  A situação "Com esporos" é captura de esporos em coletor, não confirmação de doença na lavoura. Ponto = sede/coletor
  do município. Contagem no município do talhão, na mesorregião Oeste e num raio de 100 km.
  O Consórcio Antiferrugem (consorcioantiferrugem.net) não respondeu desta rede; não usado.

CURADO — `data/contexto/pragas_alertas.json` (versionado, atualizado à mão): cigarrinha-do-milho/enfezamento e
outros alertas da ADAPAR/IDR-PR, que só existem em boletins PDF/painéis sem API documentada (CigarrinhaWeb:
https://cigarrinhaweb.com.br/). Sem scraping. Alertas vencidos (data + validade_dias) são ignorados.
Só informativo; não altera nota.
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
FONTE_FERRUGEM = B.fonte("IDR-Paraná — monitoramento da ferrugem asiática da soja (GeoServer PR)", URL_WFS)
FONTE_CURADO = B.fonte("ADAPAR / IDR-Paraná (alertas curados manualmente)", "https://cigarrinhaweb.com.br/")
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
        out["texto"] = f"IDR-PR ainda não tem coletores de ferrugem lançados para a safra {safra}."
    elif r["coletores"] == 0:
        out["texto"] = f"IDR-PR (safra {safra}): sem coletores de ferrugem da soja num raio de {int(RAIO_KM)} km do talhão."
    else:
        ult = f"; última detecção em {r['ultima_deteccao']}" if r["ultima_deteccao"] else ""
        out["texto"] = (f"IDR-PR registra esporos de ferrugem asiática em {r['com_esporos']} de {r['coletores']} coletores num raio de "
                        f"{int(RAIO_KM)} km (safra {safra}{ult}). Afeta a soja em curso; é só informação de contexto e não "
                        "altera a nota das rotações.")
    return out


def consultar_ferrugem(lat: float, lon: float, municipio: str | None, cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        safra = safra_atual()
        chave = f"ferrugem_{safra.replace('/', '_')}"
        if cache_only:
            pontos = B.ler_cache(chave, B.TTL_PRAGAS)
            if pontos is None:
                raise LookupError("sem cache; consulte GET /v1/contexto")
            cache = True
        else:
            pontos, cache = B.com_cache(chave, B.TTL_PRAGAS, lambda: _buscar_ferrugem(safra))
        return {"do_cache": cache, **resumir_ferrugem(pontos, lat, lon, municipio, safra)}

    return B.seguro("pragas_ferrugem", FONTE_FERRUGEM, _fn)


# ------------------------------------------------------------------------------------ curado
TEXTOS = {
    "cigarrinha": "Atenção ao milho safrinha: rotações com cobertura reduzem a exposição.",
}
NIVEL_TXT = {"baixo": "baixa população", "moderado": "população moderada", "alto": "alta população"}


def _aplica(alerta: dict, municipio: str | None) -> bool:
    regs = [_norm(r) for r in alerta.get("regiao", [])]
    return any(r in ("pr", "parana", "oeste do pr", "oeste") or (municipio and r == _norm(municipio)) for r in regs)


def _texto_alerta(a: dict) -> str:
    d = datetime.strptime(a["data"], "%Y-%m-%d").strftime("%d/%m")
    reg = ", ".join(a.get("regiao", [])) or "Paraná"
    praga = a["praga"]
    ind = NIVEL_TXT.get(a.get("nivel", ""), "ocorrência")
    extra = next((v for k, v in TEXTOS.items() if k in _norm(praga)), f"Atenção a {a.get('cultura_afetada', 'a lavoura')}.")
    return f"{a['fonte']} indicam {ind} de {praga} no {reg} (boletim de {d}). {extra}"


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
                        "Nenhum alerta fitossanitário curado vigente para esta região (arquivo atualizado à mão; "
                        "consulte a CigarrinhaWeb e a ADAPAR).")
        return out

    return B.seguro("pragas_curado", FONTE_CURADO, _fn)


def consultar(lat: float, lon: float, municipio: str | None, cache_only: bool = False) -> dict[str, Any]:
    return {"ferrugem_soja": consultar_ferrugem(lat, lon, municipio, cache_only),
            "alertas_curados": consultar_curado(municipio),
            "consultado_em": B.agora_iso(), "disponivel": True,
            "fonte": B.fonte("IDR-PR (WFS) + ADAPAR/IDR-PR (curado)", URL_WFS)}
