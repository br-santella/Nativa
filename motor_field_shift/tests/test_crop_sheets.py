"""Crop sheets of catalog/crops.yaml: engine -> sheet mapping, pH ranges, pH card lines (informative only)."""
import pytest

from field_shift import crop_sheets as CS
from field_shift.app import engine as E


def _cand(verao: str, segunda: str) -> dict:
    return dict(verao=verao, segunda=segunda, nome_verao=E.SUMMER[verao]["nome"], nome_segunda=E.SECOND[segunda]["nome"])


def test_catalog_loads():
    assert set(CS.sheets()) >= {"soja", "milho", "trigo", "aveia_branca"}


def test_every_engine_crop_is_mapped():
    """A new engine crop must be added to ENGINE_TO_SHEET (with a sheet id or None)."""
    assert set(E.SUMMER) | set(E.SECOND) == set(CS.ENGINE_TO_SHEET)


def test_mapped_sheets_exist():
    for crop, sid in CS.ENGINE_TO_SHEET.items():
        if sid is not None:
            assert sid in CS.sheets(), crop
            assert CS.sheet_id(crop) == sid


def test_ph_ranges_are_valid():
    for sid, sheet in CS.sheets().items():
        rng = sheet["requisitos_solo"]["ph"]
        assert 3 <= rng["min"] <= rng["max"] <= 9, sid
        assert rng["fonte"].startswith("http"), sid


@pytest.mark.parametrize("ph,expected", [(5.4, "abaixo"), (5.5, "dentro"), (6.0, "dentro"), (6.1, "acima")])
def test_ph_status_bounds_inclusive(ph, expected):
    assert CS.ph_status(ph, dict(min=5.5, max=6.0)) == expected


def test_ph_card_without_ph_is_empty():
    assert CS.ph_card(_cand("soja", "milho_safrinha"), None) == dict(evidencias=[], lacunas=[])


def test_ph_card_soybean_and_corn():
    out = CS.ph_card(_cand("soja", "milho_safrinha"), 5.0)
    soy, corn = out["evidencias"]
    assert "abaixo da" in soy and "Soja" in soy and "5,5–6,0" in soy and "pH em água" in soy
    assert "dentro da" in corn and "método de medição" in corn  # Ecocrop range: method not stated
    assert all("não muda a nota" in e for e in out["evidencias"])
    assert any("não recomendação de calagem" in g for g in out["lacunas"])


def test_ph_card_same_sheet_once_and_crop_without_sheet():
    out = CS.ph_card(_cand("milho_verao", "milho_safrinha"), 6.5)
    assert len(out["evidencias"]) == 1  # both crops use the corn sheet
    out = CS.ph_card(_cand("soja", "sorgo"), 6.5)
    assert len(out["evidencias"]) == 1
    assert any("sorgo" in g and "não comparado" in g for g in out["lacunas"])
    out = CS.ph_card(_cand("soja", "pousio"), 6.5)  # fallow: nothing to compare, no gap line
    assert not any("não comparado" in g for g in out["lacunas"])


def test_missing_catalog_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr(CS, "CATALOG_PATH", tmp_path / "missing.yaml")
    CS.sheets.cache_clear()
    try:
        assert CS.sheets() == {}
        assert CS.sheet_id("soja") is None
        out = CS.ph_card(_cand("soja", "trigo"), 5.0)
        assert out["evidencias"] == [] and len(out["lacunas"]) == 2
    finally:
        CS.sheets.cache_clear()


def test_public_sheets():
    pub = CS.public_sheets()
    assert {f["id"] for f in pub["fichas"]} == set(CS.sheets())
    assert pub["mapeamento"]["aveia"] == "aveia_branca" and pub["mapeamento"]["sorgo"] is None


@pytest.mark.integration
def test_ph_does_not_change_the_score():
    from field_shift.core import recommend

    base = dict(current_rotation="soja__milho_safrinha", reference_date="2026-12-01", include_diagnosis=False)
    a = recommend({"talhao_id": "72638"}, soil_analysis={"argila_pct": 60, "areia_pct": 15}, **base)
    b = recommend({"talhao_id": "72638"}, soil_analysis={"argila_pct": 60, "areia_pct": 15, "ph": 4.8}, **base)
    assert [(i["id"], i["nota"]) for i in a["ranking"]] == [(i["id"], i["nota"]) for i in b["ranking"]]
    assert any("pH do solo 4,8" in e for e in b["ranking"][0]["card"]["evidencias"])
    assert not any("pH do solo" in e for e in a["ranking"][0]["card"]["evidencias"])
