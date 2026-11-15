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

from field_shift import calendario as cal
from field_shift.app import estado_area
from field_shift.agua import agua_fase_critica
from field_shift.calendario import DIAS_PREPARO_2A, SEMEADURA_PADRAO, SEMEADURAS
from field_shift.clima.lookup import indicadores_para
from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import texto as pam_texto
from field_shift.renda import RENDA_ESCALA_MIN, calcular_margens, fonte_custo, fonte_preco, rendimentos
from field_shift.regiao import dentro_da_regiao, relevo
from field_shift.solo import solo as solo_poligono
from field_shift.solo.solo import solo_de_analise, texto as solo_texto

ROOT = Path(__file__).resolve().parents[3]
FTW = ROOT / "data/processed/ftw"
TALHAO_ID = "72638"  # a coluna `id` do parquet é string
LIMIAR_SOLO = 0.35  # NDVI abaixo disto = solo descoberto / baixa cobertura

# --------------------------------------------------------------------------- 1. Local
@lru_cache(maxsize=1)
def gdf_talhoes() -> gpd.GeoDataFrame:
    """Talhões FTW com MapBiomas (cache em memória; usado por carregar_talhao e pelo serviço da API)."""
    return gpd.read_parquet(FTW / "fields_tile_mapbiomas_geo.parquet")


def carregar_talhao(tid: str = TALHAO_ID) -> dict:
    gdf = gdf_talhoes()
    row = gdf[gdf["id"].astype(str) == str(tid)]
    if row.empty:
        raise ValueError(f"Talhão {tid} não encontrado")
    row = row.iloc[0]
    # centróide em CRS projetado (SIRGAS 2000 / UTM 22S) -> 4326
    c = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(31982).centroid.to_crs(4326).iloc[0]
    poly = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(4326).iloc[0]
    # Relevo em % (NASADEM) pelo módulo regiao; fora da região -> None ("sem dado").
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

# --------------------------------------------------------------------------- 2. Histórico NDVI
def carregar_ndvi(tid: str = TALHAO_ID) -> pd.Series:
    df = pd.read_csv(ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv", parse_dates=["data"])
    df = df[df["frac_clear"] >= 0.7]
    s = df.groupby("data")["ndvi_mean"].mean().sort_index()  # S30 e L30 no mesmo dia -> média
    d = s.resample("D").mean().interpolate(limit_area="inside")  # série diária
    return d.rolling(15, center=True, min_periods=1).mean()  # suavização ~15 dias


def faixas_solo(ndvi: pd.Series, limiar: float = LIMIAR_SOLO) -> list[tuple]:
    """Intervalos contíguos (ini, fim) com NDVI < limiar."""
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
    """Nº de picos de NDVI por ano agrícola (set–ago). Só anos agrícolas completos."""
    res = {}
    for ano in range(ndvi.index.min().year - 1, ndvi.index.max().year + 1):
        ini, fim = pd.Timestamp(ano, 9, 1), pd.Timestamp(ano + 1, 8, 31)
        if ini < ndvi.index.min() or fim > ndvi.index.max():
            continue  # ano incompleto
        trecho = ndvi[ini:fim]
        p, _ = find_peaks(trecho.values, height=0.6, prominence=0.2, distance=40)
        res[f"{ano}/{str(ano + 1)[2:]}"] = len(p)
    return res


def detectar_rotacao(picos: dict[str, int]) -> str:
    if not picos:
        return "Soja → milho safrinha"
    mediana = float(np.median(list(picos.values())))
    return "Soja → milho safrinha" if mediana >= 2 else "Soja → pousio"


def dias_solo_por_ano(ndvi: pd.Series) -> float:
    """Média de dias/ano com NDVI < limiar, em anos agrícolas completos."""
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
    """Retorna (DataFrame diário, origem). Tenta API; se falhar, usa cache em disco."""
    cache = ROOT / f"data/raw/power/power_{lat:.2f}_{lon:.2f}.json"
    try:
        r = requests.get(POWER_URL.format(lat=round(lat, 4), lon=round(lon, 4)), timeout=180)
        r.raise_for_status()
        js = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(js))
        origem = "API NASA POWER (ao vivo)"
    except Exception as e:
        if not cache.exists():
            raise RuntimeError(f"NASA POWER indisponível e sem cache em disco: {e}") from e
        js = json.loads(cache.read_text())
        origem = f"cache em disco ({cache.name}) — API falhou: {type(e).__name__}"
    p = js["properties"]["parameter"]
    df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    return df.replace(-999, np.nan), origem


def riscos_power(df: pd.DataFrame) -> dict:
    anos = sorted(set(df.index.year))
    geada_saf = geada_trigo = veranico = 0
    for a in anos:
        y = df[df.index.year == a]
        # limiar <= 3 C (coerente com o lookup: a validação com o INMET mostrou que o POWER subestima geada)
        geada_saf += bool((y.loc[f"{a}-06-01":f"{a}-07-31", "T2M_MIN"] <= 3).any())
        geada_trigo += bool((y.loc[f"{a}-08-15":f"{a}-09-30", "T2M_MIN"] <= 3).any())
        seca = (y.loc[f"{a}-03-01":f"{a}-04-30", "PRECTOTCORR"] < 1).astype(int)
        run = seca.groupby((seca == 0).cumsum()).cumsum()
        veranico += bool(run.max() >= 15)
    n = len(anos)
    chuva_mes = df["PRECTOTCORR"].resample("MS").sum().groupby(lambda d: d.month).mean()
    return dict(geada_safrinha=geada_saf / n, geada_trigo=geada_trigo / n,
                veranico_safrinha=veranico / n, n_anos=n, chuva_mensal=chuva_mes,
                periodo=f"{anos[0]}–{anos[-1]}", modo="reduzido", fonte="NASA POWER ao vivo (ponto do centróide)",
                semeadura=None, geada_tabela=None, diagnostico=None, celula=None, municipio=None, agua_anual=None)


# Lookup pré-calculado (Oeste do PR): indicadores da CÉLULA (~50 km); município só como contexto.


def _ind(d: dict, nome: str) -> dict:
    return d["celula"]["indicadores"][nome]


@lru_cache(maxsize=1)
def _anuais() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/processed/clima/indicadores_anuais.parquet",
                           columns=["ponto_id", "ano", "indicador", "valor"])


def agua_anual_celula(ponto_id: str) -> dict[str, dict[str, np.ndarray]]:
    """Chuva e ET0 (mm) por ano (1991–2024) da CÉLULA, por ciclo: 'safrinha' (15/02–15/06) e 'trigo' (01/05–30/09).
    Vêm de indicadores_anuais.parquet (calculados em field_shift.clima.indicadores com ET0 FAO-56 / NASA POWER)."""
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
    """Monta o dict de riscos (mesmo formato de riscos_power) a partir do lookup, mais diagnóstico e tabela de geada."""
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
                fonte="NASA POWER 1991–2024, célula ~50 km (%s)" % info["celula"]["ponto_id"],
                semeadura=semeadura, geada_tabela=tabela, diagnostico=diag,
                celula=info["celula"], municipio={k: v for k, v in info["municipio"].items() if k != "indicadores"},
                agua_anual=agua_anual_celula(info["celula"]["ponto_id"]))


def obter_clima(lat: float, lon: float, semeadura: str = SEMEADURA_PADRAO) -> tuple[dict, str]:
    """Dentro do Oeste do PR usa o lookup pré-calculado; fora, cai no POWER ao vivo (modo reduzido)."""
    info = indicadores_para(lat, lon)
    if info is not None:
        return clima_regiao(info, semeadura), "lookup pré-calculado (NASA POWER, célula ~50 km)"
    df, origem = buscar_power(lat, lon)
    return riscos_power(df), origem

def enriquecer(rk: dict, t: dict, analise_solo: dict | None = None) -> dict:
    """Acrescenta ao dict de clima: solo do talhão (SoilGrids ou, se informada, a análise de solo do produtor já validada
    por field_shift.motor.servico), contexto do balanço hídrico e PAM do município.
    Fora da região (modo reduzido) devolve rk sem solo/PAM -> o critério água usa o fallback do catálogo."""
    out = {**rk, "solo": None, "pam": None, "agua_ctx": None}
    cod0 = rk["municipio"]["cod_ibge"] if rk.get("modo") == "regiao" else None
    out["rend"] = rendimentos(None if cod0 is None else str(cod0))  # sem município: média do Oeste do PR (com aviso)
    out["rend_local"] = rk["municipio"]["nome"] if cod0 is not None else "Oeste do PR (média)"
    if rk.get("modo") != "regiao":
        return out
    s = solo_poligono(t["poly"])
    if analise_solo:
        # a análise substitui o SoilGrids (que só fornece a MO quando a análise não traz MO nem CAD)
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
    """Rendimentos PAM para a nota de renda: os de `enriquecer` (município) ou, se ausentes, a média do Oeste do PR."""
    return rk.get("rend") or rendimentos(None)


def fmt_solo(rk: dict) -> str | None:
    return solo_texto(rk["solo"]) if rk.get("solo") else None


def fmt_pam(rk: dict) -> str | None:
    return pam_texto(rk["pam"]["nome"], rk["pam"]["dados"]) if rk.get("pam") else None


# --------------------------------------------------------------------------- 5. Motor
# ESTIMATIVAS DE REFERÊNCIA — validar com agrônomo/CONAB/Embrapa.
# A rotação é um par (cultura de verão, cultura da 2ª janela). O CATALOGO de candidatas (chave = nome legível do par) é montado
# a partir de dois catálogos pequenos: VERAO (soja, milho verão) e SEGUNDA (2ª janela). Atributos de SEGUNDA:
# `renda_itens`: culturas/manejos da 2ª janela que entram na margem (field_shift.renda: rendimento PAM × preço SEAB − custo CONAB;
# cobertura/pousio = − custo estimado). A cultura de verão entra sempre (`item_renda` de VERAO).
# `agua` (0–1, demanda relativa) só é usado como FALLBACK fora do Oeste do PR (sem clima pré-calculado);
# na região o critério água vem do balanço hídrico diário com o solo do talhão (field_shift.agua; ver agua_atendida).
# `ciclo_agua`: ciclo climático da 2ª cultura (usado só no fallback por ciclo, sem solo).
# `kc`: coeficiente de cultura médio sazonal (média da curva do balanço hídrico; FAO-56, estimativa, validar).
# `bonus_sc`: ganho esperado de produtividade da soja seguinte por palhada/N (sacas/ha) — estimativa de referência,
# validar com agrônomo/Embrapa. O bônus da rotação é a soma do bônus da 2ª cultura e do bônus da cultura de verão.
# `segue_semeadura`: a 2ª cultura é semeada na data escolhida pelo produtor (milho, sorgo, feijão, milheto/crotalária); as demais têm
# data fixa (trigo/aveia 01/05, nabo 01/04) e não dependem da colheita do verão. `janela`: (início, fim) dd/mm de semeadura aceitos.
# `milho`: é milho (milho sobre milho, após o milho verão, tem penalidade de pragas).
SEGUNDA = {
    "milho_safrinha": dict(nome="milho safrinha", tipo="grão", dias_descobertos=60, cobertura=0.6, n_fix=0.4, pragas=0.5, agua=0.7,
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=0.85, bonus_sc=1.0, riscos=["geada_safrinha", "veranico_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=True,
        irrigavel=True, req_maquinas=("plataforma_milho",), vende=("milho",),
        mercado_oeste_pr=dict(nivel="alto", texto="cooperativas e agroindústria de aves e suínos do Oeste do PR")),
    "milho_braquiaria": dict(nome="milho safrinha + braquiária", tipo="grão", dias_descobertos=30, cobertura=0.9, n_fix=0.4, pragas=0.65, agua=0.75,
        renda_itens=["milho_2safra", "braquiaria_consorcio"], ciclo_agua="safrinha", kc=0.90, bonus_sc=3.0,
        riscos=["geada_safrinha", "veranico_safrinha"], soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=None, milho=True,
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
        renda_itens=["milho_2safra"], ciclo_agua="safrinha", kc=1.0, bonus_sc=0.0, riscos=["veranico_safrinha"],
        soja_viva_vazio=True, ano_soja_2=True, segue_semeadura=True, janela=None, milho=False,
        irrigavel=False, req_maquinas=(), vende=(),
        mercado_oeste_pr=dict(nivel="alto", texto="mesma cadeia da soja (mas a rotação é proibida pela regulação)")),
    # Culturas novas (grãos/cobertura que usam o maquinário e o canal de venda de grãos). Valores de catálogo: estimativas de referência.
    # Sorgo granífero: gramínea sem a cigarrinha do milho, tolerante à seca (sem veranico no risco); janela 15/01–15/03 e ciclo ~125 d
    # (FAO-56 tab. 11); colhe com a plataforma de soja/grãos adaptada.
    "sorgo": dict(nome="sorgo", tipo="grão", dias_descobertos=55, cobertura=0.7, n_fix=0.3, pragas=0.55, agua=0.5,
        renda_itens=["sorgo"], ciclo_agua="safrinha", kc=0.77, bonus_sc=1.0, riscos=["geada_safrinha"],
        soja_viva_vazio=False, ano_soja_2=False, segue_semeadura=True, janela=("15/01", "15/03"), milho=False,
        irrigavel=True, req_maquinas=(), vende=("sorgo",),
        mercado_oeste_pr=dict(nivel="médio", texto="ração animal e cooperativas, com demanda menor que a do milho")),
    # Feijão 2ª safra ("das secas"): ciclo curto (~90 d), pouca palha e hospedeiro do mofo-branco, que também ataca a soja (pragas baixas,
    # sem bônus); janela 15/01–28/02 (estimativa a partir do ZARC/IDR-PR; geada e veranico pesam).
    "feijao_safrinha": dict(nome="feijão safrinha", tipo="grão", dias_descobertos=75, cobertura=0.4, n_fix=0.4, pragas=0.3, agua=0.7,
        renda_itens=["feijao_2safra"], ciclo_agua="safrinha", kc=0.84, bonus_sc=0.0, riscos=["geada_safrinha", "veranico_safrinha"],
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
BONUS_FONTE_PADRAO = "estimativa de referência — validar com agrônomo/Embrapa"
for _e in SEGUNDA.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", BONUS_FONTE_PADRAO)
_MERCADO_COBERTURA = dict(nivel="não se aplica", texto="sem venda de grão; semente disponível em revendas")
for _e in SEGUNDA.values():
    _e["mercado_oeste_pr"] = _e["mercado_oeste_pr"] or _MERCADO_COBERTURA
MERCADO_ESTIMATIVA = "estimativa a validar com cooperativas/revendas locais"

# Cultura de verão. `colheita`: data estimada (dd/mm) de colheita; a 2ª cultura que segue a data de semeadura escolhida só pode ser
# semeada nessa data ou depois. Soja (precoce, semeada em set): premissa do motor, que já aceita a 2ª cultura a partir de 15/01.
# Milho verão (semeado de 15/09 a 15/10, ciclo médio ~130–145 d): colhe ~3–4 semanas depois da soja — estimativa, validar com ZARC/Embrapa.
# `bonus_sc`: ganho adicional (sc/ha) na soja seguinte por quebra de ciclo de doença e nematoide e mais palhada, ao trocar a soja
# de verão por milho (estimativa de referência, validar com agrônomo/Embrapa). `item_renda`: chave da margem do verão (field_shift.renda).
VERAO = {
    "soja": dict(nome="Soja", descricao="Soja no verão: a cultura mais comum do Oeste do PR; semeadura de 01/09 a 31/12.",
                 item_renda="soja", colheita="10/01", bonus_sc=0.0, req_maquinas=(), vende=()),
    "milho_verao": dict(nome="Milho verão", descricao="Milho de 1ª safra no lugar da soja: quebra ciclo de doença e nematoide e deixa mais palhada.",
                        item_renda="milho_1safra", colheita="05/02", bonus_sc=3.0, req_maquinas=("plataforma_milho",), vende=("milho",)),
}
for _e in VERAO.values():
    _e.setdefault("bonus_sc_faixa", (_e["bonus_sc"], _e["bonus_sc"]))
    _e.setdefault("bonus_fonte", BONUS_FONTE_PADRAO)
# Penalidade de pragas do milho sobre milho (milho verão + milho safrinha): hospedeiro contínuo da cigarrinha-do-milho (Dalbulus maidis)
# e do enfezamento, além de lagarta-do-cartucho e doenças foliares. Subtrai do critério pragas da candidata (estimativa, validar).
PENALIDADE_MILHO_SOBRE_MILHO = 0.25
TEXTO_MILHO_SOBRE_MILHO = (
    "Milho sobre milho (milho verão + milho safrinha): mantém hospedeiro contínuo da cigarrinha-do-milho (Dalbulus maidis) e do "
    "enfezamento, além de lagarta-do-cartucho e doenças foliares; o critério de pragas perde "
    f"{PENALIDADE_MILHO_SOBRE_MILHO:.2f} ponto (estimativa de referência, validar com agrônomo/Embrapa). "
    "Acompanhe os alertas de cigarrinha (CigarrinhaWeb/ADAPAR; veja /v1/contexto).")


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


# nome legível do par -> atributos. Soja + X mantém os nomes antigos ("Soja → milho safrinha" etc.).
CATALOGO = {f"{VERAO[v]['nome']} → {SEGUNDA[s]['nome']}": _combinacao(v, s) for v in VERAO for s in SEGUNDA}
NOME_DE = {c["id"]: n for n, c in CATALOGO.items()}  # id "<verao>__<segunda>" -> nome
ID_DE = {n: i for i, n in NOME_DE.items()}
# slugs antigos da API (só soja no verão) -> id novo
LEGADO = {s: id_rotacao("soja", s) for s in ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio", "soja_safrinha")}

# Restrições de máquinas: custo de terceirização quando o produtor NÃO tem a máquina (ESTIMATIVA, validar com prestadores).
CUSTO_MAQUINA = {
    "plataforma_milho": dict(rotulo="Colheita de milho terceirizada", custo=250.0,  # R$/ha — estimativa, validar
                             aviso="Exige plataforma de milho: alugar/terceirizar a colheita (custo extra estimado)."),
    "semeadora_consorcio": dict(rotulo="Semeadura do consórcio com braquiária terceirizada", custo=80.0,  # R$/ha — estimativa, validar
                                aviso="Exige semeadora de consórcio (ou semeadura a lanço/caixa extra): alugar/terceirizar (custo extra estimado)."),
}
CUSTO_IRRIGACAO_PADRAO = 4.0   # R$ por mm por ha (energia + mão de obra + depreciação) — estimativa, validar
LAMINA_MAX_PADRAO = 6.0        # mm/dia — estimativa de pivô/aspersão, validar
DIAS_REF_SOLO = 180    # escala absoluta de dias descobertos: 1 − dias/180 (0 dias = 1,0; ≥180 = 0)
PESOS_PADRAO = {"renda": 5, "solo": 3, "agua": 3, "pragas": 3, "risco": 3}


def agua_balanco(nome: str, riscos: dict) -> dict | None:
    """Balanço hídrico diário (balde FAO-56, célula NASA POWER + solo SoilGrids) na fase crítica; None se indisponível."""
    ctx = riscos.get("agua_ctx")
    if not ctx:
        return None
    irrig = riscos.get("irrig")
    lam = irrig["lamina_max_mm_dia"] if irrig and CATALOGO[nome].get("irrigavel") else None
    return agua_fase_critica(CATALOGO[nome]["segunda"], ctx["ponto_id"], ctx["semeadura"], ctx["cad_camadas"], lam)


def irrigacao_info(nome: str, riscos: dict) -> dict | None:
    """Irrigação aplicada à candidata (lâmina média do ciclo e custo R$/ha), ou None (sequeiro, cobertura/pousio ou sem solo)."""
    irrig = riscos.get("irrig")
    if not irrig or not CATALOGO[nome].get("irrigavel"):
        return None
    b = agua_balanco(nome, riscos)
    if b is None or not b.get("irrigado"):
        return None
    return dict(lamina_media_mm=b["lamina_media_mm"], custo_r_mm_ha=irrig["custo_r_mm_ha"],
                custo_r_ha=b["lamina_media_mm"] * irrig["custo_r_mm_ha"], lamina_max_mm_dia=irrig["lamina_max_mm_dia"])


def riscos_efetivos(nome: str, c: dict, riscos: dict) -> list[str]:
    """Riscos climáticos da candidata; o veranico deixa de valer se ela é irrigada (a geada continua)."""
    irr = irrigacao_info(nome, riscos) is not None
    return [r for r in c["riscos"] if not (irr and r == "veranico_safrinha")]


def checar_restricoes(nome: str, c: dict, riscos: dict) -> list[str]:
    """Eliminações por restrição do produtor (`riscos['restr']`: excluidas {nomes}, sem_comprador {milho|trigo|sorgo|feijao|aveia_grao}).
    `c['vende']` lista as culturas de venda da rotação (verão e 2ª janela)."""
    r = riscos.get("restr") or {}
    motivos = []
    if nome in r.get("excluidas", ()):
        motivos.append("Excluída pelo produtor.")
    for v in c["vende"]:
        if v in r.get("sem_comprador", ()):
            motivos.append(f"Sem comprador local informado pelo produtor ({v}).")
    return motivos


def extras_custo(nome: str, c: dict, riscos: dict) -> list[dict]:
    """Custos extras da candidata: terceirização das máquinas que o produtor disse NÃO ter + irrigação."""
    out = []
    maq = (riscos.get("restr") or {}).get("maquinas", {})
    for m, sufixo in [(m, "") for m in c["req_maquinas"]] + [(m, " (milho verão)") for m in c["req_maquinas_verao"]]:
        if maq.get(m) is False:
            out.append(dict(chave=f"terceirizacao_{m}", rotulo=CUSTO_MAQUINA[m]["rotulo"] + sufixo, custo=CUSTO_MAQUINA[m]["custo"],
                            detalhe="estimativa de terceirização, validar com prestadores"))
    ir = irrigacao_info(nome, riscos)
    if ir:
        out.append(dict(chave="irrigacao", rotulo="Irrigação", custo=ir["custo_r_ha"],
                        detalhe=f"lâmina média {ir['lamina_media_mm']:.0f} mm/ano × R$ {ir['custo_r_mm_ha']:.2f}/mm/ha"))
    return out + estado_area.custos(c, riscos.get("estado_area"))  # fertilidade informada: calagem e adubação P/K (senão, nada)


def agua_atendida(c: dict, riscos: dict, nome: str | None = None) -> tuple[float, bool]:
    """Critério água, ESCALA ABSOLUTA 0–1. Na região, com solo: média nos 34 anos de ΣETa/ΣETc na fase crítica da
    cultura (balanço diário; muda com a data de semeadura). Pousio = 1,0.
    Sem solo (ou candidata sem modelo): média dos anos de min(1, P_ciclo/(Kc·ET0_ciclo)) da célula.
    Fora da região (sem clima pré-calculado): fallback 1 − atributo `agua` (do_clima=False). Retorna (valor, do_clima)."""
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


CRITERIOS = {"renda": "Renda", "solo": "Saúde do solo", "agua": "Água", "pragas": "Quebra de pragas", "risco": "Risco climático"}
RISCO_NOME = {"geada_safrinha": "geada no milho safrinha", "veranico_safrinha": "veranico no safrinha",
              "geada_trigo": "geada no trigo (florescimento)"}


def _texto_risco(r: str, riscos: dict, cultura: str = "milho") -> str:
    p, n = riscos[r], riscos["n_anos"]
    k = round(p * n)
    fonte_c = ("NASA POWER 1991–2024, célula ~50 km" if riscos.get("modo") == "regiao"
               else f"NASA POWER {riscos['periodo']}, ponto do centróide")
    if r == "geada_safrinha":
        sem = riscos.get("semeadura")
        if sem:
            aprox = "" if cultura == "milho" else " (janela de geada do milho usada como aproximação)"
            return f"Geada no florescimento/enchimento do {cultura} semeado em {sem}: {k} de {n} anos ({p:.0%}), {fonte_c}{aprox}."
        return f"Geada (≤ 3 °C) em jun–jul, enchimento do milho safrinha: {k} de {n} anos ({p:.0%}), {fonte_c}."
    if r == "geada_trigo":
        return f"Geada (≤ 3 °C) no florescimento do trigo (15/08–30/09): {k} de {n} anos ({p:.0%}), {fonte_c}."
    return f"Veranico ≥ 15 dias em mar–abr: {k} de {n} anos ({p:.0%}), {fonte_c}."
AVISO_ZARC = "Fora do ZARC pode comprometer crédito/seguro (não elimina a candidata)."


def _dm(ddmm: str) -> tuple[int, int]:
    d, m = map(int, ddmm.split("/"))
    return m, d


def checar_regras(c: dict, riscos: dict | None = None) -> list[str]:
    """Regras duras: devolve a lista de motivos de eliminação (vazia = válida). `riscos['semeadura']` (dd/mm da 2ª cultura)
    ativa as regras de calendário: colheita do verão e janela de semeadura da 2ª cultura."""
    motivos = []
    sem = (riscos or {}).get("semeadura")
    if c["ano_soja_2"]:
        if c["verao"] == "soja":
            motivos.append("Soja sobre soja no mesmo ano agrícola é proibida (Portaria SDA/MAPA 1.124/2024).")
        motivos.append(f"Soja na 2ª janela{f' (semeadura em {sem})' if sem else ''} fica fora da janela legal de semeadura da soja (01/09–31/12).")
    if sem and c["segue_semeadura"] and not c["ano_soja_2"]:
        # colheita do verão: a do produtor (estágio/colheita prevista), se for da mesma cultura de verão; senão a do catálogo
        prod = (riscos or {}).get("colheita_produtor")
        if prod and prod["verao"] == c["verao"]:
            colh, origem = prod["colheita"], "informada pelo produtor"
        else:
            colh, origem = c["colheita_verao"], "estimativa, validar"
        if cal.chave(cal.somar_dias(colh, cal.DIAS_PREPARO_2A)) > cal.chave(SEMEADURAS[-1]):
            motivos.append(f"Colheita tarde demais para a safrinha: a colheita de {c['nome_verao'].lower()} é estimada em ~{colh} "
                           f"({origem}) e a última semeadura da 2ª janela considerada é {SEMEADURAS[-1]}.")
        elif cal.chave(sem) < cal.chave(cal.somar_dias(colh, cal.DIAS_PREPARO_2A)):
            motivos.append(f"A colheita de {c['nome_verao'].lower()} é estimada em ~{colh} ({origem}): "
                           f"a semeadura da 2ª cultura em {sem} cairia antes dela.")
        if c["janela"] and not (_dm(c["janela"][0]) <= _dm(sem) <= _dm(c["janela"][1])):
            motivos.append(f"Semeadura em {sem} fora da janela de {c['nome_segunda']} no Oeste do PR "
                           f"({c['janela'][0]}–{c['janela'][1]}; estimativa de referência com base no ZARC/IDR-PR, validar).")
    if c["soja_viva_vazio"]:
        motivos.append("Há soja viva durante o vazio sanitário do Oeste do PR (02/06–31/08).")
    mes, dia = map(int, c["plantio_soja"].split("-"))
    if not ((9, 1) <= (mes, dia) <= (12, 31)):
        motivos.append(f"Semeadura de soja em {dia:02d}/{mes:02d} fora da janela 01/09–31/12.")
    return motivos


class SemCandidatas(ValueError):
    """Todas as rotações avaliadas foram eliminadas (regras duras + restrições do produtor). `eliminadas`: {nome: motivos}."""

    def __init__(self, msg: str, eliminadas: dict | None = None):
        super().__init__(msg)
        self.eliminadas = eliminadas or {}


def pontuar(pesos: dict[str, float], riscos: dict, ajustes: dict | None = None, nomes: list[str] | None = None) -> dict:
    """Retorna dict com tabela das válidas (DataFrame), eliminadas e contribuições. `nomes`: só avalia essas candidatas
    (nomes do CATALOGO); None = todas. Todos os critérios em ESCALA ABSOLUTA 0–1 (sem min-max entre candidatas), maior = melhor."""
    validas, eliminadas = {}, {}
    for nome in (nomes if nomes is not None else CATALOGO):
        c = CATALOGO[nome]
        m = checar_regras(c, riscos) + checar_restricoes(nome, c, riscos)
        (eliminadas if m else validas)[nome] = m or c
    if not validas:
        raise SemCandidatas("As restrições informadas eliminam todas as rotações.", eliminadas)
    # Risco: 1 - P(algum risco); com vários riscos independentes, critério = Π(1 - pᵢ). Sem risco = 1,0.
    # Candidata irrigada: o veranico não conta (a geada continua).
    rs_ef = {n: riscos_efetivos(n, c, riscos) for n, c in validas.items()}
    risco_abs = {n: float(np.prod([1 - riscos[r] for r in rs_ef[n]])) if rs_ef[n] else 1.0 for n in validas}
    # Solo: média de cobertura, fixação de N e (1 - dias descobertos/180), todos 0–1 absolutos.
    solo = {n: (c["cobertura"] + c["n_fix"] + max(0.0, 1 - c["dias_descobertos"] / DIAS_REF_SOLO)) / 3
            for n, c in validas.items()}
    # Renda pela margem INCREMENTAL sobre a soja de verão do município: incremental = margem da rotação − margem da soja
    # = (margem do verão − margem da soja) + margem da 2ª cultura (vendida: PAM × preço − custo; cobertura: − custo de
    # implantação; pousio: − custo de manejo) + bônus na soja seguinte (bonus_sc × preço da soja). Com soja no verão o primeiro
    # termo é zero (fórmula original); milho verão entra com PAM de milho 1ª safra × preço do milho − custo CONAB do milho verão.
    # renda = clip(0,5 + incremental / (2·S), 0, 1), S = max(margem da soja do município, RENDA_ESCALA_MIN):
    # incremental = +S → 1,0; zero → 0,5; −S → 0. Mede quanto a 2ª safra soma ou tira na escala da soja do próprio município.
    extras = {n: extras_custo(n, c, riscos) for n, c in validas.items()}
    margens = calcular_margens({n: c for n, c in validas.items()}, rendimentos_rk(riscos), ajustes, extras)
    renda = {n: float(np.clip(0.5 + m["incremental"] / (2 * m["escala_S"]), 0.0, 1.0)) for n, m in margens.items()}
    aviso_renda = (None if any(m["total"] > 0 for m in margens.values())
                   else "Nenhuma rotação válida tem margem total positiva com os preços e custos usados (informativo).")
    # Estado da área informado pelo produtor (problemas_area, fertilidade): deltas aditivos em solo e pragas, limitados a [0, 1].
    # Sem a informação, `riscos["estado_area"]` não existe e nada muda.
    pragas = {n: c["pragas"] for n, c in validas.items()}
    if riscos.get("estado_area"):
        aj_ea = {n: estado_area.ajuste(c, riscos["estado_area"]) for n, c in validas.items()}
        solo = {n: float(np.clip(solo[n] + aj_ea[n]["solo"], 0.0, 1.0)) for n in validas}
        pragas = {n: float(np.clip(pragas[n] + aj_ea[n]["pragas"], 0.0, 1.0)) for n in validas}
    crit = {
        "renda": renda,
        "solo": solo,
        "agua": {n: agua_atendida(c, riscos, n)[0] for n, c in validas.items()},
        "pragas": pragas,
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

# --------------------------------------------------------------------------- 6. Textos dos cards
def _r(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def local_rend(riscos: dict, chave: str) -> str:
    """Origem do rendimento PAM de uma cultura: município ou, se ele não tem PAM suficiente, média do Oeste do PR."""
    if chave in (riscos.get("rend") or {}).get("_regionais", ()):
        return "Oeste do PR (média, o município não tem PAM recente)"
    return riscos.get("rend_local") or "Oeste do PR"


def fmt_margem(m: dict, riscos: dict) -> list[str]:
    """Decomposição da margem da rotação (linhas de evidência do card)."""
    linhas = []
    for i in m["itens"]:
        local = local_rend(riscos, i["chave"])
        if i.get("extra"):
            nome_c = "custo extra" if i["custo"] >= 0 else "economia"
            linhas.append(f"{i['rotulo']}: {nome_c} R$ {_r(abs(i['custo']))}/ha ({i['detalhe']}) = {_rs(i['margem'])}.")
        elif i["sc_ha"] is not None and i.get("prod_usuario"):
            rz = i.get("razao_p20")
            ruim = (f"ano ruim: rendimento próprio × p20/média da PAM ({rz:.2f}) = {i['sc_ha_ruim']:.0f} sc/ha → R$ {_r(i['margem_ano_ruim'])}/ha"
                    if i["sc_ha_ruim"] is not None else "sem ano ruim (PAM sem série)")
            linhas.append(f"{i['rotulo']}: {i['sc_ha']:.0f} sc/ha (informado pelo produtor; PAM {local}: {i['sc_ha_pam']:.0f} sc/ha) × "
                          f"R$ {i['preco']:.2f}/sc ({fonte_preco(i)}) − custo R$ {_r(i['custo'])}/ha ({fonte_custo(i, m['linha_custo'])}) "
                          f"= R$ {_r(i['margem'])}/ha ({ruim}).")
        elif i["sc_ha"] is not None:
            linhas.append(f"{i['rotulo']}: {i['sc_ha']:.0f} sc/ha (PAM {local} {i['anos']}) × R$ {i['preco']:.2f}/sc ({fonte_preco(i)}) − custo "
                          f"R$ {_r(i['custo'])}/ha ({fonte_custo(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha "
                          f"(CV do rendimento {i['cv']:.0%}; ano ruim, p20 de 10 anos = {i['sc_ha_ruim']:.0f} sc/ha → "
                          f"R$ {_r(i['margem_ano_ruim'])}/ha).")
        else:
            linhas.append(f"{i['rotulo']}: sem venda, custo de implantação R$ {_r(i['custo'])}/ha ({fonte_custo(i, m['linha_custo'])}) = R$ {_r(i['margem'])}/ha.")
    detalhe_bonus = (f" ({m['bonus_verao_sc']:g} sc/ha do milho verão no lugar da soja + {m['bonus_sc'] - m['bonus_verao_sc']:g} da 2ª cultura)"
                     if m["bonus_verao_sc"] else "")
    linhas.append(f"Bônus na soja seguinte: {m['bonus_sc']:g} sc/ha × R$ {m['preco_soja']:.2f}/sc = R$ {_r(m['bonus'])}/ha{detalhe_bonus} "
                  f"(palhada/N e quebra de ciclo de doença, estimativa de referência).")
    t = (f"Total da rotação: R$ {_r(m['total'])}/ha/ano; incremental da 2ª safra (sem a soja, com o bônus): R$ {_r(m['incremental'])}/ha, "
         f"na escala S = R$ {_r(m['escala_S'])}/ha (margem da soja do município, mín. {_r(RENDA_ESCALA_MIN)})")
    if m["total_ano_ruim"] is not None:
        t += f"; em ano ruim (rendimento p20): R$ {_r(m['total_ano_ruim'])}/ha/ano"
    linhas.append(t + ".")
    return linhas


def _rs(x: float) -> str:
    return f"R$ {_r(x)}/ha" if x >= -0.5 else f"−R$ {_r(-x)}/ha"


def _c2(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _nome_curto(n: str) -> str:
    return n.replace("Soja → ", "")


def _texto_criterio(k: str, alt: str, atu: str, res: dict, d: float) -> str:
    """Frase curta sobre o critério k da alternativa `alt` contra a atual `atu` (d = Δcritério, com sinal)."""
    t, m = res["tabela"].set_index("candidata"), res["margens"]
    ca, cb = t.loc[alt], t.loc[atu]
    ganha = d > 0
    if k == "renda":
        a, b = m[alt]["incremental"], m[atu]["incremental"]
        if ganha:
            pct = f" (+{(a - b) / abs(b):.0%})" if b > 0 else ""
            return f"soma {_rs(a)} contra {_rs(b)} na 2ª safra{pct}"
        return f"abre mão de {_rs(b - a)} na 2ª safra ({_rs(a)} contra {_rs(b)})"
    if k == "solo":
        da, db = CATALOGO[alt]["dias_descobertos"], CATALOGO[atu]["dias_descobertos"]
        return (f"{'melhora' if ganha else 'piora'} a saúde do solo ({_c2(ca['solo'])} contra {_c2(cb['solo'])}; "
                f"~{da} dias de solo descoberto contra {db})")
    if k == "agua":
        return f"{'atende melhor' if ganha else 'atende pior'} a demanda de água ({_c2(ca['agua'])} contra {_c2(cb['agua'])})"
    if k == "pragas":
        return f"{'quebra melhor' if ganha else 'quebra menos'} o ciclo de pragas ({_c2(ca['pragas'])} contra {_c2(cb['pragas'])})"
    pa, pb = 1 - ca["risco"], 1 - cb["risco"]
    return (f"{'reduz' if ganha else 'aumenta'} o risco climático (algum evento adverso em {pa:.0%} dos anos "
            f"contra {pb:.0%})")


def por_que_comparado(res: dict, nome: str, atual: str | None) -> str | None:
    """Texto do 'por quê' de `nome` comparado com a rotação atual (None se a atual não está entre as válidas)."""
    tab = res["tabela"]
    nomes = list(tab["candidata"])
    if atual is None or atual not in nomes or nome not in nomes:
        return None
    if nome == atual:
        pos, n = nomes.index(atual) + 1, len(nomes)
        if pos == 1:
            o = tab.iloc[1]
            return (f"É a rotação atual; ficou em 1º lugar entre {n} opções válidas. A 2ª melhor ({_nome_curto(o['candidata'])}) "
                    f"tem nota {_c2(o['nota'])}.")
        b = tab.iloc[0]
        return (f"É a rotação atual; ficou em {pos}º lugar entre {n} opções válidas. A melhor alternativa "
                f"({_nome_curto(b['candidata'])}) tem nota {_c2(b['nota'])}.")
    t = tab.set_index("candidata")
    w = res["pesos_norm"]
    dif = {k: w[k] * (t.loc[nome, k] - t.loc[atual, k]) for k in CRITERIOS}
    tops = [k for k, v in sorted(dif.items(), key=lambda kv: -abs(kv[1]))[:3] if abs(v) >= 0.005]
    frases = [_texto_criterio(k, nome, atual, res, dif[k]) for k in tops]
    cab = f"Em relação à atual ({_nome_curto(atual)}): "
    if not frases:
        txt = cab + "desempenho praticamente igual nos cinco critérios."
    elif len(frases) == 1:
        txt = cab + frases[0] + "."
    else:
        txt = cab + ", ".join(frases[:-1]) + " e " + frases[-1] + "."
    if "risco" not in tops and 1 - t.loc[nome, "risco"] > 0.005:
        txt += f" Risco climático igual (algum evento adverso em {1 - t.loc[nome, 'risco']:.0%} dos anos)."
    return txt


def montar_card(linha: pd.Series, atual: bool, riscos: dict, dias_solo_ndvi: float, margem: dict | None = None,
                por_que_cmp: str | None = None) -> dict:
    """`por_que_cmp`: texto de `por_que_comparado` (comparação com a rotação atual); se None, só as maiores contribuições."""
    c = CATALOGO[linha["candidata"]]
    top = sorted(linha["contrib"].items(), key=lambda kv: -kv[1])[:2]
    contribs = "Maiores contribuições para a nota: " + " e ".join(f"{CRITERIOS[k]} ({_c2(v)})" for k, v in top) + "."
    por_que = f"{por_que_cmp} {contribs}" if por_que_cmp else contribs
    ev = [f"Dias de solo descoberto/ano (catálogo): ~{c['dias_descobertos']} dias."]
    if atual and not np.isnan(dias_solo_ndvi):
        ev.append(f"NDVI observado (NASA HLS): ~{dias_solo_ndvi:.0f} dias/ano com NDVI<{LIMIAR_SOLO}.")
    if margem is not None:
        ev += fmt_margem(margem, riscos)
    ag, do_clima = agua_atendida(c, riscos, linha["candidata"])
    bal = agua_balanco(linha["candidata"], riscos)
    fonte_solo = ("análise de solo do produtor" if (riscos.get("solo") or {}).get("fonte") == "análise de solo do produtor"
                  else "solo SoilGrids")
    ir = irrigacao_info(linha["candidata"], riscos)
    if c["ciclo_agua"] is None:
        ev.append("Água: sem cultura, sem demanda hídrica (nota 1,00); o custo do pousio aparece em solo.")
    elif bal is not None:
        ev.append(f"Água: na fase crítica ({bal['fase']}, semeadura em {bal['semeadura']}), a água no solo atendeu em média "
                  f"{bal['media']:.0%} da demanda; em {bal['n_abaixo']} de {bal['n_anos']} anos ficou abaixo de 70% "
                  f"(balanço diário NASA POWER + {fonte_solo}{', irrigado' if bal.get('irrigado') else ''}, CAD {bal['taw_mm']:.0f} mm).")
    elif do_clima:
        nome_c = c["nome_segunda"]
        ev.append(f"Água: chuva cobre em média {ag:.0%} da demanda ({nome_c}, Kc {c['kc']:.2f}; "
                  f"NASA POWER {riscos['periodo']}, FAO-56).")
    else:
        ev.append(f"Água: estimativa fixa do catálogo ({ag:.0%}); sem clima pré-calculado fora do Oeste do PR.")
    if ir:
        ev.append(f"Irrigado: lâmina média {ir['lamina_media_mm']:.0f} mm/ano, custo R$ {_r(ir['custo_r_ha'])}/ha "
                  f"(R$ {ir['custo_r_mm_ha']:.2f}/mm/ha, lâmina máx. {ir['lamina_max_mm_dia']:g} mm/dia; o ganho de produtividade "
                  f"da irrigação não é modelado, o rendimento esperado não muda).")
    rs_ef = riscos_efetivos(linha["candidata"], c, riscos)
    for r in rs_ef:
        ev.append(_texto_risco(r, riscos, "milho" if c["milho"] else c["nome_segunda"]))
    if ir and len(rs_ef) < len(c["riscos"]):
        ev.append("Veranico não conta no risco: a candidata é irrigada (a geada continua).")
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
    if margem is not None and margem["total"] >= 2000: ben.append(f"Margem da rotação alta (~R$ {_r(margem['total'])}/ha/ano).")
    if c["ciclo_agua"] is None or agua_atendida(c, riscos, linha["candidata"])[0] >= 0.9: ben.append("Chuva atende praticamente toda a demanda hídrica.")
    solo_p = riscos.get("solo") or {}
    if solo_p.get("fonte") == "análise de solo do produtor":
        lacuna_cad = ("CAD vinda da análise do produtor (informada ou por Saxton & Rawls com a análise), "
                      "tomada como representativa do perfil de 0–60 cm.")
    else:
        lacuna_cad = "CAD por pedotransferência (Saxton & Rawls), pode errar em latossolos tropicais."
    ea = estado_area.card(c, riscos.get("estado_area"))
    ev += ea["evidencias"]
    lacunas = ([] if riscos.get("solo") else ["Textura/CAD do solo (SoilGrids) não considerada (talhão fora do Oeste do PR)."]) + [
               lacuna_cad,
               "Umidade do solo (SMAP) e chuva satelital (GPM) não usadas.",
               *([f"{c['nome_verao']} no verão: risco climático e balanço hídrico do verão não modelados (só a 2ª janela entra nesses critérios)."]
                 if c["verao"] != "soja" else []),
               "Renda: preço = média PR dos últimos 12 meses (SEAB/DERAL); custo CONAB de Londrina/Ponta Grossa (não do Oeste do PR); "
               "custo de cobertura/pousio, bônus da palhada/N e Kc são estimativas de referência.", *ea["lacunas"]]
    revisar = [AVISO_ZARC, "Confirmar com o agrônomo calendário, cultivar e janela do ZARC.", *ea["revisar"]]
    if c["milho_sobre_milho"]:
        revisar.append(TEXTO_MILHO_SOBRE_MILHO)
        ev.append(f"Pragas: milho sobre milho, nota de catálogo {c['pragas_base']:.2f} − penalidade {PENALIDADE_MILHO_SOBRE_MILHO:.2f} "
                  f"= {c['pragas']:.2f} (cigarrinha-do-milho/enfezamento; estimativa de referência).")
    if "geada_safrinha" in c["riscos"] and riscos["geada_safrinha"] >= 0.2:
        revisar.append(f"Geada (≤ 3 °C) no safrinha em {riscos['geada_safrinha']:.0%} dos anos"
                       + (f" com semeadura em {riscos['semeadura']}" if riscos.get("semeadura") else "")
                       + ": avaliar data de semeadura/híbrido.")
    if "veranico_safrinha" in rs_ef and riscos["veranico_safrinha"] >= 0.2:
        revisar.append(f"Veranico ≥15 dias em mar–abr em {riscos['veranico_safrinha']:.0%} dos anos.")
    if "geada_trigo" in c["riscos"] and riscos["geada_trigo"] >= 0.2:
        revisar.append(f"Geada no florescimento do trigo em {riscos['geada_trigo']:.0%} dos anos.")
    if c["dias_descobertos"] >= 100: revisar.append("Muitos dias de solo exposto: risco de erosão e plantas daninhas.")
    maq = (riscos.get("restr") or {}).get("maquinas", {})
    avisos = list(dict.fromkeys(CUSTO_MAQUINA[m]["aviso"] for m in c["req_maquinas"] + c["req_maquinas_verao"] if maq.get(m) is False))
    mer = c["mercado_oeste_pr"]
    mercado = dict(nivel=mer["nivel"], texto=mer["texto"], estimativa=MERCADO_ESTIMATIVA)
    ev.append(f"Mercado no Oeste do PR: {mer['nivel']}; {mer['texto']} ({MERCADO_ESTIMATIVA}).")
    return dict(por_que=por_que, evidencia=ev, beneficios=ben or ["Sem benefício marcante nos critérios avaliados."],
                lacunas=lacunas, revisar=revisar, avisos=avisos, mercado=mercado, irrigacao=ir)


def fmt_diagnostico(d: dict) -> list[str]:
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
    sem = sys.argv[1] if len(sys.argv) > 1 else SEMEADURA_PADRAO
    t = carregar_talhao()
    dec = "sem dado" if t["declividade"] is None else f"{t['declividade']:.1f}% (p90 {t['declividade_p90']:.1f}%, {t['classe_embrapa']})"
    alt = "sem dado" if t["altitude"] is None else f"{t['altitude']:.0f} m"
    print(f"Talhão {t['id']}: {t['area_ha']:.1f} ha  lat={t['lat']:.5f} lon={t['lon']:.5f} declividade={dec}  altitude={alt}")
    print("Histórico MapBiomas:", t["historico"])
    nd = carregar_ndvi()
    pk = picos_por_ano_agricola(nd)
    print("Picos NDVI por ano agrícola:", pk, "→", detectar_rotacao(pk))
    print(f"Dias/ano com NDVI<{LIMIAR_SOLO}: {dias_solo_por_ano(nd):.0f}; faixas: {len(faixas_solo(nd))}")
    rk, origem = obter_clima(t["lat"], t["lon"], sem)
    rk = enriquecer(rk, t)
    print(f"Clima [{rk['modo']}]: {origem} · {rk['fonte']} · semeadura safrinha {rk['semeadura']}")
    if rk["modo"] == "reduzido":
        print("AVISO: modo reduzido (fora do Oeste do PR; POWER ao vivo, sem diagnóstico nem tabela por data).")
    else:
        m = rk["municipio"]
        print(f"Célula {rk['celula']['ponto_id']} (elev {rk['celula']['elev']:.0f} m); município (contexto): {m['nome']} ({m['cod_ibge']})")
        print("Geada ≤3 °C no safrinha por data de semeadura:",
              {r["semeadura"]: f"{r['prob']:.2f} ({r['anos']}/{r['n_anos']})" for r in rk["geada_tabela"]})
        for linha in fmt_diagnostico(rk["diagnostico"]):
            print("  -", linha)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rk.items()
           if k in ("geada_safrinha", "geada_trigo", "veranico_safrinha", "n_anos", "periodo")})
    print("Chuva mensal média (mm):", rk["chuva_mensal"].round(0).to_dict())
    if rk.get("solo"):
        print("Solo:", fmt_solo(rk))
        print("PAM:", fmt_pam(rk))
    print("Água atendida (fase crítica, balanço diário):", {n.replace("Soja → ", ""): round(agua_atendida(c, rk, n)[0], 3) for n, c in CATALOGO.items()})
    for n in CATALOGO:
        b = agua_balanco(n, rk)
        if b:
            print(f"  {n}: {b['fase']} ({b['semeadura']}) média {b['media']:.3f}, {b['n_abaixo']}/{b['n_anos']} anos <0,7, TAW {b['taw_mm']:.0f} mm")
    ajustes = {"linha_custo": sys.argv[2]} if len(sys.argv) > 2 else None
    res = pontuar(PESOS_PADRAO, rk, ajustes)
    print(res["tabela"].drop(columns="contrib").round(2).to_string())
    if res["aviso_renda"]:
        print("AVISO:", res["aviso_renda"])
    print("Rendimento:", rk["rend"]["_origem"])
    for n, m in res["margens"].items():
        print(f"\n{n}:")
        for l in fmt_margem(m, rk):
            print("  -", l)
    for n, m in res["eliminadas"].items():
        print("ELIMINADA:", n, m)
