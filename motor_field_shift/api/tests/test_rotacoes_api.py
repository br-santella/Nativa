"""Validação do campo `rotacoes` e dos ids de rotação na API (serviço falso: só o contrato de entrada/saída)."""

from __future__ import annotations

import pytest

from field_shift.app import engine as E
from field_shift_api import schemas

AREA = {"talhao_id": "72638"}
RA = {"rotacao_atual": "soja__milho_safrinha"}
OK = {"verao": "soja", "segunda": "milho_safrinha"}


def test_rotacoes_repassadas_ao_servico(client, chamadas):
    rotacoes = [OK, {"verao": "milho_verao", "segunda": "sorgo"}]
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "rotacoes": rotacoes})
    assert r.status_code == 200
    assert chamadas[0][2]["rotacoes"] == rotacoes


def test_sem_rotacoes_avalia_tudo(client, chamadas):
    client.post("/v1/recomendacao", json={"area": AREA, **RA})
    assert chamadas[0][2]["rotacoes"] is None


@pytest.mark.parametrize(
    "rotacoes",
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
def test_rotacoes_invalidas_422(client, chamadas, rotacoes):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "rotacoes": rotacoes})
    assert r.status_code == 422 and not chamadas


def test_ids_novos_e_slugs_antigos_aceitos(client, chamadas):
    for rid in ("soja__milho_safrinha", "milho_verao__aveia_nabo", "milho_safrinha", "soja_safrinha"):
        assert client.post("/v1/recomendacao", json={"area": AREA, "rotacao_atual": rid}).status_code == 200
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "restricoes": {"culturas_excluidas": ["trigo", "milho_verao__trigo"]}})
    assert r.status_code == 200
    assert client.post("/v1/recomendacao", json={"area": AREA, "rotacao_atual": "milho_verao__milho"}).status_code == 422
    assert client.post("/v1/recomendacao", json={"area": AREA, **RA, "restricoes": {"sem_comprador": ["sorgo", "feijao"]}}).status_code == 200


def test_enums_da_api_espelham_o_catalogo():
    assert set(schemas.CulturaVerao.__args__) == set(E.VERAO)
    assert set(schemas.CulturaSegunda.__args__) == set(E.SEGUNDA)
    assert set(schemas.IDS_ROTACAO) == set(E.NOME_DE)
    assert set(schemas.SLUGS_LEGADOS) == set(E.LEGADO)
    assert set(schemas.RotacaoSlug.__args__) == set(E.NOME_DE) | set(E.LEGADO)


def test_estagios_e_calendario_repassados_ao_servico(client, chamadas):
    corpo = {"area": AREA, **RA, "estagio_verao": "enchimento_graos", "data_referencia": "2026-12-01", "colheita_prevista": "20/01"}
    assert client.post("/v1/recomendacao", json=corpo).status_code == 200
    kw = chamadas[0][2]
    assert kw["estagio_verao"] == "enchimento_graos" and kw["colheita_prevista"] == "20/01"
    assert str(kw["data_referencia"]) == "2026-12-01" and kw["semeadura_safrinha"] is None


def test_estagio_do_milho_com_verao_milho_ok_e_com_soja_422(client, chamadas):
    ok = {"area": AREA, "rotacao_atual": "milho_verao__aveia", "estagio_verao": "grao_leitoso"}
    assert client.post("/v1/recomendacao", json=ok).status_code == 200
    r = client.post("/v1/recomendacao", json={**ok, "rotacao_atual": "milho_safrinha"})  # slug antigo = soja no verão
    assert r.status_code == 422 and "milho verao" in r.text.replace("_", " ") and len(chamadas) == 1


def test_semeadura_anterior_a_colheita_422_com_mensagem(client, chamadas):
    r = client.post("/v1/recomendacao", json={"area": AREA, **RA, "colheita_prevista": "20/02", "semeadura_safrinha": "01/02"})
    assert r.status_code == 422 and "anterior à colheita" in r.text and not chamadas


def test_rotacao_atual_obrigatoria_422(client, chamadas):
    r = client.post("/v1/recomendacao", json={"area": AREA})
    assert r.status_code == 422 and "rotacao_atual" in r.text and not chamadas


def test_estagios_da_api_espelham_o_calendario():
    from field_shift import calendario

    assert set(schemas.EstagioVerao.__args__) == set(calendario.TODOS_ESTAGIOS)
    assert set(schemas.EstagioVerao.__args__) == {e for v in calendario.ESTAGIOS.values() for e in v}
