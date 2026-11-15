"""Municipal yield (IBGE PAM, SIDRA 1612, 839 and 1002), read from data/raw/ibge/pam_oeste_pr.parquet and, if it exists,
from data/raw/ibge/pam_extra_oeste_pr.parquet (sorghum and 2nd-season beans; ingest/pam_culturas_extra.py), same schema.

produtividade(cod_ibge) -> {crop: {...}}; crops: soja, milho_total, milho_1safra, milho_2safra, trigo, aveia, sorgo, feijao_2safra.
Bag = 60 kg (soybean, corn, wheat, sorghum, beans); oat only in kg/ha. Last 5 years WITH data (up to 2025, if available).
CV = standard deviation / mean of the last 10 years. Trend = slope (kg/ha/year) of the linear regression over the last 10 years.
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
ANO_MIN = {"sorgo": 2013, "feijao_2safra": 2013}  # old/interrupted sorghum and 2nd-season bean series do not represent current management
NOMES = {"soja": "soybean", "milho_total": "corn", "milho_1safra": "1st-season corn", "milho_2safra": "2nd-season corn",
         "trigo": "wheat", "aveia": "oat", "sorgo": "sorghum", "feijao_2safra": "2nd-season beans"}


@lru_cache(maxsize=1)
def _rend() -> pd.DataFrame:
    d = pd.read_parquet(PAM)
    if PAM_EXTRA.exists():
        d = pd.concat([d, pd.read_parquet(PAM_EXTRA)], ignore_index=True)
    d = d[d["variavel"] == "rendimento_kg_ha"]
    return d.pivot_table(index=["cod_ibge", "ano"], columns="cultura", values="valor").sort_index()


def serie(cod_ibge, cultura: str) -> pd.Series:
    """Annual yield (kg/ha) of the municipality; NaN removed."""
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
    """Line ready for display."""
    partes = []
    for c in ("soja", "milho_2safra", "trigo"):
        if c in p:
            partes.append(f"{NOMES[c]} {p[c]['sc_ha']:.0f} bags/ha")
    if "aveia" in p:
        partes.append(f"oat {p['aveia']['kg_ha']:.0f} kg/ha")
    anos = p[next(iter(p))]["anos"] if p else ""
    return f"Mean yield in {nome_mun}, {anos}: " + ", ".join(partes) + "."
