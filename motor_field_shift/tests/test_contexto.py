"""Tests of the context sources with a mocked network (no internet access, cache in a temporary directory)."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from field_shift.contexto import _base as B
from field_shift.contexto import alertas_inmet, enso, mjo, pragas, smap

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


def _rede_enso(monkeypatch, falhar=False):
    def baixar(url, *a, **k):
        if falhar:
            raise ConnectionError("no network")
        return ONI_TXT if "oni.ascii" in url else STATUS_HTML
    monkeypatch.setattr(B, "baixar_texto", baixar)


def test_enso_sucesso_e_historico(monkeypatch):
    _rede_enso(monkeypatch)
    anuais = []
    # agricultural years 1991..1995 -> DJF 1992..1996 (El Niño, Neutro, La Niña, El Niño, La Niña)
    for y, v in zip(range(1991, 1996), [1, 0, 0, 1, 0]):
        anuais.append(("c1", y, "veranico_safrinha_ge15", float(v)))
    monkeypatch.setattr(enso, "_anuais", lambda: pd.DataFrame(anuais, columns=["ponto_id", "ano", "indicador", "valor"]))
    r = enso.consultar("c1", "01/02")
    assert r["disponivel"] and r["fase_atual"] == "El Niño" and r["status_alerta"] == "El Niño Advisory"
    assert r["boletim"]["percentuais_citados"] == [79] and r["boletim"]["proximo"] == "10 December 2026"
    h = r["historico_por_fase"]["indicadores"]["veranico_safrinha"]
    assert h["por_fase"]["El Niño"] == {"n_anos": 2, "anos_com_evento": 2, "frequencia": 1.0}
    assert h["por_fase"]["La Niña"]["n_anos"] == 2 and h["por_fase"]["Neutro"]["n_anos"] == 1
    assert r["frase_historico"] == ("In El Niño years in this field's series, there was off-season dry spell in 2 of 2 years "
                                    "(vs 40% on average over 5 years).")
    assert r["consultado_em"] and r["fonte"]["url"].startswith("https://www.cpc.ncep.noaa.gov")


def test_enso_cache_e_fallback_com_cache_vencido(monkeypatch):
    _rede_enso(monkeypatch)
    monkeypatch.setattr(enso, "_anuais", lambda: pd.DataFrame(columns=["ponto_id", "ano", "indicador", "valor"]))
    assert enso.consultar(None)["do_cache"] is False
    _rede_enso(monkeypatch, falhar=True)
    assert enso.consultar(None)["do_cache"] is True  # did not even touch the network


def test_enso_fallback_sem_rede(monkeypatch):
    _rede_enso(monkeypatch, falhar=True)
    r = enso.consultar(None)
    assert r["disponivel"] is False and "no network" in r["motivo"] and r["fonte"]["url"] and r["consultado_em"]


def test_enso_formato_inesperado(monkeypatch):
    monkeypatch.setattr(B, "baixar_texto", lambda url, *a, **k: "<html>nada</html>" if "ensodisc" in url else ONI_TXT)
    assert enso.consultar(None)["disponivel"] is False


def test_classificar_e_cache_only(monkeypatch):
    assert [enso.classificar(x) for x in (0.5, -0.5, 0.49)] == ["El Niño", "La Niña", "Neutro"]
    r = enso.consultar(None, cache_only=True)
    assert r["disponivel"] is False and "cache" in r["motivo"]


def test_mjo_fase_e_fallback(monkeypatch):
    # PC1=0,PC2=1 -> RMM1=1, RMM2=0 -> angle 0 -> phase 5; amplitude 1
    assert mjo.fase_rmm(0.0, 1.0)[0] == 5
    assert mjo.fase_rmm(0.0, -1.0)[0] == 1
    assert mjo.fase_rmm(1.0, 0.0)[0] == 7 or mjo.fase_rmm(1.0, 0.0)[0] in range(1, 9)
    monkeypatch.setattr(B, "baixar_texto", lambda *a, **k: "2026 11 10 0  0.5  0.95  1.08\n2026 11 11 0  0.1  0.1  0.14\n")
    r = mjo.consultar()
    assert r["disponivel"] and r["ativa"] is False and r["fase"] is None and "fraca" in r["texto"]
    monkeypatch.setattr(B, "CACHE_DIR", B.CACHE_DIR / "outro")

    def erro(*a, **k):
        raise TimeoutError("lento")
    monkeypatch.setattr(B, "baixar_texto", erro)
    assert mjo.consultar()["disponivel"] is False


def test_inmet_sempre_indisponivel():
    r = alertas_inmet.consultar()
    assert r["disponivel"] is False and "motivo" in r and r["fonte"]["url"] and r["consultado_em"]


PONTOS = [
    {"municipio": "Toledo", "mesorregiao": "Oeste", "regiao": "Toledo", "situacao": "Com esporos", "data_esporos": "03/11/2026",
     "estadio": "R3", "lat": -24.7, "lon": -53.74},
    {"municipio": "Cascavel", "mesorregiao": "Oeste", "regiao": "Cascavel", "situacao": "Sem esporos", "data_esporos": None,
     "estadio": "0", "lat": -24.95, "lon": -53.45},
    {"municipio": "Londrina", "mesorregiao": "Norte", "regiao": "Londrina", "situacao": "Com esporos", "data_esporos": "09/11/2026",
     "estadio": "R1", "lat": -23.3, "lon": -51.17},
]


def test_ferrugem_resumo():
    r = pragas.resumir_ferrugem(PONTOS, -24.81, -53.55, "Toledo", "2026/2027")
    assert r["municipio"] == {"nome": "Toledo", "coletores": 1, "com_esporos": 1, "ultima_deteccao": "03/11/2026"}
    assert r["mesorregiao_oeste"]["coletores"] == 2 and r["raio_100_km"]["coletores"] == 2
    assert "IDR-PR" in r["texto"] and "does not change the score" in r["texto"]


def test_ferrugem_consulta_mock_e_falha(monkeypatch):
    monkeypatch.setattr(pragas, "_buscar_ferrugem", lambda safra: PONTOS)
    r = pragas.consultar_ferrugem(-24.81, -53.55, "Toledo")
    assert r["disponivel"] and r["safra"] == pragas.safra_atual() and r["fonte"]["url"].startswith("https://geoserver.pr.gov.br")

    def erro(safra):
        raise ConnectionError("down")
    monkeypatch.setattr(pragas, "_buscar_ferrugem", erro)
    monkeypatch.setattr(B, "CACHE_DIR", B.CACHE_DIR / "x")
    r = pragas.consultar_ferrugem(-24.81, -53.55, "Toledo")
    assert r["disponivel"] is False and "down" in r["motivo"]


def test_safra_atual():
    assert pragas.safra_atual(date(2026, 11, 14)) == "2026/2027"
    assert pragas.safra_atual(date(2027, 3, 1)) == "2026/2027"


def _curado(tmp_path, alertas):
    p = tmp_path / "pragas.json"
    p.write_text(json.dumps({"atualizado_em": "2026-11-10", "fontes_monitoramento": [{"nome": "CW", "url": "u"}], "alertas": alertas}))
    return p


def test_curado_vigente_vencido_e_regiao(tmp_path):
    base = {"praga": "cigarrinha-do-milho", "cultura_afetada": "milho", "nivel": "alto", "fonte": "ADAPAR/IDR-PR",
            "url": "https://x", "data": "2026-11-05", "validade_dias": 30}
    arq = _curado(tmp_path, [
        {**base, "id": "a", "regiao": ["Oeste do PR"]},
        {**base, "id": "b", "regiao": ["Oeste do PR"], "data": "2026-01-01"},       # expired
        {**base, "id": "c", "regiao": ["Londrina"]},                                  # another region
    ])
    r = pragas.consultar_curado("Toledo", hoje=date(2026, 11, 14), arquivo=arq)
    assert [a["id"] for a in r["alertas"]] == ["a"] and r["alertas_vencidos_ignorados"] == 1
    assert r["alertas"][0]["texto"] == ("ADAPAR/IDR-PR report a high population of cigarrinha-do-milho in Oeste do PR "
                                        "(bulletin of 05/11). Watch the off-season corn: rotations with cover crops reduce the exposure.")


def test_curado_sem_alerta_e_arquivo_ausente(tmp_path):
    r = pragas.consultar_curado("Toledo", arquivo=_curado(tmp_path, []))
    assert r["disponivel"] and r["alertas"] == [] and r["como_consultar"]
    r = pragas.consultar_curado("Toledo", arquivo=tmp_path / "nao_existe.json")
    assert r["disponivel"] is False and r["motivo"]


def test_smap_pixel_classe_e_fallback(monkeypatch):
    row, col = smap.pixel_ease2(-24.95, -53.45)
    assert abs(row - 1154) <= 3 and abs(col - 1355) <= 3
    with pytest.raises(ValueError):
        smap.pixel_ease2(89.9, 0)
    assert [smap.classe(x) for x in (10, 50, 90)] == ["abaixo do normal", "normal", "acima do normal"]
    bruto = {"referencia_utc": "2026-11-10T21:00:00+00:00", "pixel_ease2": {"linha": row, "coluna": col},
             "atual": {"sm_rootzone": 0.3, "sm_rootzone_pctl": 12.0, "sm_surface": 0.2},
             "ha_7_dias": {"sm_rootzone": 0.35, "sm_rootzone_pctl": 30.0}}
    monkeypatch.setattr(smap, "_buscar", lambda lat, lon: bruto)
    r = smap.consultar(-24.95, -53.45)
    assert r["disponivel"] and r["classe"] == "abaixo do normal" and r["tendencia_7d_percentil"] == -18.0
    assert "percentile 12" in r["texto"]

    def erro(lat, lon):
        raise RuntimeError("earthdata down")
    monkeypatch.setattr(B, "CACHE_DIR", B.CACHE_DIR / "y")
    monkeypatch.setattr(smap, "_buscar", erro)
    r = smap.consultar(-24.95, -53.45)
    assert r["disponivel"] is False and "earthdata down" in r["motivo"] and r["fonte"]["url"]


def test_montar_isola_falhas(monkeypatch):
    from field_shift import contexto

    monkeypatch.setattr(contexto.enso, "consultar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(contexto.smap, "consultar", lambda *a, **k: {"disponivel": True})
    monkeypatch.setattr(contexto.mjo, "consultar", lambda *a, **k: {"disponivel": True})
    monkeypatch.setattr(contexto.pragas, "consultar", lambda *a, **k: {"disponivel": True})
    r = contexto.montar(-24.81, -53.55)
    assert r["enso"]["disponivel"] is False and r["smap"]["disponivel"] is True
    assert r["alertas_inmet"]["disponivel"] is False and "does not change" in r["aviso"]
