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

from field_shift.clima.indicadores import et0_fao56

ROOT = Path(__file__).resolve().parents[3]
POWER = ROOT / "data/processed/clima/power_diario.parquet"
ANOS = range(1991, 2025)
P_DEPL = 0.55  # fração de depleção sem estresse — FAO-56 tabela 22 (milho/trigo ~0,55), validar
SEMEADURA_TRIGO = "01/05"  # trigo e aveia: semeadura fixa em 01/05 — estimativa, validar com ZARC
LIMIAR_FRACAO = 0.7  # ETa/ETc abaixo disto = estresse relevante na fase crítica

# Cada modelo: zr (m), kc=(ini, mid, end), est=(dias ini, desenv, mid, final) — FAO-56 tabelas 11 e 12 (estimativa, validar);
# fase=(dia_ini, dia_fim) após a semeadura (None = usar fase_ini/fim do ciclo). `semeadura`: 'app' (data escolhida para o safrinha) ou 'fixa'
# (`data` dd/mm; padrão SEMEADURA_TRIGO). `p`: fração de depleção sem estresse da cultura (padrão P_DEPL).
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
CANDIDATAS = {
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
FASE_TXT = {"milho": "floração/enchimento do milho", "milho+braquiaria": "floração/enchimento do milho consorciado",
            "trigo": "espigamento/enchimento do trigo", "aveia": "estabelecimento da aveia (30 primeiros dias)",
            "milheto": "estabelecimento do milheto/crotalária (30 primeiros dias)",
            "crotalaria": "estabelecimento do milheto/crotalária (30 primeiros dias)",
            "sorgo": "emborrachamento/enchimento do sorgo", "feijao": "floração/formação de vagens do feijão",
            "nabo": "estabelecimento do nabo forrageiro (30 primeiros dias)"}


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


def _simula(p, et0, kc, taw, p_depl=P_DEPL, lamina_max=None):
    """Balde diário. Retorna ETa, ETc e lâmina irrigada (arrays). Dr = depleção (mm), 0 = cheio.
    `lamina_max` (mm/dia): com valor, irriga no início do dia quando Dr > RAW (p·TAW), repondo até a capacidade (Dr -> 0),
    limitado a `lamina_max` por dia, durante todo o ciclo (lâmina líquida, eficiência de aplicação 100%). None = sequeiro."""
    raw = p_depl * taw
    dr = 0.0
    eta = np.empty_like(kc)
    irr = np.zeros_like(kc)
    for i in range(len(kc)):
        if lamina_max is not None and dr > raw:
            irr[i] = min(lamina_max, dr)
            dr -= irr[i]
        etc = kc[i] * et0[i]
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
        eta[i] = ks * etc
        dr = min(taw, max(0.0, dr - p[i] + eta[i]))
    return eta, kc * et0, irr


def _data_semeadura(m: dict, semeadura: str) -> str:
    return semeadura if m["semeadura"] == "app" else m.get("data", SEMEADURA_TRIGO)


def _um_modelo(cl: pd.DataFrame, nome: str, semeadura: str, taw: float, lamina_max=None):
    m = MODELOS[nome]
    dd, mm = (int(x) for x in _data_semeadura(m, semeadura).split("/"))
    kc = curva_kc(m["kc"], m["est"])
    a, b = m["fase"]
    razoes, lams = [], []
    for y in ANOS:
        ini = pd.Timestamp(y + 1, mm, dd)  # safra Y -> semeadura em Y+1
        j = cl.loc[ini:ini + pd.Timedelta(days=len(kc) - 1)]
        if len(j) < len(kc):
            razoes.append(np.nan)
            lams.append(np.nan)
            continue
        eta, etc, irr = _simula(j["p"].to_numpy(), j["et0"].to_numpy(), kc, taw, p_depl=m.get("p", P_DEPL), lamina_max=lamina_max)
        lams.append(irr.sum())
        s = slice(a, b + 1) if b > a else slice(a, a + 1)
        razoes.append(eta[s].sum() / max(etc[s].sum(), 1e-9))
    return np.array(razoes), np.array(lams)


@lru_cache(maxsize=512)
def _cached(cand: str, ponto_id: str, semeadura: str, cad_t: tuple, lamina_max=None):
    cad = dict(zip(("0-5cm", "5-15cm", "15-30cm", "30-60cm"), cad_t))
    cl = clima_diario(ponto_id)
    modelos = CANDIDATAS[cand]
    rs, ls, tawl = [], [], []
    for nome in modelos:
        taw = taw_mm(cad, MODELOS[nome]["zr"])
        tawl.append(taw)
        r_, l_ = _um_modelo(cl, nome, semeadura, taw, lamina_max)
        rs.append(r_)
        ls.append(l_)
    r = np.mean(rs, axis=0)
    lam = np.mean(ls, axis=0)
    lam = lam[~np.isnan(r)]
    r = r[~np.isnan(r)]
    return dict(lamina_media_mm=float(lam.mean()) if lamina_max is not None else 0.0, irrigado=lamina_max is not None,
                lamina_max_mm_dia=lamina_max, media=float(r.mean()), frac_abaixo=float(np.mean(r < LIMIAR_FRACAO)), n_abaixo=int((r < LIMIAR_FRACAO).sum()),
                n_anos=len(r), taw_mm=float(np.mean(tawl)), razoes=r,
                fase=FASE_TXT[modelos[0]],
                semeadura=_data_semeadura(MODELOS[modelos[0]], semeadura))


def agua_fase_critica(cand: str, ponto_id: str, semeadura: str, cad_camadas: dict, lamina_max_mm_dia: float | None = None) -> dict | None:
    """Critério água = média nos 34 anos de ΣETa/ΣETc na fase crítica (0–1). `cand` = slug da 2ª cultura (CANDIDATAS). None se não tem modelo
    (ex.: pousio, que o engine trata como 1,0). `lamina_max_mm_dia`: com valor, simula irrigação (ver _simula) e devolve
    `lamina_media_mm` (lâmina total do ciclo, média dos anos); None = sequeiro."""
    if cand not in CANDIDATAS:
        return None
    lm = None if lamina_max_mm_dia is None else float(lamina_max_mm_dia)
    return _cached(cand, ponto_id, semeadura, tuple(cad_camadas[k] for k in ("0-5cm", "5-15cm", "15-30cm", "30-60cm")), lm)
