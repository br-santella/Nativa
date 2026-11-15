"""Soybean sanitary void and sowing window by ADAPAR region (Portaria SDA/MAPA 1.579/2026, crop 2026/2027)."""
import pytest

from field_shift.app import engine as E
from field_shift.regiao.vazio_sanitario import _load, calendario_soja, in_window

TOLEDO, CURITIBA, FCO_BELTRAO = 4127700, 4106902, 4108403


def test_every_parana_municipality_has_exactly_one_region():
    d = _load()
    assert sorted(len(r["municipios"]) for r in d["ref"]["regioes"]) == [48, 84, 267]
    codes = [c for r in d["ref"]["regioes"] for c in r["municipios"]]
    assert len(codes) == len(set(codes)) == 399


@pytest.mark.parametrize("cod,regiao,vazio,semeadura", [
    (TOLEDO, 2, ("02/06", "31/08"), ("01/09", "31/12")),
    (CURITIBA, 1, ("21/06", "19/09"), ("20/09", "20/01")),
    (FCO_BELTRAO, 3, ("12/06", "10/09"), ("11/09", "10/01")),
    (str(TOLEDO), 2, ("02/06", "31/08"), ("01/09", "31/12")),  # string codes work too
])
def test_region_dates_by_municipality(cod, regiao, vazio, semeadura):
    cs = calendario_soja(cod)
    assert (cs["regiao"], cs["vazio"], cs["semeadura"], cs["padrao"]) == (regiao, vazio, semeadura, False)
    assert cs["safra"] == "2026/2027"


def test_unknown_municipality_uses_the_default_region_and_says_so():
    for cod in (None, 1234567):
        cs = calendario_soja(cod)
        assert cs["padrao"] is True and cs["regiao"] == 2


def test_window_may_cross_the_new_year():
    assert in_window("15/10", "20/09", "20/01") and in_window("10/01", "20/09", "20/01") and in_window("20/01", "20/09", "20/01")
    assert not in_window("25/01", "20/09", "20/01") and not in_window("19/09", "20/09", "20/01")
    assert in_window("15/10", "01/09", "31/12") and not in_window("01/01", "01/09", "31/12")


def _soy_second_window():
    return next(c for c in E.CATALOGO.values() if c["ano_soja_2"] and c["verao"] != "soja")


def test_rules_quote_the_window_of_the_region():
    c = _soy_second_window()
    r1 = " ".join(E.checar_regras(c, {"calendario_soja": calendario_soja(CURITIBA)}))
    assert "20/09–20/01" in r1 and "Região 1" in r1 and "21/06–19/09" in r1
    r3 = " ".join(E.checar_regras(c, {"calendario_soja": calendario_soja(FCO_BELTRAO)}))
    assert "11/09–10/01" in r3 and "Região 3" in r3 and "12/06–10/09" in r3


def test_rules_default_to_the_oeste_window_without_calendar():
    txt = " ".join(E.checar_regras(_soy_second_window(), {}))
    assert "01/09–31/12" in txt and "02/06–31/08" in txt


def test_default_soybean_sowing_date_is_legal_in_every_region():
    for cod in (TOLEDO, CURITIBA, FCO_BELTRAO):
        assert not any("fora da janela" in m and "Semeadura de soja em" in m
                       for c in E.CATALOGO.values() for m in E.checar_regras(c, {"calendario_soja": calendario_soja(cod)}))
