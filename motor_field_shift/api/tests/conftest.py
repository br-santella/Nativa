"""Fixtures: serviço falso (monkeypatch) para testar a API sem dados em data/."""

from __future__ import annotations

import sys
import types

import pytest

try:  # serviço real, se já existir
    from field_shift.core import service  # noqa: F401

    REAL_SERVICE = True
except ImportError:  # registra um módulo mínimo para a API poder ser importada
    REAL_SERVICE = False
    import field_shift

    _mod = types.ModuleType("field_shift.core.service")

    class OutOfRegion(Exception): ...

    class InvalidInput(Exception): ...

    _mod.OutOfRegion = OutOfRegion
    _mod.InvalidInput = InvalidInput
    _mod.ROTATIONS = {"milho_safrinha": "Milho safrinha"}
    for _n in ("options", "diagnose", "recommend", "warm_up"):
        setattr(_mod, _n, lambda *a, **k: None)
    _pkg = types.ModuleType("field_shift.core")
    _pkg.__path__ = []
    _pkg.service = _mod
    sys.modules["field_shift.core"] = _pkg
    sys.modules["field_shift.core.service"] = _mod
    field_shift.core = _pkg

from fastapi.testclient import TestClient  # noqa: E402

from field_shift.core import service as svc  # noqa: E402

CLIMATE = {
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
    "clima": CLIMATE,
    "produtividade": {"soja": 58},
    "avisos": [],
}
_ITEM = {
            "posicao": 1,
            "id": "milho_verao__aveia",
            "rotacao": "Milho verão → aveia",
            "nota": 6.1,
            "atual": False,
            "criterios": {"renda": 5, "solo": 6, "agua": 7, "pragas": 7, "risco": 6},
            "contribuicoes": {},
            "margem": {"total_r_ha": 900.0, "itens": [], "ano_ruim_r_ha": 100.0},
            "card": {"por_que": "y", "evidencias": [], "beneficios": [], "lacunas": [], "riscos": [], "avisos": []},
            "ganho_vs_atual": {"comparado_com": "soja__milho_safrinha", "soja_seguinte_sc": 2.0, "soja_seguinte_sc_faixa": [2.0, 2.0], "soja_seguinte_rs": 240.0},
}
REC = {
    "entrada": {"semeadura_safrinha": "01/02"},
    "cultura_atual": {"id": "soja", "nome": "Soja"},
    "estagio_verao": {"id": "enchimento_graos", "nome": "Enchimento de grãos (R5–R6)", "dias_tipicos_ate_colheita": 32},
    "colheita_estimada": {"data": "02/01", "origem": "estagio"},
    "semeadura_2a": {"data": "15/01", "origem": "derivada"},
    "dias_ate_colheita": 32,
    "proxima_safra": {"ranking": [_ITEM], "alternativas": [], "eliminadas": []},
    "diagnostico": DIAG,
    "ranking": [
        {
            "posicao": 1,
            "id": "soja__milho_safrinha",
            "id_legado": "milho_safrinha",
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
    "eliminadas": [{"id": "soja__soja_safrinha", "rotacao": "Soja safrinha", "motivos": ["soja sobre soja"]}],
    "avisos": [],
    "metodologia": {"formula": "soma ponderada", "criterios": {}, "versao": "0.1"},
}
REC["agora"] = {"ranking": REC["ranking"], "alternativas": [], "eliminadas": REC["eliminadas"]}
OPTIONS = {
    "rotacoes": [{"id": "soja__milho_safrinha", "nome": "Soja → milho safrinha"}],
    "culturas_verao": [{"id": "soja", "nome": "Soja", "tipo": "grão"}],
    "culturas_segunda": [{"id": "milho_safrinha", "nome": "Milho safrinha", "tipo": "grão"}],
    "combinacoes": [{"id": "soja__milho_safrinha", "verao": "soja", "segunda": "milho_safrinha", "valida": True}],
    "semeaduras": ["15/01", "01/02", "15/02", "01/03", "15/03"],
    "semeadura_padrao": "01/02",
    "criterios": ["renda", "solo", "agua", "pragas", "risco"],
    "pesos_padrao": {"renda": 5, "solo": 3, "agua": 3, "pragas": 3, "risco": 3},
    "renda_referencia": {},
    "regiao": {"nome": "Paraná"},
    "talhoes_demo": [{"talhao_id": "72638", "nome": "Talhão 72638"}],
}


@pytest.fixture
def calls():
    return []


@pytest.fixture
def fake(monkeypatch, calls):
    def diagnose(area, sowing_second="01/02", **kw):
        calls.append(("diagnose", area, {"sowing_second": sowing_second, **kw}))
        return DIAG

    def recommend(area, sowing_second="01/02", **kw):
        calls.append(("recommend", area, {"sowing_second": sowing_second, **kw}))
        return REC

    monkeypatch.setattr(svc, "warm_up", lambda: None)
    monkeypatch.setattr(svc, "options", lambda: OPTIONS)
    monkeypatch.setattr(svc, "diagnose", diagnose)
    monkeypatch.setattr(svc, "recommend", recommend)
    return svc


@pytest.fixture
def client(fake):
    from field_shift_api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
