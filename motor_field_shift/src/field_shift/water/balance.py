"""Balanço hídrico diário (modelo de balde FAO-56) para o critério ÁGUA.

Por candidata e por ano (safras 1991–2024; o safrinha e o trigo da safra Y caem em Y+1, mesma convenção de
field_shift.clima.indicadores): simula ETa = Ks·Kc·ET0 com P e ET0 diários da CÉLULA NASA POWER e a CAD do solo
(SoilGrids + Saxton & Rawls) × profundidade de raiz. Critério = média nos anos de ΣETa/ΣETc na FASE CRÍTICA.

Hipóteses simplificadas (documentadas; validar com agrônomo):
 - Balde começa cheio na semeadura; toda chuva infiltra (sem escoamento/interceptação); excesso além de TAW drena.
 - Profundidade de raiz constante (não cresce com o ciclo); G = 0 no ET0; sem ascensão capilar.
 - Ks = 1 enquanto depleção Dr ≤ RAW = p·TAW; depois Ks = (TAW − Dr)/((1 − p)·TAW). p = 0,55 (FAO-56 tab. 22, cereais).
 - Irrigação (opcional): quando Dr > RAW repõe até a capacidade, limitada pela lâmina máxima diária, no ciclo todo; lâmina líquida
   (eficiência 100%). O ganho de produtividade da irrigação NÃO é modelado (só o critério água, o risco e o custo).
 - CAD só vai até 60 cm no SoilGrids; para raiz 0,8 m a camada 60–80 cm usa a CAD da camada 30–60 cm (extrapolação).
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
P_DEPL = 0.55  # fração de depleção sem estresse — FAO-56 tabela 22 (milho/trigo ~0,55), validar
WHEAT_SOWING = "01/05"  # trigo e aveia: semeadura fixa em 01/05 — estimativa, validar com ZARC
FRACTION_THRESHOLD = 0.7  # ETa/ETc abaixo disto = estresse relevante na fase crítica
# Water-deficit risk (risk criterion): a year counts as a loss when ETa/ETc in the critical phase (the ZARC "ISNA" concept) is
# below this value. Calibrated in docs/validation.md §2.4: against IBGE PAM, off-season corn years below 0.55 failed in 65 % of
# the cases vs 20 % otherwise (Oeste, 2003–2025), and it gave the best agreement with the ZARC risk classes (κ 0.63).
DEFICIT_THRESHOLD = 0.55

# Cada modelo: zr (m), kc=(ini, mid, end), est=(dias ini, desenv, mid, final) — FAO-56 tabelas 11 e 12 (estimativa, validar);
# fase=(dia_ini, dia_fim) após a semeadura (None = usar fase_ini/fim do ciclo). `semeadura`: 'app' (data escolhida para o safrinha) ou 'fixa'
# (`data` dd/mm; padrão SEMEADURA_TRIGO). `p`: fração de depleção sem estresse da cultura (padrão P_DEPL).
# Fase crítica: milho = florescimento/enchimento (+55 a +95 d); trigo = espigamento/enchimento (+60 a +100 d no ciclo de 120 d);
# aveia, milheto, crotalária (sem colheita de grão) = estabelecimento (primeiros 30 d), pois a falha de estande é o que importa.
MODELS = {
    "milho": dict(zr=0.8, kc=(0.30, 1.20, 0.60), est=(25, 40, 45, 30), fase=(55, 95), semeadura="app"),
    "milho+braquiaria": dict(zr=0.8, kc=(0.30, 1.25, 0.60), est=(25, 40, 45, 30), fase=(55, 95), semeadura="app"),  # Kc_mid +0,05
    "trigo": dict(zr=0.8, kc=(0.30, 1.15, 0.30), est=(20, 30, 45, 25), fase=(60, 100), semeadura="fixa"),
    "aveia": dict(zr=0.6, kc=(0.30, 1.15, 0.25), est=(20, 25, 35, 20), fase=(0, 30), semeadura="fixa"),
    "milheto": dict(zr=0.6, kc=(0.30, 1.00, 0.30), est=(20, 30, 30, 20), fase=(0, 30), semeadura="app"),
    # crotalária não está na FAO-56: aproximada por leguminosa de cobertura (Kc_ini 0,4; mid 1,10; end 0,50) — validar.
    "crotalaria": dict(zr=0.6, kc=(0.40, 1.10, 0.50), est=(20, 30, 40, 20), fase=(0, 30), semeadura="app"),
    # Sorgo granífero — FAO-56 (Allen et al., 1998) tab. 12: Kc ini 0,30, mid 1,00–1,10 (usado 1,05), end 0,55; tab. 11: estágios 20/35/40/30 d
    # (125 d); p = 0,55 (tab. 22). Fase crítica: emborrachamento a enchimento de grãos (+50 a +90 d). Raiz 0,8 m (a FAO dá 1,0–2,0 m; o CAD
    # do SoilGrids só vai a 60 cm) — estimativa, validar.
    "sorgo": dict(zr=0.8, kc=(0.30, 1.05, 0.55), est=(20, 35, 40, 30), fase=(50, 90), semeadura="app"),
    # Feijão seco — FAO-56 tab. 12: Kc ini 0,40, mid 1,15, end 0,35; tab. 11: 20/30/40/20 d (110 d; ciclo de 85–95 d no PR, conservador);
    # p = 0,45 e raiz 0,6–0,7 m (tab. 22). Fase crítica: floração e formação de vagens (+30 a +65 d) — estimativa, validar.
    "feijao": dict(zr=0.6, kc=(0.40, 1.15, 0.35), est=(20, 30, 40, 20), fase=(30, 65), semeadura="app", p=0.45),
    # Nabo forrageiro: não está na FAO-56; aproximado pelo nabo (Turnip) da tab. 12 (Kc ini 0,50, mid 1,10, end 0,95), estágios de ciclo
    # curto (15/25/35/20 d) e raiz 0,5 m; semeadura fixa em 01/04 (cobertura de outono; data estimada, validar com Embrapa/IDR-PR) —
    # fase crítica = estabelecimento (30 primeiros dias), como as demais coberturas. Estimativa, validar.
    "nabo": dict(zr=0.5, kc=(0.50, 1.10, 0.95), est=(15, 25, 35, 20), fase=(0, 30), semeadura="fixa", data="01/04"),
}
# cultura da 2ª janela (slug de field_shift.app.engine.SEGUNDA) -> lista de modelos; com 2+ modelos, o critério é a média entre eles.
# O balanço só depende da 2ª cultura (a cultura de verão não entra no modelo de água).
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
    """P e ET0 diários (mm) da célula, 1991–2025. ET0 FAO-56 via field_shift.clima.indicadores."""
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
    """Água disponível total (mm) até zr_m. cad_camadas: mm/cm por camada {'0-5cm','5-15cm','15-30cm','30-60cm'};
    abaixo de 60 cm repete a camada 30–60 (extrapolação)."""
    lim = [(0, 5, "0-5cm"), (5, 15, "5-15cm"), (15, 30, "15-30cm"), (30, 60, "30-60cm"), (60, 200, "30-60cm")]
    z = zr_m * 100
    return float(sum(max(0.0, min(z, b) - a) * awc_layers[k] for a, b, k in lim))


def _simulate(p, et0, kc, taw, p_depl=P_DEPL, max_depth=None):
    """Balde diário. Retorna ETa, ETc e lâmina irrigada (arrays). Dr = depleção (mm), 0 = cheio.
    `lamina_max` (mm/dia): com valor, irriga no início do dia quando Dr > RAW (p·TAW), repondo até a capacidade (Dr -> 0),
    limitado a `lamina_max` por dia, durante todo o ciclo (lâmina líquida, eficiência de aplicação 100%). None = sequeiro."""
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
        start = pd.Timestamp(y + 1, mm, dd)  # safra Y -> semeadura em Y+1
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
    """Critério água = média nos 34 anos de ΣETa/ΣETc na fase crítica (0–1). `cand` = slug da 2ª cultura (CANDIDATAS). None se não tem modelo
    (ex.: pousio, que o engine trata como 1,0). `lamina_max_mm_dia`: com valor, simula irrigação (ver _simula) e devolve
    `lamina_media_mm` (lâmina total do ciclo, média dos anos); None = sequeiro."""
    if cand not in CANDIDATES:
        return None
    lm = None if max_depth_mm_day is None else float(max_depth_mm_day)
    return _cached(cand, point_id, sowing, tuple(awc_layers[k] for k in ("0-5cm", "5-15cm", "15-30cm", "30-60cm")), lm)
