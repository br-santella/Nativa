"""Service layer of the Field Shift engine (no FastAPI): accepts any polygon in Paraná.

Public functions: options(), diagnose(area, sowing), recommend(area, ...), warm_up().
Exceptions: OutOfRegion, InvalidInput, ExternalQueryError. Every output is JSON-serializable (NaN -> None).

`area` (exactly one shape):
  {"geometry": <GeoJSON Polygon/MultiPolygon or Feature>}  EPSG:4326, [lon, lat] order
  {"lat": float, "lon": float}  point -> ~100 ha square (1000 m x 1000 m, UTM 22S) centered on the point
  {"talhao_id": "72638"}        FTW demo field (id from the FTW parquet)
"""
from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.error import URLError

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry

from field_shift import crop_calendar as cal
from field_shift.app import engine as E
from field_shift.app import field_state as EA
from field_shift.i18n import Join, Msg
from field_shift.climate.lookup import indicators_for
from field_shift.pam import productivity as pam_yield
from field_shift.pam.productivity import text as pam_text
from field_shift.region import inside_region, inside_oeste, mapbiomas_history, relief
from field_shift.region.clip import REGION
from field_shift.income import load_reference, cost_source, price_source, yields
from field_shift.soil.soil import ANALYSIS_SOURCE, text as soil_text

VERSION = "0.1.0"
AREA_MAX_HA = 5000.0
POINT_AREA_HA = 100.0
CRS_M = 32722  # UTM 22S (m), for areas and the point square


# Shown when the area centroid is in Paraná but outside the Oeste mesoregion: the engine works statewide (climate, soil, PAM of the
# municipality or its mesoregion, ZARC and the ADAPAR region), but prices/costs are statewide references and the catalog texts
# (sowing windows, market) and the validation come from the Oeste.
WARNINGS_OUTSIDE_OESTE = [
    "Área fora do Oeste do Paraná: preços (média estadual SEAB/DERAL) e custos (fichas CONAB de Londrina, Ponta Grossa e Francisco "
    "Beltrão) são referências do estado e podem diferir na sua região; informe os seus em `ajustes`. As janelas de semeadura e o "
    "mercado do catálogo são do Oeste do PR; a renda, o risco e a concordância com o ZARC foram testados no estado todo.",
    "Fora do Oeste, a cobertura (milheto/crotalária) fica em 1º com mais frequência, pelos critérios de solo e pragas; na renda "
    "realizada (IBGE PAM, safras passadas) ela perdeu do milho safrinha na média de todas as mesorregiões do PR. Quando a 1ª "
    "colocada não é a de maior renda, o card diz quanto se abre mão.",
]


def soy_calendar_warning(cs: dict) -> str:
    """Warning with the soybean window of the area's ADAPAR region (the calendar is regional and changes every crop year)."""
    return (f"Calendário da soja desta área: {cs['nome']}, vazio sanitário {cs['vazio'][0]}–{cs['vazio'][1]} e semeadura "
            f"{cs['semeadura'][0]}–{cs['semeadura'][1]} (safra {cs['safra']}, {cs['portaria']}); confirme a portaria vigente da ADAPAR "
            "e o ZARC do município.")


class OutOfRegion(Exception):
    """Area (or part of it) outside Paraná."""


class InvalidInput(Exception):
    """Invalid input: geometry, sowing, rotation, weights, adjustments, area > 5000 ha etc."""


class ExternalQueryError(Exception):
    """Timeout or connection failure when querying external APIs (NASA POWER / SoilGrids)."""


# Rotation = pair (summer crop, 2nd-window crop). Stable id "<verao>__<segunda>" (e.g. soja__milho_safrinha) -> catalog name.
# The old API slugs (soybean-only summer: milho_safrinha, trigo...) are still accepted via E.LEGACY (milho_safrinha = soja__milho_safrinha).
ROTATIONS: dict[str, str] = dict(E.NOME_DE)
_SLUG_DE = dict(E.ID_DE)
SUMMER_CROPS = tuple(E.SUMMER)
SECOND_CROPS = tuple(E.SECOND)

_DESCRIPTION = {  # per 2nd-window crop
    "milho_safrinha": "Milho na segunda safra, após a soja; rotação mais comum no Oeste do PR.",
    "milho_braquiaria": "Milho safrinha consorciado com braquiária: grãos mais palhada para o plantio direto.",
    "trigo": "Trigo de inverno após a soja; sensível a geada no florescimento.",
    "aveia": "Aveia para cobertura/palha (e eventual grão) no inverno.",
    "milheto_crotalaria": "Cobertura de milheto e crotalária: palhada e fixação de nitrogênio, sem venda de grão.",
    "pousio": "Sem cultura na segunda janela; solo exposto e sem renda adicional.",
    "soja_safrinha": "Soja sobre soja no mesmo ano agrícola; proibida pela regulação (sempre eliminada).",
    "sorgo": "Sorgo granífero na segunda safra: tolerante à seca, sem cigarrinha do milho; usa o maquinário e o canal de venda de grãos.",
    "feijao_safrinha": "Feijão de 2ª safra: ciclo curto e boa renda em ano bom, mas sensível a geada e a déficit hídrico e hospedeiro do mofo-branco.",
    "nabo_forrageiro": "Cobertura de nabo forrageiro: ciclagem de nutrientes e supressão de daninhas, palha de decomposição rápida; sem venda de grão.",
    "aveia_nabo": "Mix de cobertura aveia + nabo forrageiro: palha duradoura e ciclagem de nutrientes, sem venda de grão.",
}

_CRITERION_METHOD = {
    "renda": "Margem incremental da 2ª safra (rendimento PAM do município × preço SEAB/DERAL − custo CONAB; cobertura/pousio = "
             "−custo estimado; mais o bônus de palhada/N na soja seguinte; milho safrinha, milho + braquiária e trigo pela média realizada das "
             "últimas 5 safras no município, quando há histórico), na escala S = R$ 1.110/ha, a mesma no Paraná todo (margem mediana da soja no Oeste "
             "do PR): renda = 0,5 + 0,5·tanh(incremental / S). Incremental zero = 0,5; +S ≈ 0,88; −S ≈ 0,12.",
    "solo": "Média de cobertura de palha, fixação de N e (1 − dias de solo descoberto/180); valores de catálogo "
            "(estimativas de referência, validar com agrônomo/Embrapa).",
    "agua": "Média nos 34 anos (1991–2024) de ΣETa/ΣETc na fase crítica da 2ª cultura, por balanço hídrico diário "
            "(NASA POWER + CAD do solo do polígono, SoilGrids); depende da data de semeadura. Pousio = 1,0.",
    "pragas": "Potencial de quebra de ciclo de pragas e doenças por rotação; valor de catálogo (0–1), estimativa a validar.",
    "risco": "Π(1 − p) dos riscos climáticos da 2ª cultura em 1991–2024: geada na fase crítica (célula NASA POWER ~50 km) e "
             "déficit hídrico na fase crítica (anos com ETa/ETc < 0,55 no balanço diário com o solo da área; sem solo, veranico "
             "≥ 15 dias em mar–abr); sem risco considerado = 1,0.",
}

_COST_ALIAS = {"milho": "milho_2safra", "milho_verao": "milho_1safra", "feijao": "feijao_2safra"}
_PRODUCTIVITY = ("soja", "milho_2safra", "trigo", "milho_1safra", "feijao_2safra", "sorgo")


# Utilities
def _clean(o):
    """Convert to native JSON types: numpy -> python, NaN/inf -> None, tuples -> lists, keys -> str."""
    if o is None or isinstance(o, (str, bool)):
        return o
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, pd.Series):
        return _clean(o.to_dict())
    if isinstance(o, pd.DataFrame):
        return _clean(o.to_dict("records"))
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if o is pd.NaT:
        return None
    return str(o)


def _num(v, nome: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
        raise InvalidInput(f"{nome} deve ser numérico (recebido: {v!r}).")
    f = float(v)
    if not math.isfinite(f):
        raise InvalidInput(f"{nome} deve ser finito.")
    if (lo is not None and f < lo) or (hi is not None and f > hi):
        raise InvalidInput(f"{nome} fora do intervalo [{lo}, {hi}] (recebido: {f}).")
    return f


@lru_cache(maxsize=1)
def _region_info() -> dict:
    r = gpd.read_file(REGION)
    b = [round(float(x), 4) for x in r.total_bounds]
    mun = gpd.read_file(REGION.parent / "municipios_pr.geojson")
    return dict(nome="Paraná (IBGE 41)", bbox=b, n_municipios=int(len(mun)))


def _project_to_m():
    from pyproj import Transformer
    return (Transformer.from_crs(4326, CRS_M, always_xy=True), Transformer.from_crs(CRS_M, 4326, always_xy=True))


@lru_cache(maxsize=1)
def _transformers():
    return _project_to_m()


def _area_ha(poly: BaseGeometry) -> float:
    from shapely.ops import transform
    t, _ = _transformers()
    return float(transform(t.transform, poly).area / 10_000.0)


def _centroid(poly: BaseGeometry) -> tuple[float, float]:
    from shapely.ops import transform
    t, inv = _transformers()
    c = transform(t.transform, poly).centroid
    lon, lat = inv.transform(c.x, c.y)
    return float(lat), float(lon)


def _geojson(poly: BaseGeometry) -> dict:
    import shapely
    return json.loads(shapely.to_geojson(shapely.set_precision(poly, 1e-6)))


# Resolve the area
def _polygon_geojson(g) -> BaseGeometry:
    if not isinstance(g, dict):
        raise InvalidInput("'geometry' deve ser um objeto GeoJSON (Polygon, MultiPolygon ou Feature).")
    if g.get("type") == "Feature":
        g = g.get("geometry")
        if not isinstance(g, dict):
            raise InvalidInput("Feature sem geometria.")
    if g.get("type") not in ("Polygon", "MultiPolygon"):
        raise InvalidInput(f"Tipo de geometria não suportado: {g.get('type')!r} (use Polygon, MultiPolygon ou Feature).")
    try:
        poly = shape(g)
    except Exception as e:  # coordenadas malformadas
        raise InvalidInput(f"Geometria GeoJSON malformada: {e}") from e
    if poly.is_empty:
        raise InvalidInput("Geometria vazia.")
    minx, miny, maxx, maxy = poly.bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise InvalidInput("Coordenadas não finitas.")
    if not (-180 <= minx and maxx <= 180 and -90 <= miny and maxy <= 90):
        raise InvalidInput("Coordenadas fora de EPSG:4326 (esperado [lon, lat] em graus).")
    if not poly.is_valid:
        from shapely.validation import explain_validity
        raise InvalidInput(f"Geometria inválida: {explain_validity(poly)}.")
    return poly


def _resolver_area(area: dict) -> dict:
    if not isinstance(area, dict):
        raise InvalidInput("'area' deve ser um objeto com 'geometry', 'lat'+'lon' ou 'talhao_id'.")
    shape_geom, shape_point, shape_fid = "geometry" in area, ("lat" in area or "lon" in area), "talhao_id" in area
    if sum([shape_geom, shape_point, shape_fid]) != 1:
        raise InvalidInput("'area' deve ter exatamente uma forma: {'geometry'}, {'lat','lon'} ou {'talhao_id'}.")
    tid = None
    if shape_fid:
        tid = str(area["talhao_id"])
        gdf = E.fields_gdf()
        row = gdf[gdf["id"].astype(str) == tid]
        if row.empty:
            raise InvalidInput(f"talhao_id {tid!r} não encontrado entre os talhões demo.")
        poly = gpd.GeoSeries([row.iloc[0].geometry], crs=gdf.crs).to_crs(4326).iloc[0]
        origin, lat, lon = "talhao_id", *_centroid(poly)
    elif shape_point:
        if not ("lat" in area and "lon" in area):
            raise InvalidInput("Ponto exige 'lat' e 'lon'.")
        lat, lon = _num(area["lat"], "lat", -90, 90), _num(area["lon"], "lon", -180, 180)
        if not inside_region(Point(lon, lat)):
            raise OutOfRegion(f"O ponto (lat {lat:.5f}, lon {lon:.5f}) está fora do Paraná; o motor só cobre o estado.")
        t, inv = _transformers()
        x, y = t.transform(lon, lat)
        h = 500.0
        sw, ne = inv.transform(x - h, y - h), inv.transform(x + h, y + h)
        poly = box(sw[0], sw[1], ne[0], ne[1])
        origin = "ponto"
    else:
        poly = _polygon_geojson(area["geometry"])
        origin, lat, lon = "geometry", *_centroid(poly)
    ha = _area_ha(poly)
    if ha <= 0:
        raise InvalidInput("Área nula.")
    if ha > AREA_MAX_HA:
        raise InvalidInput(f"Área de {ha:.0f} ha excede o limite de {AREA_MAX_HA:.0f} ha.")
    if not inside_region(poly):
        raise OutOfRegion("A área não está inteiramente dentro do Paraná (confira a ordem [lon, lat] das coordenadas).")
    return dict(origem=origin, talhao_id=tid, poly=poly, area_ha=ha, lat=lat, lon=lon)


# Diagnosis
def _validate_sowing(s) -> str:
    if s not in E.SOWINGS_2ND:
        raise InvalidInput(f"semeadura_safrinha inválida: {s!r}. Opções: {E.SOWINGS_2ND}.")
    return s


def _legacy(id_: str | None) -> str | None:
    """Old API slug (soybean-only summer, the 7 original rotations): soja__milho_safrinha -> milho_safrinha; None for the others."""
    return id_.split("__", 1)[1] if id_ in E.LEGACY.values() else None


def _ids(id_: str) -> dict:
    """{'id': new id} + 'id_legado' (old slug) when there is one."""
    leg = _legacy(id_)
    return dict(id=id_, **({"id_legado": leg} if leg else {}))


def _resolver_id(x, field_name: str) -> str:
    """Accept the new id ('soja__milho_safrinha') or the old slug ('milho_safrinha' = soja__milho_safrinha)."""
    if isinstance(x, str) and x in ROTATIONS:
        return x
    if isinstance(x, str) and x in E.LEGACY:
        return E.LEGACY[x]
    raise InvalidInput(f"{field_name} desconhecida: {x!r}. Opções: {list(ROTATIONS)} (ou os slugs antigos {list(E.LEGACY)}).")


def _normalize_rotations(r) -> list[str] | None:
    """Validate `rotacoes` ([{'verao','segunda'}], catalog enums, no duplicates, not empty). Return the ids in the given order, or None."""
    if r is None:
        return None
    if not isinstance(r, (list, tuple)) or not r:
        raise InvalidInput("'rotacoes' deve ser uma lista não vazia de {'verao', 'segunda'}.")
    ids = []
    for x in r:
        if not isinstance(x, dict) or set(x) != {"verao", "segunda"}:
            raise InvalidInput(f"Cada rotação deve ser {{'verao': ..., 'segunda': ...}} (recebido: {x!r}).")
        if x["verao"] not in SUMMER_CROPS:
            raise InvalidInput(f"verao desconhecida: {x['verao']!r}. Opções: {list(SUMMER_CROPS)}.")
        if x["segunda"] not in SECOND_CROPS:
            raise InvalidInput(f"segunda desconhecida: {x['segunda']!r}. Opções: {list(SECOND_CROPS)}.")
        ids.append(E.rotation_id(x["verao"], x["segunda"]))
    if len(set(ids)) != len(ids):
        raise InvalidInput("'rotacoes' tem combinações duplicadas.")
    return ids


def _detected_rotation(tid: str | None) -> dict:
    void = dict(rotacao=None, fonte=None, dias_solo_descoberto=None)
    if tid is None or not (E.ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv").exists():
        return void
    nd = E.load_ndvi(tid)
    peaks = E.peaks_by_crop_year(nd)
    return dict(rotacao=_legacy(_SLUG_DE.get(E.detect_rotation(peaks))),
                fonte="NDVI HLS Sentinel-2/Landsat (NASA): picos de verde por ano agrícola (set–ago) = " + json.dumps(peaks),
                dias_solo_descoberto=E.bare_soil_days_by_year(nd), picos_por_ano_agricola=peaks)


def _load_nasa_cache() -> dict | None:
    """Read data/nasa_normalizado.json from disk if it exists (supports a dict with metadata or a list of records)."""
    path_ = E.ROOT / "data/nasa_normalizado.json"
    if not path_.exists():
        return None
    try:
        content = json.loads(path_.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(content, dict) and content:
        return content
    if isinstance(content, list) and content:
        return {"dados": content, "total_registros": len(content)}
    return None


def _context(area: dict, sowing: str, soil_analysis: dict | None = None, fert: dict | None = None) -> dict:
    """Compute everything diagnose/recommend need; return a dict with `rk` (enriched climate) and `diag` (output)."""
    sowing = _validate_sowing(sowing)
    a = _resolver_area(area)
    poly = a["poly"]
    warnings = []
    try:
        rel = relief(poly)
    except ValueError as e:
        raise InvalidInput(f"Sem dados de relevo para a área: {e}") from e

    cache_nasa = _load_nasa_cache()
    try:
        rk, origin = E.get_climate(a["lat"], a["lon"], sowing)
    except (TimeoutError, URLError, ConnectionError, requests.RequestException) as e:
        raise ExternalQueryError(
            f"Timeout ou falha de ligação ao consultar dados climáticos da NASA: {e}"
        ) from e

    if rk.get("modo") != "regiao":
        raise OutOfRegion("Centroide sem indicadores climáticos pré-calculados (fora do Paraná).")

    try:
        rk = E.enrich(rk, dict(poly=poly), soil_analysis)
    except (TimeoutError, URLError, ConnectionError, requests.RequestException) as e:
        raise ExternalQueryError(
            f"Timeout ou falha de ligação ao consultar dados externos de solo/clima: {e}"
        ) from e

    used_disk_cache = cache_nasa is not None or "cache" in str(origin).lower()
    if cache_nasa is not None:
        query_dt = cache_nasa.get("data_consulta") or cache_nasa.get("consultado_em")
        detail = f" (consultado em {query_dt})" if query_dt else ""
        warnings.append(f"Cache local NASA utilizado: data/nasa_normalizado.json{detail}.")
    elif "cache" in str(origin).lower():
        warnings.append(f"Cache local NASA utilizado: {origin}.")

    if soil_analysis is None and fert is not None and rk["solo"] is not None:
        warnings.append("Análise de solo só com fertilidade (sem argila/areia nem CAD): textura e CAD seguem o SoilGrids.")
    if not inside_oeste(Point(a["lon"], a["lat"])):
        warnings += WARNINGS_OUTSIDE_OESTE + [soy_calendar_warning(rk["calendario_soja"])]
    if a["origem"] == "ponto":
        warnings.append(f"Ponto convertido em quadrado de ~{POINT_AREA_HA:.0f} ha centrado nele; relevo, histórico e solo "
                      "valem para esse quadrado, não para a lavoura real.")
    if rk["solo"] is not None:
        warnings += rk["solo"].get("avisos", [])
    if rk["solo"] is None:
        warnings.append("Sem dados de solo (SoilGrids) para a área: o critério água usa a estimativa por chuva/ET0 da célula.")
    if rk["rend"]["_origem"].startswith("média"):
        warnings.append(Msg("Sem PAM do município: rendimento = {0}.", rk["rend"]["_origem"]))
    hist = mapbiomas_history(poly)
    history = [dict(ano=int(r.ano), classe=int(r.classe), nome_classe=r.nome_classe,
                      fracao_dominante=None if pd.isna(r.fracao_dominante) else float(r.fracao_dominante))
                 for r in hist.itertuples()]
    last_items = [h for h in history if h["ano"] >= max(x["ano"] for x in history) - 2]
    if last_items and not any(h["nome_classe"] and ("Soja" in h["nome_classe"] or "Temporária" in h["nome_classe"]
                                                  or "Agri" in h["nome_classe"] or "Lavoura" in h["nome_classe"])
                           for h in last_items):
        warnings.append("O MapBiomas dos últimos anos não indica lavoura na área; confira o polígono.")
    rel_out = dict(rel, texto=f"Declividade média {rel['declividade_media']:.1f}% ({rel['classe_embrapa']}), "
                              f"altitude média {rel['altitude_media']:.0f} m.")
    solo_out = None
    if rk["solo"]:
        s = rk["solo"]
        solo_out = dict(p30=s["p30"], prof=s["prof"], cad_mm_cm=s["cad_mm_cm"], cad_mm_0_30=s["cad_mm_0_30"],
                        cad_mm_0_60=s["cad_mm_0_60"], classe_textura=s["classe_textura"], cad_metodo=s["cad_metodo"],
                        texto=soil_text(s), fonte=s.get("fonte") or "SoilGrids (ISRIC), média no polígono")
        if s.get("fonte") == ANALYSIS_SOURCE:
            solo_out["profundidade_amostra_cm"] = s["amostra_profundidade_cm"]
    fert_out = None
    if fert:
        fert_out = dict(valores=fert["valores"], classes=fert["classes"], v_pct_origem=fert["v_origem"], severidade_acidez=fert["severidade_acidez"],
                        nao_informados=fert["ausentes"], fonte="análise de solo do produtor; classes: " + EA.MANUAL_SOURCE)
        if fert.get("argila_faixa_g_kg"):
            fert_out["argila_faixa_g_kg"] = fert["argila_faixa_g_kg"]
            fert_out["argila_origem"] = fert["argila_origem"]
    d = rk["diagnostico"]
    cell = rk["celula"]
    climate = dict(
        fonte=rk["fonte"], cache_utilizado=used_disk_cache,
        celula=dict(id=cell["ponto_id"], lat=cell["lat"], lon=cell["lon"], elev=cell["elev"]),
        semeadura_safrinha=sowing,
        riscos=dict(geada_safrinha=round(rk["geada_safrinha"], 3), geada_trigo=round(rk["geada_trigo"], 3),
                    veranico_safrinha=round(rk["veranico_safrinha"], 3), n_anos=rk["n_anos"], periodo=rk["periodo"]),
        geada_por_semeadura=[dict(semeadura=r["semeadura"], prob=round(r["prob"], 3), anos_com_evento=r["anos"], n_anos=r["n_anos"])
                             for r in rk["geada_tabela"]],
        diagnostico=dict(
            inicio_chuvas=dict(mediana=d["inicio_chuvas_mediana"], p80=d["inicio_chuvas_p80"]),
            calor_soja=dict(mediana=d["calor_soja_mediana"], media=d["calor_soja_media"], p80=d["calor_soja_p80"]),
            balanco_p_et0=dict(soja=d["balanco_soja"], safrinha=d["balanco_safrinha"], trigo=d["balanco_trigo"]),
            chuva_intensa=dict(media=d["chuva_intensa_media"], mediana=d["chuva_intensa_mediana"])),
        textos=E.fmt_diagnosis(d))
    pam = rk["pam"]
    prod = dict(municipio=rk["municipio"]["nome"], cod_ibge=str(rk["municipio"]["cod_ibge"]), fonte="IBGE PAM",
                culturas=pam["dados"] if pam else {}, texto=pam_text(pam["nome"], pam["dados"]) if pam else None,
                rendimento_usado=rk["rend"]["_origem"])
    mun = rk["municipio"]
    diag = dict(
        area=dict(origem=a["origem"], talhao_id=a["talhao_id"], area_ha=a["area_ha"], centroide=dict(lat=a["lat"], lon=a["lon"]),
                  municipio=dict(cod_ibge=str(mun["cod_ibge"]), nome=mun["nome"]), geometry=_geojson(poly)),
        relevo=rel_out, solo=solo_out, historico=history, rotacao_detectada=_detected_rotation(a["talhao_id"]),
        clima=climate, produtividade=prod, avisos=warnings)
    if fert_out:
        diag["fertilidade"] = fert_out
    return dict(rk=rk, diag=_clean(diag), dias_solo_ndvi=diag["rotacao_detectada"]["dias_solo_descoberto"])


def diagnose(area: dict, sowing_second: str = "01/02", soil_analysis: dict | None = None) -> dict:
    """Area diagnosis (slope, 0–30 cm soil + AWC, MapBiomas history, cell climate, municipality PAM).
    `soil_analysis` (optional, see `recommend`) replaces SoilGrids in the soil block.

    Raises InvalidInput (invalid geometry/sowing/area/soil analysis), OutOfRegion or ExternalQueryError."""
    phys, fert = _split_fertility(_normalize_soil_analysis(soil_analysis))
    return _context(area, sowing_second, phys, fert)["diag"]


# Rounding only at serialization (the computation and the ranking order use full precision).
def _round(o, digits: int):
    if isinstance(o, dict):
        return {k: _round(v, digits) for k, v in o.items()}
    return None if o is None else round(float(o), digits)


def _round_ranking(item: dict) -> dict:
    """score, criteria and contributions with 3 decimals; R$ values with 0 decimals; yields/prices/probabilities 3 decimals."""
    r0 = lambda x: None if x is None else float(round(x))
    item["nota"] = _round(item["nota"], 3)
    item["criterios"] = _round(item["criterios"], 3)
    item["contribuicoes"] = _round(item["contribuicoes"], 3)
    m = item["margem"]
    for k in ("total_r_ha", "incremental_r_ha", "incremental_preco_atual_r_ha", "escala_S_r_ha", "ano_ruim_r_ha", "bonus_proxima_soja_r_ha"):
        m[k] = r0(m[k])
    for i in m["itens"]:
        i["margem_r_ha"], i["custo"] = r0(i["margem_r_ha"]), r0(i["custo"])
        i["rendimento_sc_ha"] = None if i["rendimento_sc_ha"] is None else round(i["rendimento_sc_ha"], 1)
        i["preco"] = None if i["preco"] is None else round(i["preco"], 2)
    return item


# Recommendation
def _normalize_adjustments(aj) -> dict:
    """Accept {"precos": {soja, milho, trigo, feijao, sorgo}, "custos": {soja, milho|milho_2safra, milho_verao|milho_1safra,
    trigo, feijao|feijao_2safra, sorgo, aveia, milheto_crotalaria, braquiaria_consorcio, pousio, nabo_forrageiro, aveia_nabo},
    "linha_custo": coe|cot|ct}; return the engine format (preco/custo/linha_custo)."""
    if aj is None:
        return {}
    if not isinstance(aj, dict):
        raise InvalidInput("'ajustes' deve ser um objeto.")
    ref = load_reference()
    unknown = set(aj) - {"precos", "custos", "linha_custo", "produtividade"}
    if unknown:
        raise InvalidInput(f"Chaves de ajustes desconhecidas: {sorted(unknown)}.")
    out: dict = {}
    for k, v in (aj.get("precos") or {}).items():
        if k not in ref["prices"]:
            raise InvalidInput(f"Preço desconhecido: {k!r}. Opções: {sorted(ref['prices'])}.")
        out.setdefault("preco", {})[k] = _num(v, f"preço {k}", 0)
    for k, v in (aj.get("custos") or {}).items():
        kk = _COST_ALIAS.get(k, k)
        if kk not in ref["costs"]:
            raise InvalidInput(f"Custo desconhecido: {k!r}. Opções: {sorted(ref['costs']) + ['milho']}.")
        out.setdefault("custo", {})[kk] = _num(v, f"custo {k}", 0)
    prod = aj.get("produtividade")
    if prod is not None:
        if not isinstance(prod, dict):
            raise InvalidInput("'ajustes.produtividade' deve ser um objeto {cultura: sc/ha}.")
        if "milho" in prod and "milho_2safra" in prod:
            raise InvalidInput("Informe a produtividade do milho 2ª safra em 'milho' OU 'milho_2safra', não nas duas.")
        for k, v in prod.items():
            kk = _COST_ALIAS.get(k, k)
            if kk not in _PRODUCTIVITY:
                raise InvalidInput(f"Produtividade desconhecida: {k!r}. Opções: ['soja', 'milho', 'milho_2safra', 'milho_verao', "
                                      "'milho_1safra', 'trigo', 'feijao', 'feijao_2safra', 'sorgo'].")
            if kk in out.get("produtividade", {}):
                raise InvalidInput(f"Produtividade de {kk} informada duas vezes (alias).")
            f = _num(v, f"produtividade {k}", 0, 500)
            if f <= 0:
                raise InvalidInput(f"produtividade {k} deve ser maior que zero (recebido: {f}).")
            out.setdefault("produtividade", {})[kk] = f
    lc = aj.get("linha_custo")
    if lc is not None:
        if lc not in ("coe", "cot", "ct"):
            raise InvalidInput("linha_custo deve ser 'coe', 'cot' ou 'ct'.")
        out["linha_custo"] = lc
    return out


_FERT_FIELDS = set(EA.FERTILITY_FIELDS)  # fertilidade (opcional): p_mg_dm3, k/ca/mg/al/ctc_cmolc_dm3, v_pct
_CAMPOS_SOLO = {"argila_pct", "areia_pct", "materia_organica_pct", "carbono_organico_g_kg", "ph", "cad_mm_cm", "profundidade_cm"} | _FERT_FIELDS


def _normalize_area_problems(p) -> list[str] | None:
    """Validate `problemas_area` (closed list from catalog/vocabulario.yaml; no duplicates). None/[] = not given."""
    if p is None:
        return None
    if not isinstance(p, (list, tuple)):
        raise InvalidInput(f"'problemas_area' deve ser uma lista (opções: {list(EA.PROBLEMS)}).")
    for x in p:
        if x not in EA.PROBLEMS:
            raise InvalidInput(f"problema_area desconhecido: {x!r}. Opções: {list(EA.PROBLEMS)}.")
    return list(dict.fromkeys(p)) or None


def _split_fertility(solo_n: dict | None) -> tuple[dict | None, dict | None]:
    """Split the validated analysis into (physical/AWC part that replaces SoilGrids | None, interpreted fertility | None)."""
    if not solo_n:
        return None, None
    fert = EA.prepare_fertility({k: v for k, v in solo_n.items() if k in _FERT_FIELDS}, solo_n.get("argila_pct"),
                                 solo_n.get("soc_g_kg"))  # organic carbon of the report (g/kg read as g/dm3)
    phys = {k: v for k, v in solo_n.items() if k not in _FERT_FIELDS}
    return (phys if ("argila_pct" in phys or "cad_mm_cm" in phys) else None), fert


def _normalize_soil_analysis(a) -> dict | None:
    """Validate the farmer's soil analysis. Return {argila_pct, areia_pct, soc_g_kg, ph, cad_mm_cm, profundidade_cm}
    (only what was given; `profundidade_cm` defaults to 20) or None. Requires clay+sand OR cad_mm_cm OR some fertility field
    (p_mg_dm3, k_cmolc_dm3, ca_cmolc_dm3, mg_cmolc_dm3, al_cmolc_dm3, v_pct, ctc_cmolc_dm3: all optional, nothing is estimated
    when they are missing)."""
    if a is None:
        return None
    if not isinstance(a, dict):
        raise InvalidInput("'analise_solo' deve ser um objeto.")
    desc = set(a) - _CAMPOS_SOLO
    if desc:
        raise InvalidInput(f"Campos desconhecidos em analise_solo: {sorted(desc)}. Opções: {sorted(_CAMPOS_SOLO)}.")
    a = {k: v for k, v in a.items() if v is not None}
    out: dict = {}
    for k in ("argila_pct", "areia_pct"):
        if k in a:
            out[k] = _num(a[k], k, 0, 100)
    if ("argila_pct" in out) != ("areia_pct" in out):
        raise InvalidInput("Informe argila_pct e areia_pct juntos (ou apenas cad_mm_cm).")
    if "argila_pct" in out and out["argila_pct"] + out["areia_pct"] > 100:
        raise InvalidInput("argila_pct + areia_pct não pode passar de 100.")
    if "materia_organica_pct" in a and "carbono_organico_g_kg" in a:
        raise InvalidInput("Informe materia_organica_pct OU carbono_organico_g_kg, não os dois.")
    if "materia_organica_pct" in a:
        out["soc_g_kg"] = _num(a["materia_organica_pct"], "materia_organica_pct", 0, 100) / 1.724 * 10.0
    if "carbono_organico_g_kg" in a:
        out["soc_g_kg"] = _num(a["carbono_organico_g_kg"], "carbono_organico_g_kg", 0, 580)
    if "ph" in a:
        out["ph"] = _num(a["ph"], "ph", 3, 9)
    if "cad_mm_cm" in a:
        out["cad_mm_cm"] = _num(a["cad_mm_cm"], "cad_mm_cm", 0.3, 3)
    for k, (lo, hi) in EA.FERTILITY_FIELDS.items():
        if k in a:
            out[k] = _num(a[k], k, lo, hi)
    if "argila_pct" not in out and "cad_mm_cm" not in out and not any(k in out for k in _FERT_FIELDS):
        raise InvalidInput("analise_solo exige argila_pct e areia_pct, ou cad_mm_cm, ou algum campo de fertilidade.")
    out["profundidade_cm"] = _num(a["profundidade_cm"], "profundidade_cm", 1, 200) if "profundidade_cm" in a else 20.0
    return out


_NO_BUYER = {"milho": "milho", "milho_2safra": "milho", "trigo": "trigo", "sorgo": "sorgo", "feijao": "feijao", "aveia_grao": "aveia_grao"}


def _normalize_constraints(r) -> dict | None:
    """Validate `restricoes`. Return {'excluidas': {catalog names}, 'maquinas': {...}, 'sem_comprador': {...},
    'eco': normalized input format} or None."""
    if r is None:
        return None
    if not isinstance(r, dict):
        raise InvalidInput("'restricoes' deve ser um objeto.")
    desc = set(r) - {"culturas_excluidas", "maquinas", "sem_comprador"}
    if desc:
        raise InvalidInput(f"Campos desconhecidos em restricoes: {sorted(desc)}.")
    exc = r.get("culturas_excluidas") or []
    sow_date = r.get("sem_comprador") or []
    mach = r.get("maquinas") or {}
    if not isinstance(exc, list) or not isinstance(sow_date, list) or not isinstance(mach, dict):
        raise InvalidInput("restricoes: 'culturas_excluidas' e 'sem_comprador' são listas; 'maquinas' é um objeto.")
    exc = [_resolver_id(x, "Rotação excluída") for x in exc]  # new ids or old slugs (= soja__<slug>)
    for x in sow_date:
        if x not in _NO_BUYER:
            raise InvalidInput(f"sem_comprador desconhecido: {x!r}. Opções: {sorted(_NO_BUYER)}.")
    for k, v in mach.items():
        if k not in E.MACHINE_COST:
            raise InvalidInput(f"Máquina desconhecida: {k!r}. Opções: {sorted(E.MACHINE_COST)}.")
        if not isinstance(v, bool):
            raise InvalidInput(f"maquinas.{k} deve ser true ou false.")
    return dict(excluidas={ROTATIONS[x] for x in exc}, maquinas=dict(mach), sem_comprador={_NO_BUYER[x] for x in sow_date},
                eco=dict(culturas_excluidas=list(dict.fromkeys(exc)), maquinas=dict(mach),
                         sem_comprador=list(dict.fromkeys(sow_date))))


def _normalize_irrigation(i) -> dict | None:
    """Validate `irrigacao`: {disponivel: bool, custo_r_mm_ha (default 4.0), lamina_max_mm_dia (default 6)}."""
    if i is None:
        return None
    if not isinstance(i, dict):
        raise InvalidInput("'irrigacao' deve ser um objeto.")
    desc = set(i) - {"disponivel", "custo_r_mm_ha", "lamina_max_mm_dia"}
    if desc:
        raise InvalidInput(f"Campos desconhecidos em irrigacao: {sorted(desc)}.")
    if not isinstance(i.get("disponivel"), bool):
        raise InvalidInput("irrigacao.disponivel é obrigatório e deve ser true ou false.")
    cost = E.DEFAULT_IRRIGATION_COST if i.get("custo_r_mm_ha") is None else _num(i["custo_r_mm_ha"], "custo_r_mm_ha", 0, 100)
    lam = E.DEFAULT_MAX_DEPTH if i.get("lamina_max_mm_dia") is None else _num(i["lamina_max_mm_dia"], "lamina_max_mm_dia", 0, 30)
    if lam <= 0:
        raise InvalidInput("lamina_max_mm_dia deve ser maior que zero.")
    return dict(disponivel=i["disponivel"], custo_r_mm_ha=cost, lamina_max_mm_dia=lam)


def _normalize_weights(pesos) -> dict:
    out = dict(E.DEFAULT_WEIGHTS)
    if pesos is None:
        return out
    if not isinstance(pesos, dict):
        raise InvalidInput("'pesos' deve ser um objeto.")
    for k, v in pesos.items():
        if k not in E.CRITERIA:
            raise InvalidInput(f"Peso desconhecido: {k!r}. Critérios: {list(E.CRITERIA)}.")
        out[k] = _num(v, f"peso {k}", 0, 10)
    return out


def _summer_second(nome: str) -> dict:
    c = E.CATALOG[nome]
    return dict(verao=dict(id=c["verao"], nome=c["nome_verao"]), segunda=dict(id=c["segunda"], nome=_capitalize(c["nome_segunda"])))


# Score gap below which the top options are a technical tie: ±20 % on single catalog estimates (prices, pest break, cover,
# bonus) moves the gap between the top two of field 72638 by up to ~0.02 (docs/validation.md §1.2).
TECHNICAL_TIE = 0.02


def technical_tie(items: list[dict]) -> dict | None:
    """Options within TECHNICAL_TIE of the first one (at least two), or None. Adds a warning to the card of each tied option."""
    if len(items) < 2 or items[0]["nota"] is None:
        return None
    top = items[0]["nota"]
    tied = [x for x in items if x["nota"] is not None and top - x["nota"] < TECHNICAL_TIE - 1e-9]
    if len(tied) < 2:
        return None
    names = [x["rotacao"] for x in tied]
    gap = top - tied[-1]["nota"]
    text = Msg("Empate técnico: {0} estão a menos de {1} ponto da melhor nota (diferença {2}). Variações pequenas nas "
               "estimativas (preços, quebra de ciclo de pragas, cobertura, bônus na soja) trocam a ordem entre elas; escolha pelo "
               "que pesa mais na sua realidade (renda, máquinas, mercado, histórico da área).",
               Join([n.replace(".", ",") for n in names], ", ", last=" e "),
               f"{TECHNICAL_TIE:.2f}".replace(".", ","), f"{gap:.3f}".replace(".", ","))
    for x in tied:
        x["card"]["avisos"].insert(0, text)
    return dict(ids=[x["id"] for x in tied], diferenca=round(gap, 3), limiar=TECHNICAL_TIE, texto=text)


# Income gap (R$/ha/yr) below which two options are treated as earning the same: about one bag of soybean per hectare, the order
# of the price and cost noise (docs/validation.md §7.5).
INCOME_GAP_NOTE = 100.0


def income_trade_off(items: list[dict]) -> dict | None:
    """Best-income option of the block (largest incremental margin) and what each option earns less than it
    (`margem.abaixo_da_maior_renda_r_ha`). The options ranked ABOVE it by more than INCOME_GAP_NOTE get a card warning: they are
    ahead because of soil, pests, water and risk, which costs income. Returns the block field `maior_renda`, or None."""
    valid = [x for x in items if x["margem"].get("incremental_r_ha") is not None]
    if not valid:
        return None
    best = max(valid, key=lambda x: x["margem"]["incremental_r_ha"])
    top_inc = best["margem"]["incremental_r_ha"]
    for x in valid:
        x["margem"]["abaixo_da_maior_renda_r_ha"] = float(round(top_inc - x["margem"]["incremental_r_ha"]))
    best_name = best["rotacao"].replace(".", ",")
    for x in valid:
        gap = x["margem"]["abaixo_da_maior_renda_r_ha"]
        if x["posicao"] < best["posicao"] and gap > INCOME_GAP_NOTE:
            x["card"]["avisos"].append(Msg(
                "Renda: esta opção rende R$ {0}/ha/ano a menos que a de maior renda ({1}). Ela fica à frente pelos critérios solo, "
                "pragas, água e risco; solo e pragas são estimativas de catálogo. Se a renda pesa mais para você, aumente o peso da "
                "renda.", f"{gap:,.0f}".replace(",", "."), best_name))
    first = items[0]
    gap_first = first["margem"].get("abaixo_da_maior_renda_r_ha")
    return dict(id=best["id"], rotacao=best["rotacao"], incremental_r_ha=top_inc,
                primeira_abaixo_r_ha=gap_first, primeira_e_maior_renda=bool(gap_first is not None and gap_first <= INCOME_GAP_NOTE))


def _recovery_out(r: dict) -> dict:
    """API block `recuperacao_solo` (R$/ha rounded; text already in the card)."""
    rd = lambda x: None if x is None else float(round(x))  # noqa: E731
    return dict(calagem_total_r_ha=rd(r["calagem_total_r_ha"]),
                calagem_t_ha=None if r["calagem_t_ha"] is None else round(r["calagem_t_ha"], 2),
                adubacao_pk_r_ha_ano=rd(r["adubacao_pk_r_ha_ano"]), renda_abdicada_r_ha=rd(r["renda_abdicada_r_ha"]),
                referencia_renda=r["referencia_renda"], credito_k2o_ate_r_ha=rd(r["credito_k2o_ate_r_ha"]),
                total_primeiro_ano_r_ha=rd(r["total_primeiro_ano_r_ha"]), texto=r["texto"])


def _uncertainty_out(u: dict | None) -> dict | None:
    """API view of `engine.uncertainty`: R$ without decimals, scores and probabilities with 3."""
    if u is None:
        return None
    r0 = lambda x: None if x is None else float(round(x))  # noqa: E731
    r3 = lambda x: None if x is None else round(float(x), 3)  # noqa: E731
    rc = u["risco_climatico"]
    return dict(
        renda=dict(incremental_r_ha=r0(u["renda"]["incremental_r_ha"]), faixa_r_ha=[r0(x) for x in u["renda"]["faixa_r_ha"]],
                   origem=u["renda"]["origem"]),
        nota_faixa=[r3(x) for x in u["nota_faixa"]],
        nota_por_safra=None if u["nota_por_safra"] is None else {str(k): r3(v) for k, v in sorted(u["nota_por_safra"].items())},
        risco_climatico=None if rc is None else dict(rc, probabilidade=r3(rc["probabilidade"])),
        criterios_estimados=u["criterios_estimados"])


def ranking_stability(items: list[dict], margins: dict) -> dict | None:
    """How often each option of the block would be first if each of the last seasons of the track record repeated (income of
    the options with a track record varies by season; the other criteria and options stay fixed). None without track records."""
    def by_season(x) -> dict:
        return (margins[x["rotacao"]].get("incerteza") or {}).get("nota_por_safra") or {}

    years = sorted({y for x in items for y in by_season(x)})
    if not years or not items:
        return None
    wins: dict[str, int] = {}
    for y in years:
        best = max(items, key=lambda x: by_season(x).get(y, x["nota"]))["id"]
        wins[best] = wins.get(best, 0) + 1
    first = [dict(id=k, safras=v) for k, v in sorted(wins.items(), key=lambda kv: -kv[1])]
    return dict(safras=years, primeiro=first,
                texto=Msg("Repetindo a renda realizada de cada uma das últimas {0} safras ({1}–{2}), com os demais critérios "
                          "fixos, a 1ª colocada seria: {3}.", str(len(years)), str(years[0]), str(years[-1]),
                          Join([Msg("{0} em {1}", p["id"], str(p["safras"])) for p in first], "; ")))


def _item_ranking(pos, nome, line, marg_, current, rk, ndvi_days, why_cmp=None) -> dict:
    card = E.build_card(line, current, rk, ndvi_days, marg_, why_cmp)
    items = []
    for i in marg_["itens"]:
        items.append(dict(
            cultura=i["rotulo"], rendimento_sc_ha=i["sc_ha"], preco=i["preco"], custo=i["custo"], margem_r_ha=i["margem"],
            fonte=(Msg("rendimento informado pelo produtor; preço {0}; custo {1}", price_source(i), cost_source(i, marg_["linha_custo"]))
                   if i.get("prod_usuario") else
                   Msg("rendimento IBGE PAM ({0}, {1}); preço {2}; custo {3}", E.local_rend(rk, i["chave"]), str(i["anos"]),
                       price_source(i), cost_source(i, marg_["linha_custo"]))
                   if i["sc_ha"] is not None else
                   Msg("custo extra: {0} (sem venda)", i["detalhe"]) if i.get("extra") else
                   Msg("custo {0} (sem venda)", cost_source(i, marg_["linha_custo"])))))
    warnings = []
    if marg_["total"] < 0:
        warnings.append("Margem total negativa com os preços e custos usados.")
    margin = dict(total_r_ha=marg_["total"], incremental_r_ha=marg_["incremental"], escala_S_r_ha=marg_["escala_S"], itens=items, ano_ruim_r_ha=marg_["total_ano_ruim"],
                  bonus_proxima_soja_r_ha=marg_["bonus"], linha_custo=marg_["linha_custo"],
                  base_renda=marg_.get("base_renda", "preco_atual"),
                  incremental_preco_atual_r_ha=marg_.get("incremental_preco_atual", marg_["incremental"]))
    return dict(
        posicao=pos, **_ids(_SLUG_DE[nome]), **_summer_second(nome), rotacao=nome, nota=float(line["nota"]), atual=current,
        criterios={k: float(line[k]) for k in E.CRITERIA},
        contribuicoes={k: float(v) for k, v in line["contrib"].items()}, margem=margin,
        card=dict(por_que=card["por_que"], evidencias=card["evidencia"], beneficios=card["beneficios"],
                  lacunas=card["lacunas"], riscos=card["revisar"], avisos=warnings + card["avisos"], mercado=card["mercado"]),
        **({"zarc": card["zarc"]} if card["zarc"] is not None else {}),
        **({"historico_renda": card["historico"]} if card.get("historico") is not None else {}),
        **({"incerteza": _uncertainty_out(marg_.get("incerteza"))} if marg_.get("incerteza") is not None else {}),
        **({"recuperacao_solo": _recovery_out(marg_["recuperacao"])} if marg_.get("recuperacao") else {}),
        **({"irrigacao": dict(lamina_media_mm_ano=round(card["irrigacao"]["lamina_media_mm"], 1),
                                           custo_r_ha=float(round(card["irrigacao"]["custo_r_ha"])))}
           if card["irrigacao"] else {}))


def _applied_adjustments(aj: dict, soil, restr, irr) -> list[str]:
    """One sentence per adjustment/optional input used (goes into metodologia.ajustes_aplicados)."""
    o = []
    if aj.get("preco"):
        items = ", ".join(f"{k} R$ {v:g}/sc" for k, v in aj["preco"].items())
        o.append(f"Preços informados pelo produtor ({items}) substituem a média de 12 meses da SEAB/DERAL.")
    if aj.get("custo"):
        items = ", ".join(f"{k} R$ {v:g}/ha" for k, v in aj["custo"].items())
        o.append(f"Custos informados pelo produtor ({items}) substituem o custo CONAB.")
    if aj.get("linha_custo"):
        o.append(f"Linha de custo CONAB '{aj['linha_custo']}' em vez do padrão.")
    if aj.get("produtividade"):
        items = ", ".join(f"{k} {v:g} sc/ha" for k, v in aj["produtividade"].items())
        o.append(f"Produtividade informada pelo produtor ({items}) substitui o rendimento PAM do município; o ano ruim escala "
                 "proporcionalmente (próprio × p20/média da PAM).")
    if soil:
        if "cad_mm_cm" in soil:
            o.append("Análise de solo do produtor substitui o SoilGrids no diagnóstico e na CAD do balanço hídrico (CAD informada diretamente).")
        else:
            o.append("Análise de solo do produtor substitui o SoilGrids no diagnóstico e na CAD do balanço hídrico "
                     "(CAD por Saxton & Rawls com a análise).")
    if restr:
        e = restr["eco"]
        if e["culturas_excluidas"]:
            o.append(f"Rotações excluídas pelo produtor: {', '.join(e['culturas_excluidas'])}.")
        if e["sem_comprador"]:
            crops = ", ".join(e["sem_comprador"])
            if "aveia_grao" in e["sem_comprador"]:
                o.append(f"Sem comprador local (eliminam as rotações que dependem da venda): {crops}; aveia_grao não tem efeito, pois a "
                         "aveia é tratada como cobertura sem venda.")
            else:
                o.append(f"Sem comprador local (eliminam as rotações que dependem da venda): {crops}.")
        sow_date = [k for k, v in e["maquinas"].items() if v is False]
        if sow_date:
            o.append(f"Máquinas que o produtor não tem ({', '.join(sow_date)}): a rotação não é eliminada, ganha aviso e custo extra "
                     "de terceirização (estimativas, validar).")
    if irr and irr["disponivel"]:
        o.append(f"Irrigação disponível (R$ {irr['custo_r_mm_ha']:g}/mm/ha, lâmina máx. {irr['lamina_max_mm_dia']:g} mm/dia): irriga "
                 "milho, milho+braquiária, trigo, sorgo e feijão quando a depleção passa de p (0,55; feijão 0,45); água sobe, o déficit hídrico não conta no risco e a "
                 "margem desconta lâmina × custo. O ganho de produtividade da irrigação não é modelado; cobertura e pousio não são irrigados.")
    return o


_INCOME_SOURCE = "dado: rendimento IBGE PAM × preço SEAB/DERAL − custo CONAB (ou os valores informados pelo produtor)"
_SOIL_SOURCE = "estimativa de catálogo, validar com agrônomo/Embrapa"


def _gain_vs_current(res: dict, nome: str, current_name: str) -> dict | None:
    """How the candidate improves (or worsens) production relative to the current rotation. None if it is the current one itself or if
    the current one was eliminated (no margin to compare). Signed values: positive = the candidate gains."""
    m, ma = res["margens"].get(nome), res["margens"].get(current_name)
    if nome == current_name or m is None or ma is None:
        return None
    c, ca = E.CATALOG[nome], E.CATALOG[current_name]
    t = res["tabela"].set_index("candidata")
    sc = c["bonus_sc"] - ca["bonus_sc"]
    range_ = (c["bonus_sc_faixa"][0] - ca["bonus_sc_faixa"][1], c["bonus_sc_faixa"][1] - ca["bonus_sc_faixa"][0])  # pior e melhor caso
    income_2nd = sum(i["margem"] for i in m["itens"][1:]) - sum(i["margem"] for i in ma["itens"][1:])
    return dict(
        comparado_com=E.ID_DE[current_name],
        soja_seguinte_sc=round(sc, 1), soja_seguinte_sc_faixa=[round(range_[0], 1), round(range_[1], 1)],
        soja_seguinte_rs=float(round(sc * m["preco_soja"])), preco_soja_r_sc=round(m["preco_soja"], 2),
        fonte=f"soja seguinte: {c['bonus_fonte']} (preço da soja SEAB/DERAL)",
        renda_2a_safra=dict(r_ha=float(round(income_2nd)), origem=_INCOME_SOURCE),
        margem_total=dict(r_ha=float(round(m["total"] - ma["total"])), origem=_INCOME_SOURCE + "; inclui o bônus na soja seguinte"),
        solo=dict(dias_descobertos=c["dias_descobertos"] - ca["dias_descobertos"],
                  cobertura=round(c["cobertura"] - ca["cobertura"], 2), origem=_SOIL_SOURCE + " (dias negativos = menos solo descoberto)"),
        agua=dict(criterio=round(float(t.loc[nome, "agua"] - t.loc[current_name, "agua"]), 3),
                  origem="dado: balanço hídrico diário com NASA POWER e CAD do solo"),
        risco_climatico=dict(criterio=round(float(t.loc[nome, "risco"] - t.loc[current_name, "risco"]), 3),
                             origem="dado: geada (NASA POWER) e déficit hídrico (balanço diário NASA POWER + solo), 1991–2024"))


def _reference_date(d) -> date | None:
    if d is None or isinstance(d, date):
        return d
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        raise InvalidInput(f"data_referencia deve ser uma data ISO (AAAA-MM-DD); recebido: {d!r}.") from None


def _normalize_inputs(sowing_second, pesos, current_rotation, adjustments, soil_analysis, constraints, irrigation, rotations,
                         area_problems) -> dict:
    """Validate and normalize the inputs of `recommend` (same error order)."""
    if current_rotation is None:
        raise InvalidInput("'rotacao_atual' é obrigatória (id '<verao>__<segunda>', ex.: soja__milho_safrinha).")
    if sowing_second is not None:
        sowing_second = _validate_sowing(sowing_second)
    pesos_n = _normalize_weights(pesos)
    aj_n = _normalize_adjustments(adjustments)
    solo_n = _normalize_soil_analysis(soil_analysis)
    soil_phys, fert_n = _split_fertility(solo_n)
    probs_n = _normalize_area_problems(area_problems)
    restr_n = _normalize_constraints(constraints)
    irr_n = _normalize_irrigation(irrigation)
    sel = _normalize_rotations(rotations)
    current_rotation = _resolver_id(current_rotation, "rotacao_atual")
    current_name = ROTATIONS[current_rotation]
    return dict(pesos_n=pesos_n, aj_n=aj_n, solo_n=solo_n, solo_fis=soil_phys, fert_n=fert_n, probs_n=probs_n, restr_n=restr_n,
                irr_n=irr_n, sel=sel, rotacao_atual=current_rotation, nome_atual=current_name,
                verao_atual=E.CATALOG[current_name]["verao"])


def _timeline_and_context(area, inp: dict, sowing_second, summer_stage, expected_harvest, reference_date) -> dict:
    """Timeline of the current season (estimated harvest, 2nd-window sowing) and area context (`rk` ready for `E.score_rotation`)."""
    current_summer, restr_n, irr_n = inp["verao_atual"], inp["restr_n"], inp["irr_n"]
    data_ref = _reference_date(reference_date) or date.today()
    try:
        cron = cal.resolver(current_summer, summer_stage, expected_harvest, data_ref, sowing_second)
    except ValueError as e:
        raise InvalidInput(str(e)) from e
    calendar_warnings = []
    if cron:
        harvest = dict(data=cron["colheita"], origem=cron["origem"])
        days_until = cron["dias_ate_colheita"]
        sow_2nd = cron["semeadura_2a"]  # None = colheita tarde demais
        sow_origin = "informada" if sowing_second else "derivada"
        if expected_harvest is not None and summer_stage is not None:
            calendar_warnings.append("colheita_prevista e estagio_verao informados: vale a colheita_prevista.")
        if sowing_second:
            calendar_warnings.append(f"semeadura_safrinha {sowing_second} informada: vale no lugar da derivada da colheita "
                              f"(primeira data >= colheita: {cal.derived_sowing(cron['data']) or 'nenhuma'}).")
        if sow_2nd is None:
            calendar_warnings.append(f"Colheita de {E.SUMMER[current_summer]['nome'].lower()} estimada em ~{cron['colheita']}, depois da última "
                              f"semeadura considerada ({E.SOWINGS_2ND[-1]}): tarde demais para a safrinha; só as culturas de "
                              "data fixa (inverno e cobertura) seguem avaliadas.")
    else:
        harvest = dict(data=E.SUMMER[current_summer]["colheita"], origem="premissa")
        days_until = None
        sow_2nd = sowing_second or E.DEFAULT_SOWING
        sow_origin = "informada" if sowing_second else "premissa"
        crop = E.SUMMER[current_summer]["nome"].lower()
        if sowing_second:
            calendar_warnings.append(f"Sem estagio_verao nem colheita_prevista: colheita de {crop} assumida em ~{harvest['data']} (premissa "
                                     "do catálogo, estimativa). Informe o estágio da cultura de verão para uma resposta sobre o que entra "
                                     "depois da colheita.")
        else:
            calendar_warnings.append(f"Sem estagio_verao nem colheita_prevista: colheita de {crop} assumida em ~{harvest['data']} (premissa "
                                     f"do catálogo, estimativa) e semeadura da 2ª janela em {sow_2nd} (padrão). Informe o estágio da "
                                     "cultura de verão para uma resposta sobre o que entra depois da colheita.")
    ctx = _context(area, sow_2nd or E.SOWINGS_2ND[-1], inp["solo_fis"], inp["fert_n"])
    rk, diag = ctx["rk"], ctx["diag"]
    probs_n, fert_n = inp["probs_n"], inp["fert_n"]
    if probs_n or fert_n:  # only exists if the farmer gave it; without it the engine runs exactly as before
        rk["estado_area"] = dict(problemas=probs_n or [], fert=fert_n)
    rk["restr"] = restr_n
    rk["irrig"] = irr_n if irr_n and irr_n["disponivel"] else None
    if cron:
        rk["colheita_produtor"] = dict(verao=current_summer, colheita=cron["colheita"])
    warnings = list(diag["avisos"]) + calendar_warnings
    if rk["irrig"] and rk.get("agua_ctx") is None:
        warnings.append("Irrigação informada, mas sem solo para o balanço hídrico: ignorada.")
    days = ctx["dias_solo_ndvi"]
    days = float("nan") if days is None else days
    return dict(cron=cron, colheita=harvest, dias_ate=days_until, sem_2a=sow_2nd, sem_origem=sow_origin, data_ref=data_ref, ctx=ctx,
                rk=rk, diag=diag, avisos=warnings, dias=days)


def recommend(area: dict, sowing_second: str | None = None, pesos: dict | None = None,
               current_rotation: str | None = None, adjustments: dict | None = None,
               n_alternatives: int = 3, include_diagnosis: bool = True, soil_analysis: dict | None = None,
               constraints: dict | None = None, irrigation: dict | None = None, rotations: list[dict] | None = None,
               summer_stage: str | None = None, expected_harvest: str | None = None, reference_date=None,
               area_problems: list[str] | None = None) -> dict:
    """What can come after the summer harvest and how it improves production, plus what to change in the next season.

    current_rotation (REQUIRED): id from ROTATIONS ("soja__milho_safrinha") or old slug ("milho_safrinha" = soja__milho_safrinha).
    summer_stage (optional): stage of the summer crop of the current rotation (crop_calendar.STAGES; soybean: vegetativo, floracao,
      formacao_vagens, enchimento_graos, maturacao, colhida; summer corn: vegetativo, pendoamento, grao_leitoso, grao_farinaceo,
      maturacao, colhida). estimated harvest = reference_date + typical days of the stage.
    expected_harvest (optional, dd/mm): overrides the stage. reference_date (optional, date or ISO; default today).
    sowing_second (optional): without it, it is the first date in SOWINGS_2ND >= estimated harvest (+ preparation); with it, it overrides
      the derived one but cannot be earlier than the harvest. Without stage or harvest: catalog assumption (harvest) and 01/02 (sowing).
      Harvest after the last date in SOWINGS_2ND: the 2nd-window crops that follow the sowing date are eliminated.

    Output: `agora` (same summer as the current one: ranking, alternatives, eliminated) and `proxima_safra` (the other summer), each item
    with `ganho_vs_atual`. `ranking`, `alternativas` and `eliminadas` at the top are aliases of `agora` (eliminadas = union of both blocks).

    rotations (optional): [{"verao": "soja"|"milho_verao", "segunda": <2nd-window crop>}]; when given, only these are evaluated and
      ranked (closed catalog enums; not empty, no duplicates); each pair lands in the block of its summer. Without `rotations`, every
      catalog combination is evaluated. A combination eliminated by the rules comes back in `eliminadas` with a reason (not an error).

    pesos: renda, solo, agua, pragas, risco (0–10; missing = default {renda 5, others 3}; all 0 = equal weights).
    adjustments (all optional):
      "precos": {"soja"|"milho"|"trigo": R$/60 kg bag}
      "custos": {"soja"|"milho"|"milho_verao"|"trigo"|"feijao"|"sorgo"|"aveia"|"milheto_crotalaria"|"braquiaria_consorcio"|
                "pousio"|"nabo_forrageiro"|"aveia_nabo": R$/ha} ("milho" = 2nd-season corn; "milho_verao" = 1st-season corn)
      "linha_custo": "coe" (variable cost, default) | "cot" | "ct"  (CONAB; applies to soybean, corn and wheat)
      "produtividade": {"soja"|"milho"|"milho_2safra"|"milho_verao"|"trigo"|"feijao"|"sorgo": bags/ha > 0}  replaces the municipality PAM
                yield; the bad year scales proportionally (own × p20/PAM mean)
    soil_analysis (optional): {"argila_pct", "areia_pct", "materia_organica_pct"|"carbono_organico_g_kg", "ph", "cad_mm_cm",
      "profundidade_cm"}; requires clay+sand or cad_mm_cm (or fertility only). Replaces SoilGrids in the diagnosis and in the AWC of the
      water balance. Fertility (optional, any subset): p_mg_dm3, k_cmolc_dm3, ca_cmolc_dm3, mg_cmolc_dm3, al_cmolc_dm3, v_pct,
      ctc_cmolc_dm3. When given: liming and P/K fertilization cost in the margin, a penalty (soil criterion) for sensitive crops on
      acid/poor soil and a bonus for nutrient-recycling cover crops; when NOT given, it does not enter the analysis (no estimate or default).
    area_problems (optional): closed list ["nematoide", "mofo_branco", "cigarrinha", "compactacao"] (catalog/vocabulario.yaml);
      adjusts the pest and soil criteria per crop on three levels (favors/neutral/penalizes), only where there is a source read
      (table and sources in field_shift.app.field_state; without a source the effect is neutral). Without it, nothing changes.
    constraints (optional): {"culturas_excluidas": [slugs], "maquinas": {"plataforma_milho": bool, "semeadora_consorcio": bool},
      "sem_comprador": ["milho"|"trigo"|"aveia_grao"]}. Excluded/no buyer -> eliminated; machine false -> warning + extra
      outsourcing cost (estimate); omitted machine = owned.
    irrigation (optional): {"disponivel": bool, "custo_r_mm_ha": 4.0, "lamina_max_mm_dia": 6}. Irrigates corn, corn+brachiaria,
      wheat, sorghum and 2nd-window beans (not cover/fallow nor the summer crop): water goes up, the water deficit does not count in
      the risk, the margin subtracts depth × cost. The yield gain from irrigation is NOT modeled.
    n_alternatives: 1–6 best rotations of each block, excluding the current one. If the current one is eliminated by the hard rules
    (e.g. soja__soja_safrinha or a too-late harvest), `atual` holds {"eliminada": True, "motivos": [...]}, with no position or score
    (and no `ganho_vs_atual` in the items). With `rotations` that do not include the current one, `atual` holds {"avaliada": False}."""
    inp = _normalize_inputs(sowing_second, pesos, current_rotation, adjustments, soil_analysis, constraints, irrigation, rotations,
                               area_problems)
    if isinstance(n_alternatives, bool) or not isinstance(n_alternatives, int) or not 1 <= n_alternatives <= 6:
        raise InvalidInput("n_alternativas deve ser um inteiro entre 1 e 6.")
    pesos_n, aj_n, solo_n, soil_phys, fert_n = inp["pesos_n"], inp["aj_n"], inp["solo_n"], inp["solo_fis"], inp["fert_n"]
    probs_n, restr_n, irr_n, sel = inp["probs_n"], inp["restr_n"], inp["irr_n"], inp["sel"]
    current_rotation, current_name, current_summer = inp["rotacao_atual"], inp["nome_atual"], inp["verao_atual"]
    base = _timeline_and_context(area, inp, sowing_second, summer_stage, expected_harvest, reference_date)
    cron, harvest, days_until, sow_2nd, sow_origin = base["cron"], base["colheita"], base["dias_ate"], base["sem_2a"], base["sem_origem"]
    data_ref, ctx, rk, diag, warnings, days = base["data_ref"], base["ctx"], base["rk"], base["diag"], base["avisos"], base["dias"]
    # the current rotation is always evaluated (for ganho_vs_atual), even outside `rotations`; it only shows up if it is in `rotations`
    evaluate = None if sel is None else list(dict.fromkeys([ROTATIONS[i] for i in sel] + [current_name]))
    try:
        res = E.score_rotation(pesos_n, rk, aj_n, evaluate)
    except E.NoCandidates as e:
        if sel is None:
            raise InvalidInput(str(e)) from e
        res = dict(tabela=pd.DataFrame(columns=["candidata"]), eliminadas=e.eliminated_list, margens={}, aviso_renda=None)
    if res["aviso_renda"]:
        warnings.append(res["aviso_renda"])
    requested = None if sel is None else {ROTATIONS[i] for i in sel}
    show = lambda n: requested is None or n in requested  # noqa: E731
    in_now = lambda n: E.CATALOG[n]["verao"] == current_summer  # noqa: E731
    elim = {n: m for n, m in res["eliminadas"].items() if show(n)}

    def block(now: bool) -> dict:
        names = [n for n in res["tabela"]["candidata"] if show(n) and in_now(n) == now]
        tab = res["tabela"]
        res_b = dict(res, tabela=tab[tab["candidata"].isin(names + ([current_name] if not now and show(current_name) else []))]
                     .reset_index(drop=True))
        items = []
        for pos, (_, line) in enumerate(res_b["tabela"][res_b["tabela"]["candidata"].isin(names)].iterrows(), start=1):
            n = line["candidata"]
            item = _item_ranking(pos, n, line, res["margens"][n], n == current_name, rk, days if n == current_name else float("nan"),
                                 E.why_compared(res_b, n, current_name))
            item["ganho_vs_atual"] = _gain_vs_current(res, n, current_name)
            items.append(_round_ranking(item))
        el = [dict(**_ids(_SLUG_DE[n]), **_summer_second(n), rotacao=n, motivos=list(m)) for n, m in elim.items() if in_now(n) == now]
        tie = technical_tie(items)
        return dict(ranking=items, alternativas=[r for r in items if not r["atual"]][:n_alternatives], eliminadas=el,
                    empate_tecnico=tie, estabilidade=ranking_stability(items, res["margens"]), maior_renda=income_trade_off(items))

    now, next_ = block(True), block(False)
    if sel is not None and not now["ranking"] and not next_["ranking"]:
        warnings.append("Todas as rotações pedidas em 'rotacoes' foram eliminadas pelas regras ou restrições (veja 'eliminadas').")
    current = next((r for r in now["ranking"] if r["atual"]), None)
    if current is not None and current.get("zarc") and not current["zarc"]["indicado"]:
        fora = ", ".join(f"{x['cultura']} em {x['semeadura']}" for x in current["zarc"]["culturas"] if not x["indicado"])
        warnings.append(f"A rotação atual está fora do {current['zarc']['fonte'].split(' (')[0]} no município ({fora}): sem acesso ao "
                      "crédito rural com juros controlados, ao Proagro nem ao seguro rural subvencionado (aviso informativo).")
    if current is None and current_name in res["eliminadas"]:
        reason_ = res["eliminadas"][current_name]
        current = dict(posicao=None, **_ids(current_rotation), rotacao=current_name, nota=None, atual=True, eliminada=True, motivos=list(reason_))
        warnings.append(f"A rotação atual ({current_name}) é eliminada ({'regras duras ou restrições do produtor' if restr_n else 'regras duras'}): "
                      + " ".join(reason_))
    elif current is None:
        current = dict(posicao=None, **_ids(current_rotation), rotacao=current_name, nota=None, atual=True, avaliada=False)
        warnings.append(f"A rotação atual ({current_name}) não está em 'rotacoes': não foi avaliada nem comparada.")
    input_ = dict(semeadura_safrinha=sow_2nd, pesos=pesos_n, rotacao_atual=current_rotation, estagio_verao=summer_stage,
                   colheita_prevista=expected_harvest, data_referencia=data_ref.isoformat(),
                   ajustes=adjustments or {}, n_alternativas=n_alternatives)
    if sel is not None:
        input_["rotacoes"] = [dict(verao=E.CATALOG[ROTATIONS[i]]["verao"], segunda=E.CATALOG[ROTATIONS[i]]["segunda"]) for i in sel]
    if probs_n:
        input_["problemas_area"] = probs_n
    if solo_n:
        input_["analise_solo"] = {k: v for k, v in dict(solo_n, cad_mm_cm=solo_n.get("cad_mm_cm")).items() if v is not None}
        if "soc_g_kg" in solo_n:
            input_["analise_solo"]["carbono_organico_g_kg"] = round(input_["analise_solo"].pop("soc_g_kg"), 2)
    if restr_n:
        input_["restricoes"] = restr_n["eco"]
    if irr_n:
        input_["irrigacao"] = irr_n
    est = None
    if summer_stage is not None:
        e = cal.STAGES[current_summer][summer_stage]
        est = dict(id=summer_stage, nome=e["nome"], dias_tipicos_ate_colheita=e["dias"], fonte=cal.STAGES_SOURCE)
    out = dict(
        entrada=input_,
        cultura_atual=dict(id=current_summer, nome=E.SUMMER[current_summer]["nome"]),
        estagio_verao=est,
        colheita_estimada=harvest,
        semeadura_2a=None if sow_2nd is None else dict(data=sow_2nd, origem=sow_origin),
        dias_ate_colheita=days_until,
        atual=current,
        agora=now, proxima_safra=next_,
        ranking=now["ranking"], alternativas=now["alternativas"],
        eliminadas=now["eliminadas"] + next_["eliminadas"], avisos=warnings,
        metodologia=dict(formula="Nota = Σ peso_i × critério_i / Σ peso_i", criterios=_CRITERION_METHOD, versao=VERSION))
    applied = _applied_adjustments(aj_n, soil_phys, restr_n, irr_n) + EA.applied_adjustments(rk.get("estado_area"), solo_n is not None)
    if applied:
        out["metodologia"]["ajustes_aplicados"] = applied
    if include_diagnosis:
        out["diagnostico"] = diag
    return _clean(out)


# Options and warm-up
@lru_cache(maxsize=1)
def _demo_fields() -> list[dict]:
    demo = gpd.read_file(E.ROOT / "data/processed/ftw/candidatos_demo.geojson")
    out = [dict(id=E.FIELD_ID, **_field_point(E.FIELD_ID))]
    for tid in dict.fromkeys(demo["id"].astype(str)):
        if tid != E.FIELD_ID:
            out.append(dict(id=tid, **_field_point(tid)))
    return out


def _field_point(tid: str) -> dict:
    gdf = E.fields_gdf()
    row = gdf[gdf["id"].astype(str) == tid].iloc[0]
    poly = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(4326).iloc[0]
    lat, lon = _centroid(poly)
    return dict(area_ha=round(float(row["area_ha"]), 2), lat=round(lat, 5), lon=round(lon, 5))


def _capitalize(t: str) -> str:
    return t[0].upper() + t[1:]


def _combinations() -> list[dict]:
    """Every (summer, 2nd window) pair in the catalog. `semeaduras_validas`: 2nd-crop sowings in which the pair passes the calendar
    and legal rules (empty = always eliminated, e.g. soybean in the 2nd window)."""
    out = []
    for i, nome in ROTATIONS.items():
        c = E.CATALOG[nome]
        valid_items = [x for x in E.SOWINGS_2ND if not E.check_rules(c, {"semeadura": x})]
        out.append(dict(id=i, **({"id_legado": _legacy(i)} if _legacy(i) else {}), nome=nome, verao=c["verao"], segunda=c["segunda"],
                        valida=bool(valid_items), semeaduras_validas=valid_items,
                        motivo_se_invalida=None if valid_items else " ".join(E.check_rules(c, {"semeadura": E.DEFAULT_SOWING}))))
    return out


def options() -> dict:
    """Catalog to build the form: summer and 2nd-window crops, combinations (rotations), sowings, criteria, weights,
    income reference, region, demo fields."""
    ref = load_reference()
    sources = [dict(item=f"preço {k}", fonte=v["source"], periodo=v.get("period"), estimativa=v.get("estimate", False), url=v.get("url"))
              for k, v in ref["prices"].items()]
    sources += [dict(item=f"custo {k}", fonte=v["source"], estimativa=v.get("estimate", False), url=v.get("url"))
               for k, v in ref["costs"].items()]
    return _clean(dict(
        culturas_verao=[dict(id=k, nome=v["nome"], tipo="grão", descricao_curta=v["descricao"],
                             estagios=[dict(id=e, nome=d["nome"], dias_ate_colheita=d["dias"]) for e, d in cal.STAGES[k].items()],
                             colheita_catalogo=v["colheita"]) for k, v in E.SUMMER.items()],
        estagios_fonte=cal.STAGES_SOURCE, dias_preparo_2a=cal.PREP_DAYS_2ND,
        culturas_segunda=[dict(id=k, nome=_capitalize(v["nome"]), tipo=v["tipo"], descricao_curta=_DESCRIPTION[k]) for k, v in E.SECOND.items()],
        combinacoes=_combinations(),
        rotacoes=[dict(id=i, **({"id_legado": _legacy(i)} if _legacy(i) else {}), nome=n,
                       descricao_curta=_DESCRIPTION[E.CATALOG[n]["segunda"]] if E.CATALOG[n]["verao"] == "soja"
                       else f"{E.CATALOG[n]['nome_verao']} no verão, depois: {_DESCRIPTION[E.CATALOG[n]['segunda']]}")
                  for i, n in ROTATIONS.items()],
        semeaduras=list(E.SOWINGS_2ND), semeadura_padrao=E.DEFAULT_SOWING,
        criterios=[dict(id=k, nome=v) for k, v in E.CRITERIA.items()], pesos_padrao=dict(E.DEFAULT_WEIGHTS),
        renda_referencia=dict(
            precos={k: v["value"] for k, v in ref["prices"].items()},
            custos={k: {l: v[l] for l in ("coe", "cot", "ct") if l in v} for k, v in ref["costs"].items()},
            linha_custo_padrao=ref["default_cost_line"], fontes=sources),
        regiao=_region_info(), talhoes_demo=_demo_fields()))


def warm_up() -> None:
    """Preload heavy parquets/rasters/caches (call at API startup)."""
    E.fields_gdf()
    E._annual()
    _region_info()
    yields(None)
    _demo_fields()
    indicators_for(-24.9555, -53.4552)  # Cascavel: loads the climate lookup
    pam_yield("4104808")
    recommend({"talhao_id": E.FIELD_ID}, current_rotation="soja__milho_safrinha", include_diagnosis=False)
