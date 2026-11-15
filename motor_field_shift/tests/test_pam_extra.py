"""Selection of the extra PAM file (sorghum and 2nd-season beans): the state-wide file wins over the Oeste-only one."""
import sys

import pandas as pd
import pytest

import field_shift.pam  # noqa: F401  (the package re-exports a function named like the module)

P = sys.modules["field_shift.pam.produtividade"]


def _frame(path, cod, value):
    pd.DataFrame([dict(tabela="1612", cod_ibge=cod, ano=2022, variavel="rendimento_kg_ha", cultura="sorgo", valor=value)]).to_parquet(path)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    base = tmp_path / "pam.parquet"
    pd.DataFrame([dict(tabela="839", cod_ibge="4100001", ano=2022, variavel="rendimento_kg_ha", cultura="soja", valor=3000.0)]).to_parquet(base)
    monkeypatch.setattr(P, "PAM", base)
    P._rend.cache_clear()
    yield tmp_path
    P._rend.cache_clear()


def test_state_wide_file_is_preferred_and_not_duplicated(isolated, monkeypatch):
    oeste, estado = isolated / "oeste.parquet", isolated / "estado.parquet"
    _frame(oeste, "4100001", 1000.0)
    _frame(estado, "4100001", 2000.0)
    monkeypatch.setattr(P, "PAM_EXTRA", oeste)
    monkeypatch.setattr(P, "PAM_EXTRA_PR", estado)
    assert P._rend().loc[("4100001", 2022), "sorgo"] == 2000.0


def test_falls_back_to_the_oeste_file(isolated, monkeypatch):
    oeste = isolated / "oeste.parquet"
    _frame(oeste, "4100001", 1000.0)
    monkeypatch.setattr(P, "PAM_EXTRA", oeste)
    monkeypatch.setattr(P, "PAM_EXTRA_PR", isolated / "inexistente.parquet")
    assert P._rend().loc[("4100001", 2022), "sorgo"] == 1000.0
