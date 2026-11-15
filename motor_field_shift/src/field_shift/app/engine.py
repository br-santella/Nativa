"""Field Shift MVP engine: data (field, NDVI, NASA POWER) + hard rules + scoring.

Everything here is pure logic (no Streamlit), so it can be tested with:  uv run python src/field_shift/app/engine.py
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy.signal import find_peaks

from field_shift import calendario as cal
from field_shift.agua import agua_fase_critica
from field_shift.calendario import DIAS_PREPARO_2A, SEMEADURA_PADRAO, SEMEADURAS
from field_shift.clima.lookup import indicadores_para
from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import texto as pam_texto
from field_shift.renda import RENDA_ESCALA_MIN, calcular_margens, fonte_custo, fonte_preco, rendimentos
from field_shift.regiao import dentro_da_regiao, relevo
from field_shift.solo import solo as solo_poligono
from field_shift.solo.solo import FONTE_ANALISE, solo_de_analise, texto as solo_texto

ROOT = Path(__file__).resolve().parents[3]
FTW = ROOT / "data/processed/ftw"
TALHAO_ID = "72638"  # the parquet `id` column is a string
LIMIAR_SOLO = 0.35  # NDVI below this = bare soil / low cover

# --------------------------------------------------------------------------- 1. Location
@lru_cache(maxsize=1)
def gdf_talhoes() -> gpd.GeoDataFrame:
    """FTW fields with MapBiomas (in-memory cache; used by carregar_talhao and by the API service)."""
    return gpd.read_parquet(FTW / "fields_tile_mapbiomas_geo.parquet")


def carregar_talhao(tid: str = TALHAO_ID) -> dict:
    gdf = gdf_talhoes()
    row = gdf[gdf["id"].astype(str) == str(tid)]
    if row.empty:
        raise ValueError(f"Field {tid} not found")
    row = row.iloc[0]
    # centroid in a projected CRS (SIRGAS 2000 / UTM 22S) -> 4326
    c = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(31982).centroid.to_crs(4326).iloc[0]
    poly = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(4326).iloc[0]
    # Terrain in % (NASADEM) from the regiao module; outside the region -> None ("no data").
    rel = None
    if dentro_da_regiao(poly):
        rel = relevo(poly)
    legenda = json.loads((FTW / "mapbiomas_legend_c10.json").read_text())
    hist = {a: legenda.get(str(int(row[f"lc_{a}"])), "?") for a in range(2019, 2025)}
    return dict(id=tid, area_ha=float(row["area_ha"]), lat=c.y, lon=c.x, poly=poly,
                relevo=rel, declividade=None if rel is None else rel["declividade_media"],
                declividade_p90=None if rel is None else rel["declividade_p90"],
                classe_embrapa=None if rel is None else rel["classe_embrapa"],
                altitude=None if rel is None else rel["altitude_media"], historico=hist)

# --------------------------------------------------------------------------- 2. NDVI history
def carregar_ndvi(tid: str = TALHAO_ID) -> pd.Series:
    df = pd.read_csv(ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv", parse_dates=["data"])
    df = df[df["frac_clear"] >= 0.7]
    s = df.groupby("data")["ndvi_mean"].mean().sort_index()  # S30 and L30 on the same day -> mean
    d = s.resample("D").mean().interpolate(limit_area="inside")  # daily series
    return d.rolling(15, center=True, min_periods=1).mean()  # ~15-day smoothing


def faixas_solo(ndvi: pd.Series, limiar: float = LIMIAR_SOLO) -> list[tuple]:
    """Contiguous intervals (start, end) with NDVI < threshold."""
    baixo = (ndvi < limiar).values
    faixas, ini = [], None
    for i, b in enumerate(baixo):
        if b and ini is None:
            ini = ndvi.index[i]
        if not b and ini is not None:
            faixas.append((ini, ndvi.index[i - 1])); ini = None
    if ini is not None:
        faixas.append((ini, ndvi.index[-1]))
    return faixas


def picos_por_ano_agricola(ndvi: pd.Series) -> dict[str, int]:
    """Number of NDVI peaks per agricultural year (Sep–Aug). Complete agricultural years only."""
    res = {}
    for ano in range(ndvi.index.min().year - 1, ndvi.index.max().year + 1):
        ini, fim = pd.Timestamp(ano, 9, 1), pd.Timestamp(ano + 1, 8, 31)
        if ini < ndvi.index.min() or fim > ndvi.index.max():
            continue  # incomplete year
        trecho = ndvi[ini:fim]
        p, _ = find_peaks(trecho.values, height=0.6, prominence=0.2, distance=40)
        res[f"{ano}/{str(ano + 1)[2:]}"] = len(p)
    return res


def detectar_rotacao(picos: dict[str, int]) -> str:
    if not picos:
        return "Soybean → off-season corn"
    mediana = float(np.median(list(picos.values())))
    return "Soybean → off-season corn" if mediana >= 2 else "Soybean → fallow"


def dias_solo_por_ano(ndvi: pd.Series) -> float:
    """Mean days/year with NDVI < threshold, over complete agricultural years."""
    tot = []
    for ano in range(ndvi.index.min().year - 1, ndvi.index.max().year + 1):
        ini, fim = pd.Timestamp(ano, 9, 1), pd.Timestamp(ano + 1, 8, 31)
        if ini >= ndvi.index.min() and fim <= ndvi.index.max():
            tot.append(int((ndvi[ini:fim] < LIMIAR_SOLO).sum()))
    return float(np.mean(tot)) if tot else float("nan")

# --------------------------------------------------------------------------- 3. Clima NASA POWER
POWER_URL = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MIN,T2M_MAX,PRECTOTCORR"
             "&community=AG&longitude={lon}&latitude={lat}&start=19950101&end=20241231&format=JSON")


def buscar_power(lat: float, lon: float) -> tuple[pd.DataFrame, str]:
    """Returns (daily DataFrame, origin). Tries the API; if it fails, uses the disk cache."""
    cache = ROOT / f"data/raw/power/power_{lat:.2f}_{lon:.2f}.json"
    try:
        r = requests.get(POWER_URL.format(lat=round(lat, 4), lon=round(lon, 4)), timeout=180)
        r.raise_for_status()
        js = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(js))
        origem = "NASA POWER API (live)"
    except Exception as e:
        if not cache.exists():
            raise RuntimeError(f"NASA POWER unavailable and no disk cache: {e}") from e
        js = json.loads(cache.read_text())
        origem = f"disk cache ({cache.name}) — API failed: {type(e).__name__}"
    p = js["properties"]["parameter"]
    df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    return df.replace(-999, np.nan), origem


def riscos_power(df: pd.DataFrame) -> dict:
    anos = sorted(set(df.index.year))
    geada_saf = geada_trigo = veranico = 0
    for a in anos:
        y = df[df.index.year == a]
        # threshold <= 3 C (consistent with the lookup: validation against INMET showed that POWER underestimates frost)
        geada_saf += bool((y.loc[f"{a}-06-01":f"{a}-07-31", "T2M_MIN"] <= 3).any())
        geada_trigo += bool((y.loc[f"{a}-08-15":f"{a}-09-30", "T2M_MIN"] <= 3).any())
        seca = (y.loc[f"{a}-03-01":f"{a}-04-30", "PRECTOTCORR"] < 1).astype(int)
        run = seca.groupby((seca == 0).cumsum()).cumsum()
        veranico += bool(run.max() >= 15)
    n = len(anos)
    chuva_mes = df["PRECTOTCORR"].resample("MS").sum().groupby(lambda d: d.month).mean()
    return dict(geada_safrinha=geada_saf / n, geada_trigo=geada_trigo / n,
                veranico_safrinha=veranico / n, n_anos=n, chuva_mensal=chuva_mes,
                periodo=f"{anos[0]}–{anos[-1]}", modo="reduzido", fonte="NASA POWER live (centroid point)",
                semeadura=None, geada_tabela=None, diagnostico=None, celula=None, municipio=None, agua_anual=None)


# Pre-computed lookup (Western Paraná): indicators of the CELL (~50 km); the municipality is context only.


def _ind(d: dict, nome: str) -> dict:
    return d["celula"]["indicadores"][nome]


@lru_cache(maxsize=1)
def _anuais() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/processed/clima/indicadores_anuais.parquet",
                           columns=["ponto_id", "ano", "indicador", "valor"])


def agua_anual_celula(ponto_id: str) -> dict[str, dict[str, np.ndarray]]:
    """Rain and ET0 (mm) per year (1991–2024) of the CELL, per cycle: 'safrinha' (15/02–15/06) and 'trigo' (01/05–30/09).
    They come from indicadores_anuais.parquet (computed in field_shift.clima.indicadores with FAO-56 ET0 / NASA POWER)."""
    a = _anuais()
    a = a[a["ponto_id"] == ponto_id]
    out = {}
    for ciclo in ("safrinha", "trigo"):
        ch = a[a["indicador"] == f"chuva_{ciclo}_mm"].set_index("ano")["valor"]
        et = a[a["indicador"] == f"et0_{ciclo}_mm"].set_index("ano")["valor"]
        df = pd.concat([ch, et], axis=1, keys=["p", "et0"]).dropna().sort_index()
        out[ciclo] = dict(p=df["p"].to_numpy(), et0=df["et0"].to_numpy())
    return out


def clima_regiao(info: dict, semeadura: str = SEMEADURA_PADRAO) -> dict:
    """Builds the risk dict (same format as riscos_power) from the lookup, plus the diagnosis and the frost table."""
    ddmm = semeadura.replace("/", "")
    g = lambda s: _ind(info, f"geada_safrinha_semeadura_{s.replace('/', '')}_le3")
    n = int(_ind(info, f"geada_safrinha_semeadura_{ddmm}_le3")["n_anos"])
    tabela = [dict(semeadura=s, prob=g(s)["media"], anos=round(g(s)["media"] * g(s)["n_anos"]), n_anos=int(g(s)["n_anos"]),
                   prob_1991_2020=g(s)["media_1991_2020"]) for s in SEMEADURAS]
    ic = _ind(info, "inicio_chuvas_dias_desde_0109")
    diag = dict(
        inicio_chuvas_mediana=ic["mediana_ddmm"], inicio_chuvas_p80=ic["p80_ddmm"],
        calor_soja_mediana=_ind(info, "calor_soja_dias")["mediana"], calor_soja_media=_ind(info, "calor_soja_dias")["media"],
        calor_soja_p80=_ind(info, "calor_soja_dias")["p80"],
        balanco_soja=_ind(info, "balanco_p_et0_soja_mm"), balanco_safrinha=_ind(info, "balanco_p_et0_safrinha_mm"),
        balanco_trigo=_ind(info, "balanco_p_et0_trigo_mm"),
        chuva_intensa_media=_ind(info, "chuva_intensa_dias_ge50")["media"],
        chuva_intensa_mediana=_ind(info, "chuva_intensa_dias_ge50")["mediana"])
    meses = {m: _ind(info, f"chuva_mensal_mm_m{m:02d}")["media"] for m in range(1, 13)}
    return dict(geada_safrinha=g(semeadura)["media"], geada_trigo=_ind(info, "geada_trigo_le3")["media"],
                veranico_safrinha=_ind(info, "veranico_safrinha_ge15")["media"], n_anos=n,
                chuva_mensal=pd.Series(meses), periodo="1991–2024", modo="regiao",
                fonte="NASA POWER 1991–2024, ~50 km cell (%s)" % info["celula"]["ponto_id"],
                semeadura=semeadura, geada_tabela=tabela, diagnostico=diag,
                celula=info["celula"], municipio={k: v for k, v in info["municipio"].items() if k != "indicadores"},
                agua_anual=agua_anual_celula(info["celula"]["ponto_id"]))


def obter_clima(lat: float, lon: float, semeadura: str = SEMEADURA_PADRAO) -> tuple[dict, str]:
    """Inside Western Paraná it uses the pre-computed lookup; outside, it falls back to live POWER (reduced mode)."""
    info = indicadores_para(lat, lon)
    if info is not None:
        return clima_regiao(info, semeadura), "pre-computed lookup (NASA POWER, ~50 km cell)"
    df, origem = buscar_power(lat, lon)
    return riscos_power(df), origem

def enriquecer(rk: dict, t: dict, analise_solo: dict | None = None) -> dict:
    """Adds to the climate dict: the field's soil (SoilGrids or, if provided, the farmer's soil analysis already validated
    by field_shift.motor.servico), the water-balance context and the municipality's PAM.
    Outside the region (reduced mode) it returns rk without soil/PAM -> the water criterion uses the catalog fallback."""
    out = {**rk, "solo": None, "pam": None, "agua_ctx": None}
    cod0 = rk["municipio"]["cod_ibge"] if rk.get("modo") == "regiao" else None
    out["rend"] = rendimentos(None if cod0 is None else str(cod0))  # no municipality: Western Paraná average (with a warning)
    out["rend_local"] = rk["municipio"]["nome"] if cod0 is not None else "Western Paraná (average)"
    if rk.get("modo") != "regiao":
        return out
    s = solo_poligono(t["poly"])
    if analise_solo:
        # the analysis replaces SoilGrids (which only supplies organic matter when the analysis has neither OM nor AWC)
        s = solo_de_analise(analise_solo, None if s is None else s["p30"]["soc"])
    out["solo"] = s
    if s is not None:
        out["agua_ctx"] = dict(ponto_id=rk["celula"]["ponto_id"], semeadura=rk["semeadura"],
                               cad_camadas={k: s["cad_mm_cm"][k] for k in ("0-5cm", "5-15cm", "15-30cm", "30-60cm")})
    cod = rk["municipio"]["cod_ibge"]
    p = pam_produtividade(cod)
    out["pam"] = dict(cod_ibge=cod, nome=rk["municipio"]["nome"], dados=p) if p else None
    return out


def rendimentos_rk(rk: dict) -> dict:
    """PAM yields for the income score: those from `enriquecer` (municipality) or, if missing, the Western Paraná average."""
    return rk.get("rend") or rendimentos(None)


def fmt_solo(rk: dict) -> str | None:
    return solo_texto(rk["solo"]) if rk.get("solo") else None


def fmt_pam(rk: dict) -> str | None:
    return pam_texto(rk["pam"]["nome"], rk["pam"]["dados"]) if rk.get("pam") else None


# --------------------------------------------------------------------------- 5. Engine
# REFERENCE ESTIMATES — to be validated with an agronomist/CONAB/Embrapa.
# A rotation is a pair (summer crop, second-window crop). The candidate CATALOGO (key = readable name of the pair) is built
# from two small catalogs: VERAO (soybean, summer corn) and SEGUNDA (second window). SEGUNDA attributes:
# `renda_itens`: second-window crops/practices that enter the margin (field_shift.renda: PAM yield × SEAB price − CONAB cost;
# cover/fallow = − estimated cost). The summer crop always enters (`item_renda` of VERAO).
# `agua` (0–1, relative demand) is only used as a FALLBACK outside Western Paraná (no pre-computed climate);
# inside the region the water criterion comes from the daily water balance with the field's soil (field_shift.agua; see agua_atendida).
# `ciclo_agua`: climate cycle of the second crop (used only in the per-cycle fallback, without soil).
# `kc`: seasonal mean crop coefficient (mean of the water-balance curve; FAO-56, estimate, to be validated).
# `bonus_sc`: expected yield gain on the following soybean from straw/N (bags/ha) — reference estimate,
# to be validated with an agronomist/Embrapa. The rotation bonus is the sum of the second crop's and the summer crop's bonus.
# `segue_semeadura`: the second crop is sown on the date chosen by the farmer (corn, sorghum, beans, millet/crotalaria); the others have
# a fixed date (wheat/oat 01/05, radish 01/04) and do not depend on the summer harvest. `janela`: accepted (start, end) dd/mm sowing window.
# `milho`: it is corn (corn after corn, following summer corn, has a pest penalty).
SEGUNDA = {
    "milho_safrinha": dict(nome="off-season corn", tipo="grão", dias_descobertos=60, cobertura=0.6, n_fix=0.4, pragas=0.5, agua=0.7,
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=0.85, bonus_sc=1.0, riscos=["geada_safrinha", "veranico_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=True,
        irrigavel=True, req_maquinas=("plataforma_milho",), vende=("milho",),
        mercado_oeste_pr=dict(nivel="alto", texto="cooperatives and the poultry and pork agro-industry of Western Paraná")),
    "milho_braquiaria": dict(nome="off-season corn + brachiaria", tipo="grão", dias_descobertos=30, cobertura=0.9, n_fix=0.4, pragas=0.65, agua=0.75,
        renda_itens=["milho_2safra", "braquiaria_consorcio"], ciclo_agua="safrinha", kc=0.90, bonus_sc=3.0,
        riscos=["geada_safrinha", "veranico_safrinha"], soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=True,
        irrigavel=True, req_maquinas=("plataforma_milho", "semeadora_consorcio"), vende=("milho",),
        mercado_oeste_pr=dict(nivel="alto", texto="corn with the same demand from cooperatives and agro-industry; brachiaria seed at retailers")),
    "trigo": dict(nome="wheat", tipo="grão", dias_descobertos=70, cobertura=0.6, n_fix=0.3, pragas=0.6, agua=0.6,
        renda_itens=["trigo"], ciclo_agua="trigo", kc=0.75, bonus_sc=1.0, riscos=["geada_trigo"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=True, req_maquinas=(), vende=("trigo",),
        mercado_oeste_pr=dict(nivel="médio", texto="cooperatives and mills, with lower liquidity than corn")),
    "aveia": dict(nome="oat (cover/straw)", tipo="cobertura", dias_descobertos=40, cobertura=0.8, n_fix=0.3, pragas=0.6, agua=0.3,
        renda_itens=["aveia"], ciclo_agua="trigo", kc=0.70, bonus_sc=2.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    "milheto_crotalaria": dict(nome="millet/crotalaria (cover)", tipo="cobertura", dias_descobertos=35, cobertura=0.85, n_fix=0.8, pragas=0.7, agua=0.3,
        renda_itens=["milheto_crotalaria"], ciclo_agua="safrinha", kc=0.65, bonus_sc=3.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    "pousio": dict(nome="fallow", tipo="pousio", dias_descobertos=150, cobertura=0.2, n_fix=0.0, pragas=0.3, agua=0.1,
        renda_itens=["pousio"], ciclo_agua=None, kc=None, bonus_sc=0.0,  # no crop: no water demand (water = 1.0)
        riscos=[], soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="não se aplica", texto="no production in the second window")),
    "soja_safrinha": dict(nome="off-season soybean", tipo="grão", dias_descobertos=60, cobertura=0.4, n_fix=0.8, pragas=0.0, agua=0.8,
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=1.0, bonus_sc=0.0, riscos=["veranico_safrinha"],
        soja_viva_vazio=True, ano_soja_2=True, segue_semeadura=True, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="alto", texto="same supply chain as soybean (but the rotation is prohibited by regulation)")),
    # New crops (grain/cover crops that use grain machinery and the grain sales channel). Catalog values: reference estimates.
    # Grain sorghum: a grass without the corn leafhopper, drought tolerant (no dry spell in the risk); window 15/01–15/03 and ~125 d cycle
    # (FAO-56 table 11); harvested with an adapted soybean/grain header.
    "sorgo": dict(nome="sorghum", tipo="grão", dias_descobertos=55, cobertura=0.7, n_fix=0.3, pragas=0.55, agua=0.5,
        renda_itens=["sorgo"], ciclo_agua="safrinha", kc=0.77, bonus_sc=1.0, riscos=["geada_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "15/03"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("sorgo",),
        mercado_oeste_pr=dict(nivel="médio", texto="animal feed and cooperatives, with lower demand than corn")),
    # 2nd-season beans ("das secas"): short cycle (~90 d), little straw and a host of white mold, which also attacks soybean (low pest score,
    # no bonus); window 15/01–28/02 (estimate based on ZARC/IDR-PR; frost and dry spells weigh in).
    "feijao_safrinha": dict(nome="off-season beans", tipo="grão", dias_descobertos=75, cobertura=0.4, n_fix=0.4, pragas=0.3, agua=0.7,
        renda_itens=["feijao_2safra"], ciclo_agua="safrinha", kc=0.84, bonus_sc=0.0, riscos=["geada_safrinha", "veranico_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "28/02"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("feijao",),
        mercado_oeste_pr=dict(nivel="médio", texto="grain merchants and cooperatives, with a volatile price and fewer buyers than corn and soybean")),
    # Forage radish: nutrient cycling and suppression of weeds/nematodes, but a host of white mold; fast-decomposing
    # straw; sown on 01/04, no grain sale.
    "nabo_forrageiro": dict(nome="forage radish (cover)", tipo="cobertura", dias_descobertos=35, cobertura=0.65, n_fix=0.1, pragas=0.6, agua=0.3,
        renda_itens=["nabo_forrageiro"], ciclo_agua="trigo", kc=0.90, bonus_sc=2.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    # Oat + radish mix: the oat's long-lasting straw plus the radish's nutrient cycling.
    "aveia_nabo": dict(nome="oat + forage radish (cover)", tipo="cobertura", dias_descobertos=35, cobertura=0.85, n_fix=0.2, pragas=0.65, agua=0.3,
        renda_itens=["aveia_nabo"], ciclo_agua="trigo", kc=0.85, bonus_sc=2.5, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
}
# `bonus_sc_faixa` (min, max) and `bonus_fonte`: range and source of the bonus (`bonus_sc` is the central value used in the score and margin).
# The range currently equals the central value; the literature research will replace it with real numbers (declare them in the entry itself).
BONUS_FONTE_PADRAO = "reference estimate — to be validated with an agronomist/Embrapa"
for _e in SEGUNDA.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", BONUS_FONTE_PADRAO)
_MERCADO_COBERTURA = dict(nivel="não se aplica", texto="no grain sale; seed available at retailers")
for _e in SEGUNDA.values():
    _e["mercado_oeste_pr"] = _e["mercado_oeste_pr"] or _MERCADO_COBERTURA
MERCADO_ESTIMATIVA = "estimate to be validated with local cooperatives/retailers"
MERCADO_NIVEL_TXT = {"alto": "high", "médio": "medium", "baixo": "low", "não se aplica": "not applicable"}  # labels for the `nivel` codes

# Summer crop. `colheita`: estimated harvest date (dd/mm); a second crop that follows the chosen sowing date can only be
# sown on that date or later. Soybean (early, sown in Sep): an engine assumption, which already accepts the second crop from 15/01.
# Summer corn (sown from 15/09 to 15/10, medium cycle ~130–145 d): harvested ~3–4 weeks after soybean — estimate, validate with ZARC/Embrapa.
# `bonus_sc`: additional gain (bags/ha) on the following soybean from breaking the disease and nematode cycle and more straw, when replacing
# summer soybean with corn (reference estimate, validate with an agronomist/Embrapa). `item_renda`: key of the summer margin (field_shift.renda).
VERAO = {
    "soja": dict(nome="Soybean", descricao="Soybean in summer: the most common crop in Western Paraná; sowing from 01/09 to 31/12.",
                 item_renda="soja", colheita="10/01", bonus_sc=0.0, req_maquinas=(), vende=()),
    "milho_verao": dict(nome="Summer corn", descricao="First-season corn instead of soybean: breaks the disease and nematode cycle and leaves more straw.",
                        item_renda="milho_1safra", colheita="05/02", bonus_sc=3.0, req_maquinas=("plataforma_milho",), vende=("milho",)),
}
for _e in VERAO.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", BONUS_FONTE_PADRAO)
# Corn-after-corn pest penalty (summer corn + off-season corn): a continuous host for the corn leafhopper (Dalbulus maidis)
# and corn stunt, plus fall armyworm and leaf diseases. Subtracted from the candidate's pest criterion (estimate, to be validated).
PENALIDADE_MILHO_SOBRE_MILHO = 0.25
TEXTO_MILHO_SOBRE_MILHO = (
    "Corn after corn (summer corn + off-season corn): keeps a continuous host for the corn leafhopper (Dalbulus maidis) and "
    "corn stunt, plus fall armyworm and leaf diseases; the pest criterion loses "
    f"{PENALIDADE_MILHO_SOBRE_MILHO:.2f} points (reference estimate, validate with an agronomist/Embrapa). "
    "Follow the leafhopper alerts (CigarrinhaWeb/ADAPAR; see /v1/contexto).")


def id_rotacao(verao: str, segunda: str) -> str:
    return f"{verao}__{segunda}"


def _combinacao(verao: str, segunda: str) -> dict:
    v, s = VERAO[verao], SEGUNDA[segunda]
    c = {k: val for k, val in s.items() if k != "nome"}
    sobre_milho = verao == "milho_verao" and s["milho"]
    c.update(
        id=id_rotacao(verao, segunda), verao=verao, segunda=segunda, nome_verao=v["nome"], nome_segunda=s["nome"],
        item_renda_verao=v["item_renda"], colheita_verao=v["colheita"], bonus_verao_sc=v["bonus_sc"],
        bonus_sc=s["bonus_sc"] + v["bonus_sc"], plantio_soja="10-15",
        bonus_sc_faixa=(s["bonus_sc_faixa"][0] + v["bonus_sc_faixa"][0], s["bonus_sc_faixa"][1] + v["bonus_sc_faixa"][1]),
        bonus_fonte=" + ".join(dict.fromkeys([s["bonus_fonte"], v["bonus_fonte"]])),
        req_maquinas_verao=v["req_maquinas"], vende=tuple(dict.fromkeys(s["vende"] + v["vende"])), milho_sobre_milho=sobre_milho,
        pragas=max(0.0, s["pragas"] - (PENALIDADE_MILHO_SOBRE_MILHO if sobre_milho else 0.0)), pragas_base=s["pragas"])
    return c


# readable name of the pair -> attributes (e.g. "Soybean → off-season corn").
CATALOGO = {f"{VERAO[v]['nome']} → {SEGUNDA[s]['nome']}": _combinacao(v, s) for v in VERAO for s in SEGUNDA}
NOME_DE = {c["id"]: n for n, c in CATALOGO.items()}  # id "<verao>__<segunda>" -> nome
ID_DE = {n: i for i, n in NOME_DE.items()}
# old API slugs (soybean in summer only) -> new id
LEGADO = {s: id_rotacao("soja", s) for s in ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio", "soja_safrinha")}

# Machinery restrictions: outsourcing cost when the farmer does NOT have the machine (ESTIMATE, validate with service providers).
CUSTO_MAQUINA = {
    "plataforma_milho": dict(rotulo="Outsourced corn harvest", custo=250.0,  # BRL/ha — estimate, to be validated
                             aviso="Requires a corn header: rent/outsource the harvest (estimated extra cost)."),
    "semeadora_consorcio": dict(rotulo="Outsourced brachiaria intercrop sowing", custo=80.0,  # BRL/ha — estimate, to be validated
                                aviso="Requires an intercrop seeder (or broadcast sowing/extra seed box): rent/outsource (estimated extra cost)."),
}
CUSTO_IRRIGACAO_PADRAO = 4.0   # BRL per mm per ha (energy + labor + depreciation) — estimate, to be validated
LAMINA_MAX_PADRAO = 6.0        # mm/day — center pivot/sprinkler estimate, to be validated
DIAS_REF_SOLO = 180    # absolute scale of bare days: 1 − days/180 (0 days = 1.0; ≥180 = 0)
PESOS_PADRAO = {"renda": 5, "solo": 3, "agua": 3, "pragas": 3, "risco": 3}


def agua_balanco(nome: str, riscos: dict) -> dict | None:
    """Daily water balance (FAO-56 bucket, NASA POWER cell + SoilGrids soil) in the critical phase; None if unavailable."""
    ctx = riscos.get("agua_ctx")
    if not ctx:
        return None
    irrig = riscos.get("irrig")
    lam = irrig["lamina_max_mm_dia"] if irrig and CATALOGO[nome].get("irrigavel") else None
    return agua_fase_critica(CATALOGO[nome]["segunda"], ctx["ponto_id"], ctx["semeadura"], ctx["cad_camadas"], lam)


def irrigacao_info(nome: str, riscos: dict) -> dict | None:
    """Irrigation applied to the candidate (mean cycle depth and cost in BRL/ha), or None (rainfed, cover/fallow or no soil)."""
    irrig = riscos.get("irrig")
    if not irrig or not CATALOGO[nome].get("irrigavel"):
        return None
    b = agua_balanco(nome, riscos)
    if b is None or not b.get("irrigado"):
        return None
    return dict(lamina_media_mm=b["lamina_media_mm"], custo_r_mm_ha=irrig["custo_r_mm_ha"],
                custo_r_ha=b["lamina_media_mm"] * irrig["custo_r_mm_ha"], lamina_max_mm_dia=irrig["lamina_max_mm_dia"])


def riscos_efetivos(nome: str, c: dict, riscos: dict) -> list[str]:
    """Climate risks of the candidate; dry spells stop counting if it is irrigated (frost still counts)."""
    irr = irrigacao_info(nome, riscos) is not None
    return [r for r in c["riscos"] if not (irr and r == "veranico_safrinha")]


def checar_restricoes(nome: str, c: dict, riscos: dict) -> list[str]:
    """Eliminations from farmer restrictions (`riscos['restr']`: excluidas {names}, sem_comprador {milho|trigo|sorgo|feijao|aveia_grao}).
    `c['vende']` lists the rotation's cash crops (summer and second window)."""
    r = riscos.get("restr") or {}
    motivos = []
    if nome in r.get("excluidas", ()):
        motivos.append("Excluded by the farmer.")
    for v in c["vende"]:
        if v in r.get("sem_comprador", ()):
            motivos.append(f"No local buyer, as reported by the farmer ({v}).")
    return motivos


def extras_custo(nome: str, c: dict, riscos: dict) -> list[dict]:
    """Extra costs of the candidate: outsourcing of the machines the farmer said they do NOT have + irrigation."""
    out = []
    maq = (riscos.get("restr") or {}).get("maquinas", {})
    for m, sufixo in [(m, "") for m in c["req_maquinas"]] + [(m, " (summer corn)") for m in c["req_maquinas_verao"]]:
        if maq.get(m) is False:
            out.append(dict(chave=f"terceirizacao_{m}", rotulo=CUSTO_MAQUINA[m]["rotulo"] + sufixo, custo=CUSTO_MAQUINA[m]["custo"],
                            detalhe="outsourcing estimate, to be validated with service providers"))
    ir = irrigacao_info(nome, riscos)
    if ir:
        out.append(dict(chave="irrigacao", rotulo="Irrigation", custo=ir["custo_r_ha"],
                        detalhe=f"mean depth {ir['lamina_media_mm']:.0f} mm/year × BRL {ir['custo_r_mm_ha']:.2f}/mm/ha"))
    return out


def agua_atendida(c: dict, riscos: dict, nome: str | None = None) -> tuple[float, bool]:
    """Water criterion, ABSOLUTE 0–1 SCALE. Inside the region, with soil: mean over the 34 years of ΣETa/ΣETc in the crop's
    critical phase (daily balance; changes with the sowing date). Fallow = 1.0.
    Without soil (or a candidate without a model): mean over the years of min(1, P_cycle/(Kc·ET0_cycle)) for the cell.
    Outside the region (no pre-computed climate): fallback 1 − `agua` attribute (do_clima=False). Returns (value, do_clima)."""
    if c["ciclo_agua"] is None:
        return 1.0, True
    b = agua_balanco(nome, riscos) if nome else None
    if b is not None:
        return b["media"], True
    aa = riscos.get("agua_anual")
    if not aa:
        return 1.0 - c["agua"], False
    d = aa[c["ciclo_agua"]]
    return float(np.mean(np.minimum(1.0, d["p"] / (c["kc"] * d["et0"])))), True


CRITERIOS = {"renda": "Income", "solo": "Soil health", "agua": "Water", "pragas": "Pest break", "risco": "Climate risk"}
RISCO_NOME = {"geada_safrinha": "frost on off-season corn", "veranico_safrinha": "off-season dry spell",
              "geada_trigo": "frost on wheat (flowering)"}


def _texto_risco(r: str, riscos: dict, cultura: str = "corn") -> str:
    p, n = riscos[r], riscos["n_anos"]
    k = round(p * n)
    fonte_c = ("NASA POWER 1991–2024, ~50 km cell" if riscos.get("modo") == "regiao"
               else f"NASA POWER {riscos['periodo']}, centroid point")
    if r == "geada_safrinha":
        sem = riscos.get("semeadura")
        if sem:
            aprox = "" if cultura == "corn" else " (corn frost window used as an approximation)"
            return f"Frost at flowering/grain fill of {cultura} sown on {sem}: {k} of {n} years ({p:.0%}), {fonte_c}{aprox}."
        return f"Frost (≤ 3 °C) in Jun–Jul, off-season corn grain fill: {k} of {n} years ({p:.0%}), {fonte_c}."
    if r == "geada_trigo":
        return f"Frost (≤ 3 °C) at wheat flowering (15/08–30/09): {k} of {n} years ({p:.0%}), {fonte_c}."
    return f"Dry spell ≥ 15 days in Mar–Apr: {k} of {n} years ({p:.0%}), {fonte_c}."
AVISO_ZARC = "Being outside ZARC may compromise credit/insurance (does not eliminate the candidate)."


def _dm(ddmm: str) -> tuple[int, int]:
    d, m = map(int, ddmm.split("/"))
    return m, d


def checar_regras(c: dict, riscos: dict | None = None) -> list[str]:
    """Hard rules: returns the list of elimination reasons (empty = valid). `riscos['semeadura']` (dd/mm of the second crop)
    enables the calendar rules: summer harvest and the second crop's sowing window."""
    motivos = []
    sem = (riscos or {}).get("semeadura")
    if c["ano_soja_2"]:
        if c["verao"] == "soja":
            motivos.append("Soybean after soybean in the same agricultural year is prohibited (Ordinance SDA/MAPA 1.124/2024).")
        motivos.append(f"Soybean in the second window{f' (sowing on {sem})' if sem else ''} falls outside the legal soybean sowing window (01/09–31/12).")
    if sem and c["segue_semeadura"] and not c["ano_soja_2"]:
        # summer harvest: the farmer's (stage/expected harvest), if it is the same summer crop; otherwise the catalog's
        prod = (riscos or {}).get("colheita_produtor")
        if prod and prod["verao"] == c["verao"]:
            colh, origem = prod["colheita"], "provided by the farmer"
        else:
            colh, origem = c["colheita_verao"], "estimate, to be validated"
        if cal.chave(cal.somar_dias(colh, cal.DIAS_PREPARO_2A)) > cal.chave(SEMEADURAS[-1]):
            motivos.append(f"Harvest too late for the off-season: the {c['nome_verao'].lower()} harvest is estimated at ~{colh} "
                           f"({origem}) and the last second-window sowing date considered is {SEMEADURAS[-1]}.")
        elif cal.chave(sem) < cal.chave(cal.somar_dias(colh, cal.DIAS_PREPARO_2A)):
            motivos.append(f"The {c['nome_verao'].lower()} harvest is estimated at ~{colh} ({origem}): "
                           f"sowing the second crop on {sem} would fall before it.")
        if c["janela"] and not (_dm(c["janela"][0]) <= _dm(sem) <= _dm(c["janela"][1])):
            motivos.append(f"Sowing on {sem} is outside the {c['nome_segunda']} window in Western Paraná "
                           f"({c['janela'][0]}–{c['janela'][1]}; reference estimate based on ZARC/IDR-PR, to be validated).")
    if c["soja_viva_vazio"]:
        motivos.append("There is live soybean during the soybean-free period in Western Paraná (02/06–31/08).")
    mes, dia = map(int, c["plantio_soja"].split("-"))
    if not ((9, 1) <= (mes, dia) <= (12, 31)):
        motivos.append(f"Soybean sowing on {dia:02d}/{mes:02d} is outside the 01/09–31/12 window.")
    return motivos


class SemCandidatas(ValueError):
    """Every evaluated rotation was eliminated (hard rules + farmer restrictions). `eliminadas`: {name: reasons}."""

    def __init__(self, msg: str, eliminadas: dict | None = None):
        super().__init__(msg)
        self.eliminadas = eliminadas or {}


def pontuar(pesos: dict[str, float], riscos: dict, ajustes: dict | None = None, nomes: list[str] | None = None) -> dict:
    """Returns a dict with the table of valid candidates (DataFrame), eliminated ones and contributions. `nomes`: evaluates only these
    candidates (CATALOGO names); None = all. Every criterion on an ABSOLUTE 0–1 SCALE (no min-max across candidates), higher = better."""
    validas, eliminadas = {}, {}
    for nome in (nomes if nomes is not None else CATALOGO):
        c = CATALOGO[nome]
        m = checar_regras(c, riscos) + checar_restricoes(nome, c, riscos)
        (eliminadas if m else validas)[nome] = m or c
    if not validas:
        raise SemCandidatas("The restrictions provided eliminate every rotation.", eliminadas)
    # Risk: 1 - P(any risk); with several independent risks, criterion = Π(1 - pᵢ). No risk = 1.0.
    # Irrigated candidate: dry spells do not count (frost still counts).
    rs_ef = {n: riscos_efetivos(n, c, riscos) for n, c in validas.items()}
    risco_abs = {n: float(np.prod([1 - riscos[r] for r in rs_ef[n]])) if rs_ef[n] else 1.0 for n in validas}
    # Soil: mean of cover, N fixation and (1 - bare days/180), all absolute 0–1.
    solo = {n: (c["cobertura"] + c["n_fix"] + max(0.0, 1 - c["dias_descobertos"] / DIAS_REF_SOLO)) / 3
            for n, c in validas.items()}
    # Income from the INCREMENTAL margin over the municipality's summer soybean: incremental = rotation margin − soybean margin
    # = (summer margin − soybean margin) + second-crop margin (sold: PAM × price − cost; cover: − establishment
    # cost; fallow: − management cost) + bonus on the following soybean (bonus_sc × soybean price). With soybean in summer the first
    # term is zero (original formula); summer corn enters with PAM 1st-season corn × corn price − CONAB summer-corn cost.
    # renda = clip(0.5 + incremental / (2·S), 0, 1), S = max(municipal soybean margin, RENDA_ESCALA_MIN):
    # incremental = +S → 1.0; zero → 0.5; −S → 0. It measures how much the second season adds or takes away on the municipality's own soybean scale.
    extras = {n: extras_custo(n, c, riscos) for n, c in validas.items()}
    margens = calcular_margens({n: c for n, c in validas.items()}, rendimentos_rk(riscos), ajustes, extras)
    renda = {n: float(np.clip(0.5 + m["incremental"] / (2 * m["escala_S"]), 0.0, 1.0)) for n, m in margens.items()}
    aviso_renda = (None if any(m["total"] > 0 for m in margens.values())
                   else "No valid rotation has a positive total margin with the prices and costs used (informational).")
    crit = {
        "renda": renda,
        "solo": solo,
        "agua": {n: agua_atendida(c, riscos, n)[0] for n, c in validas.items()},
        "pragas": {n: c["pragas"] for n, c in validas.items()},
        "risco": risco_abs,
    }
    soma = sum(pesos.values()) or 1
    w = {k: (pesos[k] / soma if sum(pesos.values()) else 0.2) for k in crit}
    linhas = []
    for n in validas:
        contrib = {k: w[k] * crit[k][n] for k in crit}
        linhas.append(dict(candidata=n, nota=sum(contrib.values()),
                           **{f"{k}": crit[k][n] for k in crit}, contrib=contrib))
    tab = pd.DataFrame(linhas).sort_values("nota", ascending=False, kind="stable").reset_index(drop=True)
    return dict(tabela=tab, eliminadas=eliminadas, margens=margens, aviso_renda=aviso_renda, pesos_norm=w, riscos=riscos)

# --------------------------------------------------------------------------- 6. Card texts
def _r(x: float) -> str:
    return f"{x:,.0f}"


def local_rend(riscos: dict, chave: str) -> str:
    """Origin of a crop's PAM yield: the municipality or, if it lacks enough PAM data, the Western Paraná average."""
    if chave in (riscos.get("rend") or {}).get("_regionais", ()):
        return "Western Paraná (average; the municipality has no recent PAM)"
    return riscos.get("rend_local") or "Western Paraná"


def fmt_margem(m: dict, riscos: dict) -> list[str]:
    """Breakdown of the rotation margin (card evidence lines)."""
    linhas = []
    for i in m["itens"]:
        local = local_rend(riscos, i["chave"])
        if i.get("extra"):
            linhas.append(f"{i['rotulo']}: extra cost BRL {_r(i['custo'])}/ha ({i['detalhe']}) = {_rs(i['margem'])}.")
        elif i["sc_ha"] is not None and i.get("prod_usuario"):
            rz = i.get("razao_p20")
            ruim = (f"bad year: own yield × PAM p20/average ({rz:.2f}) = {i['sc_ha_ruim']:.0f} bags/ha → BRL {_r(i['margem_ano_ruim'])}/ha"
                    if i["sc_ha_ruim"] is not None else "no bad year (PAM without a series)")
            linhas.append(f"{i['rotulo']}: {i['sc_ha']:.0f} bags/ha (provided by the farmer; PAM {local}: {i['sc_ha_pam']:.0f} bags/ha) × "
                          f"BRL {i['preco']:.2f}/bag ({fonte_preco(i)}) − cost BRL {_r(i['custo'])}/ha ({fonte_custo(i, m['linha_custo'])}) "
                          f"= BRL {_r(i['margem'])}/ha ({ruim}).")
        elif i["sc_ha"] is not None:
            linhas.append(f"{i['rotulo']}: {i['sc_ha']:.0f} bags/ha (PAM {local} {i['anos']}) × BRL {i['preco']:.2f}/bag ({fonte_preco(i)}) − cost "
                          f"BRL {_r(i['custo'])}/ha ({fonte_custo(i, m['linha_custo'])}) = BRL {_r(i['margem'])}/ha "
                          f"(yield CV {i['cv']:.0%}; bad year, 10-year p20 = {i['sc_ha_ruim']:.0f} bags/ha → "
                          f"BRL {_r(i['margem_ano_ruim'])}/ha).")
        else:
            linhas.append(f"{i['rotulo']}: no sale, establishment cost BRL {_r(i['custo'])}/ha ({fonte_custo(i, m['linha_custo'])}) = BRL {_r(i['margem'])}/ha.")
    detalhe_bonus = (f" ({m['bonus_verao_sc']:g} bags/ha from summer corn instead of soybean + {m['bonus_sc'] - m['bonus_verao_sc']:g} from the second crop)"
                     if m["bonus_verao_sc"] else "")
    linhas.append(f"Bonus on the following soybean: {m['bonus_sc']:g} bags/ha × BRL {m['preco_soja']:.2f}/bag = BRL {_r(m['bonus'])}/ha{detalhe_bonus} "
                  f"(straw/N and disease-cycle break, reference estimate).")
    t = (f"Rotation total: BRL {_r(m['total'])}/ha/year; second-season increment (without soybean, with the bonus): BRL {_r(m['incremental'])}/ha, "
         f"on the scale S = BRL {_r(m['escala_S'])}/ha (municipal soybean margin, min. {_r(RENDA_ESCALA_MIN)})")
    if m["total_ano_ruim"] is not None:
        t += f"; in a bad year (p20 yield): BRL {_r(m['total_ano_ruim'])}/ha/year"
    linhas.append(t + ".")
    return linhas


def _rs(x: float) -> str:
    return f"BRL {_r(x)}/ha" if x >= -0.5 else f"−BRL {_r(-x)}/ha"


def _c2(x: float) -> str:
    return f"{x:.2f}"


def _nome_curto(n: str) -> str:
    return n.replace("Soybean → ", "")


def _texto_criterio(k: str, alt: str, atu: str, res: dict, d: float) -> str:
    """Short sentence about criterion k of alternative `alt` vs the current rotation `atu` (d = signed Δcriterion)."""
    t, m = res["tabela"].set_index("candidata"), res["margens"]
    ca, cb = t.loc[alt], t.loc[atu]
    ganha = d > 0
    if k == "renda":
        a, b = m[alt]["incremental"], m[atu]["incremental"]
        if ganha:
            pct = f" (+{(a - b) / abs(b):.0%})" if b > 0 else ""
            return f"adds {_rs(a)} vs {_rs(b)} in the second season{pct}"
        return f"gives up {_rs(b - a)} in the second season ({_rs(a)} vs {_rs(b)})"
    if k == "solo":
        da, db = CATALOGO[alt]["dias_descobertos"], CATALOGO[atu]["dias_descobertos"]
        return (f"{'improves' if ganha else 'worsens'} soil health ({_c2(ca['solo'])} vs {_c2(cb['solo'])}; "
                f"~{da} days of bare soil vs {db})")
    if k == "agua":
        return f"{'meets' if ganha else 'falls short of'} the water demand {'better' if ganha else 'more'} ({_c2(ca['agua'])} vs {_c2(cb['agua'])})"
    if k == "pragas":
        return f"breaks the pest cycle {'better' if ganha else 'less'} ({_c2(ca['pragas'])} vs {_c2(cb['pragas'])})"
    pa, pb = 1 - ca["risco"], 1 - cb["risco"]
    return (f"{'reduces' if ganha else 'increases'} the climate risk (some adverse event in {pa:.0%} of years "
            f"vs {pb:.0%})")


def por_que_comparado(res: dict, nome: str, atual: str | None) -> str | None:
    """The 'why' text for `nome` compared with the current rotation (None if the current one is not among the valid ones)."""
    tab = res["tabela"]
    nomes = list(tab["candidata"])
    if atual is None or atual not in nomes or nome not in nomes:
        return None
    if nome == atual:
        pos, n = nomes.index(atual) + 1, len(nomes)
        if pos == 1:
            o = tab.iloc[1]
            return (f"This is the current rotation; it ranked 1st among {n} valid options. The 2nd best ({_nome_curto(o['candidata'])}) "
                    f"scores {_c2(o['nota'])}.")
        b = tab.iloc[0]
        return (f"This is the current rotation; it ranked #{pos} among {n} valid options. The best alternative "
                f"({_nome_curto(b['candidata'])}) scores {_c2(b['nota'])}.")
    t = tab.set_index("candidata")
    w = res["pesos_norm"]
    dif = {k: w[k] * (t.loc[nome, k] - t.loc[atual, k]) for k in CRITERIOS}
    tops = [k for k, v in sorted(dif.items(), key=lambda kv: -abs(kv[1]))[:3] if abs(v) >= 0.005]
    frases = [_texto_criterio(k, nome, atual, res, dif[k]) for k in tops]
    cab = f"Compared with the current rotation ({_nome_curto(atual)}): "
    if not frases:
        txt = cab + "practically the same performance on all five criteria."
    elif len(frases) == 1:
        txt = cab + frases[0] + "."
    else:
        txt = cab + ", ".join(frases[:-1]) + " and " + frases[-1] + "."
    if "risco" not in tops and 1 - t.loc[nome, "risco"] > 0.005:
        txt += f" Same climate risk (some adverse event in {1 - t.loc[nome, 'risco']:.0%} of years)."
    return txt


def montar_card(linha: pd.Series, atual: bool, riscos: dict, dias_solo_ndvi: float, margem: dict | None = None,
                por_que_cmp: str | None = None) -> dict:
    """`por_que_cmp`: text from `por_que_comparado` (comparison with the current rotation); if None, only the largest contributions."""
    c = CATALOGO[linha["candidata"]]
    top = sorted(linha["contrib"].items(), key=lambda kv: -kv[1])[:2]
    contribs = "Largest contributions to the score: " + " and ".join(f"{CRITERIOS[k]} ({_c2(v)})" for k, v in top) + "."
    por_que = f"{por_que_cmp} {contribs}" if por_que_cmp else contribs
    ev = [f"Days of bare soil per year (catalog): ~{c['dias_descobertos']} days."]
    if atual and not np.isnan(dias_solo_ndvi):
        ev.append(f"Observed NDVI (NASA HLS): ~{dias_solo_ndvi:.0f} days/year with NDVI<{LIMIAR_SOLO}.")
    if margem is not None:
        ev += fmt_margem(margem, riscos)
    ag, do_clima = agua_atendida(c, riscos, linha["candidata"])
    bal = agua_balanco(linha["candidata"], riscos)
    fonte_solo = (FONTE_ANALISE if (riscos.get("solo") or {}).get("fonte") == FONTE_ANALISE
                  else "SoilGrids soil")
    ir = irrigacao_info(linha["candidata"], riscos)
    if c["ciclo_agua"] is None:
        ev.append("Water: no crop, no water demand (score 1.00); the cost of fallow shows up in soil.")
    elif bal is not None:
        ev.append(f"Water: in the critical phase ({bal['fase']}, sowing on {bal['semeadura']}), soil water met on average "
                  f"{bal['media']:.0%} of the demand; in {bal['n_abaixo']} of {bal['n_anos']} years it was below 70% "
                  f"(daily NASA POWER balance + {fonte_solo}{', irrigated' if bal.get('irrigado') else ''}, AWC {bal['taw_mm']:.0f} mm).")
    elif do_clima:
        nome_c = c["nome_segunda"]
        ev.append(f"Water: rain covers on average {ag:.0%} of the demand ({nome_c}, Kc {c['kc']:.2f}; "
                  f"NASA POWER {riscos['periodo']}, FAO-56).")
    else:
        ev.append(f"Water: fixed catalog estimate ({ag:.0%}); no pre-computed climate outside Western Paraná.")
    if ir:
        ev.append(f"Irrigated: mean depth {ir['lamina_media_mm']:.0f} mm/year, cost BRL {_r(ir['custo_r_ha'])}/ha "
                  f"(BRL {ir['custo_r_mm_ha']:.2f}/mm/ha, max. depth {ir['lamina_max_mm_dia']:g} mm/day; the yield gain "
                  f"from irrigation is not modeled, the expected yield does not change).")
    rs_ef = riscos_efetivos(linha["candidata"], c, riscos)
    for r in rs_ef:
        ev.append(_texto_risco(r, riscos, "corn" if c["milho"] else c["nome_segunda"]))
    if ir and len(rs_ef) < len(c["riscos"]):
        ev.append("Dry spells do not count in the risk: the candidate is irrigated (frost still counts).")
    if not c["riscos"]:
        ev.append("No second-season climate risk considered (cover species/fallow).")
    ben = []
    if c["cobertura"] >= 0.8: ben.append("Good cover/straw: protects the soil and reduces erosion.")
    if c["n_fix"] >= 0.7: ben.append("Relevant nitrogen fixation for the next soybean.")
    if c["pragas"] >= 0.6: ben.append("Helps break the pest and disease cycle.")
    if c["bonus_sc"] >= 2: ben.append(f"Straw/N raise the following soybean (~+{c['bonus_sc']:g} bags/ha, estimate).")
    if c["bonus_verao_sc"]:
        ben.append(f"{c['nome_verao']} instead of summer soybean breaks the disease and nematode cycle and leaves more straw "
                   f"(~+{c['bonus_verao_sc']:g} bags/ha on the following soybean, estimate to be validated with an agronomist/Embrapa).")
    if margem is not None and margem["total"] >= 2000: ben.append(f"High rotation margin (~BRL {_r(margem['total'])}/ha/year).")
    if c["ciclo_agua"] is None or agua_atendida(c, riscos, linha["candidata"])[0] >= 0.9: ben.append("Rain meets practically all of the water demand.")
    solo_p = riscos.get("solo") or {}
    if solo_p.get("fonte") == FONTE_ANALISE:
        lacuna_cad = ("Available water capacity from the farmer's analysis (provided or by Saxton & Rawls with the analysis), "
                      "taken as representative of the 0–60 cm profile; soil fertility not used.")
    else:
        lacuna_cad = "Available water capacity from pedotransfer (Saxton & Rawls), may be wrong in tropical Latosols; soil fertility not used."
    lacunas = ([] if riscos.get("solo") else ["Soil texture/available water capacity (SoilGrids) not considered (field outside Western Paraná)."]) + [
               lacuna_cad,
               "Soil moisture (SMAP) and satellite rainfall (GPM) not used.",
               *([f"{c['nome_verao']} in summer: summer climate risk and water balance not modeled (only the second window enters these criteria)."]
                 if c["verao"] != "soja" else []),
               "Income: price = Paraná average over the last 12 months (SEAB/DERAL); CONAB cost for Londrina/Ponta Grossa (not Western Paraná); "
               "cover/fallow cost, straw/N bonus and Kc are reference estimates."]
    revisar = [AVISO_ZARC, "Confirm the calendar, cultivar and ZARC window with the agronomist."]
    if c["milho_sobre_milho"]:
        revisar.append(TEXTO_MILHO_SOBRE_MILHO)
        ev.append(f"Pests: corn after corn, catalog score {c['pragas_base']:.2f} − penalty {PENALIDADE_MILHO_SOBRE_MILHO:.2f} "
                  f"= {c['pragas']:.2f} (corn leafhopper/corn stunt; reference estimate).")
    if "geada_safrinha" in c["riscos"] and riscos["geada_safrinha"] >= 0.2:
        revisar.append(f"Off-season frost (≤ 3 °C) in {riscos['geada_safrinha']:.0%} of years"
                       + (f" with sowing on {riscos['semeadura']}" if riscos.get("semeadura") else "")
                       + ": review the sowing date/hybrid.")
    if "veranico_safrinha" in rs_ef and riscos["veranico_safrinha"] >= 0.2:
        revisar.append(f"Dry spell ≥15 days in Mar–Apr in {riscos['veranico_safrinha']:.0%} of years.")
    if "geada_trigo" in c["riscos"] and riscos["geada_trigo"] >= 0.2:
        revisar.append(f"Frost at wheat flowering in {riscos['geada_trigo']:.0%} of years.")
    if c["dias_descobertos"] >= 100: revisar.append("Many days of exposed soil: risk of erosion and weeds.")
    maq = (riscos.get("restr") or {}).get("maquinas", {})
    avisos = list(dict.fromkeys(CUSTO_MAQUINA[m]["aviso"] for m in c["req_maquinas"] + c["req_maquinas_verao"] if maq.get(m) is False))
    mer = c["mercado_oeste_pr"]
    mercado = dict(nivel=mer["nivel"], texto=mer["texto"], estimativa=MERCADO_ESTIMATIVA)
    ev.append(f"Market in Western Paraná: {MERCADO_NIVEL_TXT.get(mer['nivel'], mer['nivel'])}; {mer['texto']} ({MERCADO_ESTIMATIVA}).")
    return dict(por_que=por_que, evidencia=ev, beneficios=ben or ["No notable benefit on the criteria evaluated."],
                lacunas=lacunas, revisar=revisar, avisos=avisos, mercado=mercado, irrigacao=ir)


def fmt_diagnostico(d: dict) -> list[str]:
    """Text lines of the climate diagnosis (display only; not part of the score)."""
    b = lambda x: f"median {x['mediana']:.0f} mm, p20 {x['p20']:.0f} mm"
    return [
        f"Rain onset (from 01/09): median {d['inicio_chuvas_mediana']}, p80 {d['inicio_chuvas_p80']} (1 in 5 years it is delayed until then).",
        f"Heat on soybean: median {d['calor_soja_mediana']:.1f} days/cycle above the threshold (mean {d['calor_soja_media']:.1f}; p80 {d['calor_soja_p80']:.1f}).",
        f"P − ET0 balance per cycle — soybean: {b(d['balanco_soja'])}; off-season: {b(d['balanco_safrinha'])}; wheat: {b(d['balanco_trigo'])}.",
        f"Heavy rain (≥ 50 mm/day): mean {d['chuva_intensa_media']:.1f} days/year (median {d['chuva_intensa_mediana']:.0f}).",
    ]


if __name__ == "__main__":
    import sys
    sem = sys.argv[1] if len(sys.argv) > 1 else SEMEADURA_PADRAO
    t = carregar_talhao()
    dec = "no data" if t["declividade"] is None else f"{t['declividade']:.1f}% (p90 {t['declividade_p90']:.1f}%, {t['classe_embrapa']})"
    alt = "no data" if t["altitude"] is None else f"{t['altitude']:.0f} m"
    print(f"Field {t['id']}: {t['area_ha']:.1f} ha  lat={t['lat']:.5f} lon={t['lon']:.5f} slope={dec}  elevation={alt}")
    print("MapBiomas history:", t["historico"])
    nd = carregar_ndvi()
    pk = picos_por_ano_agricola(nd)
    print("NDVI peaks per agricultural year:", pk, "→", detectar_rotacao(pk))
    print(f"Days/year with NDVI<{LIMIAR_SOLO}: {dias_solo_por_ano(nd):.0f}; intervals: {len(faixas_solo(nd))}")
    rk, origem = obter_clima(t["lat"], t["lon"], sem)
    rk = enriquecer(rk, t)
    print(f"Climate [{rk['modo']}]: {origem} · {rk['fonte']} · off-season sowing {rk['semeadura']}")
    if rk["modo"] == "reduzido":
        print("WARNING: reduced mode (outside Western Paraná; live POWER, no diagnosis or per-date table).")
    else:
        m = rk["municipio"]
        print(f"Cell {rk['celula']['ponto_id']} (elev {rk['celula']['elev']:.0f} m); municipality (context): {m['nome']} ({m['cod_ibge']})")
        print("Off-season frost ≤3 °C by sowing date:",
              {r["semeadura"]: f"{r['prob']:.2f} ({r['anos']}/{r['n_anos']})" for r in rk["geada_tabela"]})
        for linha in fmt_diagnostico(rk["diagnostico"]):
            print("  -", linha)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rk.items()
           if k in ("geada_safrinha", "geada_trigo", "veranico_safrinha", "n_anos", "periodo")})
    print("Mean monthly rain (mm):", rk["chuva_mensal"].round(0).to_dict())
    if rk.get("solo"):
        print("Soil:", fmt_solo(rk))
        print("PAM:", fmt_pam(rk))
    print("Water met (critical phase, daily balance):", {n.replace("Soybean → ", ""): round(agua_atendida(c, rk, n)[0], 3) for n, c in CATALOGO.items()})
    for n in CATALOGO:
        b = agua_balanco(n, rk)
        if b:
            print(f"  {n}: {b['fase']} ({b['semeadura']}) mean {b['media']:.3f}, {b['n_abaixo']}/{b['n_anos']} years <0.7, TAW {b['taw_mm']:.0f} mm")
    ajustes = {"linha_custo": sys.argv[2]} if len(sys.argv) > 2 else None
    res = pontuar(PESOS_PADRAO, rk, ajustes)
    print(res["tabela"].drop(columns="contrib").round(2).to_string())
    if res["aviso_renda"]:
        print("WARNING:", res["aviso_renda"])
    print("Yield:", rk["rend"]["_origem"])
    for n, m in res["margens"].items():
        print(f"\n{n}:")
        for l in fmt_margem(m, rk):
            print("  -", l)
    for n, m in res["eliminadas"].items():
        print("ELIMINATED:", n, m)
