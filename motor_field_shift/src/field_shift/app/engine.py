"""Field Shift MVP engine: data (field, NDVI, NASA POWER) + hard rules + scoring.

Everything here is pure logic (no Streamlit), so it can be tested:  uv run python src/field_shift/app/engine.py
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

from field_shift import crop_calendar as cal
from field_shift.app import field_state
from field_shift.water import critical_phase_water
from field_shift.water.balance import DEFICIT_THRESHOLD, WHEAT_SOWING
from field_shift import zarc
from field_shift.i18n import Join, Msg
from field_shift.income import history as income_history
from field_shift.crop_calendar import DEFAULT_SOWING, SOWINGS_2ND
from field_shift.climate.lookup import indicators_for
from field_shift.pam import productivity as pam_yield
from field_shift.pam.productivity import text as pam_text
from field_shift.income import compute_margins, cost_source, price_source, yields
from field_shift.region import inside_region, relief
from field_shift.region.soybean_free_period import soy_calendar, in_window
from field_shift.soil import soil as polygon_soil
from field_shift.soil.soil import soil_from_analysis, text as soil_text

ROOT = Path(__file__).resolve().parents[3]
FTW = ROOT / "data/processed/ftw"
FIELD_ID = "72638"  # the parquet `id` column is a string
SOIL_THRESHOLD = 0.35  # NDVI below this = bare soil / low cover

# Local
@lru_cache(maxsize=1)
def fields_gdf() -> gpd.GeoDataFrame:
    """FTW fields with MapBiomas (in-memory cache; used by load_field and by the API service)."""
    return gpd.read_parquet(FTW / "fields_tile_mapbiomas_geo.parquet")


def load_field(tid: str = FIELD_ID) -> dict:
    gdf = fields_gdf()
    row = gdf[gdf["id"].astype(str) == str(tid)]
    if row.empty:
        raise ValueError(f"Talhão {tid} não encontrado")
    row = row.iloc[0]
    # centroid in a projected CRS (SIRGAS 2000 / UTM 22S) -> 4326
    c = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(31982).centroid.to_crs(4326).iloc[0]
    poly = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(4326).iloc[0]
    # Slope in % (NASADEM) from the region module; outside the region -> None ("no data").
    rel = None
    if inside_region(poly):
        rel = relief(poly)
    legend = json.loads((FTW / "mapbiomas_legend_c10.json").read_text())
    hist = {a: legend.get(str(int(row[f"lc_{a}"])), "?") for a in range(2019, 2025)}
    return dict(id=tid, area_ha=float(row["area_ha"]), lat=c.y, lon=c.x, poly=poly,
                relevo=rel, declividade=None if rel is None else rel["declividade_media"],
                declividade_p90=None if rel is None else rel["declividade_p90"],
                classe_embrapa=None if rel is None else rel["classe_embrapa"],
                altitude=None if rel is None else rel["altitude_media"], historico=hist)

# NDVI history
def load_ndvi(tid: str = FIELD_ID) -> pd.Series:
    df = pd.read_csv(ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv", parse_dates=["data"])
    df = df[df["frac_clear"] >= 0.7]
    s = df.groupby("data")["ndvi_mean"].mean().sort_index()  # S30 and L30 on the same day -> mean
    d = s.resample("D").mean().interpolate(limit_area="inside")  # daily series
    return d.rolling(15, center=True, min_periods=1).mean()  # ~15-day smoothing


def soil_ranges(ndvi: pd.Series, threshold: float = SOIL_THRESHOLD) -> list[tuple]:
    """Contiguous intervals (start, end) with NDVI < threshold."""
    low = (ndvi < threshold).values
    ranges, start = [], None
    for i, b in enumerate(low):
        if b and start is None:
            start = ndvi.index[i]
        if not b and start is not None:
            ranges.append((start, ndvi.index[i - 1]))
            start = None
    if start is not None:
        ranges.append((start, ndvi.index[-1]))
    return ranges


def peaks_by_crop_year(ndvi: pd.Series) -> dict[str, int]:
    """Number of NDVI peaks per crop year (Sep–Aug). Complete crop years only."""
    res = {}
    for year in range(ndvi.index.min().year - 1, ndvi.index.max().year + 1):
        start, end = pd.Timestamp(year, 9, 1), pd.Timestamp(year + 1, 8, 31)
        if start < ndvi.index.min() or end > ndvi.index.max():
            continue  # ano incompleto
        excerpt = ndvi[start:end]
        p, _ = find_peaks(excerpt.values, height=0.6, prominence=0.2, distance=40)
        res[f"{year}/{str(year + 1)[2:]}"] = len(p)
    return res


def detect_rotation(peaks: dict[str, int]) -> str:
    if not peaks:
        return "Soja → milho safrinha"
    median = float(np.median(list(peaks.values())))
    return "Soja → milho safrinha" if median >= 2 else "Soja → pousio"


def bare_soil_days_by_year(ndvi: pd.Series) -> float:
    """Mean days/year with NDVI < threshold, over complete crop years."""
    tot = []
    for year in range(ndvi.index.min().year - 1, ndvi.index.max().year + 1):
        start, end = pd.Timestamp(year, 9, 1), pd.Timestamp(year + 1, 8, 31)
        if start >= ndvi.index.min() and end <= ndvi.index.max():
            tot.append(int((ndvi[start:end] < SOIL_THRESHOLD).sum()))
    return float(np.mean(tot)) if tot else float("nan")

# NASA POWER climate
POWER_URL = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MIN,T2M_MAX,PRECTOTCORR"
             "&community=AG&longitude={lon}&latitude={lat}&start=19950101&end=20241231&format=JSON")


def fetch_power(lat: float, lon: float) -> tuple[pd.DataFrame, str]:
    """Return (daily DataFrame, origin). Tries the API; on failure uses the disk cache."""
    cache = ROOT / f"data/raw/power/power_{lat:.2f}_{lon:.2f}.json"
    try:
        r = requests.get(POWER_URL.format(lat=round(lat, 4), lon=round(lon, 4)), timeout=180)
        r.raise_for_status()
        js = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(js))
        origin = "API NASA POWER (ao vivo)"
    except Exception as e:
        if not cache.exists():
            raise RuntimeError(f"NASA POWER unavailable and no disk cache: {e}") from e
        js = json.loads(cache.read_text())
        origin = f"cache em disco ({cache.name}) — API falhou: {type(e).__name__}"
    p = js["properties"]["parameter"]
    df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    return df.replace(-999, np.nan), origin


def power_risks(df: pd.DataFrame) -> dict:
    years = sorted(set(df.index.year))
    frost_2nd = frost_wheat = dry_spell = 0
    for a in years:
        y = df[df.index.year == a]
        # threshold <= 3 C (consistent with the lookup: the INMET validation showed that POWER underestimates frost)
        frost_2nd += bool((y.loc[f"{a}-06-01":f"{a}-07-31", "T2M_MIN"] <= 3).any())
        frost_wheat += bool((y.loc[f"{a}-08-15":f"{a}-09-30", "T2M_MIN"] <= 3).any())
        drought = (y.loc[f"{a}-03-01":f"{a}-04-30", "PRECTOTCORR"] < 1).astype(int)
        run = drought.groupby((drought == 0).cumsum()).cumsum()
        dry_spell += bool(run.max() >= 15)
    n = len(years)
    month_rain = df["PRECTOTCORR"].resample("MS").sum().groupby(lambda d: d.month).mean()
    return dict(geada_safrinha=frost_2nd / n, geada_trigo=frost_wheat / n,
                veranico_safrinha=dry_spell / n, n_anos=n, chuva_mensal=month_rain,
                periodo=f"{years[0]}–{years[-1]}", modo="reduzido", fonte="NASA POWER ao vivo (ponto do centróide)",
                semeadura=None, geada_tabela=None, diagnostico=None, celula=None, municipio=None, agua_anual=None)


# Precomputed lookup (Paraná): indicators of the CELL (~50 km); the municipality is only context.


def _ind(d: dict, nome: str) -> dict:
    return d["celula"]["indicadores"][nome]


@lru_cache(maxsize=1)
def _annual() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/processed/clima_pr/indicadores_anuais.parquet",
                           columns=["ponto_id", "ano", "indicador", "valor"])


def cell_annual_water(point_id: str) -> dict[str, dict[str, np.ndarray]]:
    """Rain and ET0 (mm) per year (1991–2024) of the CELL, per cycle: 'safrinha' (15/02–15/06) and 'trigo' (01/05–30/09).
    From indicadores_anuais.parquet (computed in field_shift.climate.indicators with FAO-56 ET0 / NASA POWER)."""
    a = _annual()
    a = a[a["ponto_id"] == point_id]
    out = {}
    for cycle in ("safrinha", "trigo"):
        ch = a[a["indicador"] == f"chuva_{cycle}_mm"].set_index("ano")["valor"]
        et = a[a["indicador"] == f"et0_{cycle}_mm"].set_index("ano")["valor"]
        df = pd.concat([ch, et], axis=1, keys=["p", "et0"]).dropna().sort_index()
        out[cycle] = dict(p=df["p"].to_numpy(), et0=df["et0"].to_numpy())
    return out


def region_climate(info: dict, sowing: str = DEFAULT_SOWING) -> dict:
    """Build the risks dict (same format as power_risks) from the lookup, plus diagnosis and frost table."""
    ddmm = sowing.replace("/", "")
    g = lambda s: _ind(info, f"geada_safrinha_semeadura_{s.replace('/', '')}_le3")
    n = int(_ind(info, f"geada_safrinha_semeadura_{ddmm}_le3")["n_anos"])
    table = [dict(semeadura=s, prob=g(s)["media"], anos=round(g(s)["media"] * g(s)["n_anos"]), n_anos=int(g(s)["n_anos"]),
                   prob_1991_2020=g(s)["media_1991_2020"]) for s in SOWINGS_2ND]
    ic = _ind(info, "inicio_chuvas_dias_desde_0109")
    diag = dict(
        inicio_chuvas_mediana=ic["mediana_ddmm"], inicio_chuvas_p80=ic["p80_ddmm"],
        calor_soja_mediana=_ind(info, "calor_soja_dias")["mediana"], calor_soja_media=_ind(info, "calor_soja_dias")["media"],
        calor_soja_p80=_ind(info, "calor_soja_dias")["p80"],
        balanco_soja=_ind(info, "balanco_p_et0_soja_mm"), balanco_safrinha=_ind(info, "balanco_p_et0_safrinha_mm"),
        balanco_trigo=_ind(info, "balanco_p_et0_trigo_mm"),
        chuva_intensa_media=_ind(info, "chuva_intensa_dias_ge50")["media"],
        chuva_intensa_mediana=_ind(info, "chuva_intensa_dias_ge50")["mediana"])
    months = {m: _ind(info, f"chuva_mensal_mm_m{m:02d}")["media"] for m in range(1, 13)}
    return dict(geada_safrinha=g(sowing)["media"], geada_trigo=_ind(info, "geada_trigo_le3")["media"],
                veranico_safrinha=_ind(info, "veranico_safrinha_ge15")["media"], n_anos=n,
                chuva_mensal=pd.Series(months), periodo="1991–2024", modo="regiao",
                fonte="NASA POWER 1991–2024, célula ~50 km (%s)" % info["celula"]["ponto_id"],
                semeadura=sowing, geada_tabela=table, diagnostico=diag,
                celula=info["celula"], municipio={k: v for k, v in info["municipio"].items() if k != "indicadores"},
                agua_anual=cell_annual_water(info["celula"]["ponto_id"]))


def get_climate(lat: float, lon: float, sowing: str = DEFAULT_SOWING) -> tuple[dict, str]:
    """Inside Paraná uses the precomputed lookup; outside, falls back to live POWER (reduced mode)."""
    info = indicators_for(lat, lon)
    if info is not None:
        return region_climate(info, sowing), "lookup pré-calculado (NASA POWER, célula ~50 km)"
    df, origin = fetch_power(lat, lon)
    return power_risks(df), origin

def enrich(rk: dict, t: dict, soil_analysis: dict | None = None) -> dict:
    """Add to the climate dict: field soil (SoilGrids or, when given, the farmer's soil analysis already validated
    by field_shift.core.service), water-balance context and the municipality PAM.
    Outside the region (reduced mode) returns rk without soil/PAM -> the water criterion uses the catalog fallback."""
    out = {**rk, "solo": None, "pam": None, "agua_ctx": None}
    cod0 = rk["municipio"]["cod_ibge"] if rk.get("modo") == "regiao" else None
    out["calendario_soja"] = soy_calendar(cod0)  # ADAPAR region of the municipality (default region without one)
    out["rend"] = yields(None if cod0 is None else str(cod0))  # no municipality PAM: mesoregion mean (with a warning)
    out["rend_local"] = rk["municipio"]["nome"] if cod0 is not None else f"{out['rend']['_regiao']} (média)"
    if rk.get("modo") != "regiao":
        return out
    s = polygon_soil(t["poly"])
    if soil_analysis:
        # the analysis replaces SoilGrids (which only supplies OM when the analysis brings neither OM nor AWC)
        s = soil_from_analysis(soil_analysis, None if s is None else s["p30"]["soc"])
    out["solo"] = s
    if s is not None:
        out["agua_ctx"] = dict(ponto_id=rk["celula"]["ponto_id"], semeadura=rk["semeadura"],
                               cad_camadas={k: s["cad_mm_cm"][k] for k in ("0-5cm", "5-15cm", "15-30cm", "30-60cm")})
    cod = rk["municipio"]["cod_ibge"]
    p = pam_yield(cod)
    out["pam"] = dict(cod_ibge=cod, nome=rk["municipio"]["nome"], dados=p) if p else None
    return out


def yields_rk(rk: dict) -> dict:
    """PAM yields for the income score: those from `enrich` (municipality) or, if missing, the Paraná mean."""
    return rk.get("rend") or yields(None)


def fmt_soil(rk: dict) -> str | None:
    return soil_text(rk["solo"]) if rk.get("solo") else None


def fmt_pam(rk: dict) -> str | None:
    return pam_text(rk["pam"]["nome"], rk["pam"]["dados"]) if rk.get("pam") else None


# Engine
# REFERENCE ESTIMATES — validate with an agronomist/CONAB/Embrapa.
# A rotation is a pair (summer crop, 2nd-window crop). The CATALOG of candidates (key = readable name of the pair) is built
# from two small catalogs: SUMMER (soybean, summer corn) and SECOND (2nd window). Attributes of SECOND:
# `renda_itens`: 2nd-window crops/practices that enter the margin (field_shift.income: PAM yield × SEAB price − CONAB cost;
# cover/fallow = − estimated cost). The summer crop always enters (`item_renda` of SUMMER).
# `agua` (0–1, relative demand) is only used as a FALLBACK outside Paraná (no precomputed climate);
# inside the region the water criterion comes from the daily water balance with the field soil (field_shift.water; see water_met).
# `ciclo_agua`: climatic cycle of the 2nd crop (used only in the per-cycle fallback, without soil).
# `kc`: seasonal mean crop coefficient (mean of the water-balance curve; FAO-56, estimate, to validate).
# `bonus_sc`: expected yield gain of the following soybean from straw/N (bags/ha) — reference estimate,
# validate with an agronomist/Embrapa. The rotation bonus is the sum of the 2nd-crop bonus and the summer-crop bonus.
# `segue_semeadura`: the 2nd crop is sown on the date chosen by the farmer (corn, sorghum, beans, millet/crotalaria); the others have
# a fixed date (wheat/oat 01/05, radish 01/04) and do not depend on the summer harvest. `janela`: accepted sowing (start, end) dd/mm.
# `milho`: it is corn (corn on corn, after summer corn, gets a pest penalty).
SECOND = {
    "milho_safrinha": dict(nome="milho safrinha", tipo="grão", dias_descobertos=60, cobertura=0.6, n_fix=0.4, pragas=0.5, agua=0.7,
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=0.85, bonus_sc=1.0, riscos=["geada_safrinha", "deficit_hidrico"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=True,
        irrigavel=True, req_maquinas=("plataforma_milho",), vende=("milho",),
        mercado_oeste_pr=dict(nivel="alto", texto="cooperativas e agroindústria de aves e suínos do Oeste do PR")),
    "milho_braquiaria": dict(nome="milho safrinha + braquiária", tipo="grão", dias_descobertos=30, cobertura=0.9, n_fix=0.4, pragas=0.65, agua=0.75,
        renda_itens=["milho_2safra", "braquiaria_consorcio"], ciclo_agua="safrinha", kc=0.90, bonus_sc=3.0,
        riscos=["geada_safrinha", "deficit_hidrico"], soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=True,
        irrigavel=True, req_maquinas=("plataforma_milho", "semeadora_consorcio"), vende=("milho",),
        mercado_oeste_pr=dict(nivel="alto", texto="milho com a mesma demanda de cooperativas e agroindústria; semente de braquiária em revendas")),
    "trigo": dict(nome="trigo", tipo="grão", dias_descobertos=70, cobertura=0.6, n_fix=0.3, pragas=0.6, agua=0.6,
        renda_itens=["trigo"], ciclo_agua="trigo", kc=0.75, bonus_sc=1.0, riscos=["geada_trigo"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=True, req_maquinas=(), vende=("trigo",),
        mercado_oeste_pr=dict(nivel="médio", texto="cooperativas e moinhos, com liquidez menor que a do milho")),
    "aveia": dict(nome="aveia (cobertura/palha)", tipo="cobertura", dias_descobertos=40, cobertura=0.8, n_fix=0.3, pragas=0.6, agua=0.3,
        renda_itens=["aveia"], ciclo_agua="trigo", kc=0.70, bonus_sc=2.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    "milheto_crotalaria": dict(nome="milheto/crotalária (cobertura)", tipo="cobertura", dias_descobertos=35, cobertura=0.85, n_fix=0.8, pragas=0.7, agua=0.3,
        renda_itens=["milheto_crotalaria"], ciclo_agua="safrinha", kc=0.65, bonus_sc=3.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    # dias_descobertos: off-season corn (60) + the difference measured from space around field 72638, single- vs double-crop
    # years (~31 bare days/yr, HLS NDVI < 0.35, 1,278 field-years; docs/validation.md §5.2). Was 150 (agronomic estimate).
    "pousio": dict(nome="pousio", tipo="pousio", dias_descobertos=90, cobertura=0.2, n_fix=0.0, pragas=0.3, agua=0.1,
        renda_itens=["pousio"], ciclo_agua=None, kc=None, bonus_sc=0.0,  # no crop: no water demand (water = 1.0)
        riscos=[], soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="não se aplica", texto="sem produção na 2ª janela")),
    "soja_safrinha": dict(nome="soja safrinha", tipo="grão", dias_descobertos=60, cobertura=0.4, n_fix=0.8, pragas=0.0, agua=0.8,
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=1.0, bonus_sc=0.0, riscos=["deficit_hidrico"],
        soja_viva_vazio=True, ano_soja_2=True, segue_semeadura=True, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="alto", texto="mesma cadeia da soja (mas a rotação é proibida pela regulação)")),
    # New crops (grain/cover crops that use the grain machinery and sales channel). Catalog values: reference estimates.
    # Grain sorghum: a grass without the corn leafhopper, drought tolerant (no water deficit in the risk); window 15/01–15/03 and ~125 d cycle
    # (FAO-56 table 11); harvested with the adapted soybean/grain header.
    "sorgo": dict(nome="sorgo", tipo="grão", dias_descobertos=55, cobertura=0.7, n_fix=0.3, pragas=0.55, agua=0.5,
        renda_itens=["sorgo"], ciclo_agua="safrinha", kc=0.77, bonus_sc=1.0, riscos=["geada_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "15/03"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("sorgo",),
        mercado_oeste_pr=dict(nivel="médio", texto="ração animal e cooperativas, com demanda menor que a do milho")),
    # 2nd-season beans ("das secas"): short cycle (~90 d), little straw and a host of white mold, which also attacks soybean (low pests,
    # no bonus); window 15/01–28/02 (estimate from ZARC/IDR-PR; frost and water deficit weigh in).
    "feijao_safrinha": dict(nome="feijão safrinha", tipo="grão", dias_descobertos=75, cobertura=0.4, n_fix=0.4, pragas=0.3, agua=0.7,
        renda_itens=["feijao_2safra"], ciclo_agua="safrinha", kc=0.84, bonus_sc=0.0, riscos=["geada_safrinha", "deficit_hidrico"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "28/02"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("feijao",),
        mercado_oeste_pr=dict(nivel="médio", texto="cerealistas e cooperativas, com preço volátil e menos compradores que milho e soja")),
    # Forage radish: nutrient cycling and suppression of weeds/nematodes, but a host of white mold; fast-decomposing
    # straw; sown on 01/04, no grain sale.
    "nabo_forrageiro": dict(nome="nabo forrageiro (cobertura)", tipo="cobertura", dias_descobertos=35, cobertura=0.65, n_fix=0.1, pragas=0.6, agua=0.3,
        renda_itens=["nabo_forrageiro"], ciclo_agua="trigo", kc=0.90, bonus_sc=2.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    # Oat + radish mix: long-lasting oat straw plus radish nutrient cycling.
    "aveia_nabo": dict(nome="aveia + nabo forrageiro (cobertura)", tipo="cobertura", dias_descobertos=35, cobertura=0.85, n_fix=0.2, pragas=0.65, agua=0.3,
        renda_itens=["aveia_nabo"], ciclo_agua="trigo", kc=0.85, bonus_sc=2.5, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
}
# `bonus_sc_faixa` (min, max) and `bonus_fonte`: range and source of the bonus (`bonus_sc` is the central value used in the score and margin).
# For now range = central value; the literature survey will replace it with the real numbers (declare them in the entry itself).
DEFAULT_BONUS_SOURCE = "estimativa de referência — validar com agrônomo/Embrapa"
for _e in SECOND.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", DEFAULT_BONUS_SOURCE)
_COVER_MARKET = dict(nivel="não se aplica", texto="sem venda de grão; semente disponível em revendas")
for _e in SECOND.values():
    _e["mercado_oeste_pr"] = _e["mercado_oeste_pr"] or _COVER_MARKET
MARKET_ESTIMATE = "estimativa a validar com cooperativas/revendas locais"

# Summer crop. `colheita`: estimated harvest date (dd/mm); a 2nd crop that follows the chosen sowing date can only be
# sown on that date or later. Soybean (early, sown in Sep): engine assumption, which already accepts the 2nd crop from 15/01.
# Summer corn (sown 15/09 to 15/10, medium cycle ~130–145 d): harvested ~3–4 weeks after soybean — estimate, validate with ZARC/Embrapa.
# `bonus_sc`: additional gain (bags/ha) in the following soybean from breaking the disease and nematode cycle plus more straw, when replacing
# summer soybean with corn (reference estimate, validate with an agronomist/Embrapa). `item_renda`: summer margin key (field_shift.income).
SUMMER = {
    "soja": dict(nome="Soja", descricao="Soja no verão: a cultura mais comum do Oeste do PR; semeadura de 01/09 a 31/12.",
                 item_renda="soja", colheita="10/01", bonus_sc=0.0, req_maquinas=(), vende=()),
    "milho_verao": dict(nome="Milho verão", descricao="Milho de 1ª safra no lugar da soja: quebra ciclo de doença e nematoide e deixa mais palhada.",
                        item_renda="milho_1safra", colheita="05/02", bonus_sc=3.0, req_maquinas=("plataforma_milho",), vende=("milho",)),
}
for _e in SUMMER.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", DEFAULT_BONUS_SOURCE)
# Pest penalty for corn on corn (summer corn + second-season corn): continuous host of the corn leafhopper (Dalbulus maidis)
# and corn stunt, plus fall armyworm and leaf diseases. Subtracted from the candidate's pest criterion (estimate, to validate).
CORN_ON_CORN_PENALTY = 0.25
CORN_ON_CORN_TEXT = (
    "Milho sobre milho (milho verão + milho safrinha): mantém hospedeiro contínuo da cigarrinha-do-milho (Dalbulus maidis) e do "
    "enfezamento, além de lagarta-do-cartucho e doenças foliares; o critério de pragas perde "
    f"{CORN_ON_CORN_PENALTY:.2f} ponto (estimativa de referência, validar com agrônomo/Embrapa). "
    "Acompanhe os alertas de cigarrinha (CigarrinhaWeb/ADAPAR; veja /v1/contexto).")


def rotation_id(summer: str, second: str) -> str:
    return f"{summer}__{second}"


def _combination(summer: str, second: str) -> dict:
    v, s = SUMMER[summer], SECOND[second]
    c = {k: val for k, val in s.items() if k != "nome"}
    on_corn = summer == "milho_verao" and s["milho"]
    c.update(
        id=rotation_id(summer, second), verao=summer, segunda=second, nome_verao=v["nome"], nome_segunda=s["nome"],
        item_renda_verao=v["item_renda"], colheita_verao=v["colheita"], bonus_verao_sc=v["bonus_sc"],
        bonus_sc=s["bonus_sc"] + v["bonus_sc"], plantio_soja="10-15",
        bonus_sc_faixa=(s["bonus_sc_faixa"][0] + v["bonus_sc_faixa"][0], s["bonus_sc_faixa"][1] + v["bonus_sc_faixa"][1]),
        bonus_fonte=" + ".join(dict.fromkeys([s["bonus_fonte"], v["bonus_fonte"]])),
        req_maquinas_verao=v["req_maquinas"], vende=tuple(dict.fromkeys(s["vende"] + v["vende"])), milho_sobre_milho=on_corn,
        pragas=max(0.0, s["pragas"] - (CORN_ON_CORN_PENALTY if on_corn else 0.0)), pragas_base=s["pragas"])
    return c


# readable name of the pair -> attributes. Soybean + X keeps the old names ("Soja → milho safrinha" etc.).
CATALOG = {f"{SUMMER[v]['nome']} → {SECOND[s]['nome']}": _combination(v, s) for v in SUMMER for s in SECOND}
NOME_DE = {c["id"]: n for n, c in CATALOG.items()}  # id "<verao>__<segunda>" -> nome
ID_DE = {n: i for i, n in NOME_DE.items()}
# old API slugs (soybean-only summer) -> new id
LEGACY = {s: rotation_id("soja", s) for s in ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio", "soja_safrinha")}

# Machine constraints: outsourcing cost when the farmer does NOT own the machine (ESTIMATE, validate with contractors).
MACHINE_COST = {
    "plataforma_milho": dict(rotulo="Colheita de milho terceirizada", custo=250.0,  # R$/ha — estimativa, validar
                             aviso="Exige plataforma de milho: alugar/terceirizar a colheita (custo extra estimado)."),
    "semeadora_consorcio": dict(rotulo="Semeadura do consórcio com braquiária terceirizada", custo=80.0,  # R$/ha — estimativa, validar
                                aviso="Exige semeadora de consórcio (ou semeadura a lanço/caixa extra): alugar/terceirizar (custo extra estimado)."),
}
DEFAULT_IRRIGATION_COST = 4.0   # R$ per mm per ha (energy + labor + depreciation) — estimate, to validate
DEFAULT_MAX_DEPTH = 6.0        # mm/day — center-pivot/sprinkler estimate, to validate
SOIL_REF_DAYS = 180    # absolute scale of bare days: 1 − days/180 (0 days = 1.0; ≥180 = 0)
DEFAULT_WEIGHTS = {"renda": 5, "solo": 3, "agua": 3, "pragas": 3, "risco": 3}


def water_balance(nome: str, risks: dict) -> dict | None:
    """Daily water balance (FAO-56 bucket, NASA POWER cell + SoilGrids soil) in the critical phase; None if unavailable."""
    ctx = risks.get("agua_ctx")
    if not ctx:
        return None
    irrig_ = risks.get("irrig")
    lam = irrig_["lamina_max_mm_dia"] if irrig_ and CATALOG[nome].get("irrigavel") else None
    return critical_phase_water(CATALOG[nome]["segunda"], ctx["ponto_id"], ctx["semeadura"], ctx["cad_camadas"], lam)


def irrigation_info(nome: str, risks: dict) -> dict | None:
    """Irrigation applied to the candidate (mean cycle depth and cost R$/ha), or None (rainfed, cover/fallow or no soil)."""
    irrig_ = risks.get("irrig")
    if not irrig_ or not CATALOG[nome].get("irrigavel"):
        return None
    b = water_balance(nome, risks)
    if b is None or not b.get("irrigado"):
        return None
    return dict(lamina_media_mm=b["lamina_media_mm"], custo_r_mm_ha=irrig_["custo_r_mm_ha"],
                custo_r_ha=b["lamina_media_mm"] * irrig_["custo_r_mm_ha"], lamina_max_mm_dia=irrig_["lamina_max_mm_dia"])


def effective_risks(nome: str, c: dict, risks: dict) -> list[str]:
    """Climate risks of the candidate; the water deficit no longer applies if it is irrigated (frost still does)."""
    irr = irrigation_info(nome, risks) is not None
    return [r for r in c["riscos"] if not (irr and r in DRY_RISKS)]


DRY_RISKS = ("deficit_hidrico", "veranico_safrinha")


def risk_probability(nome: str, r: str, risks: dict) -> float:
    """Probability (0–1) of climate risk `r` for candidate `nome`. "deficit_hidrico" is crop-, sowing- and soil-specific: share
    of the years with ETa/ETc < DEFICIT_THRESHOLD in the critical phase (FAO-56 daily balance). Without soil (no balance), it
    falls back to the cell's dry-spell frequency (≥ 15 days in Mar–Apr). Other risks are cell-level frequencies."""
    if r == "deficit_hidrico":
        b = water_balance(nome, risks)
        return b["deficit_prob"] if b is not None else float(risks["veranico_safrinha"])
    return float(risks[r])


def check_constraints(nome: str, c: dict, risks: dict) -> list[str]:
    """Eliminations by farmer constraints (`riscos['restr']`: excluidas {names}, sem_comprador {milho|trigo|sorgo|feijao|aveia_grao}).
    `c['vende']` lists the cash crops of the rotation (summer and 2nd window)."""
    r = risks.get("restr") or {}
    reasons = []
    if nome in r.get("excluidas", ()):
        reasons.append("Excluída pelo produtor.")
    for v in c["vende"]:
        if v in r.get("sem_comprador", ()):
            reasons.append(f"Sem comprador local informado pelo produtor ({v}).")
    return reasons


def extra_costs(nome: str, c: dict, risks: dict) -> list[dict]:
    """Extra costs of the candidate: outsourcing of the machines the farmer said they do NOT own + irrigation."""
    out = []
    mach = (risks.get("restr") or {}).get("maquinas", {})
    for m, suffix in [(m, "") for m in c["req_maquinas"]] + [(m, " (milho verão)") for m in c["req_maquinas_verao"]]:
        if mach.get(m) is False:
            out.append(dict(chave=f"terceirizacao_{m}", rotulo=MACHINE_COST[m]["rotulo"] + suffix, custo=MACHINE_COST[m]["custo"],
                            detalhe="estimativa de terceirização, validar com prestadores"))
    ir = irrigation_info(nome, risks)
    if ir:
        out.append(dict(chave="irrigacao", rotulo="Irrigação", custo=ir["custo_r_ha"],
                        detalhe=f"lâmina média {ir['lamina_media_mm']:.0f} mm/ano × R$ {ir['custo_r_mm_ha']:.2f}/mm/ha"))
    return out + field_state.costs(c, risks.get("estado_area"))  # given fertility: liming and P/K fertilization (otherwise nothing)


def water_met(c: dict, risks: dict, nome: str | None = None) -> tuple[float, bool]:
    """Water criterion, ABSOLUTE SCALE 0–1. In the region, with soil: mean over 34 years of ΣETa/ΣETc in the crop's
    critical phase (daily balance; changes with the sowing date). Fallow = 1.0.
    Without soil (or a candidate without a model): mean over years of min(1, P_cycle/(Kc·ET0_cycle)) of the cell.
    Outside the region (no precomputed climate): fallback 1 − attribute `agua` (from_climate=False). Returns (value, from_climate)."""
    if c["ciclo_agua"] is None:
        return 1.0, True
    b = water_balance(nome, risks) if nome else None
    if b is not None:
        return b["media"], True
    aa = risks.get("agua_anual")
    if not aa:
        return 1.0 - c["agua"], False
    d = aa[c["ciclo_agua"]]
    return float(np.mean(np.minimum(1.0, d["p"] / (c["kc"] * d["et0"])))), True


CRITERIA = {"renda": "Renda", "solo": "Saúde do solo", "agua": "Água", "pragas": "Quebra de pragas", "risco": "Risco climático"}
RISK_NAME = {"geada_safrinha": "geada no milho safrinha", "veranico_safrinha": "veranico no safrinha",
              "deficit_hidrico": "déficit hídrico na fase crítica",
              "geada_trigo": "geada no trigo (florescimento)"}


def _risk_text(r: str, risks: dict, crop: str = "milho", nome: str | None = None) -> str:
    if r == "deficit_hidrico":
        b = water_balance(nome, risks) if nome else None
        if b is not None:
            return (f"Déficit hídrico na fase crítica ({b['fase']}, semeadura em {b['semeadura']}): água no solo abaixo de "
                    f"{DEFICIT_THRESHOLD:.0%} da demanda em {b['deficit_years']} de {b['n_anos']} anos ({b['deficit_prob']:.0%}); "
                    f"balanço hídrico diário NASA POWER + solo, CAD {b['taw_mm']:.0f} mm.")
        r = "veranico_safrinha"  # no soil: fall back to the cell's dry-spell frequency
    p, n = risks[r], risks["n_anos"]
    k = round(p * n)
    source_c = ("NASA POWER 1991–2024, célula ~50 km" if risks.get("modo") == "regiao"
               else f"NASA POWER {risks['periodo']}, ponto do centróide")
    if r == "geada_safrinha":
        sow_date = risks.get("semeadura")
        if sow_date:
            approx = "" if crop == "milho" else " (janela de geada do milho usada como aproximação)"
            return f"Geada no florescimento/enchimento do {crop} semeado em {sow_date}: {k} de {n} anos ({p:.0%}), {source_c}{approx}."
        return f"Geada (≤ 3 °C) em jun–jul, enchimento do milho safrinha: {k} de {n} anos ({p:.0%}), {source_c}."
    if r == "geada_trigo":
        return f"Geada (≤ 3 °C) no florescimento do trigo (15/08–30/09): {k} de {n} anos ({p:.0%}), {source_c}."
    return f"Veranico ≥ 15 dias em mar–abr: {k} de {n} anos ({p:.0%}), {source_c}."
ZARC_WARNING = "Fora do ZARC pode comprometer crédito/seguro (não elimina a candidata)."


def _dm(ddmm: str) -> tuple[int, int]:
    d, m = map(int, ddmm.split("/"))
    return m, d


def check_rules(c: dict, risks: dict | None = None) -> list[str]:
    """Hard rules: return the list of elimination reasons (empty = valid). `riscos['semeadura']` (dd/mm of the 2nd crop)
    enables the calendar rules: summer harvest and sowing window of the 2nd crop."""
    reasons = []
    sow_date = (risks or {}).get("semeadura")
    cs = (risks or {}).get("calendario_soja") or soy_calendar(None)  # ADAPAR window of the area's municipality
    sow = f"{cs['semeadura'][0]}–{cs['semeadura'][1]}"
    if c["ano_soja_2"]:
        if c["verao"] == "soja":
            reasons.append("Soja sobre soja no mesmo ano agrícola é proibida (Portaria SDA/MAPA 1.124/2024).")
        reasons.append(f"Soja na 2ª janela{f' (semeadura em {sow_date})' if sow_date else ''} fica fora da janela legal de semeadura da soja ({sow}, {cs['nome'].split(' (')[0]}).")
    if sow_date and c["segue_semeadura"] and not c["ano_soja_2"]:
        # summer harvest: the farmer's (stage/expected harvest) if it is the same summer crop; otherwise the catalog's
        prod = (risks or {}).get("colheita_produtor")
        if prod and prod["verao"] == c["verao"]:
            harv, origin = prod["colheita"], "informada pelo produtor"
        else:
            harv, origin = c["colheita_verao"], "estimativa, validar"
        if cal.key(cal.add_days(harv, cal.PREP_DAYS_2ND)) > cal.key(SOWINGS_2ND[-1]):
            reasons.append(f"Colheita tarde demais para a safrinha: a colheita de {c['nome_verao'].lower()} é estimada em ~{harv} "
                           f"({origin}) e a última semeadura da 2ª janela considerada é {SOWINGS_2ND[-1]}.")
        elif cal.key(sow_date) < cal.key(cal.add_days(harv, cal.PREP_DAYS_2ND)):
            reasons.append(f"A colheita de {c['nome_verao'].lower()} é estimada em ~{harv} ({origin}): "
                           f"a semeadura da 2ª cultura em {sow_date} cairia antes dela.")
        if c["janela"] and not (_dm(c["janela"][0]) <= _dm(sow_date) <= _dm(c["janela"][1])):
            where = "no Oeste do PR" if in_oeste(risks or {}) else "de referência (Oeste do PR; confira o ZARC do município)"
            reasons.append(f"Semeadura em {sow_date} fora da janela de {c['nome_segunda']} {where} "
                           f"({c['janela'][0]}–{c['janela'][1]}; estimativa de referência com base no ZARC/IDR-PR, validar).")
    if c["soja_viva_vazio"]:
        reasons.append(f"Há soja viva durante o vazio sanitário da soja ({cs['vazio'][0]}–{cs['vazio'][1]}, {cs['nome'].split(' (')[0]} do PR).")
    mes, day = map(int, c["plantio_soja"].split("-"))
    if not in_window(f"{day:02d}/{mes:02d}", *cs["semeadura"]):
        reasons.append(f"Semeadura de soja em {day:02d}/{mes:02d} fora da janela {sow} ({cs['nome'].split(' (')[0]}).")
    return reasons


class NoCandidates(ValueError):
    """All evaluated rotations were eliminated (hard rules + farmer constraints). `eliminated_list`: {name: reasons}."""

    def __init__(self, msg: str, eliminated_list: dict | None = None):
        super().__init__(msg)
        self.eliminated_list = eliminated_list or {}


def income_score(incremental: float, scale: float) -> float:
    """Income criterion (0–1): 0.5 at zero incremental margin, ~0.88 at +S, ~0.12 at −S, strictly increasing (no ties)."""
    return float(0.5 + 0.5 * np.tanh(incremental / scale))


# Validation of the climate-risk criterion against PAM off-season corn failures (docs/validation.md §6.1): calibrated on average,
# no out-of-sample skill to tell which season or which municipality fails.
RISK_CONFIDENCE_CORN = ("baixa", "Calibrado na média (perda prevista 24 % contra 23 % de quebras observadas na PAM do Oeste, "
                        "2003–2025), mas não indica qual safra vai falhar nem diferencia municípios vizinhos (validação fora da "
                        "amostra, docs/validation.md §6.1).")
RISK_CONFIDENCE_OTHER = ("não validada", "Frequência histórica do evento no clima NASA POWER; não comparada com quebras observadas.")
CATALOG_ESTIMATES = ("solo", "pragas")


def uncertainty(c: dict, m: dict, income: float, score: float, w_income: float, p_risk: float, risks: list[str]) -> dict:
    """Uncertainty of one candidate's result: income range (realized seasons of the track record, or the bad year of the
    current-price estimate), the score range it implies (other criteria fixed), the score per past season, the confidence of the
    climate-risk criterion and which criteria are catalog estimates."""
    inc, s, ps = m["incremental"], m["escala_S"], m["preco_soja"]
    by_season = None
    if m.get("base_renda") == "historico" and m.get("historico_safras"):
        incs = {y: inc + (v - m["historico_sc_soja_ha"]) * ps for y, v in m["historico_safras"].items()}
        by_season = {y: score + w_income * (income_score(x, s) - income) for y, x in incs.items()}
        lo, hi, origin = min(incs.values()), max(incs.values()), "historico"
    else:
        second = [i for i in m["itens"] if i["chave"] in c["renda_itens"] and not i.get("extra")]
        sold = [i for i in second if i.get("sc_ha") is not None and i.get("margem_ano_ruim") is not None]
        if sold:
            lo, hi, origin = inc - sum(i["margem"] - i["margem_ano_ruim"] for i in sold), None, "ano_ruim_p20"
        else:
            lo, hi, origin = inc, inc, "custo_fixo"
    score_lo = score + w_income * (income_score(lo, s) - income)
    score_hi = None if hi is None else score + w_income * (income_score(hi, s) - income)
    conf = RISK_CONFIDENCE_CORN if c["segunda"] in ("milho_safrinha", "milho_braquiaria") else RISK_CONFIDENCE_OTHER
    return dict(renda=dict(incremental_r_ha=inc, faixa_r_ha=[lo, hi], origem=origin),
                nota_faixa=[score_lo, score_hi], nota_por_safra=by_season,
                risco_climatico=(dict(probabilidade=p_risk, eventos=[RISK_NAME.get(r, r) for r in risks], confianca=conf[0],
                                      texto=conf[1]) if risks else None),
                criterios_estimados=list(CATALOG_ESTIMATES))


def score_rotation(pesos: dict[str, float], risks: dict, adjustments: dict | None = None, names: list[str] | None = None) -> dict:
    """Return a dict with the table of valid ones (DataFrame), eliminated ones and contributions. `names`: only evaluate these candidates
    (CATALOG names); None = all. All criteria on an ABSOLUTE 0–1 SCALE (no min-max across candidates), higher = better."""
    valid_items, eliminated_list = {}, {}
    for nome in (names if names is not None else CATALOG):
        c = CATALOG[nome]
        m = check_rules(c, risks) + check_constraints(nome, c, risks)
        (eliminated_list if m else valid_items)[nome] = m or c
    if not valid_items:
        raise NoCandidates("As restrições informadas eliminam todas as rotações.", eliminated_list)
    # Risk: 1 - P(any risk); with several independent risks, criterion = Π(1 - pᵢ). No risk = 1.0.
    # Irrigated candidate: the dry spell does not count (frost still does).
    rs_ef = {n: effective_risks(n, c, risks) for n, c in valid_items.items()}
    abs_risk = {n: float(np.prod([1 - risk_probability(n, r, risks) for r in rs_ef[n]])) if rs_ef[n] else 1.0 for n in valid_items}
    # Soil: mean of cover, N fixation and (1 - bare days/180), all absolute 0–1.
    soil = {n: (c["cobertura"] + c["n_fix"] + max(0.0, 1 - c["dias_descobertos"] / SOIL_REF_DAYS)) / 3
            for n, c in valid_items.items()}
    # Income from the INCREMENTAL margin over the municipality's summer soybean: incremental = rotation margin − soybean margin
    # = (summer margin − soybean margin) + 2nd-crop margin (sold: PAM × price − cost; cover: − establishment
    # cost; fallow: − management cost) + bonus in the following soybean (bonus_sc × soybean price). With summer soybean the first
    # term is zero (original formula); summer corn enters with 1st-season corn PAM × corn price − CONAB summer-corn cost.
    # Income score: 0.5 + 0.5·tanh(incremental / S), S = INCOME_SCALE (fixed statewide, §7.5). Near zero it has the
    # same slope as the old clip(0.5 + incremental / (2·S), 0, 1), but it never saturates, so two good options are never tied
    # at 1.0 (docs/validation.md §6.3). For grain second crops with a municipal track record, the second-crop margin in
    # `incremental` is the 5-season realized margin (income.history.apply_to_income; validated out of sample, §6.2).
    extras = {n: extra_costs(n, c, risks) for n, c in valid_items.items()}
    margins = compute_margins({n: c for n, c in valid_items.items()}, yields_rk(risks), adjustments, extras)
    margins = income_history.apply_to_income(margins, valid_items, (risks.get("municipio") or {}).get("cod_ibge"))
    income = {n: income_score(m["incremental"], m["escala_S"]) for n, m in margins.items()}
    income_warning = (None if any(m["total"] > 0 for m in margins.values())
                   else "Nenhuma rotação válida tem margem total positiva com os preços e custos usados (informativo).")
    # Field state informed by the farmer (problemas_area, fertility, organic matter): additive deltas on soil and pests, applied
    # with field_state.soft_add (slope 1 at zero, never saturates at 0 or 1, so two improved options never tie at the bound).
    # Without that input, `riscos["estado_area"]` does not exist and nothing changes.
    pests = {n: c["pragas"] for n, c in valid_items.items()}
    if risks.get("estado_area"):
        aj_ea = {n: field_state.adjustment(c, risks["estado_area"]) for n, c in valid_items.items()}
        soil = {n: field_state.soft_add(soil[n], aj_ea[n]["solo"]) for n in valid_items}
        pests = {n: field_state.soft_add(pests[n], aj_ea[n]["pragas"]) for n in valid_items}
        best = max(((n, float(m["incremental"])) for n, m in margins.items()), key=lambda x: x[1], default=None)
        for n, m in margins.items():
            rec = field_state.recovery(valid_items[n], risks["estado_area"], m, best)
            if rec is not None:
                m["recuperacao"] = rec
    crit = {
        "renda": income,
        "solo": soil,
        "agua": {n: water_met(c, risks, n)[0] for n, c in valid_items.items()},
        "pragas": pests,
        "risco": abs_risk,
    }
    total = sum(pesos.values()) or 1
    w = {k: (pesos[k] / total if sum(pesos.values()) else 0.2) for k in crit}
    lines = []
    for n in valid_items:
        contrib = {k: w[k] * crit[k][n] for k in crit}
        lines.append(dict(candidata=n, nota=sum(contrib.values()),
                           **{f"{k}": crit[k][n] for k in crit}, contrib=contrib))
    tab = pd.DataFrame(lines).sort_values("nota", ascending=False, kind="stable").reset_index(drop=True)
    for n, m in margins.items():
        m["incerteza"] = uncertainty(valid_items[n], m, income[n], float(tab.loc[tab["candidata"] == n, "nota"].iloc[0]),
                                     w["renda"], 1 - abs_risk[n], rs_ef[n])
    return dict(tabela=tab, eliminadas=eliminated_list, margens=margins, aviso_renda=income_warning, pesos_norm=w, riscos=risks)

# Card texts
def _r(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def in_oeste(risks: dict) -> bool:
    """Is the field's municipality in the Oeste mesoregion (where catalog windows and market texts were written and the engine
    was validated)? Without a municipality: False."""
    return (risks.get("rend") or {}).get("_regiao") == "Oeste do PR" and bool(risks.get("municipio"))


def local_rend(risks: dict, key: str) -> str:
    """Origin of a crop's PAM yield: the municipality or, if it lacks enough PAM, the mean of its mesoregion."""
    rend = risks.get("rend") or {}
    region = rend.get("_regiao") or "Paraná"
    if key in rend.get("_regionais", ()):
        return Msg("{0} (média, o município não tem PAM recente)", (rend.get(key) or {}).get("regiao") or region)
    return risks.get("rend_local") or region


def fmt_margin(m: dict, risks: dict) -> list[str]:
    """Breakdown of the rotation margin (card evidence lines)."""
    lines = []
    for i in m["itens"]:
        local = local_rend(risks, i["chave"])
        if i.get("extra"):
            if i["custo"] >= 0:
                lines.append(Msg("{0}: custo extra R$ {1}/ha ({2}) = {3}.", i["rotulo"], _r(i["custo"]), i["detalhe"], _rs(i["margem"])))
            else:
                lines.append(Msg("{0}: economia R$ {1}/ha ({2}) = {3}.", i["rotulo"], _r(-i["custo"]), i["detalhe"], _rs(i["margem"])))
        elif i["sc_ha"] is not None and i.get("prod_usuario"):
            rz = i.get("razao_p20")
            bad = (f"ano ruim: rendimento próprio × p20/média da PAM ({rz:.2f}) = {i['sc_ha_ruim']:.0f} sc/ha → R$ {_r(i['margem_ano_ruim'])}/ha"
                    if i["sc_ha_ruim"] is not None else "sem ano ruim (PAM sem série)")
            lines.append(f"{i['rotulo']}: {i['sc_ha']:.0f} sc/ha (informado pelo produtor; PAM {local}: {i['sc_ha_pam']:.0f} sc/ha) × "
                          f"R$ {i['preco']:.2f}/sc ({price_source(i)}) − custo R$ {_r(i['custo'])}/ha ({cost_source(i, m['linha_custo'])}) "
                          f"= R$ {_r(i['margem'])}/ha ({bad}).")
        elif i["sc_ha"] is not None:
            orig = (f"tendência da PAM {local} {i['anos']} projetada para a próxima safra; média {i['sc_ha_media']:.0f} sc/ha"
                    if i.get("metodo_rend") == "tendência" and i.get("sc_ha_media") is not None else f"PAM {local} {i['anos']}")
            if i.get("sc_ha_ruim") is not None and i.get("margem_ano_ruim") is not None and i.get("cv") is not None:
                lines.append(f"{i['rotulo']}: {i['sc_ha']:.0f} sc/ha ({orig}) × R$ {i['preco']:.2f}/sc ({price_source(i)}) − custo "
                              f"R$ {_r(i['custo'])}/ha ({cost_source(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha "
                              f"(CV do rendimento {i['cv']:.0%}; ano ruim, p20 da mesma janela de 10 anos = {i['sc_ha_ruim']:.0f} sc/ha → "
                              f"R$ {_r(i['margem_ano_ruim'])}/ha).")
            else:  # short PAM series (< 4 years): no variability or bad year to show
                lines.append(f"{i['rotulo']}: {i['sc_ha']:.0f} sc/ha ({orig}) × R$ {i['preco']:.2f}/sc ({price_source(i)}) − custo "
                              f"R$ {_r(i['custo'])}/ha ({cost_source(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha "
                              f"(série da PAM curta demais para estimar a variação e o ano ruim).")
        else:
            lines.append(f"{i['rotulo']}: sem venda, custo de implantação R$ {_r(i['custo'])}/ha ({cost_source(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha.")
    bonus_detail = (f" ({m['bonus_verao_sc']:g} sc/ha do milho verão no lugar da soja + {m['bonus_sc'] - m['bonus_verao_sc']:g} da 2ª cultura)"
                     if m["bonus_verao_sc"] else "")
    lines.append(f"Bônus na soja seguinte: {m['bonus_sc']:g} sc/ha × R$ {m['preco_soja']:.2f}/sc = R$ {_r(m['bonus'])}/ha{bonus_detail} "
                  f"(palhada/N e quebra de ciclo de doença, estimativa de referência).")
    if m.get("base_renda") == "historico":
        head = Msg("Total da rotação: R$ {0}/ha/ano; incremental da 2ª safra (sem a soja, com o bônus) para a nota: R$ {1}/ha, "
                   "com a 2ª safra pela média realizada das últimas safras no município ({2} sc de soja/ha × R$ {3}/sc; "
                   "a preço atual seria R$ {4}/ha), na escala S = R$ {5}/ha (a mesma no Paraná todo: margem mediana da soja no Oeste do PR)",
                   _r(m["total"]), _r(m["incremental"]), str(round(m["historico_sc_soja_ha"], 1)).replace(".", ","),
                   f"{m['preco_soja']:.2f}", _r(m["incremental_preco_atual"]), _r(m["escala_S"]))
    else:
        head = Msg("Total da rotação: R$ {0}/ha/ano; incremental da 2ª safra (sem a soja, com o bônus): R$ {1}/ha, "
                   "na escala S = R$ {2}/ha (a mesma no Paraná todo: margem mediana da soja no Oeste do PR)",
                   _r(m["total"]), _r(m["incremental"]), _r(m["escala_S"]))
    if m["total_ano_ruim"] is not None:
        lines.append(Msg("{0}; em ano ruim (rendimento p20): R$ {1}/ha/ano.", head, _r(m["total_ano_ruim"])))
    else:
        lines.append(Msg("{0}.", head))
    return lines


def _rs(x: float) -> str:
    return f"R$ {_r(x)}/ha" if x >= -0.5 else f"−R$ {_r(-x)}/ha"


def _c2(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _short_name(n: str) -> str:
    return n.replace("Soja → ", "")


def _criterion_text(k: str, alt: str, cur: str, res: dict, d: float) -> str:
    """Short sentence about criterion k of alternative `alt` against the current `cur` (d = Δcriterion, signed)."""
    t, m = res["tabela"].set_index("candidata"), res["margens"]
    ca, cb = t.loc[alt], t.loc[cur]
    wins = d > 0
    if k == "renda":
        a, b = m[alt]["incremental"], m[cur]["incremental"]
        if wins:
            if b > 0:
                return Msg("soma {0} contra {1} na 2ª safra (+{2})", _rs(a), _rs(b), f"{(a - b) / abs(b):.0%}")
            return Msg("soma {0} contra {1} na 2ª safra", _rs(a), _rs(b))
        return Msg("abre mão de {0} na 2ª safra ({1} contra {2})", _rs(b - a), _rs(a), _rs(b))
    if k == "solo":
        da, db = CATALOG[alt]["dias_descobertos"], CATALOG[cur]["dias_descobertos"]
        return Msg("melhora a saúde do solo ({0} contra {1}; ~{2} dias de solo descoberto contra {3})" if wins else
                   "piora a saúde do solo ({0} contra {1}; ~{2} dias de solo descoberto contra {3})",
                   _c2(ca["solo"]), _c2(cb["solo"]), str(da), str(db))
    if k == "agua":
        return Msg("atende melhor a demanda de água ({0} contra {1})" if wins else "atende pior a demanda de água ({0} contra {1})",
                   _c2(ca["agua"]), _c2(cb["agua"]))
    if k == "pragas":
        return Msg("quebra melhor o ciclo de pragas ({0} contra {1})" if wins else "quebra menos o ciclo de pragas ({0} contra {1})",
                   _c2(ca["pragas"]), _c2(cb["pragas"]))
    pa, pb = 1 - ca["risco"], 1 - cb["risco"]
    return Msg("reduz o risco climático (algum evento adverso em {0} dos anos contra {1})" if wins else
               "aumenta o risco climático (algum evento adverso em {0} dos anos contra {1})", f"{pa:.0%}", f"{pb:.0%}")


def why_compared(res: dict, nome: str, current: str | None) -> str | None:
    """'Why' text of `name` compared with the current rotation (None if the current one is not among the valid ones)."""
    tab = res["tabela"]
    names = list(tab["candidata"])
    if current is None or current not in names or nome not in names:
        return None
    if nome == current:
        pos, n = names.index(current) + 1, len(names)
        if pos == 1:
            o = tab.iloc[1]
            return Msg("É a rotação atual; ficou em 1º lugar entre {0} opções válidas. A 2ª melhor ({1}) tem nota {2}.",
                       str(n), _short_name(o["candidata"]), _c2(o["nota"]))
        b = tab.iloc[0]
        return Msg("É a rotação atual; ficou em {0}º lugar entre {1} opções válidas. A melhor alternativa ({2}) tem nota {3}.",
                   str(pos), str(n), _short_name(b["candidata"]), _c2(b["nota"]))
    t = tab.set_index("candidata")
    w = res["pesos_norm"]
    diff_ = {k: w[k] * (t.loc[nome, k] - t.loc[current, k]) for k in CRITERIA}
    tops = [k for k, v in sorted(diff_.items(), key=lambda kv: -abs(kv[1]))[:3] if abs(v) >= 0.005]
    phrases = [_criterion_text(k, nome, current, res, diff_[k]) for k in tops]
    if not phrases:
        txt = Msg("Em relação à atual ({0}): desempenho praticamente igual nos cinco critérios.", _short_name(current))
    else:
        txt = Msg("Em relação à atual ({0}): {1}.", _short_name(current), Join(phrases, ", ", last=" e "))
    if "risco" not in tops and 1 - t.loc[nome, "risco"] > 0.005:
        txt = Msg("{0} Risco climático igual (algum evento adverso em {1} dos anos).", txt, f"{1 - t.loc[nome, 'risco']:.0%}")
    return txt


def build_card(line: pd.Series, current: bool, risks: dict, ndvi_bare_soil_days: float, margin: dict | None = None,
                why_cmp: str | None = None) -> dict:
    """`why_cmp`: text from `why_compared` (comparison with the current rotation); if None, only the largest contributions."""
    c = CATALOG[line["candidata"]]
    top = sorted(line["contrib"].items(), key=lambda kv: -kv[1])[:2]
    contribs = Msg("Maiores contribuições para a nota: {0}.", Join([Msg("{0} ({1})", CRITERIA[k], _c2(v)) for k, v in top], " e "))
    why = Join([why_cmp, contribs], " ") if why_cmp else contribs
    ev = [f"Dias de solo descoberto/ano (catálogo): ~{c['dias_descobertos']} dias."]
    if current and not np.isnan(ndvi_bare_soil_days):
        ev.append(f"NDVI observado (NASA HLS): ~{ndvi_bare_soil_days:.0f} dias/ano com NDVI<{SOIL_THRESHOLD}.")
    hist = None
    if margin is not None:
        ev += fmt_margin(margin, risks)
        # 5-season track record of the second crop (in the income score unless the farmer gave own data; docs/validation.md §6.2)
        hist = income_history.track_record((risks.get("municipio") or {}).get("cod_ibge"), c["segunda"])
        if (h_txt := income_history.text(hist, in_score=margin.get("base_renda") == "historico")):
            ev.append(h_txt)
    ag, from_climate = water_met(c, risks, line["candidata"])
    bal = water_balance(line["candidata"], risks)
    soil_source = ("análise de solo do produtor" if (risks.get("solo") or {}).get("fonte") == "análise de solo do produtor"
                  else "solo SoilGrids")
    ir = irrigation_info(line["candidata"], risks)
    if c["ciclo_agua"] is None:
        ev.append("Água: sem cultura, sem demanda hídrica (nota 1,00); o custo do pousio aparece em solo.")
    elif bal is not None:
        ev.append(f"Água: na fase crítica ({bal['fase']}, semeadura em {bal['semeadura']}), a água no solo atendeu em média "
                  f"{bal['media']:.0%} da demanda; em {bal['n_abaixo']} de {bal['n_anos']} anos ficou abaixo de 70% "
                  f"(balanço diário NASA POWER + {soil_source}{', irrigado' if bal.get('irrigado') else ''}, CAD {bal['taw_mm']:.0f} mm).")
    elif from_climate:
        nome_c = c["nome_segunda"]
        ev.append(f"Água: chuva cobre em média {ag:.0%} da demanda ({nome_c}, Kc {c['kc']:.2f}; "
                  f"NASA POWER {risks['periodo']}, FAO-56).")
    else:
        ev.append(f"Água: estimativa fixa do catálogo ({ag:.0%}); sem clima pré-calculado fora do Paraná.")
    if ir:
        ev.append(f"Irrigado: lâmina média {ir['lamina_media_mm']:.0f} mm/ano, custo R$ {_r(ir['custo_r_ha'])}/ha "
                  f"(R$ {ir['custo_r_mm_ha']:.2f}/mm/ha, lâmina máx. {ir['lamina_max_mm_dia']:g} mm/dia; o ganho de produtividade "
                  f"da irrigação não é modelado, o rendimento esperado não muda).")
    rs_ef = effective_risks(line["candidata"], c, risks)
    for r in rs_ef:
        ev.append(_risk_text(r, risks, "milho" if c["milho"] else c["nome_segunda"], line["candidata"]))
    if ir and len(rs_ef) < len(c["riscos"]):
        ev.append("Déficit hídrico não conta no risco: a candidata é irrigada (a geada continua).")
    if not c["riscos"]:
        ev.append("Sem risco climático da 2ª safra considerado (espécie de cobertura/pousio).")
    ben = []
    if c["cobertura"] >= 0.8:
        ben.append("Boa cobertura/palha: protege o solo e reduz erosão.")
    if c["n_fix"] >= 0.7:
        ben.append("Fixação de nitrogênio relevante para a próxima soja.")
    if c["pragas"] >= 0.6:
        ben.append("Ajuda a quebrar ciclo de pragas e doenças.")
    if c["bonus_sc"] >= 2:
        ben.append(f"Palhada/N elevam a soja seguinte (~+{c['bonus_sc']:g} sc/ha, estimativa).")
    if c["bonus_verao_sc"]:
        ben.append(f"{c['nome_verao']} no lugar da soja de verão quebra ciclo de doença e nematoide e deixa mais palhada "
                   f"(~+{c['bonus_verao_sc']:g} sc/ha na soja seguinte, estimativa a validar com agrônomo/Embrapa).")
    if margin is not None and margin["total"] >= 2000:
        ben.append(f"Margem da rotação alta (~R$ {_r(margin['total'])}/ha/ano).")
    if c["ciclo_agua"] is None or water_met(c, risks, line["candidata"])[0] >= 0.9:
        ben.append("Chuva atende praticamente toda a demanda hídrica.")
    solo_p = risks.get("solo") or {}
    if solo_p.get("fonte") == "análise de solo do produtor":
        lacuna_cad = ("CAD vinda da análise do produtor (informada ou por Saxton & Rawls com a análise), "
                      "tomada como representativa do perfil de 0–60 cm.")
    else:
        lacuna_cad = "CAD por pedotransferência (Saxton & Rawls), pode errar em latossolos tropicais."
    ea = field_state.card(c, risks.get("estado_area"))
    ev += ea["evidencias"]
    if margin is not None and margin.get("recuperacao"):
        ev.append(margin["recuperacao"]["texto"])
    lacunas = ([] if risks.get("solo") else ["Textura/CAD do solo (SoilGrids) não considerada (talhão fora do Paraná)."]) + [
               lacuna_cad,
               "Umidade do solo (SMAP) e chuva satelital (GPM) não usadas.",
               *([f"{c['nome_verao']} no verão: risco climático e balanço hídrico do verão não modelados (só a 2ª janela entra nesses critérios)."]
                 if c["verao"] != "soja" else []),
               "Renda: preço = média PR dos últimos 12 meses (SEAB/DERAL); custo CONAB de Londrina/Ponta Grossa (não do Oeste do PR); "
               "custo de cobertura/pousio, bônus da palhada/N e Kc são estimativas de referência.", *ea["lacunas"]]
    # ZARC: informative only (never changes the score). Without the table, keep the generic warning.
    mun = risks.get("municipio") or {}
    zs = zarc.rotation_status(c, mun.get("cod_ibge"), risks.get("semeadura"), WHEAT_SOWING)
    z_warning = zarc.warning_text(zs, mun.get("nome", "município"))
    z_ev = zarc.evidence_text(zs, mun.get("nome", "município"))
    if z_ev:
        ev.append(z_ev)
    review = [*([] if zs is not None else [ZARC_WARNING]), "Confirmar com o agrônomo calendário, cultivar e janela do ZARC.", *ea["revisar"]]
    if c["milho_sobre_milho"]:
        review.append(CORN_ON_CORN_TEXT)
        ev.append(f"Pragas: milho sobre milho, nota de catálogo {c['pragas_base']:.2f} − penalidade {CORN_ON_CORN_PENALTY:.2f} "
                  f"= {c['pragas']:.2f} (cigarrinha-do-milho/enfezamento; estimativa de referência).")
    if "geada_safrinha" in c["riscos"] and risks["geada_safrinha"] >= 0.2:
        if risks.get("semeadura"):
            review.append(f"Geada (≤ 3 °C) no safrinha em {risks['geada_safrinha']:.0%} dos anos com semeadura em {risks['semeadura']}: "
                          "avaliar data de semeadura/híbrido.")
        else:
            review.append(f"Geada (≤ 3 °C) no safrinha em {risks['geada_safrinha']:.0%} dos anos: avaliar data de semeadura/híbrido.")
    if "deficit_hidrico" in rs_ef and (p_def := risk_probability(line["candidata"], "deficit_hidrico", risks)) >= 0.2:
        review.append(f"Déficit hídrico na fase crítica em {p_def:.0%} dos anos: avaliar data de semeadura/cultivar.")
    if "geada_trigo" in c["riscos"] and risks["geada_trigo"] >= 0.2:
        review.append(f"Geada no florescimento do trigo em {risks['geada_trigo']:.0%} dos anos.")
    if c["dias_descobertos"] >= 100:
        review.append("Muitos dias de solo exposto: risco de erosão e plantas daninhas.")
    mach = (risks.get("restr") or {}).get("maquinas", {})
    warnings = list(dict.fromkeys(MACHINE_COST[m]["aviso"] for m in c["req_maquinas"] + c["req_maquinas_verao"] if mach.get(m) is False))
    if z_warning:
        warnings.insert(0, z_warning)
    mer = c["mercado_oeste_pr"]
    mercado = dict(nivel=mer["nivel"], texto=mer["texto"], estimativa=MARKET_ESTIMATE)
    if in_oeste(risks):
        ev.append(f"Mercado no Oeste do PR: {mer['nivel']}; {mer['texto']} ({MARKET_ESTIMATE}).")
    else:
        ev.append(f"Mercado (referência do Oeste do PR, confirme na sua região): {mer['nivel']}; {mer['texto']} ({MARKET_ESTIMATE}).")
    return dict(por_que=why, evidencia=ev, beneficios=ben or ["Sem benefício marcante nos critérios avaliados."],
                lacunas=lacunas, revisar=review, avisos=warnings, mercado=mercado, irrigacao=ir, zarc=zs, historico=hist)


def fmt_diagnosis(d: dict) -> list[str]:
    """Climate diagnosis text lines (display only; not part of the score)."""
    b = lambda x: f"mediana {x['mediana']:.0f} mm, p20 {x['p20']:.0f} mm"
    return [
        f"Início das chuvas (a partir de 01/09): mediana {d['inicio_chuvas_mediana']}, p80 {d['inicio_chuvas_p80']} (1 em 5 anos atrasa até lá).",
        f"Calor na soja: mediana {d['calor_soja_mediana']:.1f} dias/ciclo acima do limiar (média {d['calor_soja_media']:.1f}; p80 {d['calor_soja_p80']:.1f}).",
        f"Balanço P − ET0 por ciclo — soja: {b(d['balanco_soja'])}; safrinha: {b(d['balanco_safrinha'])}; trigo: {b(d['balanco_trigo'])}.",
        f"Chuva intensa (≥ 50 mm/dia): média {d['chuva_intensa_media']:.1f} dias/ano (mediana {d['chuva_intensa_mediana']:.0f}).",
    ]


if __name__ == "__main__":
    import sys
    sow_date = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOWING
    t = load_field()
    dec = "no data" if t["declividade"] is None else f"{t['declividade']:.1f}% (p90 {t['declividade_p90']:.1f}%, {t['classe_embrapa']})"
    alt = "no data" if t["altitude"] is None else f"{t['altitude']:.0f} m"
    print(f"Field {t['id']}: {t['area_ha']:.1f} ha  lat={t['lat']:.5f} lon={t['lon']:.5f} slope={dec}  altitude={alt}")
    print("MapBiomas history:", t["historico"])
    nd = load_ndvi()
    pk = peaks_by_crop_year(nd)
    print("NDVI peaks per crop year:", pk, "→", detect_rotation(pk))
    print(f"Days/year with NDVI<{SOIL_THRESHOLD}: {bare_soil_days_by_year(nd):.0f}; ranges: {len(soil_ranges(nd))}")
    rk, origin = get_climate(t["lat"], t["lon"], sow_date)
    rk = enrich(rk, t)
    print(f"Climate [{rk['modo']}]: {origin} · {rk['fonte']} · second-crop sowing {rk['semeadura']}")
    if rk["modo"] == "reduzido":
        print("WARNING: reduced mode (outside Paraná; live POWER, no diagnosis nor per-date table).")
    else:
        m = rk["municipio"]
        print(f"Cell {rk['celula']['ponto_id']} (elev {rk['celula']['elev']:.0f} m); municipality (context): {m['nome']} ({m['cod_ibge']})")
        print("Frost ≤3 °C in the second crop by sowing date:",
              {r["semeadura"]: f"{r['prob']:.2f} ({r['anos']}/{r['n_anos']})" for r in rk["geada_tabela"]})
        for line in fmt_diagnosis(rk["diagnostico"]):
            print("  -", line)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rk.items()
           if k in ("geada_safrinha", "geada_trigo", "veranico_safrinha", "n_anos", "periodo")})
    print("Mean monthly rain (mm):", rk["chuva_mensal"].round(0).to_dict())
    if rk.get("solo"):
        print("Soil:", fmt_soil(rk))
        print("PAM:", fmt_pam(rk))
    print("Water met (critical phase, daily balance):", {n.replace("Soja → ", ""): round(water_met(c, rk, n)[0], 3) for n, c in CATALOG.items()})
    for n in CATALOG:
        b = water_balance(n, rk)
        if b:
            print(f"  {n}: {b['fase']} ({b['semeadura']}) mean {b['media']:.3f}, {b['n_abaixo']}/{b['n_anos']} years <0.7, TAW {b['taw_mm']:.0f} mm")
    adjustments = {"linha_custo": sys.argv[2]} if len(sys.argv) > 2 else None
    res = score_rotation(DEFAULT_WEIGHTS, rk, adjustments)
    print(res["tabela"].drop(columns="contrib").round(2).to_string())
    if res["aviso_renda"]:
        print("WARNING:", res["aviso_renda"])
    print("Yield:", rk["rend"]["_origem"])
    for n, m in res["margens"].items():
        print(f"\n{n}:")
        for l in fmt_margin(m, rk):
            print("  -", l)
    for n, m in res["eliminadas"].items():
        print("ELIMINATED:", n, m)
