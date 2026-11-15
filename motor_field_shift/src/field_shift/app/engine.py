"""Motor do MVP Field Shift: dados (talhão, NDVI, NASA POWER) + regras duras + pontuação.

Tudo aqui é lógica pura (sem Streamlit), para poder testar:  uv run python src/field_shift/app/engine.py
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
from field_shift.income import history as income_history
from field_shift.crop_calendar import PREP_DAYS_2ND, DEFAULT_SOWING, SOWINGS_2ND
from field_shift.climate.lookup import indicators_for
from field_shift.pam import productivity as pam_yield
from field_shift.pam.productivity import text as pam_text
from field_shift.income import INCOME_SCALE_MIN, compute_margins, cost_source, price_source, yields
from field_shift.region import inside_region, relief
from field_shift.region.soybean_free_period import soy_calendar, in_window
from field_shift.soil import soil as polygon_soil
from field_shift.soil.soil import soil_from_analysis, text as soil_text

ROOT = Path(__file__).resolve().parents[3]
FTW = ROOT / "data/processed/ftw"
FIELD_ID = "72638"  # a coluna `id` do parquet é string
SOIL_THRESHOLD = 0.35  # NDVI abaixo disto = solo descoberto / baixa cobertura

# --------------------------------------------------------------------------- 1. Local
@lru_cache(maxsize=1)
def fields_gdf() -> gpd.GeoDataFrame:
    """Talhões FTW com MapBiomas (cache em memória; usado por carregar_talhao e pelo serviço da API)."""
    return gpd.read_parquet(FTW / "fields_tile_mapbiomas_geo.parquet")


def load_field(tid: str = FIELD_ID) -> dict:
    gdf = fields_gdf()
    row = gdf[gdf["id"].astype(str) == str(tid)]
    if row.empty:
        raise ValueError(f"Talhão {tid} não encontrado")
    row = row.iloc[0]
    # centróide em CRS projetado (SIRGAS 2000 / UTM 22S) -> 4326
    c = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(31982).centroid.to_crs(4326).iloc[0]
    poly = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(4326).iloc[0]
    # Relevo em % (NASADEM) pelo módulo regiao; fora da região -> None ("sem dado").
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

# --------------------------------------------------------------------------- 2. Histórico NDVI
def load_ndvi(tid: str = FIELD_ID) -> pd.Series:
    df = pd.read_csv(ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv", parse_dates=["data"])
    df = df[df["frac_clear"] >= 0.7]
    s = df.groupby("data")["ndvi_mean"].mean().sort_index()  # S30 e L30 no mesmo dia -> média
    d = s.resample("D").mean().interpolate(limit_area="inside")  # série diária
    return d.rolling(15, center=True, min_periods=1).mean()  # suavização ~15 dias


def soil_ranges(ndvi: pd.Series, threshold: float = SOIL_THRESHOLD) -> list[tuple]:
    """Intervalos contíguos (ini, fim) com NDVI < limiar."""
    low = (ndvi < threshold).values
    ranges, start = [], None
    for i, b in enumerate(low):
        if b and start is None:
            start = ndvi.index[i]
        if not b and start is not None:
            ranges.append((start, ndvi.index[i - 1])); start = None
    if start is not None:
        ranges.append((start, ndvi.index[-1]))
    return ranges


def peaks_by_crop_year(ndvi: pd.Series) -> dict[str, int]:
    """Nº de picos de NDVI por ano agrícola (set–ago). Só anos agrícolas completos."""
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
    """Média de dias/ano com NDVI < limiar, em anos agrícolas completos."""
    tot = []
    for year in range(ndvi.index.min().year - 1, ndvi.index.max().year + 1):
        start, end = pd.Timestamp(year, 9, 1), pd.Timestamp(year + 1, 8, 31)
        if start >= ndvi.index.min() and end <= ndvi.index.max():
            tot.append(int((ndvi[start:end] < SOIL_THRESHOLD).sum()))
    return float(np.mean(tot)) if tot else float("nan")

# --------------------------------------------------------------------------- 3. Clima NASA POWER
POWER_URL = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MIN,T2M_MAX,PRECTOTCORR"
             "&community=AG&longitude={lon}&latitude={lat}&start=19950101&end=20241231&format=JSON")


def fetch_power(lat: float, lon: float) -> tuple[pd.DataFrame, str]:
    """Retorna (DataFrame diário, origem). Tenta API; se falhar, usa cache em disco."""
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
            raise RuntimeError(f"NASA POWER indisponível e sem cache em disco: {e}") from e
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
        # limiar <= 3 C (coerente com o lookup: a validação com o INMET mostrou que o POWER subestima geada)
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


# Lookup pré-calculado (Paraná): indicadores da CÉLULA (~50 km); município só como contexto.


def _ind(d: dict, nome: str) -> dict:
    return d["celula"]["indicadores"][nome]


@lru_cache(maxsize=1)
def _annual() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/processed/clima_pr/indicadores_anuais.parquet",
                           columns=["ponto_id", "ano", "indicador", "valor"])


def cell_annual_water(point_id: str) -> dict[str, dict[str, np.ndarray]]:
    """Chuva e ET0 (mm) por ano (1991–2024) da CÉLULA, por ciclo: 'safrinha' (15/02–15/06) e 'trigo' (01/05–30/09).
    Vêm de indicadores_anuais.parquet (calculados em field_shift.clima.indicadores com ET0 FAO-56 / NASA POWER)."""
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
    """Monta o dict de riscos (mesmo formato de riscos_power) a partir do lookup, mais diagnóstico e tabela de geada."""
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
    """Dentro do Paraná usa o lookup pré-calculado; fora, cai no POWER ao vivo (modo reduzido)."""
    info = indicators_for(lat, lon)
    if info is not None:
        return region_climate(info, sowing), "lookup pré-calculado (NASA POWER, célula ~50 km)"
    df, origin = fetch_power(lat, lon)
    return power_risks(df), origin

def enrich(rk: dict, t: dict, soil_analysis: dict | None = None) -> dict:
    """Acrescenta ao dict de clima: solo do talhão (SoilGrids ou, se informada, a análise de solo do produtor já validada
    por field_shift.motor.servico), contexto do balanço hídrico e PAM do município.
    Fora da região (modo reduzido) devolve rk sem solo/PAM -> o critério água usa o fallback do catálogo."""
    out = {**rk, "solo": None, "pam": None, "agua_ctx": None}
    cod0 = rk["municipio"]["cod_ibge"] if rk.get("modo") == "regiao" else None
    out["calendario_soja"] = soy_calendar(cod0)  # ADAPAR region of the municipality (default region without one)
    out["rend"] = yields(None if cod0 is None else str(cod0))  # sem município: média do Oeste do PR (com aviso)
    out["rend_local"] = rk["municipio"]["nome"] if cod0 is not None else "Oeste do PR (média)"
    if rk.get("modo") != "regiao":
        return out
    s = polygon_soil(t["poly"])
    if soil_analysis:
        # a análise substitui o SoilGrids (que só fornece a MO quando a análise não traz MO nem CAD)
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
    """Rendimentos PAM para a nota de renda: os de `enriquecer` (município) ou, se ausentes, a média do Oeste do PR."""
    return rk.get("rend") or yields(None)


def fmt_soil(rk: dict) -> str | None:
    return soil_text(rk["solo"]) if rk.get("solo") else None


def fmt_pam(rk: dict) -> str | None:
    return pam_text(rk["pam"]["nome"], rk["pam"]["dados"]) if rk.get("pam") else None


# --------------------------------------------------------------------------- 5. Motor
# ESTIMATIVAS DE REFERÊNCIA — validar com agrônomo/CONAB/Embrapa.
# A rotação é um par (cultura de verão, cultura da 2ª janela). O CATALOGO de candidatas (chave = nome legível do par) é montado
# a partir de dois catálogos pequenos: VERAO (soja, milho verão) e SEGUNDA (2ª janela). Atributos de SEGUNDA:
# `renda_itens`: culturas/manejos da 2ª janela que entram na margem (field_shift.renda: rendimento PAM × preço SEAB − custo CONAB;
# cobertura/pousio = − custo estimado). A cultura de verão entra sempre (`item_renda` de VERAO).
# `agua` (0–1, demanda relativa) só é usado como FALLBACK fora do Paraná (sem clima pré-calculado);
# na região o critério água vem do balanço hídrico diário com o solo do talhão (field_shift.agua; ver agua_atendida).
# `ciclo_agua`: ciclo climático da 2ª cultura (usado só no fallback por ciclo, sem solo).
# `kc`: coeficiente de cultura médio sazonal (média da curva do balanço hídrico; FAO-56, estimativa, validar).
# `bonus_sc`: ganho esperado de produtividade da soja seguinte por palhada/N (sacas/ha) — estimativa de referência,
# validar com agrônomo/Embrapa. O bônus da rotação é a soma do bônus da 2ª cultura e do bônus da cultura de verão.
# `segue_semeadura`: a 2ª cultura é semeada na data escolhida pelo produtor (milho, sorgo, feijão, milheto/crotalária); as demais têm
# data fixa (trigo/aveia 01/05, nabo 01/04) e não dependem da colheita do verão. `janela`: (início, fim) dd/mm de semeadura aceitos.
# `milho`: é milho (milho sobre milho, após o milho verão, tem penalidade de pragas).
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
    "pousio": dict(nome="pousio", tipo="pousio", dias_descobertos=150, cobertura=0.2, n_fix=0.0, pragas=0.3, agua=0.1,
        renda_itens=["pousio"], ciclo_agua=None, kc=None, bonus_sc=0.0,  # sem cultura: sem demanda hídrica (água = 1,0)
        riscos=[], soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="não se aplica", texto="sem produção na 2ª janela")),
    "soja_safrinha": dict(nome="soja safrinha", tipo="grão", dias_descobertos=60, cobertura=0.4, n_fix=0.8, pragas=0.0, agua=0.8,
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=1.0, bonus_sc=0.0, riscos=["deficit_hidrico"],
        soja_viva_vazio=True, ano_soja_2=True, segue_semeadura=True, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="alto", texto="mesma cadeia da soja (mas a rotação é proibida pela regulação)")),
    # Culturas novas (grãos/cobertura que usam o maquinário e o canal de venda de grãos). Valores de catálogo: estimativas de referência.
    # Sorgo granífero: gramínea sem a cigarrinha do milho, tolerante à seca (sem déficit hídrico no risco); janela 15/01–15/03 e ciclo ~125 d
    # (FAO-56 tab. 11); colhe com a plataforma de soja/grãos adaptada.
    "sorgo": dict(nome="sorgo", tipo="grão", dias_descobertos=55, cobertura=0.7, n_fix=0.3, pragas=0.55, agua=0.5,
        renda_itens=["sorgo"], ciclo_agua="safrinha", kc=0.77, bonus_sc=1.0, riscos=["geada_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "15/03"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("sorgo",),
        mercado_oeste_pr=dict(nivel="médio", texto="ração animal e cooperativas, com demanda menor que a do milho")),
    # Feijão 2ª safra ("das secas"): ciclo curto (~90 d), pouca palha e hospedeiro do mofo-branco, que também ataca a soja (pragas baixas,
    # sem bônus); janela 15/01–28/02 (estimativa a partir do ZARC/IDR-PR; geada e déficit hídrico pesam).
    "feijao_safrinha": dict(nome="feijão safrinha", tipo="grão", dias_descobertos=75, cobertura=0.4, n_fix=0.4, pragas=0.3, agua=0.7,
        renda_itens=["feijao_2safra"], ciclo_agua="safrinha", kc=0.84, bonus_sc=0.0, riscos=["geada_safrinha", "deficit_hidrico"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "28/02"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("feijao",),
        mercado_oeste_pr=dict(nivel="médio", texto="cerealistas e cooperativas, com preço volátil e menos compradores que milho e soja")),
    # Nabo forrageiro: ciclagem de nutrientes e supressão de plantas daninhas/nematoides, mas hospedeiro de mofo-branco; palha de
    # decomposição rápida; semeadura em 01/04, sem venda de grão.
    "nabo_forrageiro": dict(nome="nabo forrageiro (cobertura)", tipo="cobertura", dias_descobertos=35, cobertura=0.65, n_fix=0.1, pragas=0.6, agua=0.3,
        renda_itens=["nabo_forrageiro"], ciclo_agua="trigo", kc=0.90, bonus_sc=2.0, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
    # Mix aveia + nabo: palha duradoura da aveia mais ciclagem do nabo.
    "aveia_nabo": dict(nome="aveia + nabo forrageiro (cobertura)", tipo="cobertura", dias_descobertos=35, cobertura=0.85, n_fix=0.2, pragas=0.65, agua=0.3,
        renda_itens=["aveia_nabo"], ciclo_agua="trigo", kc=0.85, bonus_sc=2.5, riscos=[],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=False, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(), mercado_oeste_pr=None),
}
# `bonus_sc_faixa` (min, max) e `bonus_fonte`: faixa e fonte do bônus (`bonus_sc` é o valor central usado na nota e na margem).
# Por enquanto faixa = valor central; a pesquisa de literatura vai substituir pelos números reais (declare na própria entrada).
DEFAULT_BONUS_SOURCE = "estimativa de referência — validar com agrônomo/Embrapa"
for _e in SECOND.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", DEFAULT_BONUS_SOURCE)
_COVER_MARKET = dict(nivel="não se aplica", texto="sem venda de grão; semente disponível em revendas")
for _e in SECOND.values():
    _e["mercado_oeste_pr"] = _e["mercado_oeste_pr"] or _COVER_MARKET
MARKET_ESTIMATE = "estimativa a validar com cooperativas/revendas locais"

# Cultura de verão. `colheita`: data estimada (dd/mm) de colheita; a 2ª cultura que segue a data de semeadura escolhida só pode ser
# semeada nessa data ou depois. Soja (precoce, semeada em set): premissa do motor, que já aceita a 2ª cultura a partir de 15/01.
# Milho verão (semeado de 15/09 a 15/10, ciclo médio ~130–145 d): colhe ~3–4 semanas depois da soja — estimativa, validar com ZARC/Embrapa.
# `bonus_sc`: ganho adicional (sc/ha) na soja seguinte por quebra de ciclo de doença e nematoide e mais palhada, ao trocar a soja
# de verão por milho (estimativa de referência, validar com agrônomo/Embrapa). `item_renda`: chave da margem do verão (field_shift.renda).
SUMMER = {
    "soja": dict(nome="Soja", descricao="Soja no verão: a cultura mais comum do Oeste do PR; semeadura de 01/09 a 31/12.",
                 item_renda="soja", colheita="10/01", bonus_sc=0.0, req_maquinas=(), vende=()),
    "milho_verao": dict(nome="Milho verão", descricao="Milho de 1ª safra no lugar da soja: quebra ciclo de doença e nematoide e deixa mais palhada.",
                        item_renda="milho_1safra", colheita="05/02", bonus_sc=3.0, req_maquinas=("plataforma_milho",), vende=("milho",)),
}
for _e in SUMMER.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", DEFAULT_BONUS_SOURCE)
# Penalidade de pragas do milho sobre milho (milho verão + milho safrinha): hospedeiro contínuo da cigarrinha-do-milho (Dalbulus maidis)
# e do enfezamento, além de lagarta-do-cartucho e doenças foliares. Subtrai do critério pragas da candidata (estimativa, validar).
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


# nome legível do par -> atributos. Soja + X mantém os nomes antigos ("Soja → milho safrinha" etc.).
CATALOG = {f"{SUMMER[v]['nome']} → {SECOND[s]['nome']}": _combination(v, s) for v in SUMMER for s in SECOND}
NOME_DE = {c["id"]: n for n, c in CATALOG.items()}  # id "<verao>__<segunda>" -> nome
ID_DE = {n: i for i, n in NOME_DE.items()}
# slugs antigos da API (só soja no verão) -> id novo
LEGACY = {s: rotation_id("soja", s) for s in ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio", "soja_safrinha")}

# Restrições de máquinas: custo de terceirização quando o produtor NÃO tem a máquina (ESTIMATIVA, validar com prestadores).
MACHINE_COST = {
    "plataforma_milho": dict(rotulo="Colheita de milho terceirizada", custo=250.0,  # R$/ha — estimativa, validar
                             aviso="Exige plataforma de milho: alugar/terceirizar a colheita (custo extra estimado)."),
    "semeadora_consorcio": dict(rotulo="Semeadura do consórcio com braquiária terceirizada", custo=80.0,  # R$/ha — estimativa, validar
                                aviso="Exige semeadora de consórcio (ou semeadura a lanço/caixa extra): alugar/terceirizar (custo extra estimado)."),
}
DEFAULT_IRRIGATION_COST = 4.0   # R$ por mm por ha (energia + mão de obra + depreciação) — estimativa, validar
DEFAULT_MAX_DEPTH = 6.0        # mm/dia — estimativa de pivô/aspersão, validar
SOIL_REF_DAYS = 180    # escala absoluta de dias descobertos: 1 − dias/180 (0 dias = 1,0; ≥180 = 0)
DEFAULT_WEIGHTS = {"renda": 5, "solo": 3, "agua": 3, "pragas": 3, "risco": 3}


def water_balance(nome: str, risks: dict) -> dict | None:
    """Balanço hídrico diário (balde FAO-56, célula NASA POWER + solo SoilGrids) na fase crítica; None se indisponível."""
    ctx = risks.get("agua_ctx")
    if not ctx:
        return None
    irrig_ = risks.get("irrig")
    lam = irrig_["lamina_max_mm_dia"] if irrig_ and CATALOG[nome].get("irrigavel") else None
    return critical_phase_water(CATALOG[nome]["segunda"], ctx["ponto_id"], ctx["semeadura"], ctx["cad_camadas"], lam)


def irrigation_info(nome: str, risks: dict) -> dict | None:
    """Irrigação aplicada à candidata (lâmina média do ciclo e custo R$/ha), ou None (sequeiro, cobertura/pousio ou sem solo)."""
    irrig_ = risks.get("irrig")
    if not irrig_ or not CATALOG[nome].get("irrigavel"):
        return None
    b = water_balance(nome, risks)
    if b is None or not b.get("irrigado"):
        return None
    return dict(lamina_media_mm=b["lamina_media_mm"], custo_r_mm_ha=irrig_["custo_r_mm_ha"],
                custo_r_ha=b["lamina_media_mm"] * irrig_["custo_r_mm_ha"], lamina_max_mm_dia=irrig_["lamina_max_mm_dia"])


def effective_risks(nome: str, c: dict, risks: dict) -> list[str]:
    """Riscos climáticos da candidata; o déficit hídrico deixa de valer se ela é irrigada (a geada continua)."""
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
    """Eliminações por restrição do produtor (`riscos['restr']`: excluidas {nomes}, sem_comprador {milho|trigo|sorgo|feijao|aveia_grao}).
    `c['vende']` lista as culturas de venda da rotação (verão e 2ª janela)."""
    r = risks.get("restr") or {}
    reasons = []
    if nome in r.get("excluidas", ()):
        reasons.append("Excluída pelo produtor.")
    for v in c["vende"]:
        if v in r.get("sem_comprador", ()):
            reasons.append(f"Sem comprador local informado pelo produtor ({v}).")
    return reasons


def extra_costs(nome: str, c: dict, risks: dict) -> list[dict]:
    """Custos extras da candidata: terceirização das máquinas que o produtor disse NÃO ter + irrigação."""
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
    return out + field_state.costs(c, risks.get("estado_area"))  # fertilidade informada: calagem e adubação P/K (senão, nada)


def water_met(c: dict, risks: dict, nome: str | None = None) -> tuple[float, bool]:
    """Critério água, ESCALA ABSOLUTA 0–1. Na região, com solo: média nos 34 anos de ΣETa/ΣETc na fase crítica da
    cultura (balanço diário; muda com a data de semeadura). Pousio = 1,0.
    Sem solo (ou candidata sem modelo): média dos anos de min(1, P_ciclo/(Kc·ET0_ciclo)) da célula.
    Fora da região (sem clima pré-calculado): fallback 1 − atributo `agua` (do_clima=False). Retorna (valor, do_clima)."""
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
    """Regras duras: devolve a lista de motivos de eliminação (vazia = válida). `riscos['semeadura']` (dd/mm da 2ª cultura)
    ativa as regras de calendário: colheita do verão e janela de semeadura da 2ª cultura."""
    reasons = []
    sow_date = (risks or {}).get("semeadura")
    cs = (risks or {}).get("calendario_soja") or soy_calendar(None)  # ADAPAR window of the area's municipality
    sow = f"{cs['semeadura'][0]}–{cs['semeadura'][1]}"
    if c["ano_soja_2"]:
        if c["verao"] == "soja":
            reasons.append("Soja sobre soja no mesmo ano agrícola é proibida (Portaria SDA/MAPA 1.124/2024).")
        reasons.append(f"Soja na 2ª janela{f' (semeadura em {sow_date})' if sow_date else ''} fica fora da janela legal de semeadura da soja ({sow}, {cs['nome'].split(' (')[0]}).")
    if sow_date and c["segue_semeadura"] and not c["ano_soja_2"]:
        # colheita do verão: a do produtor (estágio/colheita prevista), se for da mesma cultura de verão; senão a do catálogo
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
            reasons.append(f"Semeadura em {sow_date} fora da janela de {c['nome_segunda']} no Oeste do PR "
                           f"({c['janela'][0]}–{c['janela'][1]}; estimativa de referência com base no ZARC/IDR-PR, validar).")
    if c["soja_viva_vazio"]:
        reasons.append(f"Há soja viva durante o vazio sanitário da soja ({cs['vazio'][0]}–{cs['vazio'][1]}, {cs['nome'].split(' (')[0]} do PR).")
    mes, day = map(int, c["plantio_soja"].split("-"))
    if not in_window(f"{day:02d}/{mes:02d}", *cs["semeadura"]):
        reasons.append(f"Semeadura de soja em {day:02d}/{mes:02d} fora da janela {sow} ({cs['nome'].split(' (')[0]}).")
    return reasons


class NoCandidates(ValueError):
    """Todas as rotações avaliadas foram eliminadas (regras duras + restrições do produtor). `eliminadas`: {nome: motivos}."""

    def __init__(self, msg: str, eliminated_list: dict | None = None):
        super().__init__(msg)
        self.eliminated_list = eliminated_list or {}


def score_rotation(pesos: dict[str, float], risks: dict, adjustments: dict | None = None, names: list[str] | None = None) -> dict:
    """Retorna dict com tabela das válidas (DataFrame), eliminadas e contribuições. `nomes`: só avalia essas candidatas
    (nomes do CATALOGO); None = todas. Todos os critérios em ESCALA ABSOLUTA 0–1 (sem min-max entre candidatas), maior = melhor."""
    valid_items, eliminated_list = {}, {}
    for nome in (names if names is not None else CATALOG):
        c = CATALOG[nome]
        m = check_rules(c, risks) + check_constraints(nome, c, risks)
        (eliminated_list if m else valid_items)[nome] = m or c
    if not valid_items:
        raise NoCandidates("As restrições informadas eliminam todas as rotações.", eliminated_list)
    # Risco: 1 - P(algum risco); com vários riscos independentes, critério = Π(1 - pᵢ). Sem risco = 1,0.
    # Candidata irrigada: o veranico não conta (a geada continua).
    rs_ef = {n: effective_risks(n, c, risks) for n, c in valid_items.items()}
    abs_risk = {n: float(np.prod([1 - risk_probability(n, r, risks) for r in rs_ef[n]])) if rs_ef[n] else 1.0 for n in valid_items}
    # Solo: média de cobertura, fixação de N e (1 - dias descobertos/180), todos 0–1 absolutos.
    soil = {n: (c["cobertura"] + c["n_fix"] + max(0.0, 1 - c["dias_descobertos"] / SOIL_REF_DAYS)) / 3
            for n, c in valid_items.items()}
    # Renda pela margem INCREMENTAL sobre a soja de verão do município: incremental = margem da rotação − margem da soja
    # = (margem do verão − margem da soja) + margem da 2ª cultura (vendida: PAM × preço − custo; cobertura: − custo de
    # implantação; pousio: − custo de manejo) + bônus na soja seguinte (bonus_sc × preço da soja). Com soja no verão o primeiro
    # termo é zero (fórmula original); milho verão entra com PAM de milho 1ª safra × preço do milho − custo CONAB do milho verão.
    # renda = clip(0,5 + incremental / (2·S), 0, 1), S = max(margem da soja do município, RENDA_ESCALA_MIN):
    # incremental = +S → 1,0; zero → 0,5; −S → 0. Mede quanto a 2ª safra soma ou tira na escala da soja do próprio município.
    extras = {n: extra_costs(n, c, risks) for n, c in valid_items.items()}
    margins = compute_margins({n: c for n, c in valid_items.items()}, yields_rk(risks), adjustments, extras)
    income = {n: float(np.clip(0.5 + m["incremental"] / (2 * m["escala_S"]), 0.0, 1.0)) for n, m in margins.items()}
    income_warning = (None if any(m["total"] > 0 for m in margins.values())
                   else "Nenhuma rotação válida tem margem total positiva com os preços e custos usados (informativo).")
    # Estado da área informado pelo produtor (problemas_area, fertilidade): deltas aditivos em solo e pragas, limitados a [0, 1].
    # Sem a informação, `riscos["estado_area"]` não existe e nada muda.
    pests = {n: c["pragas"] for n, c in valid_items.items()}
    if risks.get("estado_area"):
        aj_ea = {n: field_state.adjustment(c, risks["estado_area"]) for n, c in valid_items.items()}
        soil = {n: float(np.clip(soil[n] + aj_ea[n]["solo"], 0.0, 1.0)) for n in valid_items}
        pests = {n: float(np.clip(pests[n] + aj_ea[n]["pragas"], 0.0, 1.0)) for n in valid_items}
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
    return dict(tabela=tab, eliminadas=eliminated_list, margens=margins, aviso_renda=income_warning, pesos_norm=w, riscos=risks)

# --------------------------------------------------------------------------- 6. Textos dos cards
def _r(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def local_rend(risks: dict, key: str) -> str:
    """Origem do rendimento PAM de uma cultura: município ou, se ele não tem PAM suficiente, média do Oeste do PR."""
    if key in (risks.get("rend") or {}).get("_regionais", ()):
        return "Oeste do PR (média, o município não tem PAM recente)"
    return risks.get("rend_local") or "Oeste do PR"


def fmt_margin(m: dict, risks: dict) -> list[str]:
    """Decomposição da margem da rotação (linhas de evidência do card)."""
    lines = []
    for i in m["itens"]:
        local = local_rend(risks, i["chave"])
        if i.get("extra"):
            nome_c = "custo extra" if i["custo"] >= 0 else "economia"
            lines.append(f"{i['rotulo']}: {nome_c} R$ {_r(abs(i['custo']))}/ha ({i['detalhe']}) = {_rs(i['margem'])}.")
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
            lines.append(f"{i['rotulo']}: {i['sc_ha']:.0f} sc/ha ({orig}) × R$ {i['preco']:.2f}/sc ({price_source(i)}) − custo "
                          f"R$ {_r(i['custo'])}/ha ({cost_source(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha "
                          f"(CV do rendimento {i['cv']:.0%}; ano ruim, p20 da mesma janela de 10 anos = {i['sc_ha_ruim']:.0f} sc/ha → "
                          f"R$ {_r(i['margem_ano_ruim'])}/ha).")
        else:
            lines.append(f"{i['rotulo']}: sem venda, custo de implantação R$ {_r(i['custo'])}/ha ({cost_source(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha.")
    bonus_detail = (f" ({m['bonus_verao_sc']:g} sc/ha do milho verão no lugar da soja + {m['bonus_sc'] - m['bonus_verao_sc']:g} da 2ª cultura)"
                     if m["bonus_verao_sc"] else "")
    lines.append(f"Bônus na soja seguinte: {m['bonus_sc']:g} sc/ha × R$ {m['preco_soja']:.2f}/sc = R$ {_r(m['bonus'])}/ha{bonus_detail} "
                  f"(palhada/N e quebra de ciclo de doença, estimativa de referência).")
    t = (f"Total da rotação: R$ {_r(m['total'])}/ha/ano; incremental da 2ª safra (sem a soja, com o bônus): R$ {_r(m['incremental'])}/ha, "
         f"na escala S = R$ {_r(m['escala_S'])}/ha (margem da soja do município, mín. {_r(INCOME_SCALE_MIN)})")
    if m["total_ano_ruim"] is not None:
        t += f"; em ano ruim (rendimento p20): R$ {_r(m['total_ano_ruim'])}/ha/ano"
    lines.append(t + ".")
    return lines


def _rs(x: float) -> str:
    return f"R$ {_r(x)}/ha" if x >= -0.5 else f"−R$ {_r(-x)}/ha"


def _c2(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _short_name(n: str) -> str:
    return n.replace("Soja → ", "")


def _criterion_text(k: str, alt: str, cur: str, res: dict, d: float) -> str:
    """Frase curta sobre o critério k da alternativa `alt` contra a atual `atu` (d = Δcritério, com sinal)."""
    t, m = res["tabela"].set_index("candidata"), res["margens"]
    ca, cb = t.loc[alt], t.loc[cur]
    wins = d > 0
    if k == "renda":
        a, b = m[alt]["incremental"], m[cur]["incremental"]
        if wins:
            pct = f" (+{(a - b) / abs(b):.0%})" if b > 0 else ""
            return f"soma {_rs(a)} contra {_rs(b)} na 2ª safra{pct}"
        return f"abre mão de {_rs(b - a)} na 2ª safra ({_rs(a)} contra {_rs(b)})"
    if k == "solo":
        da, db = CATALOG[alt]["dias_descobertos"], CATALOG[cur]["dias_descobertos"]
        return (f"{'melhora' if wins else 'piora'} a saúde do solo ({_c2(ca['solo'])} contra {_c2(cb['solo'])}; "
                f"~{da} dias de solo descoberto contra {db})")
    if k == "agua":
        return f"{'atende melhor' if wins else 'atende pior'} a demanda de água ({_c2(ca['agua'])} contra {_c2(cb['agua'])})"
    if k == "pragas":
        return f"{'quebra melhor' if wins else 'quebra menos'} o ciclo de pragas ({_c2(ca['pragas'])} contra {_c2(cb['pragas'])})"
    pa, pb = 1 - ca["risco"], 1 - cb["risco"]
    return (f"{'reduz' if wins else 'aumenta'} o risco climático (algum evento adverso em {pa:.0%} dos anos "
            f"contra {pb:.0%})")


def why_compared(res: dict, nome: str, current: str | None) -> str | None:
    """Texto do 'por quê' de `nome` comparado com a rotação atual (None se a atual não está entre as válidas)."""
    tab = res["tabela"]
    names = list(tab["candidata"])
    if current is None or current not in names or nome not in names:
        return None
    if nome == current:
        pos, n = names.index(current) + 1, len(names)
        if pos == 1:
            o = tab.iloc[1]
            return (f"É a rotação atual; ficou em 1º lugar entre {n} opções válidas. A 2ª melhor ({_short_name(o['candidata'])}) "
                    f"tem nota {_c2(o['nota'])}.")
        b = tab.iloc[0]
        return (f"É a rotação atual; ficou em {pos}º lugar entre {n} opções válidas. A melhor alternativa "
                f"({_short_name(b['candidata'])}) tem nota {_c2(b['nota'])}.")
    t = tab.set_index("candidata")
    w = res["pesos_norm"]
    diff_ = {k: w[k] * (t.loc[nome, k] - t.loc[current, k]) for k in CRITERIA}
    tops = [k for k, v in sorted(diff_.items(), key=lambda kv: -abs(kv[1]))[:3] if abs(v) >= 0.005]
    phrases = [_criterion_text(k, nome, current, res, diff_[k]) for k in tops]
    cab = f"Em relação à atual ({_short_name(current)}): "
    if not phrases:
        txt = cab + "desempenho praticamente igual nos cinco critérios."
    elif len(phrases) == 1:
        txt = cab + phrases[0] + "."
    else:
        txt = cab + ", ".join(phrases[:-1]) + " e " + phrases[-1] + "."
    if "risco" not in tops and 1 - t.loc[nome, "risco"] > 0.005:
        txt += f" Risco climático igual (algum evento adverso em {1 - t.loc[nome, 'risco']:.0%} dos anos)."
    return txt


def build_card(line: pd.Series, current: bool, risks: dict, ndvi_bare_soil_days: float, margin: dict | None = None,
                why_cmp: str | None = None) -> dict:
    """`por_que_cmp`: texto de `por_que_comparado` (comparação com a rotação atual); se None, só as maiores contribuições."""
    c = CATALOG[line["candidata"]]
    top = sorted(line["contrib"].items(), key=lambda kv: -kv[1])[:2]
    contribs = "Maiores contribuições para a nota: " + " e ".join(f"{CRITERIA[k]} ({_c2(v)})" for k, v in top) + "."
    why = f"{why_cmp} {contribs}" if why_cmp else contribs
    ev = [f"Dias de solo descoberto/ano (catálogo): ~{c['dias_descobertos']} dias."]
    if current and not np.isnan(ndvi_bare_soil_days):
        ev.append(f"NDVI observado (NASA HLS): ~{ndvi_bare_soil_days:.0f} dias/ano com NDVI<{SOIL_THRESHOLD}.")
    hist = None
    if margin is not None:
        ev += fmt_margin(margin, risks)
        # 5-season track record of the second crop (informative, never in the score; docs/validation.md §3)
        hist = income_history.track_record((risks.get("municipio") or {}).get("cod_ibge"), c["segunda"])
        if (h_txt := income_history.text(hist)):
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
    if c["cobertura"] >= 0.8: ben.append("Boa cobertura/palha: protege o solo e reduz erosão.")
    if c["n_fix"] >= 0.7: ben.append("Fixação de nitrogênio relevante para a próxima soja.")
    if c["pragas"] >= 0.6: ben.append("Ajuda a quebrar ciclo de pragas e doenças.")
    if c["bonus_sc"] >= 2: ben.append(f"Palhada/N elevam a soja seguinte (~+{c['bonus_sc']:g} sc/ha, estimativa).")
    if c["bonus_verao_sc"]:
        ben.append(f"{c['nome_verao']} no lugar da soja de verão quebra ciclo de doença e nematoide e deixa mais palhada "
                   f"(~+{c['bonus_verao_sc']:g} sc/ha na soja seguinte, estimativa a validar com agrônomo/Embrapa).")
    if margin is not None and margin["total"] >= 2000: ben.append(f"Margem da rotação alta (~R$ {_r(margin['total'])}/ha/ano).")
    if c["ciclo_agua"] is None or water_met(c, risks, line["candidata"])[0] >= 0.9: ben.append("Chuva atende praticamente toda a demanda hídrica.")
    solo_p = risks.get("solo") or {}
    if solo_p.get("fonte") == "análise de solo do produtor":
        lacuna_cad = ("CAD vinda da análise do produtor (informada ou por Saxton & Rawls com a análise), "
                      "tomada como representativa do perfil de 0–60 cm.")
    else:
        lacuna_cad = "CAD por pedotransferência (Saxton & Rawls), pode errar em latossolos tropicais."
    ea = field_state.card(c, risks.get("estado_area"))
    ev += ea["evidencias"]
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
        review.append(f"Geada (≤ 3 °C) no safrinha em {risks['geada_safrinha']:.0%} dos anos"
                       + (f" com semeadura em {risks['semeadura']}" if risks.get("semeadura") else "")
                       + ": avaliar data de semeadura/híbrido.")
    if "deficit_hidrico" in rs_ef and (p_def := risk_probability(line["candidata"], "deficit_hidrico", risks)) >= 0.2:
        review.append(f"Déficit hídrico na fase crítica em {p_def:.0%} dos anos: avaliar data de semeadura/cultivar.")
    if "geada_trigo" in c["riscos"] and risks["geada_trigo"] >= 0.2:
        review.append(f"Geada no florescimento do trigo em {risks['geada_trigo']:.0%} dos anos.")
    if c["dias_descobertos"] >= 100: review.append("Muitos dias de solo exposto: risco de erosão e plantas daninhas.")
    mach = (risks.get("restr") or {}).get("maquinas", {})
    warnings = list(dict.fromkeys(MACHINE_COST[m]["aviso"] for m in c["req_maquinas"] + c["req_maquinas_verao"] if mach.get(m) is False))
    if z_warning:
        warnings.insert(0, z_warning)
    mer = c["mercado_oeste_pr"]
    mercado = dict(nivel=mer["nivel"], texto=mer["texto"], estimativa=MARKET_ESTIMATE)
    ev.append(f"Mercado no Oeste do PR: {mer['nivel']}; {mer['texto']} ({MARKET_ESTIMATE}).")
    return dict(por_que=why, evidencia=ev, beneficios=ben or ["Sem benefício marcante nos critérios avaliados."],
                lacunas=lacunas, revisar=review, avisos=warnings, mercado=mercado, irrigacao=ir, zarc=zs, historico=hist)


def fmt_diagnosis(d: dict) -> list[str]:
    """Linhas de texto do diagnóstico de clima (apenas exibição; não entra na nota)."""
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
    dec = "sem dado" if t["declividade"] is None else f"{t['declividade']:.1f}% (p90 {t['declividade_p90']:.1f}%, {t['classe_embrapa']})"
    alt = "sem dado" if t["altitude"] is None else f"{t['altitude']:.0f} m"
    print(f"Talhão {t['id']}: {t['area_ha']:.1f} ha  lat={t['lat']:.5f} lon={t['lon']:.5f} declividade={dec}  altitude={alt}")
    print("Histórico MapBiomas:", t["historico"])
    nd = load_ndvi()
    pk = peaks_by_crop_year(nd)
    print("Picos NDVI por ano agrícola:", pk, "→", detect_rotation(pk))
    print(f"Dias/ano com NDVI<{SOIL_THRESHOLD}: {bare_soil_days_by_year(nd):.0f}; faixas: {len(soil_ranges(nd))}")
    rk, origin = get_climate(t["lat"], t["lon"], sow_date)
    rk = enrich(rk, t)
    print(f"Clima [{rk['modo']}]: {origin} · {rk['fonte']} · semeadura safrinha {rk['semeadura']}")
    if rk["modo"] == "reduzido":
        print("AVISO: modo reduzido (fora do Paraná; POWER ao vivo, sem diagnóstico nem tabela por data).")
    else:
        m = rk["municipio"]
        print(f"Célula {rk['celula']['ponto_id']} (elev {rk['celula']['elev']:.0f} m); município (contexto): {m['nome']} ({m['cod_ibge']})")
        print("Geada ≤3 °C no safrinha por data de semeadura:",
              {r["semeadura"]: f"{r['prob']:.2f} ({r['anos']}/{r['n_anos']})" for r in rk["geada_tabela"]})
        for line in fmt_diagnosis(rk["diagnostico"]):
            print("  -", line)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rk.items()
           if k in ("geada_safrinha", "geada_trigo", "veranico_safrinha", "n_anos", "periodo")})
    print("Chuva mensal média (mm):", rk["chuva_mensal"].round(0).to_dict())
    if rk.get("solo"):
        print("Solo:", fmt_soil(rk))
        print("PAM:", fmt_pam(rk))
    print("Água atendida (fase crítica, balanço diário):", {n.replace("Soja → ", ""): round(water_met(c, rk, n)[0], 3) for n, c in CATALOG.items()})
    for n in CATALOG:
        b = water_balance(n, rk)
        if b:
            print(f"  {n}: {b['fase']} ({b['semeadura']}) média {b['media']:.3f}, {b['n_abaixo']}/{b['n_anos']} anos <0,7, TAW {b['taw_mm']:.0f} mm")
    adjustments = {"linha_custo": sys.argv[2]} if len(sys.argv) > 2 else None
    res = score_rotation(DEFAULT_WEIGHTS, rk, adjustments)
    print(res["tabela"].drop(columns="contrib").round(2).to_string())
    if res["aviso_renda"]:
        print("AVISO:", res["aviso_renda"])
    print("Rendimento:", rk["rend"]["_origem"])
    for n, m in res["margens"].items():
        print(f"\n{n}:")
        for l in fmt_margin(m, rk):
            print("  -", l)
    for n, m in res["eliminadas"].items():
        print("ELIMINADA:", n, m)
