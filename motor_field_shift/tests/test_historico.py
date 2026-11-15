"""Track record of the second crop (field_shift.renda.historico). Run: uv run pytest tests/test_historico.py"""
from field_shift.motor import recomendar
from field_shift.renda import historico as H

TOLEDO = "4127700"


def test_track_record_has_last_five_seasons_in_soy_bags():
    tr = H.track_record(TOLEDO, "milho_safrinha")
    assert tr is not None and len(tr["safras"]) == 5
    anos = [r["ano"] for r in tr["safras"]]
    assert anos == sorted(anos) and anos[-1] >= 2024
    assert tr["min_sc_soja_ha"] <= tr["media_sc_soja_ha"] <= tr["max_sc_soja_ha"]
    # brachiaria only adds a cost to the same corn
    br = H.track_record(TOLEDO, "milho_braquiaria")
    assert all(b["margem_sc_soja_ha"] < m["margem_sc_soja_ha"] for b, m in zip(br["safras"], tr["safras"]))


def test_no_track_record_for_covers_or_without_municipality():
    assert H.track_record(TOLEDO, "milheto_crotalaria") is None
    assert H.track_record(None, "milho_safrinha") is None


def test_track_record_never_changes_scores(monkeypatch):
    a = recomendar({"talhao_id": "72638"}, rotacao_atual="soja__milho_safrinha", incluir_diagnostico=False)
    assert any("historico_renda" in x for x in a["ranking"])
    monkeypatch.setattr(H, "track_record", lambda *a, **k: None)
    b = recomendar({"talhao_id": "72638"}, rotacao_atual="soja__milho_safrinha", incluir_diagnostico=False)
    assert [(x["id"], x["nota"]) for x in a["ranking"]] == [(x["id"], x["nota"]) for x in b["ranking"]]
    assert not any("historico_renda" in x for x in b["ranking"])
