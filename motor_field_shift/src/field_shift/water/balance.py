"""Daily water balance (FAO-56 bucket model) for the WATER criterion.

Per candidate and per year (seasons 1991–2024; the 2nd-season crop and wheat of season Y fall in Y+1, same convention as
field_shift.climate.indicators): simulates ETa = Ks·Kc·ET0 with daily P and ET0 of the NASA POWER CELL and the soil AWC
(SoilGrids + Saxton & Rawls) × root depth. Criterion = mean over the years of ΣETa/ΣETc in the CRITICAL PHASE.

Simplifying assumptions (documented; validate with an agronomist):
 - The bucket starts full at sowing; all rain infiltrates (no runoff/interception); excess above TAW drains.
 - Constant root depth (does not grow over the cycle); G = 0 in ET0; no capillary rise.
 - Ks = 1 while depletion Dr ≤ RAW = p·TAW; then Ks = (TAW − Dr)/((1 − p)·TAW). p = 0.55 (FAO-56 table 22, cereals).
 - Irrigation (optional): when Dr > RAW it refills up to capacity, limited by the maximum daily depth, over the whole cycle; net depth
   (100% efficiency). The yield gain from irrigation is NOT modeled (only the water criterion, the risk and the cost).
 - The SoilGrids AWC only goes to 60 cm; for a 0.8 m root the 60–80 cm layer uses the AWC of the 30–60 cm layer (extrapolation).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.climate.indicators import et0_fao56

ROOT = Path(__file__).resolve().parents[3]
POWER = ROOT / "data/processed/clima_pr/power_diario.parquet"
YEARS = range(1991, 2025)
P_DEPL = 0.55  # depletion fraction without stress — FAO-56 table 22 (corn/wheat ~0.55), to validate
WHEAT_SOWING = "01/05"  # wheat and oat: fixed sowing on 01/05 — estimate, validate with ZARC
FRACTION_THRESHOLD = 0.7  # ETa/ETc below this = relevant stress in the critical phase
# Water-deficit risk (risk criterion): a year counts as a loss when ETa/ETc in the critical phase (the ZARC "ISNA" concept) is
# below this value. Calibrated in docs/validation.md §2.4: against IBGE PAM, off-season corn years below 0.55 failed in 65 % of
# the cases vs 20 % otherwise (Oeste, 2003–2025), and it gave the best agreement with the ZARC risk classes (κ 0.63).
DEFICIT_THRESHOLD = 0.55

# Each model: zr (m), kc=(ini, mid, end), est=(days ini, dev, mid, late) — FAO-56 tables 11 and 12 (estimate, to validate);
# fase=(start_day, end_day) after sowing (None = use the cycle's fase_ini/fim). `semeadura`: 'app' (date chosen for the 2nd season) or 'fixa'
# (`data` dd/mm; default WHEAT_SOWING). `p`: the crop's depletion fraction without stress (default P_DEPL).
# Critical phase: corn = flowering/grain fill (+55 to +95 d); wheat = heading/grain fill (+60 to +100 d in the 120 d cycle);
# oat, millet, crotalaria (no grain harvest) = establishment (first 30 d), since stand failure is what matters.
MODELS = {
    "milho": dict(zr=0.8, kc=(0.30, 1.20, 0.60), est=(25, 40, 45, 30), fase=(55, 95), semeadura="app"),
    "milho+braquiaria": dict(zr=0.8, kc=(0.30, 1.25, 0.60), est=(25, 40, 45, 30), fase=(55, 95), semeadura="app"),  # Kc_mid +0,05
    "trigo": dict(zr=0.8, kc=(0.30, 1.15, 0.30), est=(20, 30, 45, 25), fase=(60, 100), semeadura="fixa"),
    "aveia": dict(zr=0.6, kc=(0.30, 1.15, 0.25), est=(20, 25, 35, 20), fase=(0, 30), semeadura="fixa"),
    "milheto": dict(zr=0.6, kc=(0.30, 1.00, 0.30), est=(20, 30, 30, 20), fase=(0, 30), semeadura="app"),
    # crotalaria is not in FAO-56: approximated by a cover legume (Kc_ini 0.4; mid 1.10; end 0.50) — to validate.
    "crotalaria": dict(zr=0.6, kc=(0.40, 1.10, 0.50), est=(20, 30, 40, 20), fase=(0, 30), semeadura="app"),
    # Grain sorghum — FAO-56 (Allen et al., 1998) table 12: Kc ini 0.30, mid 1.00–1.10 (1.05 used), end 0.55; table 11: stages 20/35/40/30 d
    # (125 d); p = 0.55 (table 22). Critical phase: boot to grain fill (+50 to +90 d). Root 0.8 m (FAO gives 1.0–2.0 m; the SoilGrids AWC
    # only goes to 60 cm) — estimate, to validate.
    "sorgo": dict(zr=0.8, kc=(0.30, 1.05, 0.55), est=(20, 35, 40, 30), fase=(50, 90), semeadura="app"),
    # Dry bean — FAO-56 table 12: Kc ini 0.40, mid 1.15, end 0.35; table 11: 20/30/40/20 d (110 d; 85–95 d cycle in PR, conservative);
    # p = 0.45 and root 0.6–0.7 m (table 22). Critical phase: flowering and pod formation (+30 to +65 d) — estimate, to validate.
    "feijao": dict(zr=0.6, kc=(0.40, 1.15, 0.35), est=(20, 30, 40, 20), fase=(30, 65), semeadura="app", p=0.45),
    # Forage radish: not in FAO-56; approximated by the turnip of table 12 (Kc ini 0.50, mid 1.10, end 0.95), short-cycle stages
    # (15/25/35/20 d) and 0.5 m root; fixed sowing on 01/04 (autumn cover; estimated date, validate with Embrapa/IDR-PR) —
    # critical phase = establishment (first 30 days), like the other cover crops. Estimate, to validate.
    "nabo": dict(zr=0.5, kc=(0.50, 1.10, 0.95), est=(15, 25, 35, 20), fase=(0, 30), semeadura="fixa", data="01/04"),
}
# 2nd-window crop (slug of field_shift.app.engine.SECOND) -> list of models; with 2+ models, the criterion is their mean.
# The balance only depends on the 2nd crop (the summer crop does not enter the water model).
CANDIDATES = {
    "milho_safrinha": ["milho"],
    "milho_braquiaria": ["milho+braquiaria"],
    "trigo": ["trigo"],
    "aveia": ["aveia"],
    "milheto_crotalaria": ["milheto", "crotalaria"],
    "sorgo": ["sorgo"],
    "feijao_safrinha": ["feijao"],
    "nabo_forrageiro": ["nabo"],
    "aveia_nabo": ["aveia", "nabo"],
}
PHASE_TXT = {"milho": "floração/enchimento do milho", "milho+braquiaria": "floração/enchimento do milho consorciado",
            "trigo": "espigamento/enchimento do trigo", "aveia": "estabelecimento da aveia (30 primeiros dias)",
            "milheto": "estabelecimento do milheto/crotalária (30 primeiros dias)",
            "crotalaria": "estabelecimento do milheto/crotalária (30 primeiros dias)",
            "sorgo": "emborrachamento/enchimento do sorgo", "feijao": "floração/formação de vagens do feijão",
            "nabo": "estabelecimento do nabo forrageiro (30 primeiros dias)"}


@lru_cache(maxsize=8)
def daily_climate(point_id: str) -> pd.DataFrame:
    """Daily P and ET0 (mm) of the cell, 1991–2025. FAO-56 ET0 via field_shift.climate.indicators."""
    d = pd.read_parquet(POWER, filters=[("ponto_id", "==", point_id)])
    d = d.set_index("data").sort_index()
    et0 = et0_fao56(d, float(d["lat"].iloc[0]), float(d["elev"].iloc[0]))
    return pd.DataFrame({"p": d["PRECTOTCORR"].astype(float).fillna(0.0), "et0": et0.astype(float)})


def kc_curve(kc, est) -> np.ndarray:
    start, mid, end = kc
    n_start, n_dev, n_mid, n_late = est
    return np.concatenate([np.full(n_start, start), np.linspace(start, mid, n_dev + 1)[1:], np.full(n_mid, mid),
                           np.linspace(mid, end, n_late + 1)[1:]])


def taw_mm(awc_layers: dict, zr_m: float) -> float:
    """Total available water (mm) down to zr_m. awc_layers: mm/cm per layer {'0-5cm','5-15cm','15-30cm','30-60cm'};
    below 60 cm the 30–60 layer is repeated (extrapolation)."""
    lim = [(0, 5, "0-5cm"), (5, 15, "5-15cm"), (15, 30, "15-30cm"), (30, 60, "30-60cm"), (60, 200, "30-60cm")]
    z = zr_m * 100
    return float(sum(max(0.0, min(z, b) - a) * awc_layers[k] for a, b, k in lim))


def _simulate(p, et0, kc, taw, p_depl=P_DEPL, max_depth=None):
    """Daily bucket. Returns ETa, ETc and irrigated depth (arrays). Dr = depletion (mm), 0 = full.
    `max_depth` (mm/day): when set, irrigates at the start of the day when Dr > RAW (p·TAW), refilling to capacity (Dr -> 0),
    limited to `max_depth` per day, over the whole cycle (net depth, 100% application efficiency). None = rainfed."""
    raw = p_depl * taw
    dr = 0.0
    eta = np.empty_like(kc)
    irr = np.zeros_like(kc)
    for i in range(len(kc)):
        if max_depth is not None and dr > raw:
            irr[i] = min(max_depth, dr)
            dr -= irr[i]
        etc = kc[i] * et0[i]
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
        eta[i] = ks * etc
        dr = min(taw, max(0.0, dr - p[i] + eta[i]))
    return eta, kc * et0, irr


def _sowing_date(m: dict, sowing: str) -> str:
    return sowing if m["semeadura"] == "app" else m.get("data", WHEAT_SOWING)


def _one_model(cl: pd.DataFrame, nome: str, sowing: str, taw: float, max_depth=None):
    m = MODELS[nome]
    dd, mm = (int(x) for x in _sowing_date(m, sowing).split("/"))
    kc = kc_curve(m["kc"], m["est"])
    a, b = m["fase"]
    ratios, lams = [], []
    for y in YEARS:
        start = pd.Timestamp(y + 1, mm, dd)  # season Y -> sowing in Y+1
        j = cl.loc[start:start + pd.Timedelta(days=len(kc) - 1)]
        if len(j) < len(kc):
            ratios.append(np.nan)
            lams.append(np.nan)
            continue
        eta, etc, irr = _simulate(j["p"].to_numpy(), j["et0"].to_numpy(), kc, taw, p_depl=m.get("p", P_DEPL), max_depth=max_depth)
        lams.append(irr.sum())
        s = slice(a, b + 1) if b > a else slice(a, a + 1)
        ratios.append(eta[s].sum() / max(etc[s].sum(), 1e-9))
    return np.array(ratios), np.array(lams)


@lru_cache(maxsize=512)
def _cached(cand: str, point_id: str, sowing: str, cad_t: tuple, max_depth=None):
    cad = dict(zip(("0-5cm", "5-15cm", "15-30cm", "30-60cm"), cad_t))
    cl = daily_climate(point_id)
    models = CANDIDATES[cand]
    rs, ls, tawl = [], [], []
    for nome in models:
        taw = taw_mm(cad, MODELS[nome]["zr"])
        tawl.append(taw)
        r_, l_ = _one_model(cl, nome, sowing, taw, max_depth)
        rs.append(r_)
        ls.append(l_)
    r = np.mean(rs, axis=0)
    lam = np.mean(ls, axis=0)
    lam = lam[~np.isnan(r)]
    r = r[~np.isnan(r)]
    return dict(lamina_media_mm=float(lam.mean()) if max_depth is not None else 0.0, irrigado=max_depth is not None,
                lamina_max_mm_dia=max_depth, media=float(r.mean()), frac_abaixo=float(np.mean(r < FRACTION_THRESHOLD)), n_abaixo=int((r < FRACTION_THRESHOLD).sum()),
                deficit_prob=float(np.mean(r < DEFICIT_THRESHOLD)), deficit_years=int((r < DEFICIT_THRESHOLD).sum()),
                n_anos=len(r), taw_mm=float(np.mean(tawl)), razoes=r,
                fase=PHASE_TXT[models[0]],
                semeadura=_sowing_date(MODELS[models[0]], sowing))


def critical_phase_water(cand: str, point_id: str, sowing: str, awc_layers: dict, max_depth_mm_day: float | None = None) -> dict | None:
    """Water criterion = mean over 34 years of ΣETa/ΣETc in the critical phase (0–1). `cand` = 2nd-crop slug (CANDIDATES). None if there is no
    model (e.g. fallow, which the engine treats as 1.0). `max_depth_mm_day`: when set, simulates irrigation (see _simulate) and returns
    `lamina_media_mm` (total cycle depth, mean over the years); None = rainfed."""
    if cand not in CANDIDATES:
        return None
    lm = None if max_depth_mm_day is None else float(max_depth_mm_day)
    return _cached(cand, point_id, sowing, tuple(awc_layers[k] for k in ("0-5cm", "5-15cm", "15-30cm", "30-60cm")), lm)
