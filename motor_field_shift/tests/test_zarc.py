"""ZARC lookup in the engine: informative only. Run: uv run pytest tests/test_zarc.py"""
import pytest

from field_shift import zarc as Z
from field_shift.app import engine as E
from field_shift.motor import recomendar

needs_table = pytest.mark.skipif(not Z.TABLE.exists(), reason="run ingest/zarc_pr.py first")
TOLEDO = "4127700"


@pytest.mark.parametrize("ddmm,dec", [("01/01", 1), ("15/01", 2), ("21/01", 3), ("01/03", 7), ("15/03", 8), ("15/10", 29), ("31/12", 36)])
def test_decendio(ddmm, dec):
    assert Z.decendio(ddmm) == dec


@needs_table
def test_status_toledo_corn():
    assert Z.status(TOLEDO, "Milho 2ª Safra", "01/03")["indicado"] is True
    s = Z.status(TOLEDO, "Milho 2ª Safra", "15/03")
    assert s["indicado"] is False and s["risco_pct"] is None and s["portaria"]
    assert Z.status("0000000", "Milho 2ª Safra", "15/01")["motivo"] == "cultura sem zoneamento no município"


@needs_table
def test_rotation_status_checks_summer_and_second_crop():
    c = E.CATALOGO[E.NOME_DE["soja__milho_safrinha"]]
    zs = Z.rotation_status(c, TOLEDO, "15/03", "01/05")
    assert [x["cultura_zarc"] for x in zs["culturas"]] == ["Soja", "Milho 2ª Safra"] and zs["indicado"] is False
    assert "Fora do ZARC" in Z.warning_text(zs, "Toledo")
    cover = Z.rotation_status(E.CATALOGO[E.NOME_DE["soja__milheto_crotalaria"]], TOLEDO, "15/03", "01/05")
    assert cover["indicado"] is True and cover["segunda_sem_zoneamento"] is True


@needs_table
def test_zarc_never_changes_scores(monkeypatch):
    kw = dict(rotacao_atual="soja__milho_safrinha", colheita_prevista="10/03", data_referencia="2026-12-01")
    with_z = recomendar({"talhao_id": "72638"}, **kw)
    monkeypatch.setattr(Z, "table", lambda: None)
    without = recomendar({"talhao_id": "72638"}, **kw)
    assert [(x["id"], x["nota"]) for x in with_z["agora"]["ranking"]] == [(x["id"], x["nota"]) for x in without["agora"]["ranking"]]
    milho = {x["id"]: x for x in with_z["agora"]["ranking"]}["soja__milho_safrinha"]
    assert milho["zarc"]["indicado"] is False and any("Fora do ZARC" in a for a in milho["card"]["avisos"])
    assert any("rotação atual está fora do ZARC" in a for a in with_z["avisos"])
    assert all("zarc" not in x for x in without["agora"]["ranking"])
    assert any(E.AVISO_ZARC in r for r in without["agora"]["ranking"][0]["card"]["riscos"])
