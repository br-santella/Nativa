"""Regenerates api/exemplos/*.json from the REAL API (in-process TestClient).

Run from the motor_field_shift folder:  uv run python scripts/generate_examples.py
The examples are documentation of the public contract, so they must always be produced by the API itself, never edited by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))  # field_shift_api lives in api/, outside the installed package
from field_shift_api.main import app  # noqa: E402

OUT = ROOT / "api" / "exemplos"
STAGE = {"estagio_verao": "enchimento_graos", "data_referencia": "2026-12-01"}
FIELD = {"talhao_id": "72638"}
POLYGON = {"type": "Polygon", "coordinates": [[[-53.3045, -24.9045], [-53.3045, -24.8955], [-53.2955, -24.8955], [-53.2955, -24.9045], [-53.3045, -24.9045]]]}


def rec(**kw):
    return ("POST", "/v1/recomendacao", dict(rotacao_atual="soja__milho_safrinha", **STAGE, **kw))


REQUESTS = {
    "recomendacao_talhao_72638": rec(area=FIELD),
    "recomendacao_talhao_72638_2a_chamada": rec(area=FIELD),
    "recomendacao_dados_proprios": rec(
        area=FIELD, ajustes={"produtividade": {"soja": 65, "milho": 110, "trigo": 50}},
        analise_solo={"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "ph": 5.4, "cad_mm_cm": 1.4},
        restricoes={"culturas_excluidas": ["trigo"], "maquinas": {"plataforma_milho": True, "semeadora_consorcio": False}, "sem_comprador": ["aveia_grao"]},
        irrigacao={"disponivel": True, "custo_r_mm_ha": 4.5}),
    "recomendacao_pesos": rec(area=FIELD, pesos={"renda": 9, "solo": 2, "agua": 3, "pragas": 4, "risco": 6}, n_alternativas=4),
    "recomendacao_poligono_cascavel": rec(area={"geometry": POLYGON}, semeadura_safrinha="15/02"),
    "recomendacao_ponto_guaira": rec(area={"lat": -24.2, "lon": -54.2}),
    "recomendacao_precos": rec(area=FIELD, ajustes={"precos": {"soja": 125, "milho": 58, "trigo": 82}, "linha_custo": "cot"}),
    "recomendacao_rotacoes": rec(area=FIELD, semeadura_safrinha="01/03", rotacoes=[
        {"verao": "soja", "segunda": "milho_safrinha"}, {"verao": "soja", "segunda": "sorgo"},
        {"verao": "milho_verao", "segunda": "aveia_nabo"}, {"verao": "milho_verao", "segunda": "milho_safrinha"},
        {"verao": "milho_verao", "segunda": "soja_safrinha"}]),
    "recomendacao_estado_area": rec(
        area=FIELD, problemas_area=["mofo_branco", "nematoide", "compactacao"],
        analise_solo={"argila_pct": 55, "areia_pct": 15, "p_mg_dm3": 4, "k_cmolc_dm3": 0.10, "ca_cmolc_dm3": 2.5, "mg_cmolc_dm3": 0.8,
                      "al_cmolc_dm3": 0.9, "ctc_cmolc_dm3": 9.0}),
    "recomendacao_atual_eliminada": ("POST", "/v1/recomendacao", dict(area=FIELD, rotacao_atual="soja__soja_safrinha", **STAGE)),
    "diagnostico_talhao_72638": ("POST", "/v1/diagnostico", {"area": FIELD, "semeadura_safrinha": "01/02"}),
    "clima_ponto": ("GET", "/v1/clima?lat=-24.95&lon=-53.45&semeadura_safrinha=01/02", None),
    "opcoes": ("GET", "/v1/opcoes", None),
    "talhoes_demo": ("GET", "/v1/talhoes/demo", None),
    "recomendacao_ponto_curitiba": rec(area={"lat": -25.43, "lon": -49.27}),  # outside the Oeste: Região 1 calendar and prices warning
    "erro_fora_da_regiao": ("POST", "/v1/recomendacao", dict(area={"lat": -23.55, "lon": -46.63}, rotacao_atual="soja__milho_safrinha", **STAGE)),  # São Paulo
    "erro_validacao": rec(area=FIELD, pesos={"renda": 11}),
    "erro_ajuste_invalido": rec(area=FIELD, ajustes={"custos": {"milho": -1}}),
}


def main() -> None:
    with TestClient(app) as client:
        for name, (method, url, body) in REQUESTS.items():
            r = client.request(method, url, json=body) if body is not None else client.get(url)
            print(name, r.status_code)
            compact = name.startswith("erro") or name == "talhoes_demo"  # errors and the demo list stay in one line
            txt = json.dumps(r.json(), ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(r.json(), ensure_ascii=False, indent=2)
            (OUT / f"{name}.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
