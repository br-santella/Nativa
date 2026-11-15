"""Message catalog and response translation (pt-BR -> en)."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from field_shift import i18n
from field_shift.i18n import Translator, locale_from_accept_language, normalize_locale, resolve_locale

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{\d+\}")


def _catalog() -> dict:
    return json.loads(i18n.CATALOG_FILE.read_text(encoding="utf-8"))


def test_every_template_has_english():
    missing = [k for k, v in _catalog().items() if not v]
    assert not missing, f"{len(missing)} templates without English, e.g. {missing[:3]}"


def test_placeholders_match():
    bad = [k for k, v in _catalog().items() if sorted(PLACEHOLDER.findall(k)) != sorted(PLACEHOLDER.findall(v or ""))]
    assert not bad, bad[:3]


def test_catalog_covers_the_code():
    """Every user-facing Portuguese text in the code/data has an entry (run scripts/i18n_extract.py after adding one)."""
    spec = importlib.util.spec_from_file_location("i18n_extract", ROOT / "scripts" / "i18n_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    missing = sorted(set(mod.extract()) - set(_catalog()))
    assert not missing, f"run `uv run python scripts/i18n_extract.py` and translate: {missing[:5]}"


@pytest.mark.parametrize(("value", "expected"), [
    ("en", "en"), ("en-US", "en"), ("EN_gb", "en"), ("pt", "pt-BR"), ("pt-BR", "pt-BR"), ("pt_PT", "pt-BR"),
    ("fr", None), ("", None), (None, None),
])
def test_normalize_locale(value, expected):
    assert normalize_locale(value) == expected


def test_accept_language_quality_order():
    assert locale_from_accept_language("fr-FR,en;q=0.5,pt;q=0.8") == "pt-BR"
    assert locale_from_accept_language("en-US,en;q=0.9,pt;q=0.8") == "en"
    assert locale_from_accept_language("de, fr") is None
    assert locale_from_accept_language("en;q=abc, pt") == "pt-BR"


def test_resolve_locale_precedence():
    assert resolve_locale("en", "pt-BR") == "en"
    assert resolve_locale("pt-BR", "en") == "pt-BR"
    assert resolve_locale(None, "en-US") == "en"
    assert resolve_locale("xx", None) == "pt-BR"
    assert resolve_locale(None, None) == "pt-BR"


TR = Translator({
    "Milho safrinha": "Second-season corn",
    "soja": "soybean",
    "Custo de {0}: R$ {1}/ha.": "Cost of {0}: R$ {1}/ha.",
    "Total da rotação: R$ {0}/ha/ano": "Rotation total: R$ {0}/ha/year",
    "; em ano ruim: R$ {0}/ha": "; in a bad year: R$ {0}/ha",
    "Fonte: {0}": "Source: {0}",
    "Problema ({0}): {1}": "Problem ({0}): {1}",
    "nematoide": "nematode",
})


def test_translator_exact_template_and_numbers():
    assert TR.translate("Custo de soja: R$ 1.234,5/ha.") == "Cost of soybean: R$ 1,234.5/ha."


def test_translator_case_and_concatenation():
    assert TR.translate("milho safrinha") == "second-season corn"
    assert TR.translate("Total da rotação: R$ 2.000/ha/ano; em ano ruim: R$ 900/ha") == (
        "Rotation total: R$ 2,000/ha/year; in a bad year: R$ 900/ha")


def test_translator_keeps_codes_and_unknown_text():
    assert TR.translate({"id": "soja", "nivel": "não se aplica", "nome": "soja"}) == (
        {"id": "soja", "nivel": "não se aplica", "nome": "soja"})  # whole-value slugs and enum keys are codes
    assert TR.translate({"cultura": "soja"}) == {"cultura": "soybean"}  # display key
    assert TR.translate("Texto sem tradução") == "Texto sem tradução"
    assert TR.translate([1, 2.5, None, True]) == [1, 2.5, None, True]


def test_translator_balanced_values():
    # the value of {0} must not swallow a parenthesis it did not open
    assert TR.translate("Problema (nematoide): soja") == "Problem (nematode): soybean"


def test_pt_br_is_untouched():
    obj = {"a": ["Custo de soja: R$ 1.234,5/ha."]}
    assert i18n.translate(obj, "pt-BR") is obj


def test_msg_is_the_ptbr_text_and_renders_english_from_its_template():
    from field_shift.i18n import Join, Msg, translator
    m = Msg("Maiores contribuições para a nota: {0}.", Join([Msg("{0} ({1})", "Água", "0,18"), Msg("{0} ({1})", "Risco climático", "0,18")], " e "))
    assert m == "Maiores contribuições para a nota: Água (0,18) e Risco climático (0,18)."
    en = translator().translate(m)
    assert en.startswith("Largest contributions to the score: ")
    assert "0.18" in en and " and " in en and "Água" not in en


def test_structural_templates_are_not_used_as_patterns():
    from field_shift.i18n import translator
    # "{0} ({1})" is only for Msg: a plain string must not be matched by it
    assert translator().text("xyzzy (plugh)") == "xyzzy (plugh)"
