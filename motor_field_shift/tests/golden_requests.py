"""Requests replayed by the golden API tests (tests/test_golden_api.py).

The snapshots in tests/golden/ were recorded from the API before the English migration;
any change in a response body or status code is a contract break.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("generate_examples_requests", ROOT / "scripts" / "generate_examples.py")


def _example_requests() -> dict:
    # Read REQUESTS without importing the API app at module import time.
    src = (ROOT / "scripts" / "generate_examples.py").read_text(encoding="utf-8")
    head = src.split("def main()")[0]
    head = head.replace("from field_shift_api.main import app  # noqa: E402", "")
    ns: dict = {"__file__": str(ROOT / "scripts" / "generate_examples.py")}
    exec(compile(head, "generate_examples.py", "exec"), ns)  # noqa: S102
    return ns["REQUESTS"]


FIELD = {"talhao_id": "72638"}

EXTRA = {
    "health": ("GET", "/health", None),
    "diagnostico_analise_solo": ("POST", "/v1/diagnostico", {
        "area": FIELD, "semeadura_safrinha": "15/02",
        "analise_solo": {"argila_pct": 60, "ph": 5.0, "p_mg_dm3": 6, "k_cmolc_dm3": 0.2}}),
    "recomendacao_sem_estagio": ("POST", "/v1/recomendacao", {"area": FIELD, "rotacao_atual": "soja__milho_safrinha", "data_referencia": "2026-12-01"}),
    "recomendacao_colheita_prevista": ("POST", "/v1/recomendacao", {
        "area": FIELD, "rotacao_atual": "soja__milho_safrinha", "colheita_prevista": "2027-02-10",
        "data_referencia": "2026-12-01", "incluir_diagnostico": False}),
    "recomendacao_irrigacao_custos": ("POST", "/v1/recomendacao", {
        "area": {"lat": -24.7, "lon": -53.7}, "rotacao_atual": "milho_verao__aveia", "estagio_verao": "grao_farinaceo",
        "data_referencia": "2026-12-01", "irrigacao": {"disponivel": True, "custo_r_mm_ha": 3.0},
        "ajustes": {"custos": {"milho": 4000}}, "problemas_area": ["percevejo", "erosao"]}),
    "diagnostico_analise_solo_valida": ("POST", "/v1/diagnostico", {
        "area": FIELD, "analise_solo": {"argila_pct": 60, "areia_pct": 15, "ph": 5.0, "p_mg_dm3": 6, "k_cmolc_dm3": 0.2}}),
    "recomendacao_colheita_prevista_valida": ("POST", "/v1/recomendacao", {
        "area": FIELD, "rotacao_atual": "soja__milho_safrinha", "colheita_prevista": "10/02",
        "data_referencia": "2026-12-01", "incluir_diagnostico": False}),
    "recomendacao_irrigacao_custos_valida": ("POST", "/v1/recomendacao", {
        "area": {"lat": -24.7, "lon": -53.7}, "rotacao_atual": "milho_verao__aveia", "estagio_verao": "grao_farinaceo",
        "data_referencia": "2026-12-01", "irrigacao": {"disponivel": True, "custo_r_mm_ha": 3.0},
        "ajustes": {"custos": {"milho": 4000}}, "problemas_area": ["cigarrinha", "compactacao"]}),
    "erro_talhao_inexistente": ("POST", "/v1/recomendacao", {"area": {"talhao_id": "nao_existe"}, "rotacao_atual": "soja__milho_safrinha"}),
    "erro_sem_area": ("POST", "/v1/diagnostico", {"area": {}}),
}


def all_requests() -> dict:
    reqs = dict(_example_requests())
    reqs.pop("recomendacao_talhao_72638_2a_chamada", None)  # same body as the first call
    reqs.update(EXTRA)
    return reqs
