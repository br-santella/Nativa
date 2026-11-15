"""Rendimento municipal (IBGE PAM, SIDRA 1612, 839 e 1002), lido de data/raw/ibge/pam_pr.parquet e, se existir,
de data/raw/ibge/pam_extra_pr.parquet (ou pam_extra_oeste_pr.parquet; sorgo e feijão 2ª safra; ingest/pam_culturas_extra.py), mesmo esquema.

produtividade(cod_ibge) -> {cultura: {...}}; culturas: soja, milho_total, milho_1safra, milho_2safra, trigo, aveia, sorgo, feijao_2safra.
Saca = 60 kg (soja, milho, trigo, sorgo, feijão); aveia só em kg/ha. Últimos YIELD_WINDOW_YEARS (10) anos COM dado (até 2025, se existir).
Expected yield (`kg_ha`/`sc_ha`) = linear trend of that window projected to the next season, clipped to the window's min–max
(`expected_yield`); the plain mean stays in `media_kg_ha`/`media_sc_ha`. CV and the p20 "bad year" (renda.py) use the same window.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PAM = ROOT / "data/raw/ibge/pam_pr.parquet"
PAM_EXTRA_PR = ROOT / "data/raw/ibge/pam_extra_pr.parquet"  # sorgo e feijão 2ª safra, 399 municípios (ingest/pam_culturas_extra.py --regiao pr)
PAM_EXTRA = ROOT / "data/raw/ibge/pam_extra_oeste_pr.parquet"  # só os 50 municípios do Oeste; usado se o do PR inteiro não existir
BAG_KG = {"soja": 60, "milho_total": 60, "milho_1safra": 60, "milho_2safra": 60, "trigo": 60, "sorgo": 60, "feijao_2safra": 60}
MIN_YEAR = {"sorgo": 2013, "feijao_2safra": 2013}  # séries antigas/interrompidas do sorgo e do feijão 2ª safra não representam o manejo atual
YIELD_WINDOW_YEARS = 10  # single window for the expected yield (trend), CV and the p20 "bad year" (renda._p20_sc)
MIN_YEARS_TREND = 5  # fewer years: the expected yield is the plain mean
NAMES = {"soja": "soja", "milho_total": "milho", "milho_1safra": "milho 1ª safra", "milho_2safra": "milho 2ª safra",
         "trigo": "trigo", "aveia": "aveia", "sorgo": "sorgo", "feijao_2safra": "feijão 2ª safra"}


@lru_cache(maxsize=1)
def _yield() -> pd.DataFrame:
    d = pd.read_parquet(PAM)
    extra = PAM_EXTRA_PR if PAM_EXTRA_PR.exists() else PAM_EXTRA  # the state-wide file already contains the Oeste: never read both
    if extra.exists():
        d = pd.concat([d, pd.read_parquet(extra)], ignore_index=True)
    d = d[d["variavel"] == "rendimento_kg_ha"]
    return d.pivot_table(index=["cod_ibge", "ano"], columns="cultura", values="valor").sort_index()


def series(cod_ibge, crop: str) -> pd.Series:
    """Rendimento anual (kg/ha) do município; NaN removidos."""
    r = _yield()
    try:
        s = r.xs(str(int(cod_ibge)), level="cod_ibge")[crop]
    except KeyError:
        return pd.Series(dtype=float)
    s = s.dropna()
    return s[s.index >= MIN_YEAR[crop]] if crop in MIN_YEAR else s


def expected_yield(u: pd.Series) -> tuple[float, float]:
    """Expected yield (kg/ha) of the next season from the window `u` (index = year): the linear trend of the window projected to
    the year after its last one, clipped to the window's [min, max]; the plain mean when there are fewer than MIN_YEARS_TREND
    years. Returns (expected, slope kg/ha/yr; NaN without trend).

    Why: in the historical backtest (docs/validation.md §3) the 10-year mean underestimated the next season by 7–12 % (median,
    Oeste 2008–2025: technology gains), while the clipped trend has a bias of −1 % (off-season corn, wheat, summer corn) to −6 %
    (soybean) with the same absolute error. The clip keeps one extreme year at the end of the window from throwing the projection
    outside what the municipality has ever produced."""
    if len(u) < MIN_YEARS_TREND:
        return float(u.mean()), float("nan")
    slope, icpt = np.polyfit(u.index.values.astype(float), u.values, 1)
    proj = slope * (float(u.index[-1]) + 1) + icpt
    return float(np.clip(proj, u.min(), u.max())), float(slope)


def productivity(cod_ibge, n_years: int = YIELD_WINDOW_YEARS) -> dict:
    out = {}
    for cult in NAMES:
        s = series(cod_ibge, cult)
        if len(s) == 0:
            continue
        u = s.iloc[-n_years:]
        exp, slope = expected_yield(u)
        out[cult] = dict(
            kg_ha=exp, sc_ha=exp / BAG_KG[cult] if cult in BAG_KG else None,
            media_kg_ha=float(u.mean()), media_sc_ha=float(u.mean() / BAG_KG[cult]) if cult in BAG_KG else None,
            metodo="tendência" if len(u) >= MIN_YEARS_TREND else "média",
            cv=float(u.std(ddof=0) / u.mean()) if len(u) >= 4 else np.nan,
            tendencia_kg_ha_ano=slope, anos=f"{int(u.index[0])}–{int(u.index[-1])}", n=len(u))
    return out


def text(mun_name: str, p: dict) -> str:
    """Linha pronta para exibição."""
    parts = []
    for c in ("soja", "milho_2safra", "trigo"):
        if c in p:
            parts.append(f"{NAMES[c]} {p[c]['sc_ha']:.0f} sc/ha")
    if "aveia" in p:
        parts.append(f"aveia {p['aveia']['kg_ha']:.0f} kg/ha")
    years = p[next(iter(p))]["anos"] if p else ""
    return (f"Rendimento esperado em {mun_name} (tendência da PAM {years}, projetada para a próxima safra): " + ", ".join(parts)
            + ".")
