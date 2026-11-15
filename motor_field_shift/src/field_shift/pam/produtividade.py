"""Rendimento municipal (IBGE PAM, SIDRA 1612, 839 e 1002), lido de data/raw/ibge/pam_oeste_pr.parquet e, se existir,
de data/raw/ibge/pam_extra_oeste_pr.parquet (sorgo e feijão 2ª safra; ingest/pam_culturas_extra.py), mesmo esquema.

produtividade(cod_ibge) -> {cultura: {...}}; culturas: soja, milho_total, milho_1safra, milho_2safra, trigo, aveia, sorgo, feijao_2safra.
Saca = 60 kg (soja, milho, trigo, sorgo, feijão); aveia só em kg/ha. Últimos 5 anos COM dado (até 2025, se existir).
CV = desvio padrão / média dos últimos 10 anos. Tendência = inclinação (kg/ha/ano) da regressão linear dos últimos 10 anos.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PAM = ROOT / "data/raw/ibge/pam_oeste_pr.parquet"
PAM_EXTRA = ROOT / "data/raw/ibge/pam_extra_oeste_pr.parquet"
SACA_KG = {"soja": 60, "milho_total": 60, "milho_1safra": 60, "milho_2safra": 60, "trigo": 60, "sorgo": 60, "feijao_2safra": 60}
ANO_MIN = {"sorgo": 2013, "feijao_2safra": 2013}  # séries antigas/interrompidas do sorgo e do feijão 2ª safra não representam o manejo atual
NOMES = {"soja": "soja", "milho_total": "milho", "milho_1safra": "milho 1ª safra", "milho_2safra": "milho 2ª safra",
         "trigo": "trigo", "aveia": "aveia", "sorgo": "sorgo", "feijao_2safra": "feijão 2ª safra"}


@lru_cache(maxsize=1)
def _rend() -> pd.DataFrame:
    d = pd.read_parquet(PAM)
    if PAM_EXTRA.exists():
        d = pd.concat([d, pd.read_parquet(PAM_EXTRA)], ignore_index=True)
    d = d[d["variavel"] == "rendimento_kg_ha"]
    return d.pivot_table(index=["cod_ibge", "ano"], columns="cultura", values="valor").sort_index()


def serie(cod_ibge, cultura: str) -> pd.Series:
    """Rendimento anual (kg/ha) do município; NaN removidos."""
    r = _rend()
    try:
        s = r.xs(str(int(cod_ibge)), level="cod_ibge")[cultura]
    except KeyError:
        return pd.Series(dtype=float)
    s = s.dropna()
    return s[s.index >= ANO_MIN[cultura]] if cultura in ANO_MIN else s


def produtividade(cod_ibge, n_anos: int = 5) -> dict:
    out = {}
    for cult in NOMES:
        s = serie(cod_ibge, cult)
        if len(s) == 0:
            continue
        u = s.iloc[-n_anos:]
        u10 = s.iloc[-10:]
        tend = float(np.polyfit(u10.index.values, u10.values, 1)[0]) if len(u10) >= 4 else np.nan
        out[cult] = dict(
            kg_ha=float(u.mean()), sc_ha=float(u.mean() / SACA_KG[cult]) if cult in SACA_KG else None,
            cv=float(u10.std(ddof=0) / u10.mean()) if len(u10) >= 4 else np.nan,
            tendencia_kg_ha_ano=tend, anos=f"{int(u.index[0])}–{int(u.index[-1])}", n=len(u))
    return out


def texto(nome_mun: str, p: dict) -> str:
    """Linha pronta para exibição."""
    partes = []
    for c in ("soja", "milho_2safra", "trigo"):
        if c in p:
            partes.append(f"{NOMES[c]} {p[c]['sc_ha']:.0f} sc/ha")
    if "aveia" in p:
        partes.append(f"aveia {p['aveia']['kg_ha']:.0f} kg/ha")
    anos = p[next(iter(p))]["anos"] if p else ""
    return f"Rendimento médio em {nome_mun}, {anos}: " + ", ".join(partes) + "."
