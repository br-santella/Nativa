"""Validação do campo `rotacoes` e dos ids de rotação na API (serviço falso: só o contrato de entrada/saída)."""

from __future__ import annotations

import pytest

from field_shift.app import engine as E
from field_shift_api import schemas

AREA = {"talhao_id": "72638"}
RA = {"rotacao_atual": "soja__milho_safrinha"}
OK = {"verao": "soja", "segunda": "milho_safrinha"}


def test_rotations_forwarded_to_service(client, calls):
    rotations = [OK, {"verao": "milho_verao", "segunda": "sorgo"}]
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "rotacoes": rotations})
    assert r.status_code == 200
    assert calls[0][2]["rotations"] == rotations


def test_no_rotations_evaluates_all(client, calls):
    client.post("/v1/recomendacao", json={"area": AREA, **RA})
    assert calls[0][2]["rotations"] is None


@pytest.mark.parametrize(
    "rotations",
    [
        [],  # vazia
        [OK, OK],  # duplicada
        [{"verao": "soja", "segunda": "girassol"}],  # fora do enum
        [{"verao": "trigo", "segunda": "milho_safrinha"}],
        [{"verao": "soja"}],  # falta campo
        [{"verao": "soja", "segunda": "pousio", "x": 1}],  # campo extra
        ["soja__milho_safrinha"],  # texto livre no lugar do par
    ],
)
def test_invalid_rotations_422(client, calls, rotations):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "rotacoes": rotations})
    assert r.status_code == 422 and not calls


def test_new_ids_and_old_slugs_accepted(client, calls):
    for rid in ("soja__milho_safrinha", "milho_verao__aveia_nabo", "milho_safrinha", "soja_safrinha"):
        assert client.post("/v1/recomendacao", json={"area": AREA, "rotacao_atual": rid}).status_code == 200
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "restricoes": {"culturas_excluidas": ["trigo", "milho_verao__trigo"]}})
    assert r.status_code == 200
    assert client.post("/v1/recomendacao", json={"area": AREA, "rotacao_atual": "milho_verao__milho"}).status_code == 422
    assert client.post("/v1/recomendacao", json={"area": AREA, **RA, "restricoes": {"sem_comprador": ["sorgo", "feijao"]}}).status_code == 200


def test_api_enums_mirror_the_catalog():
    assert set(schemas.SummerCrop.__args__) == set(E.SUMMER)
    assert set(schemas.SecondCrop.__args__) == set(E.SECOND)
    assert set(schemas.ROTATION_IDS) == set(E.NOME_DE)
    assert set(schemas.LEGACY_SLUGS) == set(E.LEGACY)
    assert set(schemas.RotationSlug.__args__) == set(E.NOME_DE) | set(E.LEGACY)


def test_stages_and_calendar_forwarded_to_service(client, calls):
    body = {"area": AREA, **RA, "estagio_verao": "enchimento_graos", "data_referencia": "2026-12-01", "colheita_prevista": "20/01"}
    assert client.post("/v1/recomendacao", json=body).status_code == 200
    kw = calls[0][2]
    assert kw["summer_stage"] == "enchimento_graos" and kw["expected_harvest"] == "20/01"
    assert str(kw["reference_date"]) == "2026-12-01" and kw["sowing_second"] is None


def test_corn_stage_ok_with_summer_corn_and_422_with_soy(client, calls):
    ok = {"area": AREA, "rotacao_atual": "milho_verao__aveia", "estagio_verao": "grao_leitoso"}
    assert client.post("/v1/recomendacao", json=ok).status_code == 200
    r = client.post("/v1/recomendacao", json={**ok, "rotacao_atual": "milho_safrinha"})  # slug antigo = soja no verão
    assert r.status_code == 422 and "milho verao" in r.text.replace("_", " ") and len(calls) == 1


def test_sowing_before_harvest_422_with_message(client, calls):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "colheita_prevista": "20/02", "semeadura_safrinha": "01/02"})
    assert r.status_code == 422 and "anterior à colheita" in r.text and not calls


def test_current_rotation_required_422(client, calls):
    r = client.post("/v1/recomendacao", json={"area": AREA})
    assert r.status_code == 422 and "rotacao_atual" in r.text and not calls


def test_api_stages_mirror_the_calendar():
    from field_shift import crop_calendar

    assert set(schemas.SummerStage.__args__) == set(crop_calendar.ALL_STAGES)
    assert set(schemas.SummerStage.__args__) == {e for v in crop_calendar.STAGES.values() for e in v}
