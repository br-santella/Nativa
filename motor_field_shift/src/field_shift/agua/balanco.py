"""Balanço hídrico diário (modelo de balde FAO-56) para o critério ÁGUA.

Por candidata e por ano (safras 1991–2024; o safrinha e o trigo da safra Y caem em Y+1, mesma convenção de
field_shift.clima.indicadores): simula ETa = Ks·Kc·ET0 com P e ET0 diários da CÉLULA NASA POWER e a CAD do solo
(SoilGrids + Saxton & Rawls) × profundidade de raiz. Critério = média nos anos de ΣETa/ΣETc na FASE CRÍTICA.

Hipóteses simplificadas (documentadas; validar com agrônomo):
 - Balde começa cheio na semeadura; toda chuva infiltra (sem escoamento/interceptação); excesso além de TAW drena.
 - Profundidade de raiz constante (não cresce com o ciclo); G = 0 no ET0; sem ascensão capilar.
 - Ks = 1 enquanto depleção Dr ≤ RAW = p·TAW; depois Ks = (TAW − Dr)/((1 − p)·TAW). p = 0,55 (FAO-56 tab. 22, cereais).
 - CAD só vai até 60 cm no SoilGrids; para raiz 0,8 m a camada 60–80 cm usa a CAD da camada 30–60 cm (extrapolação).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.clima.indicadores import et0_fao56

ROOT = Path(__file__).resolve().parents[3]
POWER = ROOT / "data/processed/clima/power_diario.parquet"
ANOS = range(1991, 2025)
P_DEPL = 0.55  # fração de depleção sem estresse — FAO-56 tabela 22 (milho/trigo ~0,55), validar
SEMEADURA_TRIGO = "01/05"  # trigo e aveia: semeadura fixa em 01/05 — estimativa, validar com ZARC
LIMIAR_FRACAO = 0.7  # ETa/ETc abaixo disto = estresse relevante na fase crítica

# Cada modelo: zr (m), kc=(ini, mid, end), est=(dias ini, desenv, mid, final) — FAO-56 tabelas 11 e 12 (estimativa, validar);
# fase=(dia_ini, dia_fim) após a semeadura (None = usar fase_ini/fim do ciclo). `semeadura`: 'app' (data escolhida para o safrinha) ou 'fixa'.
# Fase crítica: milho = florescimento/enchimento (+55 a +95 d); trigo = espigamento/enchimento (+60 a +100 d no ciclo de 120 d);
# aveia, milheto, crotalária (sem colheita de grão) = estabelecimento (primeiros 30 d), pois a falha de estande é o que importa.
MODELOS = {
    "milho": dict(zr=0.8, kc=(0.30, 1.20, 0.60), est=(25, 40, 45, 30), fase=(55, 95), semeadura="app"),
    "milho+braquiaria": dict(zr=0.8, kc=(0.30, 1.25, 0.60), est=(25, 40, 45, 30), fase=(55, 95), semeadura="app"),  # Kc_mid +0,05
    "trigo": dict(zr=0.8, kc=(0.30, 1.15, 0.30), est=(20, 30, 45, 25), fase=(60, 100), semeadura="fixa"),
    "aveia": dict(zr=0.6, kc=(0.30, 1.15, 0.25), est=(20, 25, 35, 20), fase=(0, 30), semeadura="fixa"),
    "milheto": dict(zr=0.6, kc=(0.30, 1.00, 0.30), est=(20, 30, 30, 20), fase=(0, 30), semeadura="app"),
    # crotalária não está na FAO-56: aproximada por leguminosa de cobertura (Kc_ini 0,4; mid 1,10; end 0,50) — validar.
    "crotalaria": dict(zr=0.6, kc=(0.40, 1.10, 0.50), est=(20, 30, 40, 20), fase=(0, 30), semeadura="app"),
}
# candidata (nome no CATALOGO) -> lista de modelos; com 2+ modelos, o critério é a média entre eles.
CANDIDATAS = {
    "Soja → milho safrinha": ["milho"],
    "Soja → milho safrinha + braquiária": ["milho+braquiaria"],
    "Soja → trigo": ["trigo"],
    "Soja → aveia (cobertura/palha)": ["aveia"],
    "Soja → milheto/crotalária (cobertura)": ["milheto", "crotalaria"],
}
FASE_TXT = {"milho": "floração/enchimento do milho", "milho+braquiaria": "floração/enchimento do milho consorciado",
            "trigo": "espigamento/enchimento do trigo", "aveia": "estabelecimento da aveia (30 primeiros dias)",
            "milheto": "estabelecimento do milheto/crotalária (30 primeiros dias)",
            "crotalaria": "estabelecimento do milheto/crotalária (30 primeiros dias)"}


@lru_cache(maxsize=8)
def clima_diario(ponto_id: str) -> pd.DataFrame:
    """P e ET0 diários (mm) da célula, 1991–2025. ET0 FAO-56 via field_shift.clima.indicadores."""
    d = pd.read_parquet(POWER, filters=[("ponto_id", "==", ponto_id)])
    d = d.set_index("data").sort_index()
    et0 = et0_fao56(d, float(d["lat"].iloc[0]), float(d["elev"].iloc[0]))
    return pd.DataFrame({"p": d["PRECTOTCORR"].astype(float).fillna(0.0), "et0": et0.astype(float)})


def curva_kc(kc, est) -> np.ndarray:
    ini, mid, fim = kc
    n_ini, n_dev, n_mid, n_late = est
    return np.concatenate([np.full(n_ini, ini), np.linspace(ini, mid, n_dev + 1)[1:], np.full(n_mid, mid),
                           np.linspace(mid, fim, n_late + 1)[1:]])


def taw_mm(cad_camadas: dict, zr_m: float) -> float:
    """Água disponível total (mm) até zr_m. cad_camadas: mm/cm por camada {'0-5cm','5-15cm','15-30cm','30-60cm'};
    abaixo de 60 cm repete a camada 30–60 (extrapolação)."""
    lim = [(0, 5, "0-5cm"), (5, 15, "5-15cm"), (15, 30, "15-30cm"), (30, 60, "30-60cm"), (60, 200, "30-60cm")]
    z = zr_m * 100
    return float(sum(max(0.0, min(z, b) - a) * cad_camadas[k] for a, b, k in lim))


def _simula(p, et0, kc, taw, p_depl=P_DEPL):
    """Balde diário. Retorna ETa e ETc (arrays). Dr = depleção (mm), 0 = cheio."""
    raw = p_depl * taw
    dr = 0.0
    eta = np.empty_like(kc)
    for i in range(len(kc)):
        etc = kc[i] * et0[i]
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
        eta[i] = ks * etc
        dr = min(taw, max(0.0, dr - p[i] + eta[i]))
    return eta, kc * et0


def _um_modelo(cl: pd.DataFrame, nome: str, semeadura: str, taw: float):
    m = MODELOS[nome]
    dd, mm = (int(x) for x in (semeadura if m["semeadura"] == "app" else SEMEADURA_TRIGO).split("/"))
    kc = curva_kc(m["kc"], m["est"])
    a, b = m["fase"]
    razoes = []
    for y in ANOS:
        ini = pd.Timestamp(y + 1, mm, dd)  # safra Y -> semeadura em Y+1
        j = cl.loc[ini:ini + pd.Timedelta(days=len(kc) - 1)]
        if len(j) < len(kc):
            razoes.append(np.nan)
            continue
        eta, etc = _simula(j["p"].to_numpy(), j["et0"].to_numpy(), kc, taw)
        s = slice(a, b + 1) if b > a else slice(a, a + 1)
        razoes.append(eta[s].sum() / max(etc[s].sum(), 1e-9))
    return np.array(razoes)


@lru_cache(maxsize=512)
def _cached(cand: str, ponto_id: str, semeadura: str, cad_t: tuple):
    cad = dict(zip(("0-5cm", "5-15cm", "15-30cm", "30-60cm"), cad_t))
    cl = clima_diario(ponto_id)
    modelos = CANDIDATAS[cand]
    rs, tawl = [], []
    for nome in modelos:
        taw = taw_mm(cad, MODELOS[nome]["zr"])
        tawl.append(taw)
        rs.append(_um_modelo(cl, nome, semeadura, taw))
    r = np.mean(rs, axis=0)
    r = r[~np.isnan(r)]
    return dict(media=float(r.mean()), frac_abaixo=float(np.mean(r < LIMIAR_FRACAO)), n_abaixo=int((r < LIMIAR_FRACAO).sum()),
                n_anos=len(r), taw_mm=float(np.mean(tawl)), razoes=r,
                fase=FASE_TXT[modelos[0]],
                semeadura=semeadura if MODELOS[modelos[0]]["semeadura"] == "app" else SEMEADURA_TRIGO)


def agua_fase_critica(cand: str, ponto_id: str, semeadura: str, cad_camadas: dict) -> dict | None:
    """Critério água = média nos 34 anos de ΣETa/ΣETc na fase crítica (0–1). None se a candidata não tem modelo
    (ex.: pousio, que o engine trata como 1,0)."""
    if cand not in CANDIDATAS:
        return None
    return _cached(cand, ponto_id, semeadura, tuple(cad_camadas[k] for k in ("0-5cm", "5-15cm", "15-30cm", "30-60cm")))
