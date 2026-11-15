"""Unit tests of the ZARC comparison helpers (no ZARC data needed). Run: uv run pytest tests/test_validation_zarc.py"""
import pytest

from field_shift.app import engine as E
from field_shift.validation import zarc as Z


@pytest.mark.parametrize("ddmm,dec", [("01/01", 1), ("10/01", 1), ("11/01", 2), ("15/01", 2), ("21/01", 3), ("31/01", 3),
                                      ("01/02", 4), ("15/02", 5), ("28/02", 6), ("01/03", 7), ("15/03", 8),
                                      ("01/05", 13), ("15/10", 29), ("31/12", 36)])
def test_dekad(ddmm, dec):
    assert Z.dekad(ddmm) == dec


@pytest.mark.parametrize("p,cls", [(0.0, 20), (0.20, 20), (0.21, 30), (0.30, 30), (0.35, 40), (0.40, 40), (0.41, Z.OUT_CLASS)])
def test_loss_class(p, cls):
    assert Z.loss_class(p) == cls


def test_engine_loss_matches_risk_criterion_formula():
    rk = {"geada_safrinha": 0.2, "veranico_safrinha": 0.1, "geada_trigo": 0.3}  # no soil: the deficit falls back to the dry spell
    corn = E.CATALOG[E.NOME_DE["soja__milho_safrinha"]]
    assert Z.engine_loss(corn, rk) == pytest.approx(1 - 0.8 * 0.9)
    assert Z.engine_loss(E.CATALOG[E.NOME_DE["soja__aveia"]], rk) == 0.0


def test_crop_mapping_covers_every_sowing_dependent_grain():
    zoned = set(Z.SECOND_CROPS)
    grains = {k for k, s in E.SECOND.items() if s["segue_semeadura"] and s["tipo"] == "grão" and not s["ano_soja_2"]}
    assert grains <= zoned
