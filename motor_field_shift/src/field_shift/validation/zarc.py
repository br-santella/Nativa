"""Agreement between the engine's calendar/climate-risk logic and ZARC (Zoneamento Agrícola de Risco Climático, MAPA).

ZARC "tábua de risco" (dados.agricultura.gov.br, one CSV per season): for every crop, municipality, soil class and cycle group
it lists the 36 ten-day periods (decêndios) of the year with the sowing risk class: 20, 30 or 40 (% chance of loss), 0 = not
indicated. The engine's climate-risk criterion is Π(1 − pᵢ) over the candidate's risks (frost in the critical phase and, since the
recalibration of §2.4, the water deficit of the FAO-56 balance with the municipality's soil; NASA POWER 1991–2024), so its loss
probability 1 − Π(1 − pᵢ) is directly comparable with the ZARC class. The ZARC table is the same one the engine uses
(`field_shift.zarc`, built by `ingest/zarc_pr.py`).

ZARC side, per (crop, municipality, ten-day period): rainfed rows only, the lowest risk over cycle groups for each soil, then
`best` = lowest over soils (the most permissive reading: "is there a ZARC-indicated option?") and `share_soils` = share of the
soil classes in which the period is indicated.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from shapely.geometry import box

from field_shift import zarc as RZ
from field_shift.app import engine as E
from field_shift.climate.lookup import MUN, indicators_for

ROOT = Path(__file__).resolve().parents[3]
RAW = RZ.RAW_DIR
ZARC_PR = RZ.RAW_PR
SEASON = RZ.SEASON
OESTE_MESOREGION = "06"  # IBGE mesoregion "Oeste Paranaense" (Cod_Meso in the ZARC table)
OUT_CLASS = RZ.NOT_INDICATED  # "not indicated" in ordinal comparisons (above the 40 % class)
HALF_SIDE_DEG = 0.0045  # ~100 ha square around the municipality centroid for the soil (SoilGrids) of the water balance

# engine second-window crop -> ZARC crop name
SECOND_CROPS = {
    "milho_safrinha": "Milho 2ª Safra",
    "milho_braquiaria": "Milho 2ª Safra consorciado com Braquiária",
    "sorgo": "Sorgo Granífero 2ª Safra",
    "feijao_safrinha": "Feijão 2ª Safra",
}
# fixed-date crops: engine crop -> (ZARC crop, engine sowing date)
FIXED_CROPS = {
    "trigo": ("Trigo", "01/05"),
    "aveia": ("Aveia", "01/05"),
    "soja (verão)": ("Soja", "15/10"),
    "milho_verao": ("Milho 1ª Safra", "01/10"),
}


dekad = RZ.dekad


@lru_cache(maxsize=1)
def zarc_pr() -> pd.DataFrame:
    return pd.read_parquet(ZARC_PR, columns=["geocodigo", "Cod_Meso"])


@lru_cache(maxsize=None)
def zarc_classes(crop: str) -> pd.DataFrame:
    """Per (geocodigo, decendio): `best` class (20/30/40, OUT_CLASS if not indicated) and `share_soils` indicated
    (the engine's own compact table)."""
    t = RZ.table()
    if t is None:
        raise FileNotFoundError("ZARC table missing: run `uv run python ingest/zarc_pr.py`")
    t = t.reset_index()
    return t[t["crop"] == crop][["geocodigo", "decendio", "best", "share_soils"]].reset_index(drop=True)


def loss_class(p_loss: float) -> int:
    """Engine loss probability in the ZARC classes (20 / 30 / 40 / not indicated)."""
    return 20 if p_loss <= 0.20 + 1e-9 else 30 if p_loss <= 0.30 + 1e-9 else 40 if p_loss <= 0.40 + 1e-9 else OUT_CLASS


@lru_cache(maxsize=1)
def municipalities() -> pd.DataFrame:
    import geopandas as gpd
    m = gpd.read_file(MUN)
    meso = zarc_pr()[["geocodigo", "Cod_Meso"]].drop_duplicates().set_index("geocodigo")["Cod_Meso"]
    m["geocodigo"] = m["cod_ibge"].astype(str)
    m["oeste"] = m["geocodigo"].map(meso).eq(OESTE_MESOREGION)
    return pd.DataFrame(m.drop(columns="geometry"))


def engine_side(lat: float, lon: float, sowing: str) -> dict | None:
    """Engine context of one municipality and sowing date: climate risks of the cell plus the soil (SoilGrids, ~100 ha square at
    the centroid) that the water balance needs, exactly as `engine.enriquecer` builds it for a field."""
    info = indicators_for(lat, lon)
    if info is None:
        return None
    rk = E.region_climate(info, sowing)
    h = HALF_SIDE_DEG
    rk = E.enrich(rk, dict(poly=box(lon - h, lat - h, lon + h, lat + h)))
    rk["semeadura"] = sowing
    return rk


def _candidate(second: str, summer: str = "soja") -> dict:
    return E.CATALOG[E.NOME_DE[E.rotation_id(summer, second)]]


def engine_loss(c: dict, rk: dict) -> float:
    """1 − Π(1 − pᵢ) over the candidate's climate risks (rainfed): same formula as the risk criterion in engine.pontuar
    (per-candidate probabilities from `engine.risk_probability`)."""
    nome = E.NOME_DE[c["id"]]
    return float(1 - np.prod([1 - E.risk_probability(nome, r, rk) for r in c["riscos"]])) if c["riscos"] else 0.0


def second_window_table() -> pd.DataFrame:
    """One row per (municipality, second-window crop, engine sowing date) with the engine and ZARC views."""
    rows = []
    for m in municipalities().itertuples():
        for sow in E.SOWINGS_2ND:
            rk = engine_side(m.lat_c, m.lon_c, sow)
            if rk is None:
                continue
            dec = dekad(sow)
            for crop, zname in SECOND_CROPS.items():
                c = _candidate(crop)
                z = zarc_classes(zname)
                hit = z[(z["geocodigo"] == m.geocodigo) & (z["decendio"] == dec)]
                if hit.empty:
                    continue
                p = engine_loss(c, rk)
                rows.append(dict(geocodigo=m.geocodigo, municipio=m.nome, oeste=m.oeste, crop=crop, sowing=sow, decendio=dec,
                                 engine_valid=not E.check_rules(c, rk), engine_loss=p, engine_class=loss_class(p),
                                 zarc_class=int(hit["best"].iloc[0]), zarc_share_soils=float(hit["share_soils"].iloc[0])))
    df = pd.DataFrame(rows)
    df["zarc_indicated"] = df["zarc_class"] < OUT_CLASS
    df["engine_within"] = df["engine_class"] < OUT_CLASS
    return df


def fixed_date_table() -> pd.DataFrame:
    """Winter crops and summer crops at the engine's fixed sowing dates: ZARC class and, for wheat, the engine frost risk."""
    rows = []
    for m in municipalities().itertuples():
        rk = engine_side(m.lat_c, m.lon_c, E.SOWINGS_2ND[0])
        if rk is None:
            continue
        for crop, (zname, sow) in FIXED_CROPS.items():
            z = zarc_classes(zname)
            hit = z[(z["geocodigo"] == m.geocodigo) & (z["decendio"] == dekad(sow))]
            if hit.empty:
                continue
            p = engine_loss(_candidate(crop), rk) if crop in E.SECOND else None
            rows.append(dict(geocodigo=m.geocodigo, municipio=m.nome, oeste=m.oeste, crop=crop, sowing=sow,
                             zarc_class=int(hit["best"].iloc[0]), zarc_share_soils=float(hit["share_soils"].iloc[0]),
                             engine_loss=p, engine_class=None if p is None else loss_class(p)))
    return pd.DataFrame(rows)


def last_indicated(crop: str, geocode: str, start: int = 1, end: int = 12) -> int | None:
    """Last ZARC-indicated ten-day period of the second window (Jan–Apr) for the municipality (best soil)."""
    z = zarc_classes(crop)
    z = z[(z["geocodigo"] == geocode) & z["decendio"].between(start, end) & (z["best"] < OUT_CLASS)]
    return int(z["decendio"].max()) if len(z) else None


def summarize(df: pd.DataFrame) -> dict:
    """Agreement metrics: binary (indicated vs engine-valid / engine loss ≤ 40 %), exact and ±1 class, weighted kappa."""
    from sklearn.metrics import cohen_kappa_score
    out = {}
    for crop, g in df.groupby("crop"):
        cls = [20, 30, 40, OUT_CLASS]
        e = g["engine_class"].map(cls.index)
        z = g["zarc_class"].map(cls.index)
        out[crop] = dict(
            n=len(g),
            valid_vs_indicated=float((g["engine_valid"] == g["zarc_indicated"]).mean()),
            engine_valid_zarc_out=int((g["engine_valid"] & ~g["zarc_indicated"]).sum()),
            engine_out_zarc_ok=int((~g["engine_valid"] & g["zarc_indicated"]).sum()),
            within_vs_indicated=float((g["engine_within"] == g["zarc_indicated"]).mean()),
            exact_class=float((e == z).mean()),
            within_one_class=float(((e - z).abs() <= 1).mean()),
            kappa_linear=float(cohen_kappa_score(e, z, weights="linear", labels=range(4))),
            engine_more_optimistic=float((e < z).mean()),
            engine_more_pessimistic=float((e > z).mean()),
        )
    return out
