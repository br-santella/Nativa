"""Statewide behaviour (all of Paraná, not only the Oeste pilot). Run: uv run pytest tests/test_statewide.py"""
import pandas as pd

from field_shift.app import engine as E
from field_shift.core import recommend
from field_shift.income import income as I

TOLEDO, CURITIBA = "4127700", "4106902"
CORNELIO = {"lat": -23.157, "lon": -50.595}  # soybean field (MapBiomas 2024) in Cornélio Procópio, Norte Pioneiro
LONDRINA = {"lat": -23.31, "lon": -51.08}


def test_mesoregion_table_covers_paraná_and_matches_the_oeste_pilot():
    m = pd.read_csv(I.MESOREGIONS, dtype={"cod_ibge": str})
    assert len(m) == 399 and m["mesorregiao"].nunique() == 10
    assert (m["mesorregiao"] == "Oeste Paranaense").sum() == 50
    assert I.mesoregion(TOLEDO) == "Oeste Paranaense" and I.region_label("Oeste Paranaense") == "Oeste do PR"
    assert I.region_label("Norte Central Paranaense") == "Norte Central do PR" and I.region_label(None) == "Paraná"


def test_yield_fallback_uses_the_municipality_mesoregion():
    y = I.yields(CURITIBA)  # no off-season corn PAM in Curitiba
    assert y["_regiao"] == "Metropolitana de Curitiba" and y["soja"]["regiao"] == "Metropolitana de Curitiba"
    assert y["_origem"].startswith("média dos") and "Metropolitana de Curitiba" in y["_origem"]
    assert "Oeste" not in y["_origem"]
    # Oeste municipality: extra crops without recent PAM use the Oeste mean (the validated behaviour)
    t = I.yields(TOLEDO)
    assert t["_origem"].startswith("PAM do município") and all(t[c]["regiao"] == "Oeste do PR" for c in t["_regionais"])
    # no municipality at all: the Paraná mean
    assert I.yields(None)["soja"]["regiao"] == "Paraná"


def test_card_texts_outside_the_oeste():
    r = recommend(LONDRINA, current_rotation="soja__milho_safrinha", include_diagnosis=False)
    corn = next(x for x in r["agora"]["ranking"] if x["id"] == "soja__milho_safrinha")
    ev = " ".join(corn["card"]["evidencias"])
    assert "Mercado (referência do Oeste do PR, confirme na sua região)" in ev
    assert any(a.startswith("Área fora do Oeste do Paraná: preços (média estadual") for a in r["avisos"])
    t = recommend({"talhao_id": "72638"}, current_rotation="soja__milho_safrinha", include_diagnosis=False)
    ev_t = " ".join(next(x for x in t["agora"]["ranking"] if x["id"] == "soja__milho_safrinha")["card"]["evidencias"])
    assert "Mercado no Oeste do PR:" in ev_t
    assert not any(a.startswith("Área fora do Oeste") for a in t["avisos"])


def test_north_of_paraná_field_runs_end_to_end():
    # regression: a crop with a short PAM series (no p20 bad year) used to crash the card with a None format
    r = recommend(CORNELIO, current_rotation="soja__milho_safrinha")
    assert r["agora"]["ranking"] and r["diagnostico"]["area"]["municipio"]["nome"] == "Cornélio Procópio"


def test_margin_line_without_bad_year():
    item = dict(chave="sorgo", rotulo="Sorgo", sc_ha=50.0, sc_ha_ruim=None, margem_ano_ruim=None, cv=None, preco=40.0, custo=2000.0,
                margem=0.0, anos="2023–2025", metodo_rend="", sc_ha_media=None, extra=False, preco_usuario=True,
                custo_usuario=True, prod_usuario=False)
    m = dict(itens=[item], linha_custo="coe", bonus_sc=0.0, bonus_verao_sc=0.0, preco_soja=120.0, bonus=0.0, total=0.0,
             incremental=0.0, escala_S=1000.0, total_ano_ruim=None)
    risks = {"rend": {"_regionais": [], "_regiao": "Norte Pioneiro do PR"}, "rend_local": "Cornélio Procópio"}
    lines = E.fmt_margin(m, risks)
    assert any("série da PAM curta demais" in x for x in lines)
