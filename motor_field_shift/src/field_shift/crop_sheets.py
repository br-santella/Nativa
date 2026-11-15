"""Agronomic crop sheets from `catalog/crops.yaml` (ranges with unit and source: Embrapa, FAO Ecocrop, FAO-56).

Two uses, both informative (they never change the score):
1. Compare the farmer's soil pH (`analise_solo.ph`) with the pH range of each crop of a candidate (card evidence).
2. Expose the sheets to the API (`GET /v1/culturas/fichas` and the `ficha` id in `/v1/opcoes`) so the frontend can show
   the source of each number.

The engine's crop ids differ from the catalog's (and the catalog covers fewer crops): `ENGINE_TO_SHEET` maps them; an engine
crop without a sheet maps to None. If the catalog file is missing (engine-only deploy), there are no sheets and the card says so.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from field_shift.i18n import Msg

CATALOG_PATH = Path(__file__).resolve().parents[3] / "catalog" / "crops.yaml"

# Engine crop id (summer or 2nd window) -> catalog sheet id. Missing / None: the catalog has no sheet for that crop.
ENGINE_TO_SHEET: dict[str, str | None] = {
    # summer
    "soja": "soja",
    "milho_verao": "milho",
    # 2nd window
    "milho_safrinha": "milho",
    "milho_braquiaria": "milho",  # the sheet covers the corn only, not the brachiaria
    "soja_safrinha": "soja",
    "trigo": "trigo",
    "aveia": "aveia_branca",  # same species (Avena sativa); the sheet is written for grain, the engine uses it as cover/straw
    "aveia_nabo": "aveia_branca",  # the sheet covers the oat only, not the forage radish
    "milheto_crotalaria": None,
    "sorgo": None,
    "feijao_safrinha": None,
    "nabo_forrageiro": None,
    "pousio": None,
}
NO_CROP = {"pousio"}  # no crop, nothing to compare
WATER_PH_UNIT = "pH em água"  # unit of the farmer's report (`analise_solo.ph`)


@lru_cache(maxsize=1)
def sheets() -> dict[str, dict]:
    """All sheets by catalog id ({} if the catalog file is missing or unreadable)."""
    try:
        data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
        return dict(data["culturas"])
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return {}


def sheet_id(engine_crop: str) -> str | None:
    """Catalog sheet id of an engine crop, or None (no sheet, or catalog unavailable)."""
    sid = ENGINE_TO_SHEET.get(engine_crop)
    return sid if sid in sheets() else None


def public_sheets() -> dict:
    """Payload of `GET /v1/culturas/fichas`: every sheet (as in the catalog, with its id) plus the engine -> sheet mapping."""
    return dict(
        fichas=[dict(id=k, **v) for k, v in sheets().items()],
        mapeamento={k: sheet_id(k) for k in ENGINE_TO_SHEET},
        fonte="catalog/crops.yaml: faixas com unidade e fonte (Embrapa, FAO Ecocrop, FAO-56); informativo, não entra na nota",
    )


def _num(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def ph_range(sid: str) -> dict | None:
    return (sheets().get(sid) or {}).get("requisitos_solo", {}).get("ph")


def ph_status(ph: float, rng: dict) -> str:
    """'abaixo', 'dentro' or 'acima' of the sheet's range (bounds inclusive)."""
    return "abaixo" if ph < rng["min"] else "acima" if ph > rng["max"] else "dentro"


def _ph_line(ph: float, crop_name: str, rng: dict) -> str:
    status = ph_status(ph, rng)
    where = {"abaixo": "abaixo da", "dentro": "dentro da", "acima": "acima da"}[status]
    unit = rng.get("unidade") or "pH"
    method = "" if unit == WATER_PH_UNIT else "; a fonte não especifica o método de medição e o laudo é pH em água"
    return Msg("pH do solo {0} (análise do produtor) {1} faixa de referência de {2} na ficha do catálogo ({3}–{4}, {5}; fonte: {6}{7}); "
               "informativo, não muda a nota.", _num(ph), where, crop_name, _num(rng["min"]), _num(rng["max"]), unit, rng["fonte"], method)


def ph_card(c: dict, ph: float | None) -> dict:
    """Card lines for the farmer's pH against the sheets of the candidate's crops (summer and 2nd window).
    `evidencias`: one line per crop with a sheet and a pH range; `lacunas`: crops without a sheet. Nothing when pH was not given."""
    ev, gap = [], []
    if ph is None:
        return dict(evidencias=ev, lacunas=gap)
    seen = set()
    for crop, name in ((c["verao"], c["nome_verao"]), (c["segunda"], c["nome_segunda"])):
        if crop in NO_CROP:
            continue
        sid = sheet_id(crop)
        rng = ph_range(sid) if sid else None
        if sid in seen:
            continue
        if rng is None:
            gap.append(Msg("pH do solo informado, mas {0} não tem ficha com faixa de pH no catálogo: não comparado.", name))
            continue
        seen.add(sid)
        ev.append(_ph_line(ph, sheets()[sid]["nome"], rng))
    if ev:
        gap.append("Faixas de pH das fichas do catálogo (Embrapa/FAO Ecocrop) são faixas ótimas gerais, não recomendação de calagem; "
                   "a calagem segue a saturação por bases do Manual PR.")
    return dict(evidencias=ev, lacunas=gap)
