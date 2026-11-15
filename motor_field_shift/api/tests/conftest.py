"""Fixtures: serviço falso (monkeypatch) para testar a API sem dados em data/."""

from __future__ import annotations

import sys
import types

import pytest

try:  # serviço real, se já existir
    from field_shift.motor import servico  # noqa: F401

    SERVICO_REAL = True
except ImportError:  # registra um módulo mínimo para a API poder ser importada
    SERVICO_REAL = False
    import field_shift

    _mod = types.ModuleType("field_shift.motor.servico")

    class ForaDaRegiao(Exception): ...

    class EntradaInvalida(Exception): ...

    _mod.ForaDaRegiao = ForaDaRegiao
    _mod.EntradaInvalida = EntradaInvalida
    _mod.ROTACOES = {"milho_safrinha": "Milho safrinha"}
    for _n in ("opcoes", "diagnosticar", "recomendar", "aquecer"):
        setattr(_mod, _n, lambda *a, **k: None)
    _pkg = types.ModuleType("field_shift.motor")
    _pkg.__path__ = []
    _pkg.servico = _mod
    sys.modules["field_shift.motor"] = _pkg
    sys.modules["field_shift.motor.servico"] = _mod
    field_shift.motor = _pkg

from fastapi.testclient import TestClient  # noqa: E402

from field_shift.motor import servico as svc  # noqa: E402

CLIMA = {
    "fonte": "NASA POWER",
    "celula": {"lat": -24.75, "lon": -53.25},
    "semeadura_safrinha": "01/02",
    "riscos": {"geada_safrinha": 0.1, "geada_trigo": 0.2, "veranico_safrinha": 0.3, "n_anos": 40, "periodo": "1985-2024"},
    "geada_por_semeadura": [{"semeadura": "01/02", "prob": 0.1, "anos_com_evento": 4, "n_anos": 40}],
    "diagnostico": {"inicio_chuvas": "15/09"},
}
DIAG = {
    "area": {
        "origem": "talhao_demo",
        "talhao_id": "72638",
        "area_ha": 58.2,
        "centroide": {"lat": -24.95, "lon": -53.45},
        "municipio": {"cod_ibge": "4104808", "nome": "Cascavel"},
        "geometry": {"type": "Polygon", "coordinates": []},
    },
    "relevo": {"declividade_media": 3.1},
    "solo": {"argila": 55},
    "historico": [{"ano": 2023, "classe": "soja"}],
    "rotacao_detectada": {"rotacao": "milho_safrinha", "fonte": "mapbiomas", "dias_solo_descoberto": 30},
    "clima": CLIMA,
    "produtividade": {"soja": 58},
    "avisos": [],
}
REC = {
    "entrada": {"semeadura_safrinha": "01/02"},
    "diagnostico": DIAG,
    "ranking": [
        {
            "posicao": 1,
            "id": "milho_safrinha",
            "rotacao": "Milho safrinha",
            "nota": 7.4,
            "atual": False,
            "criterios": {"renda": 8, "solo": 6, "agua": 7, "pragas": 7, "risco": 6},
            "contribuicoes": {"renda": 2.0},
            "margem": {
                "total_r_ha": 1500.0,
                "itens": [
                    {"cultura": "milho", "rendimento_sc_ha": 100, "preco": 58, "custo": 3500, "margem_r_ha": 1500, "fonte": "PAM"}
                ],
                "ano_ruim_r_ha": -200.0,
            },
            "card": {"por_que": "x", "evidencias": [], "beneficios": [], "lacunas": [], "riscos": [], "avisos": []},
        }
    ],
    "atual": None,
    "alternativas": [],
    "eliminadas": [{"id": "soja_safrinha", "rotacao": "Soja safrinha", "motivos": ["soja sobre soja"]}],
    "avisos": [],
    "metodologia": {"formula": "soma ponderada", "criterios": {}, "versao": "0.1"},
}
OPCOES = {
    "rotacoes": {"milho_safrinha": "Milho safrinha"},
    "semeaduras": ["15/01", "01/02", "15/02", "01/03", "15/03"],
    "semeadura_padrao": "01/02",
    "criterios": ["renda", "solo", "agua", "pragas", "risco"],
    "pesos_padrao": {"renda": 5, "solo": 3, "agua": 3, "pragas": 3, "risco": 3},
    "renda_referencia": {},
    "regiao": {"nome": "Oeste do PR"},
    "talhoes_demo": [{"talhao_id": "72638", "nome": "Talhão 72638"}],
}


@pytest.fixture
def chamadas():
    return []


@pytest.fixture
def falso(monkeypatch, chamadas):
    def diagnosticar(area, semeadura_safrinha="01/02"):
        chamadas.append(("diagnosticar", area, {"semeadura_safrinha": semeadura_safrinha}))
        return DIAG

    def recomendar(area, semeadura_safrinha="01/02", **kw):
        chamadas.append(("recomendar", area, {"semeadura_safrinha": semeadura_safrinha, **kw}))
        return REC

    monkeypatch.setattr(svc, "aquecer", lambda: None)
    monkeypatch.setattr(svc, "opcoes", lambda: OPCOES)
    monkeypatch.setattr(svc, "diagnosticar", diagnosticar)
    monkeypatch.setattr(svc, "recomendar", recomendar)
    return svc


@pytest.fixture
def client(falso):
    from field_shift_api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
