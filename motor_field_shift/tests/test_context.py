"""Tests of the context sources with a mocked network (no internet access, cache in a temporary directory)."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from field_shift.context import _base as B
from field_shift.context import inmet_alerts, enso, mjo, pests, smap

ONI_TXT = """ SEAS  YR   TOTAL   ANOM
  DJF 1992  27.0  1.60
  DJF 1993  26.0  0.10
  DJF 1994  25.0  -0.60
  DJF 1995  25.0  0.90
  DJF 1996  25.0  -0.70
  ASO 2026  29.2  2.46
"""
STATUS_HTML = """<html><body>ENSO Alert System Status:
El Ni&ntilde;o Advisory
&nbsp; Synopsis:&nbsp;
El Ni&ntilde;o continues to strengthen, with a strong El Ni&ntilde;o likely (remaining greater than a 79&#37; chance).
Compared to last month, x. issued by CLIMATE PREDICTION CENTER 12 November 2026
The next ENSO Diagnostic Discussion is scheduled for 10 December 2026.</body></html>"""


@pytest.fixture(autouse=True)
def cache_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CACHE_DIR", tmp_path / "cache")


def _enso_network(monkeypatch, fail=False):
    def download(url, *a, **k):
        if fail:
            raise ConnectionError("sem rede")
        return ONI_TXT if "oni.ascii" in url else STATUS_HTML
    monkeypatch.setattr(B, "download_text", download)


def test_enso_success_and_history(monkeypatch):
    _enso_network(monkeypatch)
    annual = []
    # crop years 1991..1995 -> DJF 1992..1996 (El Niño, Neutral, La Niña, El Niño, La Niña)
    for y, v in zip(range(1991, 1996), [1, 0, 0, 1, 0]):
        annual.append(("c1", y, "veranico_safrinha_ge15", float(v)))
    monkeypatch.setattr(enso, "_annual", lambda: pd.DataFrame(annual, columns=["ponto_id", "ano", "indicador", "valor"]))
    r = enso.query_source("c1", "01/02")
    assert r["disponivel"] and r["fase_atual"] == "El Niño" and r["status_alerta"] == "El Niño Advisory"
    assert r["boletim"]["percentuais_citados"] == [79] and r["boletim"]["proximo"] == "10 December 2026"
    h = r["historico_por_fase"]["indicadores"]["veranico_safrinha"]
    assert h["por_fase"]["El Niño"] == {"n_anos": 2, "anos_com_evento": 2, "frequencia": 1.0}
    assert h["por_fase"]["La Niña"]["n_anos"] == 2 and h["por_fase"]["Neutro"]["n_anos"] == 1
    assert r["frase_historico"] == ("Em anos de El Niño na série deste talhão, houve veranico no safrinha em 2 de 2 anos "
                                    "(contra 40% na média de 5 anos).")
    assert r["consultado_em"] and r["fonte"]["url"].startswith("https://www.cpc.ncep.noaa.gov")


def test_enso_cache_and_fallback_with_expired_cache(monkeypatch):
    _enso_network(monkeypatch)
    monkeypatch.setattr(enso, "_annual", lambda: pd.DataFrame(columns=["ponto_id", "ano", "indicador", "valor"]))
    assert enso.query_source(None)["do_cache"] is False
    _enso_network(monkeypatch, fail=True)
    assert enso.query_source(None)["do_cache"] is True  # did not even touch the network


def test_enso_fallback_without_network(monkeypatch):
    _enso_network(monkeypatch, fail=True)
    r = enso.query_source(None)
    assert r["disponivel"] is False and "sem rede" in r["motivo"] and r["fonte"]["url"] and r["consultado_em"]


def test_enso_unexpected_format(monkeypatch):
    monkeypatch.setattr(B, "download_text", lambda url, *a, **k: "<html>nada</html>" if "ensodisc" in url else ONI_TXT)
    assert enso.query_source(None)["disponivel"] is False


def test_classify_and_cache_only(monkeypatch):
    assert [enso.classify(x) for x in (0.5, -0.5, 0.49)] == ["El Niño", "La Niña", "Neutro"]
    r = enso.query_source(None, cache_only=True)
    assert r["disponivel"] is False and "cache" in r["motivo"]


def test_mjo_phase_and_fallback(monkeypatch):
    # PC1=0,PC2=1 -> RMM1=1, RMM2=0 -> angle 0 -> phase 5; amplitude 1
    assert mjo.rmm_phase(0.0, 1.0)[0] == 5
    assert mjo.rmm_phase(0.0, -1.0)[0] == 1
    assert mjo.rmm_phase(1.0, 0.0)[0] == 7 or mjo.rmm_phase(1.0, 0.0)[0] in range(1, 9)
    monkeypatch.setattr(B, "download_text", lambda *a, **k: "2026 11 10 0  0.5  0.95  1.08\n2026 11 11 0  0.1  0.1  0.14\n")
    r = mjo.query_source()
    assert r["disponivel"] and r["ativa"] is False and r["fase"] is None and "fraca" in r["texto"]
    monkeypatch.setattr(B, "CACHE_DIR", B.CACHE_DIR / "outro")

    def error(*a, **k):
        raise TimeoutError("lento")
    monkeypatch.setattr(B, "download_text", error)
    assert mjo.query_source()["disponivel"] is False


def test_inmet_always_unavailable():
    r = inmet_alerts.query_source()
    assert r["disponivel"] is False and "motivo" in r and r["fonte"]["url"] and r["consultado_em"]


POINTS = [
    {"municipio": "Toledo", "mesorregiao": "Oeste", "regiao": "Toledo", "situacao": "Com esporos", "data_esporos": "03/11/2026",
     "estadio": "R3", "lat": -24.7, "lon": -53.74},
    {"municipio": "Cascavel", "mesorregiao": "Oeste", "regiao": "Cascavel", "situacao": "Sem esporos", "data_esporos": None,
     "estadio": "0", "lat": -24.95, "lon": -53.45},
    {"municipio": "Londrina", "mesorregiao": "Norte", "regiao": "Londrina", "situacao": "Com esporos", "data_esporos": "09/11/2026",
     "estadio": "R1", "lat": -23.3, "lon": -51.17},
]


def test_rust_summary():
    r = pests.summarize_rust(POINTS, -24.81, -53.55, "Toledo", "2026/2027")
    assert r["municipio"] == {"nome": "Toledo", "coletores": 1, "com_esporos": 1, "ultima_deteccao": "03/11/2026"}
    assert r["mesorregiao_oeste"]["coletores"] == 2 and r["raio_100_km"]["coletores"] == 2
    assert "IDR-PR" in r["texto"] and "não altera a nota" in r["texto"]


def test_rust_query_mock_and_failure(monkeypatch):
    monkeypatch.setattr(pests, "_fetch_rust", lambda season: POINTS)
    r = pests.query_rust(-24.81, -53.55, "Toledo")
    assert r["disponivel"] and r["safra"] == pests.current_season() and r["fonte"]["url"].startswith("https://geoserver.pr.gov.br")

    def error(season):
        raise ConnectionError("fora do ar")
    monkeypatch.setattr(pests, "_fetch_rust", error)
    monkeypatch.setattr(B, "CACHE_DIR", B.CACHE_DIR / "x")
    r = pests.query_rust(-24.81, -53.55, "Toledo")
    assert r["disponivel"] is False and "fora do ar" in r["motivo"]


def test_current_season():
    assert pests.current_season(date(2026, 11, 14)) == "2026/2027"
    assert pests.current_season(date(2027, 3, 1)) == "2026/2027"


def _curated(tmp_path, alerts):
    p = tmp_path / "pragas.json"
    p.write_text(json.dumps({"atualizado_em": "2026-11-10", "fontes_monitoramento": [{"nome": "CW", "url": "u"}], "alertas": alerts}))
    return p


def test_curated_current_expired_and_region(tmp_path):
    base = {"praga": "cigarrinha-do-milho", "cultura_afetada": "milho", "nivel": "alto", "fonte": "ADAPAR/IDR-PR",
            "url": "https://x", "data": "2026-11-05", "validade_dias": 30}
    path_ = _curated(tmp_path, [
        {**base, "id": "a", "regiao": ["Oeste do PR"]},
        {**base, "id": "b", "regiao": ["Oeste do PR"], "data": "2026-01-01"},       # vencido
        {**base, "id": "c", "regiao": ["Londrina"]},                                  # another region
    ])
    r = pests.query_curated("Toledo", today=date(2026, 11, 14), file_path=path_)
    assert [a["id"] for a in r["alertas"]] == ["a"] and r["alertas_vencidos_ignorados"] == 1
    assert r["alertas"][0]["texto"] == ("ADAPAR/IDR-PR indicam alta população de cigarrinha-do-milho no Oeste do PR "
                                        "(boletim de 05/11). Atenção ao milho safrinha: rotações com cobertura reduzem a exposição.")


def test_curated_without_alert_and_missing_file(tmp_path):
    r = pests.query_curated("Toledo", file_path=_curated(tmp_path, []))
    assert r["disponivel"] and r["alertas"] == [] and r["como_consultar"]
    r = pests.query_curated("Toledo", file_path=tmp_path / "nao_existe.json")
    assert r["disponivel"] is False and r["motivo"]


def test_smap_pixel_class_and_fallback(monkeypatch):
    row, col = smap.pixel_ease2(-24.95, -53.45)
    assert abs(row - 1154) <= 3 and abs(col - 1355) <= 3
    with pytest.raises(ValueError):
        smap.pixel_ease2(89.9, 0)
    assert [smap.class_(x) for x in (10, 50, 90)] == ["abaixo do normal", "normal", "acima do normal"]
    raw = {"referencia_utc": "2026-11-10T21:00:00+00:00", "pixel_ease2": {"linha": row, "coluna": col},
             "atual": {"sm_rootzone": 0.3, "sm_rootzone_pctl": 12.0, "sm_surface": 0.2},
             "ha_7_dias": {"sm_rootzone": 0.35, "sm_rootzone_pctl": 30.0}}
    monkeypatch.setattr(smap, "_fetch", lambda lat, lon: raw)
    r = smap.query_source(-24.95, -53.45)
    assert r["disponivel"] and r["classe"] == "abaixo do normal" and r["tendencia_7d_percentil"] == -18.0
    assert "percentil 12" in r["texto"]

    def error(lat, lon):
        raise RuntimeError("earthdata fora")
    monkeypatch.setattr(B, "CACHE_DIR", B.CACHE_DIR / "y")
    monkeypatch.setattr(smap, "_fetch", error)
    r = smap.query_source(-24.95, -53.45)
    assert r["disponivel"] is False and "earthdata fora" in r["motivo"] and r["fonte"]["url"]


def test_build_isolates_failures(monkeypatch):
    from field_shift import context

    monkeypatch.setattr(context.enso, "query_source", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(context.smap, "query_source", lambda *a, **k: {"disponivel": True})
    monkeypatch.setattr(context.mjo, "query_source", lambda *a, **k: {"disponivel": True})
    monkeypatch.setattr(context.pests, "query_source", lambda *a, **k: {"disponivel": True})
    r = context.build(-24.81, -53.55)
    assert r["enso"]["disponivel"] is False and r["smap"]["disponivel"] is True
    assert r["alertas_inmet"]["disponivel"] is False and "não altera" in r["aviso"]
