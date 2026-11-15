"""Service layer of the Field Shift engine (no FastAPI): accepts any polygon in Western Paraná.

Public functions: opcoes(), diagnosticar(area, semeadura), recomendar(area, ...), aquecer().
Exceptions: ForaDaRegiao, EntradaInvalida, ErroConsultaExterna. Every output is JSON-serializable (NaN -> None).

`area` (exactly one form):
  {"geometry": <GeoJSON Polygon/MultiPolygon or Feature>}  EPSG:4326, order [lon, lat]
  {"lat": float, "lon": float}  point -> ~100 ha square (1000 m x 1000 m, UTM 22S) centered on the point
  {"talhao_id": "72638"}        FTW demo field (FTW parquet id)
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

from field_shift import calendario as cal
from field_shift.app import engine as E
from field_shift.clima.lookup import indicadores_para
from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import texto as pam_texto
from field_shift.regiao import dentro_da_regiao, historico_mapbiomas, relevo
from field_shift.regiao.recorte import REGIAO
from field_shift.renda import carregar_referencia, fonte_custo, fonte_preco, rendimentos
from field_shift.solo.solo import FONTE_ANALISE, texto as solo_texto

VERSAO = "0.1.0"
AREA_MAX_HA = 5000.0
PONTO_AREA_HA = 100.0
CRS_M = 32722  # UTM 22S (m), for areas and the point square


class ForaDaRegiao(Exception):
    """Área (ou parte dela) fora do Oeste do PR."""


class EntradaInvalida(Exception):
    """Invalid input: geometry, sowing date, rotation, weights, adjustments, area > 5000 ha, etc."""


class ErroConsultaExterna(Exception):
    """Timeout or connection failure when querying external APIs (NASA POWER / SoilGrids)."""


# Rotation = pair (summer crop, second-window crop). Stable id "<verao>__<segunda>" (e.g. soja__milho_safrinha) -> catalog name.
# The old API slugs (soybean in summer only: milho_safrinha, trigo...) are still accepted via E.LEGADO (milho_safrinha = soja__milho_safrinha).
ROTACOES: dict[str, str] = dict(E.NOME_DE)
_SLUG_DE = dict(E.ID_DE)
CULTURAS_VERAO = tuple(E.VERAO)
CULTURAS_SEGUNDA = tuple(E.SEGUNDA)

_DESCRICAO = {  # per second-window crop
    "milho_safrinha": "Corn in the second season, after soybean; the most common rotation in Western Paraná.",
    "milho_braquiaria": "Off-season corn intercropped with brachiaria: grain plus straw for no-till.",
    "trigo": "Winter wheat after soybean; sensitive to frost at flowering.",
    "aveia": "Oat for cover/straw (and occasional grain) in winter.",
    "milheto_crotalaria": "Millet and crotalaria cover: straw and nitrogen fixation, no grain sale.",
    "pousio": "No crop in the second window; exposed soil and no additional income.",
    "soja_safrinha": "Soybean after soybean in the same agricultural year; prohibited by regulation (always eliminated).",
    "sorgo": "Grain sorghum in the second season: drought tolerant, no corn leafhopper; uses grain machinery and the grain sales channel.",
    "feijao_safrinha": "Second-season beans: short cycle and good income in a good year, but sensitive to frost and dry spells and a host of white mold.",
    "nabo_forrageiro": "Forage radish cover: nutrient cycling and weed suppression, fast-decomposing straw; no grain sale.",
    "aveia_nabo": "Oat + forage radish cover mix: long-lasting straw and nutrient cycling, no grain sale.",
}

_CRIT_METODO = {
    "renda": "Incremental margin of the second season (municipal PAM yield × SEAB/DERAL price − CONAB cost; cover/fallow = "
             "−estimated cost; plus the straw/N bonus on the following soybean), on the scale S = max(municipal soybean margin, "
             "BRL 1,000/ha): renda = clip(0.5 + incremental / (2·S), 0, 1). Incremental +S = 1.0; zero = 0.5; −S = 0.",
    "solo": "Mean of straw cover, N fixation and (1 − days of bare soil/180); catalog values "
            "(reference estimates, to be validated with an agronomist/Embrapa).",
    "agua": "Mean over 34 years (1991–2024) of ΣETa/ΣETc in the second crop's critical phase, from a daily water balance "
            "(NASA POWER + available water capacity of the polygon's soil, SoilGrids); depends on the sowing date. Fallow = 1.0.",
    "pragas": "Potential to break the pest and disease cycle per rotation; catalog value (0–1), estimate to be validated.",
    "risco": "Π(1 − p) of the second crop's climate risks (frost, dry spell) in 1991–2024, ~50 km NASA POWER cell; "
             "no risk considered = 1.0.",
}

_CUSTO_ALIAS = {"milho": "milho_2safra", "milho_verao": "milho_1safra", "feijao": "feijao_2safra"}
_PRODUTIVIDADE = ("soja", "milho_2safra", "trigo", "milho_1safra", "feijao_2safra", "sorgo")


# --------------------------------------------------------------------------- utilities
def _limpo(o):
    """Converts to native JSON types: numpy -> python, NaN/inf -> None, tuples -> lists, keys -> str."""
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
        return {str(k): _limpo(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_limpo(v) for v in o]
    if isinstance(o, np.ndarray):
        return _limpo(o.tolist())
    if isinstance(o, pd.Series):
        return _limpo(o.to_dict())
    if isinstance(o, pd.DataFrame):
        return _limpo(o.to_dict("records"))
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if o is pd.NaT:
        return None
    return str(o)


def _num(v, nome: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
        raise EntradaInvalida(f"{nome} must be numeric (received: {v!r}).")
    f = float(v)
    if not math.isfinite(f):
        raise EntradaInvalida(f"{nome} deve ser finito.")
    if (lo is not None and f < lo) or (hi is not None and f > hi):
        raise EntradaInvalida(f"{nome} fora do intervalo [{lo}, {hi}] (recebido: {f}).")
    return f


@lru_cache(maxsize=1)
def _regiao_info() -> dict:
    r = gpd.read_file(REGIAO)
    b = [round(float(x), 4) for x in r.total_bounds]
    mun = gpd.read_file(REGIAO.parent / "municipios_oeste_pr.geojson")
    return dict(nome="Oeste do Paraná (IBGE 4106)", bbox=b, n_municipios=int(len(mun)))


def _proj_para_m():
    from pyproj import Transformer
    return (Transformer.from_crs(4326, CRS_M, always_xy=True), Transformer.from_crs(CRS_M, 4326, always_xy=True))


@lru_cache(maxsize=1)
def _transformers():
    return _proj_para_m()


def _area_ha(poly: BaseGeometry) -> float:
    from shapely.ops import transform
    t, _ = _transformers()
    return float(transform(t.transform, poly).area / 10_000.0)


def _centroide(poly: BaseGeometry) -> tuple[float, float]:
    from shapely.ops import transform
    t, inv = _transformers()
    c = transform(t.transform, poly).centroid
    lon, lat = inv.transform(c.x, c.y)
    return float(lat), float(lon)


def _geojson(poly: BaseGeometry) -> dict:
    import shapely
    return json.loads(shapely.to_geojson(shapely.set_precision(poly, 1e-6)))


# --------------------------------------------------------------------------- 1. resolve the area
def _poligono_geojson(g) -> BaseGeometry:
    if not isinstance(g, dict):
        raise EntradaInvalida("'geometry' deve ser um objeto GeoJSON (Polygon, MultiPolygon ou Feature).")
    if g.get("type") == "Feature":
        g = g.get("geometry")
        if not isinstance(g, dict):
            raise EntradaInvalida("Feature without geometry.")
    if g.get("type") not in ("Polygon", "MultiPolygon"):
        raise EntradaInvalida(f"Unsupported geometry type: {g.get('type')!r} (use Polygon, MultiPolygon or Feature).")
    try:
        poly = shape(g)
    except Exception as e:  # coordenadas malformadas
        raise EntradaInvalida(f"Geometria GeoJSON malformada: {e}") from e
    if poly.is_empty:
        raise EntradaInvalida("Geometria vazia.")
    minx, miny, maxx, maxy = poly.bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise EntradaInvalida("Non-finite coordinates.")
    if not (-180 <= minx and maxx <= 180 and -90 <= miny and maxy <= 90):
        raise EntradaInvalida("Coordinates outside EPSG:4326 (expected [lon, lat] in degrees).")
    if not poly.is_valid:
        from shapely.validation import explain_validity
        raise EntradaInvalida(f"Geometria inválida: {explain_validity(poly)}.")
    return poly


def _resolver_area(area: dict) -> dict:
    if not isinstance(area, dict):
        raise EntradaInvalida("'area' must be an object with 'geometry', 'lat'+'lon' or 'talhao_id'.")
    forma_geom, forma_ponto, forma_tid = "geometry" in area, ("lat" in area or "lon" in area), "talhao_id" in area
    if sum([forma_geom, forma_ponto, forma_tid]) != 1:
        raise EntradaInvalida("'area' must have exactly one form: {'geometry'}, {'lat','lon'} or {'talhao_id'}.")
    tid = None
    if forma_tid:
        tid = str(area["talhao_id"])
        gdf = E.gdf_talhoes()
        row = gdf[gdf["id"].astype(str) == tid]
        if row.empty:
            raise EntradaInvalida(f"talhao_id {tid!r} not found among the demo fields.")
        poly = gpd.GeoSeries([row.iloc[0].geometry], crs=gdf.crs).to_crs(4326).iloc[0]
        origem, lat, lon = "talhao_id", *_centroide(poly)
    elif forma_ponto:
        if not ("lat" in area and "lon" in area):
            raise EntradaInvalida("Ponto exige 'lat' e 'lon'.")
        lat, lon = _num(area["lat"], "lat", -90, 90), _num(area["lon"], "lon", -180, 180)
        if not dentro_da_regiao(Point(lon, lat)):
            raise ForaDaRegiao(f"The point (lat {lat:.5f}, lon {lon:.5f}) is outside Western Paraná; the engine only covers that region.")
        t, inv = _transformers()
        x, y = t.transform(lon, lat)
        h = 500.0
        sw, ne = inv.transform(x - h, y - h), inv.transform(x + h, y + h)
        poly = box(sw[0], sw[1], ne[0], ne[1])
        origem = "ponto"
    else:
        poly = _poligono_geojson(area["geometry"])
        origem, lat, lon = "geometry", *_centroide(poly)
    ha = _area_ha(poly)
    if ha <= 0:
        raise EntradaInvalida("Área nula.")
    if ha > AREA_MAX_HA:
        raise EntradaInvalida(f"Area of {ha:.0f} ha exceeds the {AREA_MAX_HA:.0f} ha limit.")
    if not dentro_da_regiao(poly):
        raise ForaDaRegiao("The area is not entirely inside Western Paraná (check the [lon, lat] order of the coordinates).")
    return dict(origem=origem, talhao_id=tid, poly=poly, area_ha=ha, lat=lat, lon=lon)


# --------------------------------------------------------------------------- 2. diagnosis
def _validar_semeadura(s) -> str:
    if s not in E.SEMEADURAS:
        raise EntradaInvalida(f"Invalid semeadura_safrinha: {s!r}. Options: {E.SEMEADURAS}.")
    return s


def _legado(id_: str | None) -> str | None:
    """Old API slug (soybean in summer only, the 7 original rotations): soja__milho_safrinha -> milho_safrinha; None for the others."""
    return id_.split("__", 1)[1] if id_ in E.LEGADO.values() else None


def _ids(id_: str) -> dict:
    """{'id': id novo} + 'id_legado' (slug antigo) quando existe."""
    leg = _legado(id_)
    return dict(id=id_, **({"id_legado": leg} if leg else {}))


def _resolver_id(x, campo: str) -> str:
    """Aceita o id novo ('soja__milho_safrinha') ou o slug antigo ('milho_safrinha' = soja__milho_safrinha)."""
    if isinstance(x, str) and x in ROTACOES:
        return x
    if isinstance(x, str) and x in E.LEGADO:
        return E.LEGADO[x]
    raise EntradaInvalida(f"Unknown {campo}: {x!r}. Options: {list(ROTACOES)} (or the old slugs {list(E.LEGADO)}).")


def _normalizar_rotacoes(r) -> list[str] | None:
    """Validates `rotacoes` ([{'verao','segunda'}], catalog enums, no duplicates, non-empty). Returns the ids in the given order, or None."""
    if r is None:
        return None
    if not isinstance(r, (list, tuple)) or not r:
        raise EntradaInvalida("'rotacoes' must be a non-empty list of {'verao', 'segunda'}.")
    ids = []
    for x in r:
        if not isinstance(x, dict) or set(x) != {"verao", "segunda"}:
            raise EntradaInvalida(f"Each rotation must be {{'verao': ..., 'segunda': ...}} (received: {x!r}).")
        if x["verao"] not in CULTURAS_VERAO:
            raise EntradaInvalida(f"Unknown verao: {x['verao']!r}. Options: {list(CULTURAS_VERAO)}.")
        if x["segunda"] not in CULTURAS_SEGUNDA:
            raise EntradaInvalida(f"Unknown segunda: {x['segunda']!r}. Options: {list(CULTURAS_SEGUNDA)}.")
        ids.append(E.id_rotacao(x["verao"], x["segunda"]))
    if len(set(ids)) != len(ids):
        raise EntradaInvalida("'rotacoes' has duplicated combinations.")
    return ids


def _rotacao_detectada(tid: str | None) -> dict:
    vazio = dict(rotacao=None, fonte=None, dias_solo_descoberto=None)
    if tid is None or not (E.ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv").exists():
        return vazio
    nd = E.carregar_ndvi(tid)
    picos = E.picos_por_ano_agricola(nd)
    return dict(rotacao=_legado(_SLUG_DE.get(E.detectar_rotacao(picos))),
                fonte="NDVI HLS Sentinel-2/Landsat (NASA): green peaks per agricultural year (Sep–Aug) = " + json.dumps(picos),
                dias_solo_descoberto=E.dias_solo_por_ano(nd), picos_por_ano_agricola=picos)


def _carregar_cache_nasa() -> dict | None:
    """Reads data/nasa_normalizado.json from disk if it exists (supports a dict with metadata or a list of records)."""
    caminho = E.ROOT / "data/nasa_normalizado.json"
    if not caminho.exists():
        return None
    try:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(conteudo, dict) and conteudo:
        return conteudo
    if isinstance(conteudo, list) and conteudo:
        return {"dados": conteudo, "total_registros": len(conteudo)}
    return None


def _contexto(area: dict, semeadura: str, analise_solo: dict | None = None) -> dict:
    """Computes everything diagnosticar/recomendar need; returns a dict with `rk` (enriched climate) and `diag` (output)."""
    semeadura = _validar_semeadura(semeadura)
    a = _resolver_area(area)
    poly = a["poly"]
    avisos = []
    try:
        rel = relevo(poly)
    except ValueError as e:
        raise EntradaInvalida(f"No terrain data for the area: {e}") from e

    cache_nasa = _carregar_cache_nasa()
    try:
        rk, origem = E.obter_clima(a["lat"], a["lon"], semeadura)
    except (TimeoutError, URLError, ConnectionError, requests.RequestException) as e:
        raise ErroConsultaExterna(
            f"Timeout or connection failure when querying NASA climate data: {e}"
        ) from e

    if rk.get("modo") != "regiao":
        raise ForaDaRegiao("Centroid without pre-computed climate indicators (outside Western Paraná).")

    try:
        rk = E.enriquecer(rk, dict(poly=poly), analise_solo)
    except (TimeoutError, URLError, ConnectionError, requests.RequestException) as e:
        raise ErroConsultaExterna(
            f"Timeout or connection failure when querying external soil/climate data: {e}"
        ) from e

    usou_cache_disco = cache_nasa is not None or "cache" in str(origem).lower()
    if cache_nasa is not None:
        dt_consulta = cache_nasa.get("data_consulta") or cache_nasa.get("consultado_em")
        detalhe = f" (queried on {dt_consulta})" if dt_consulta else ""
        avisos.append(f"Local NASA cache used: data/nasa_normalizado.json{detalhe}.")
    elif "cache" in str(origem).lower():
        avisos.append(f"Local NASA cache used: {origem}.")

    if a["origem"] == "ponto":
        avisos.append(f"Point converted into a ~{PONTO_AREA_HA:.0f} ha square centered on it; terrain, history and soil "
                      "apply to that square, not to the actual field.")
    if rk["solo"] is not None:
        avisos += rk["solo"].get("avisos", [])
    if rk["solo"] is None:
        avisos.append("No soil data (SoilGrids) for the area: the water criterion uses the cell's rain/ET0 estimate.")
    if rk["rend"]["_origem"].startswith("average"):
        avisos.append("No PAM for the municipality: yield = " + rk["rend"]["_origem"] + ".")
    hist = historico_mapbiomas(poly)
    historico = [dict(ano=int(r.ano), classe=int(r.classe), nome_classe=r.nome_classe,
                      fracao_dominante=None if pd.isna(r.fracao_dominante) else float(r.fracao_dominante))
                 for r in hist.itertuples()]
    ultimos = [h for h in historico if h["ano"] >= max(x["ano"] for x in historico) - 2]
    if ultimos and not any(h["nome_classe"] and ("Soja" in h["nome_classe"] or "Temporária" in h["nome_classe"]
                                                  or "Agri" in h["nome_classe"] or "Lavoura" in h["nome_classe"])
                           for h in ultimos):
        avisos.append("MapBiomas for recent years does not show cropland in the area; check the polygon.")
    rel_out = dict(rel, texto=f"Mean slope {rel['declividade_media']:.1f}% ({rel['classe_embrapa']}), "
                              f"mean elevation {rel['altitude_media']:.0f} m.")
    solo_out = None
    if rk["solo"]:
        s = rk["solo"]
        solo_out = dict(p30=s["p30"], prof=s["prof"], cad_mm_cm=s["cad_mm_cm"], cad_mm_0_30=s["cad_mm_0_30"],
                        cad_mm_0_60=s["cad_mm_0_60"], classe_textura=s["classe_textura"], cad_metodo=s["cad_metodo"],
                        texto=solo_texto(s), fonte=s.get("fonte") or "SoilGrids (ISRIC), polygon mean")
        if s.get("fonte") == FONTE_ANALISE:
            solo_out["profundidade_amostra_cm"] = s["amostra_profundidade_cm"]
    d = rk["diagnostico"]
    cel = rk["celula"]
    clima = dict(
        fonte=rk["fonte"], cache_utilizado=usou_cache_disco,
        celula=dict(id=cel["ponto_id"], lat=cel["lat"], lon=cel["lon"], elev=cel["elev"]),
        semeadura_safrinha=semeadura,
        riscos=dict(geada_safrinha=round(rk["geada_safrinha"], 3), geada_trigo=round(rk["geada_trigo"], 3),
                    veranico_safrinha=round(rk["veranico_safrinha"], 3), n_anos=rk["n_anos"], periodo=rk["periodo"]),
        geada_por_semeadura=[dict(semeadura=r["semeadura"], prob=round(r["prob"], 3), anos_com_evento=r["anos"], n_anos=r["n_anos"])
                             for r in rk["geada_tabela"]],
        diagnostico=dict(
            inicio_chuvas=dict(mediana=d["inicio_chuvas_mediana"], p80=d["inicio_chuvas_p80"]),
            calor_soja=dict(mediana=d["calor_soja_mediana"], media=d["calor_soja_media"], p80=d["calor_soja_p80"]),
            balanco_p_et0=dict(soja=d["balanco_soja"], safrinha=d["balanco_safrinha"], trigo=d["balanco_trigo"]),
            chuva_intensa=dict(media=d["chuva_intensa_media"], mediana=d["chuva_intensa_mediana"])),
        textos=E.fmt_diagnostico(d))
    pam = rk["pam"]
    prod = dict(municipio=rk["municipio"]["nome"], cod_ibge=str(rk["municipio"]["cod_ibge"]), fonte="IBGE PAM",
                culturas=pam["dados"] if pam else {}, texto=pam_texto(pam["nome"], pam["dados"]) if pam else None,
                rendimento_usado=rk["rend"]["_origem"])
    mun = rk["municipio"]
    diag = dict(
        area=dict(origem=a["origem"], talhao_id=a["talhao_id"], area_ha=a["area_ha"], centroide=dict(lat=a["lat"], lon=a["lon"]),
                  municipio=dict(cod_ibge=str(mun["cod_ibge"]), nome=mun["nome"]), geometry=_geojson(poly)),
        relevo=rel_out, solo=solo_out, historico=historico, rotacao_detectada=_rotacao_detectada(a["talhao_id"]),
        clima=clima, produtividade=prod, avisos=avisos)
    return dict(rk=rk, diag=_limpo(diag), dias_solo_ndvi=diag["rotacao_detectada"]["dias_solo_descoberto"])


def diagnosticar(area: dict, semeadura_safrinha: str = "01/02", analise_solo: dict | None = None) -> dict:
    """Diagnosis of the area (terrain, soil 0–30 cm + available water capacity, MapBiomas history, cell climate, municipal PAM).
    `analise_solo` (optional, see `recomendar`) replaces SoilGrids in the soil block.

    Raises EntradaInvalida (invalid geometry/sowing date/area/soil analysis), ForaDaRegiao or ErroConsultaExterna."""
    return _contexto(area, semeadura_safrinha, _normalizar_analise_solo(analise_solo))["diag"]


# Rounding only at serialization (the calculation and the ranking order use full precision).
def _arred(o, casas: int):
    if isinstance(o, dict):
        return {k: _arred(v, casas) for k, v in o.items()}
    return None if o is None else round(float(o), casas)


def _arredondar_ranking(item: dict) -> dict:
    """nota, criterios and contribuicoes with 3 decimals; BRL values with 0 decimals; yields/prices/probabilities 3 decimals."""
    r0 = lambda x: None if x is None else float(round(x))
    item["nota"] = _arred(item["nota"], 3)
    item["criterios"] = _arred(item["criterios"], 3)
    item["contribuicoes"] = _arred(item["contribuicoes"], 3)
    m = item["margem"]
    for k in ("total_r_ha", "incremental_r_ha", "escala_S_r_ha", "ano_ruim_r_ha", "bonus_proxima_soja_r_ha"):
        m[k] = r0(m[k])
    for i in m["itens"]:
        i["margem_r_ha"], i["custo"] = r0(i["margem_r_ha"]), r0(i["custo"])
        i["rendimento_sc_ha"] = None if i["rendimento_sc_ha"] is None else round(i["rendimento_sc_ha"], 1)
        i["preco"] = None if i["preco"] is None else round(i["preco"], 2)
    return item


# --------------------------------------------------------------------------- 3. recommendation
def _normalizar_ajustes(aj) -> dict:
    """Accepts {"precos": {soja, milho, trigo, feijao, sorgo}, "custos": {soja, milho|milho_2safra, milho_verao|milho_1safra,
    trigo, feijao|feijao_2safra, sorgo, aveia, milheto_crotalaria, braquiaria_consorcio, pousio, nabo_forrageiro, aveia_nabo},
    "linha_custo": coe|cot|ct}; returns the engine format (preco/custo/linha_custo)."""
    if aj is None:
        return {}
    if not isinstance(aj, dict):
        raise EntradaInvalida("'ajustes' deve ser um objeto.")
    ref = carregar_referencia()
    desconhecidas = set(aj) - {"precos", "custos", "linha_custo", "produtividade"}
    if desconhecidas:
        raise EntradaInvalida(f"Unknown adjustment keys: {sorted(desconhecidas)}.")
    out: dict = {}
    for k, v in (aj.get("precos") or {}).items():
        if k not in ref["precos"]:
            raise EntradaInvalida(f"Unknown price: {k!r}. Options: {sorted(ref['precos'])}.")
        out.setdefault("preco", {})[k] = _num(v, f"price {k}", 0)
    for k, v in (aj.get("custos") or {}).items():
        kk = _CUSTO_ALIAS.get(k, k)
        if kk not in ref["custos"]:
            raise EntradaInvalida(f"Unknown cost: {k!r}. Options: {sorted(ref['custos']) + ['milho']}.")
        out.setdefault("custo", {})[kk] = _num(v, f"custo {k}", 0)
    prod = aj.get("produtividade")
    if prod is not None:
        if not isinstance(prod, dict):
            raise EntradaInvalida("'ajustes.produtividade' must be an object {crop: bags/ha}.")
        if "milho" in prod and "milho_2safra" in prod:
            raise EntradaInvalida("Provide the 2nd-season corn yield in 'milho' OR 'milho_2safra', not both.")
        for k, v in prod.items():
            kk = _CUSTO_ALIAS.get(k, k)
            if kk not in _PRODUTIVIDADE:
                raise EntradaInvalida(f"Unknown yield: {k!r}. Options: ['soja', 'milho', 'milho_2safra', 'milho_verao', "
                                      "'milho_1safra', 'trigo', 'feijao', 'feijao_2safra', 'sorgo'].")
            if kk in out.get("produtividade", {}):
                raise EntradaInvalida(f"Yield for {kk} provided twice (alias).")
            f = _num(v, f"produtividade {k}", 0, 500)
            if f <= 0:
                raise EntradaInvalida(f"yield {k} must be greater than zero (received: {f}).")
            out.setdefault("produtividade", {})[kk] = f
    lc = aj.get("linha_custo")
    if lc is not None:
        if lc not in ("coe", "cot", "ct"):
            raise EntradaInvalida("linha_custo deve ser 'coe', 'cot' ou 'ct'.")
        out["linha_custo"] = lc
    return out


_CAMPOS_SOLO = {"argila_pct", "areia_pct", "materia_organica_pct", "carbono_organico_g_kg", "ph", "cad_mm_cm", "profundidade_cm"}


def _normalizar_analise_solo(a) -> dict | None:
    """Validates the farmer's soil analysis. Returns {argila_pct, areia_pct, soc_g_kg, ph, cad_mm_cm, profundidade_cm}
    (only what was sent; `profundidade_cm` defaults to 20) or None. Requires clay+sand OR cad_mm_cm."""
    if a is None:
        return None
    if not isinstance(a, dict):
        raise EntradaInvalida("'analise_solo' deve ser um objeto.")
    desc = set(a) - _CAMPOS_SOLO
    if desc:
        raise EntradaInvalida(f"Unknown fields in analise_solo: {sorted(desc)}. Options: {sorted(_CAMPOS_SOLO)}.")
    a = {k: v for k, v in a.items() if v is not None}
    out: dict = {}
    for k in ("argila_pct", "areia_pct"):
        if k in a:
            out[k] = _num(a[k], k, 0, 100)
    if ("argila_pct" in out) != ("areia_pct" in out):
        raise EntradaInvalida("Informe argila_pct e areia_pct juntos (ou apenas cad_mm_cm).")
    if "argila_pct" in out and out["argila_pct"] + out["areia_pct"] > 100:
        raise EntradaInvalida("argila_pct + areia_pct cannot exceed 100.")
    if "materia_organica_pct" in a and "carbono_organico_g_kg" in a:
        raise EntradaInvalida("Provide materia_organica_pct OR carbono_organico_g_kg, not both.")
    if "materia_organica_pct" in a:
        out["soc_g_kg"] = _num(a["materia_organica_pct"], "materia_organica_pct", 0, 100) / 1.724 * 10.0
    if "carbono_organico_g_kg" in a:
        out["soc_g_kg"] = _num(a["carbono_organico_g_kg"], "carbono_organico_g_kg", 0, 580)
    if "ph" in a:
        out["ph"] = _num(a["ph"], "ph", 3, 9)
    if "cad_mm_cm" in a:
        out["cad_mm_cm"] = _num(a["cad_mm_cm"], "cad_mm_cm", 0.3, 3)
    if "argila_pct" not in out and "cad_mm_cm" not in out:
        raise EntradaInvalida("analise_solo exige argila_pct e areia_pct, ou cad_mm_cm.")
    out["profundidade_cm"] = _num(a["profundidade_cm"], "profundidade_cm", 1, 200) if "profundidade_cm" in a else 20.0
    return out


_SEM_COMPRADOR = {"milho": "milho", "milho_2safra": "milho", "trigo": "trigo", "sorgo": "sorgo", "feijao": "feijao", "aveia_grao": "aveia_grao"}


def _normalizar_restricoes(r) -> dict | None:
    """Validates `restricoes`. Returns {'excluidas': {catalog names}, 'maquinas': {...}, 'sem_comprador': {...},
    'eco': normalized input format} or None."""
    if r is None:
        return None
    if not isinstance(r, dict):
        raise EntradaInvalida("'restricoes' deve ser um objeto.")
    desc = set(r) - {"culturas_excluidas", "maquinas", "sem_comprador"}
    if desc:
        raise EntradaInvalida(f"Unknown fields in restricoes: {sorted(desc)}.")
    exc = r.get("culturas_excluidas") or []
    sem = r.get("sem_comprador") or []
    maq = r.get("maquinas") or {}
    if not isinstance(exc, list) or not isinstance(sem, list) or not isinstance(maq, dict):
        raise EntradaInvalida("restricoes: 'culturas_excluidas' and 'sem_comprador' are lists; 'maquinas' is an object.")
    exc = [_resolver_id(x, "excluded rotation") for x in exc]  # new ids or old slugs (= soja__<slug>)
    for x in sem:
        if x not in _SEM_COMPRADOR:
            raise EntradaInvalida(f"Unknown sem_comprador: {x!r}. Options: {sorted(_SEM_COMPRADOR)}.")
    for k, v in maq.items():
        if k not in E.CUSTO_MAQUINA:
            raise EntradaInvalida(f"Unknown machine: {k!r}. Options: {sorted(E.CUSTO_MAQUINA)}.")
        if not isinstance(v, bool):
            raise EntradaInvalida(f"maquinas.{k} deve ser true ou false.")
    return dict(excluidas={ROTACOES[x] for x in exc}, maquinas=dict(maq), sem_comprador={_SEM_COMPRADOR[x] for x in sem},
                eco=dict(culturas_excluidas=list(dict.fromkeys(exc)), maquinas=dict(maq),
                         sem_comprador=list(dict.fromkeys(sem))))


def _normalizar_irrigacao(i) -> dict | None:
    """Validates `irrigacao`: {disponivel: bool, custo_r_mm_ha (default 4.0), lamina_max_mm_dia (default 6)}."""
    if i is None:
        return None
    if not isinstance(i, dict):
        raise EntradaInvalida("'irrigacao' deve ser um objeto.")
    desc = set(i) - {"disponivel", "custo_r_mm_ha", "lamina_max_mm_dia"}
    if desc:
        raise EntradaInvalida(f"Unknown fields in irrigacao: {sorted(desc)}.")
    if not isinstance(i.get("disponivel"), bool):
        raise EntradaInvalida("irrigacao.disponivel is required and must be true or false.")
    custo = E.CUSTO_IRRIGACAO_PADRAO if i.get("custo_r_mm_ha") is None else _num(i["custo_r_mm_ha"], "custo_r_mm_ha", 0, 100)
    lam = E.LAMINA_MAX_PADRAO if i.get("lamina_max_mm_dia") is None else _num(i["lamina_max_mm_dia"], "lamina_max_mm_dia", 0, 30)
    if lam <= 0:
        raise EntradaInvalida("lamina_max_mm_dia must be greater than zero.")
    return dict(disponivel=i["disponivel"], custo_r_mm_ha=custo, lamina_max_mm_dia=lam)


def _normalizar_pesos(pesos) -> dict:
    out = dict(E.PESOS_PADRAO)
    if pesos is None:
        return out
    if not isinstance(pesos, dict):
        raise EntradaInvalida("'pesos' deve ser um objeto.")
    for k, v in pesos.items():
        if k not in E.CRITERIOS:
            raise EntradaInvalida(f"Unknown weight: {k!r}. Criteria: {list(E.CRITERIOS)}.")
        out[k] = _num(v, f"peso {k}", 0, 10)
    return out


def _verao_segunda(nome: str) -> dict:
    c = E.CATALOGO[nome]
    return dict(verao=dict(id=c["verao"], nome=c["nome_verao"]), segunda=dict(id=c["segunda"], nome=_maiuscula(c["nome_segunda"])))


def _item_ranking(pos, nome, linha, marg, atual, rk, dias_ndvi, por_que_cmp=None) -> dict:
    card = E.montar_card(linha, atual, rk, dias_ndvi, marg, por_que_cmp)
    itens = []
    for i in marg["itens"]:
        itens.append(dict(
            cultura=i["rotulo"], rendimento_sc_ha=i["sc_ha"], preco=i["preco"], custo=i["custo"], margem_r_ha=i["margem"],
            fonte=(f"yield provided by the farmer; price {fonte_preco(i)}; cost {fonte_custo(i, marg['linha_custo'])}"
                   if i.get("prod_usuario") else
                   f"yield IBGE PAM ({E.local_rend(rk, i['chave'])}, {i['anos']}); price {fonte_preco(i)}; cost {fonte_custo(i, marg['linha_custo'])}"
                   if i["sc_ha"] is not None else
                   f"extra cost: {i['detalhe']} (no sale)" if i.get("extra") else
                   f"cost {fonte_custo(i, marg['linha_custo'])} (no sale)")))
    avisos = []
    if marg["total"] < 0:
        avisos.append("Negative total margin with the prices and costs used.")
    margem = dict(total_r_ha=marg["total"], incremental_r_ha=marg["incremental"], escala_S_r_ha=marg["escala_S"], itens=itens, ano_ruim_r_ha=marg["total_ano_ruim"],
                  bonus_proxima_soja_r_ha=marg["bonus"], linha_custo=marg["linha_custo"])
    return dict(
        posicao=pos, **_ids(_SLUG_DE[nome]), **_verao_segunda(nome), rotacao=nome, nota=float(linha["nota"]), atual=atual,
        criterios={k: float(linha[k]) for k in E.CRITERIOS},
        contribuicoes={k: float(v) for k, v in linha["contrib"].items()}, margem=margem,
        card=dict(por_que=card["por_que"], evidencias=card["evidencia"], beneficios=card["beneficios"],
                  lacunas=card["lacunas"], riscos=card["revisar"], avisos=avisos + card["avisos"], mercado=card["mercado"]),
        **({"irrigacao": dict(lamina_media_mm_ano=round(card["irrigacao"]["lamina_media_mm"], 1),
                                           custo_r_ha=float(round(card["irrigacao"]["custo_r_ha"])))}
           if card["irrigacao"] else {}))


def _ajustes_aplicados(aj: dict, solo, restr, irr) -> list[str]:
    """One sentence per adjustment/optional input used (goes into metodologia.ajustes_aplicados)."""
    o = []
    if aj.get("preco"):
        o.append("Prices provided by the farmer (" + ", ".join(f"{k} BRL {v:g}/bag" for k, v in aj["preco"].items())
                 + ") replace the SEAB/DERAL 12-month average.")
    if aj.get("custo"):
        o.append("Costs provided by the farmer (" + ", ".join(f"{k} BRL {v:g}/ha" for k, v in aj["custo"].items())
                 + ") replace the CONAB cost.")
    if aj.get("linha_custo"):
        o.append(f"CONAB cost line '{aj['linha_custo']}' instead of the default.")
    if aj.get("produtividade"):
        o.append("Yield provided by the farmer (" + ", ".join(f"{k} {v:g} bags/ha" for k, v in aj["produtividade"].items())
                 + ") replaces the municipal PAM yield; the bad year scales proportionally (own × PAM p20/average); "
                 "the soybean value also changes the income scale S.")
    if solo:
        o.append("The farmer's soil analysis replaces SoilGrids in the diagnosis and in the water-balance available water capacity"
                 + (" (capacity provided directly)." if "cad_mm_cm" in solo else " (capacity by Saxton & Rawls with the analysis)."))
    if restr:
        e = restr["eco"]
        if e["culturas_excluidas"]:
            o.append("Rotations excluded by the farmer: " + ", ".join(e["culturas_excluidas"]) + ".")
        if e["sem_comprador"]:
            o.append("No local buyer (eliminates the rotations that depend on the sale): " + ", ".join(e["sem_comprador"])
                     + ("; aveia_grao has no effect, because oat is treated as a cover crop without sale." if "aveia_grao" in e["sem_comprador"] else "."))
        sem = [k for k, v in e["maquinas"].items() if v is False]
        if sem:
            o.append("Machines the farmer does not have (" + ", ".join(sem) + "): the rotation is not eliminated; it gets a warning and an extra "
                     "outsourcing cost (estimates, to be validated).")
    if irr and irr["disponivel"]:
        o.append(f"Irrigation available (BRL {irr['custo_r_mm_ha']:g}/mm/ha, max. depth {irr['lamina_max_mm_dia']:g} mm/day): irrigates "
                 "corn, corn+brachiaria, wheat, sorghum and beans when depletion exceeds p (0.55; beans 0.45); water goes up, dry spells do not count in the risk and the "
                 "margin subtracts depth × cost. The yield gain from irrigation is not modeled; cover crops and fallow are not irrigated.")
    return o


_FONTE_RENDA = "data: IBGE PAM yield × SEAB/DERAL price − CONAB cost (or the values provided by the farmer)"
_FONTE_SOLO = "catalog estimate, to be validated with an agronomist/Embrapa"


def _ganho_vs_atual(res: dict, nome: str, nome_atual: str) -> dict | None:
    """How the candidate improves (or worsens) production relative to the current rotation. None if it is the current one or if the
    current one was eliminated (no margin to compare). Signed values: positive = the candidate gains."""
    m, ma = res["margens"].get(nome), res["margens"].get(nome_atual)
    if nome == nome_atual or m is None or ma is None:
        return None
    c, ca = E.CATALOGO[nome], E.CATALOGO[nome_atual]
    t = res["tabela"].set_index("candidata")
    sc = c["bonus_sc"] - ca["bonus_sc"]
    faixa = (c["bonus_sc_faixa"][0] - ca["bonus_sc_faixa"][1], c["bonus_sc_faixa"][1] - ca["bonus_sc_faixa"][0])  # pior e melhor caso
    renda_2a = sum(i["margem"] for i in m["itens"][1:]) - sum(i["margem"] for i in ma["itens"][1:])
    return dict(
        comparado_com=E.ID_DE[nome_atual],
        soja_seguinte_sc=round(sc, 1), soja_seguinte_sc_faixa=[round(faixa[0], 1), round(faixa[1], 1)],
        soja_seguinte_rs=float(round(sc * m["preco_soja"])), preco_soja_r_sc=round(m["preco_soja"], 2),
        fonte=f"following soybean: {c['bonus_fonte']} (SEAB/DERAL soybean price)",
        renda_2a_safra=dict(r_ha=float(round(renda_2a)), origem=_FONTE_RENDA),
        margem_total=dict(r_ha=float(round(m["total"] - ma["total"])), origem=_FONTE_RENDA + "; includes the bonus on the following soybean"),
        solo=dict(dias_descobertos=c["dias_descobertos"] - ca["dias_descobertos"],
                  cobertura=round(c["cobertura"] - ca["cobertura"], 2), origem=_FONTE_SOLO + " (negative days = less bare soil)"),
        agua=dict(criterio=round(float(t.loc[nome, "agua"] - t.loc[nome_atual, "agua"]), 3),
                  origem="data: daily water balance with NASA POWER and soil available water capacity"),
        risco_climatico=dict(criterio=round(float(t.loc[nome, "risco"] - t.loc[nome_atual, "risco"]), 3),
                             origem="data: frost and dry spells in NASA POWER (1991–2024)"))


def _data_referencia(d) -> date | None:
    if d is None or isinstance(d, date):
        return d
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        raise EntradaInvalida(f"data_referencia must be an ISO date (YYYY-MM-DD); received: {d!r}.") from None


def recomendar(area: dict, semeadura_safrinha: str | None = None, pesos: dict | None = None,
               rotacao_atual: str | None = None, ajustes: dict | None = None,
               n_alternativas: int = 3, incluir_diagnostico: bool = True, analise_solo: dict | None = None,
               restricoes: dict | None = None, irrigacao: dict | None = None, rotacoes: list[dict] | None = None,
               estagio_verao: str | None = None, colheita_prevista: str | None = None, data_referencia=None) -> dict:
    """What can go in after the summer harvest and how it improves production, plus what to change in the next season.

    rotacao_atual (REQUIRED): ROTACOES id ("soja__milho_safrinha") or old slug ("milho_safrinha" = soja__milho_safrinha).
    estagio_verao (optional): stage of the current rotation's summer crop (calendario.ESTAGIOS; soybean: vegetativo, floracao,
      formacao_vagens, enchimento_graos, maturacao, colhida; summer corn: vegetativo, pendoamento, grao_leitoso, grao_farinaceo,
      maturacao, colhida). estimated harvest = data_referencia + typical days of the stage.
    colheita_prevista (optional, dd/mm): overrides the stage. data_referencia (optional, date or ISO; default today).
    semeadura_safrinha (optional): without it, it is the first SEMEADURAS date >= estimated harvest (+ preparation); with it, it overrides
      the derived date but cannot be earlier than the harvest. Without a stage or harvest: catalog assumption (harvest) and 01/02 (sowing).
      Harvest after the last SEMEADURAS date: the second-window crops that follow the sowing date are eliminated.

    Output: `agora` (same summer as the current rotation: ranking, alternatives, eliminated) and `proxima_safra` (the other summer), each item with
    `ganho_vs_atual`. `ranking`, `alternativas` and `eliminadas` at the top level are aliases of `agora` (eliminadas = union of both blocks).

    rotacoes (optional): [{"verao": "soja"|"milho_verao", "segunda": <second-window crop>}]; if present, evaluates and ranks only
      those (closed catalog enums; non-empty, no duplicates); each pair goes into the block of its summer crop. Without `rotacoes`, evaluates
      every catalog combination. A combination eliminated by the rules comes back in `eliminadas` with the reason (not an error).

    pesos: renda, solo, agua, pragas, risco (0–10; missing = default {renda 5, others 3}; all 0 = equal weights).
    ajustes (all optional):
      "precos": {"soja"|"milho"|"trigo": BRL per 60 kg bag}
      "custos": {"soja"|"milho"|"milho_verao"|"trigo"|"feijao"|"sorgo"|"aveia"|"milheto_crotalaria"|"braquiaria_consorcio"|
                "pousio"|"nabo_forrageiro"|"aveia_nabo": BRL/ha} ("milho" = 2nd-season corn; "milho_verao" = 1st-season corn)
      "linha_custo": "coe" (variable cost, default) | "cot" | "ct"  (CONAB; applies to soybean, corn and wheat)
      "produtividade": {"soja"|"milho"|"milho_2safra"|"milho_verao"|"trigo"|"feijao"|"sorgo": bags/ha > 0}  replaces the municipal PAM yield; the bad year
                scales proportionally (own × PAM p20/average); the soybean value also changes the income scale S
    analise_solo (optional): {"argila_pct", "areia_pct", "materia_organica_pct"|"carbono_organico_g_kg", "ph", "cad_mm_cm",
      "profundidade_cm"}; requires clay+sand or cad_mm_cm. Replaces SoilGrids in the diagnosis and in the water-balance capacity.
    restricoes (optional): {"culturas_excluidas": [slugs], "maquinas": {"plataforma_milho": bool, "semeadora_consorcio": bool},
      "sem_comprador": ["milho"|"trigo"|"aveia_grao"]}. Excluded/no buyer -> eliminated; machine false -> warning + extra
      outsourcing cost (estimate); omitted machine = available.
    irrigacao (optional): {"disponivel": bool, "custo_r_mm_ha": 4.0, "lamina_max_mm_dia": 6}. Irrigates second-window corn, corn+brachiaria,
      wheat, sorghum and beans (not cover/fallow or the summer crop): water goes up, dry spells do not count in the risk, the margin subtracts depth × cost.
      The yield gain from irrigation is NOT modeled.
    n_alternativas: 1–6 best rotations of each block, excluding the current one. If the current one is eliminated by the hard rules
    (e.g. soja__soja_safrinha or a harvest that is too late), `atual` holds {"eliminada": True, "motivos": [...]}, with no position or score
    (and no `ganho_vs_atual` in the items). With a `rotacoes` list that does not include the current one, `atual` holds {"avaliada": False}."""
    if rotacao_atual is None:
        raise EntradaInvalida("'rotacao_atual' is required (id '<verao>__<segunda>', e.g. soja__milho_safrinha).")
    if semeadura_safrinha is not None:
        semeadura_safrinha = _validar_semeadura(semeadura_safrinha)
    pesos_n = _normalizar_pesos(pesos)
    aj_n = _normalizar_ajustes(ajustes)
    solo_n = _normalizar_analise_solo(analise_solo)
    restr_n = _normalizar_restricoes(restricoes)
    irr_n = _normalizar_irrigacao(irrigacao)
    sel = _normalizar_rotacoes(rotacoes)
    rotacao_atual = _resolver_id(rotacao_atual, "rotacao_atual")
    if isinstance(n_alternativas, bool) or not isinstance(n_alternativas, int) or not 1 <= n_alternativas <= 6:
        raise EntradaInvalida("n_alternativas deve ser um inteiro entre 1 e 6.")
    nome_atual = ROTACOES[rotacao_atual]
    verao_atual = E.CATALOGO[nome_atual]["verao"]
    data_ref = _data_referencia(data_referencia) or date.today()
    try:
        cron = cal.resolver(verao_atual, estagio_verao, colheita_prevista, data_ref, semeadura_safrinha)
    except ValueError as e:
        raise EntradaInvalida(str(e)) from e
    avisos_cal = []
    if cron:
        colheita = dict(data=cron["colheita"], origem=cron["origem"])
        dias_ate = cron["dias_ate_colheita"]
        sem_2a = cron["semeadura_2a"]  # None = harvest too late
        sem_origem = "informada" if semeadura_safrinha else "derivada"
        if colheita_prevista is not None and estagio_verao is not None:
            avisos_cal.append("colheita_prevista e estagio_verao informados: vale a colheita_prevista.")
        if semeadura_safrinha:
            avisos_cal.append(f"semeadura_safrinha {semeadura_safrinha} provided: it replaces the date derived from the harvest "
                              f"(first date >= harvest: {cal.semeadura_derivada(cron['data']) or 'none'}).")
        if sem_2a is None:
            avisos_cal.append(f"{E.VERAO[verao_atual]['nome']} harvest estimated at ~{cron['colheita']}, after the last "
                              f"sowing date considered ({E.SEMEADURAS[-1]}): too late for the off-season; only the fixed-date "
                              "crops (winter and cover) are still evaluated.")
    else:
        colheita = dict(data=E.VERAO[verao_atual]["colheita"], origem="premissa")
        dias_ate = None
        sem_2a = semeadura_safrinha or E.SEMEADURA_PADRAO
        sem_origem = "informada" if semeadura_safrinha else "premissa"
        avisos_cal.append(f"No estagio_verao or colheita_prevista: {E.VERAO[verao_atual]['nome'].lower()} harvest assumed on "
                          f"~{colheita['data']} (catalog assumption, estimate)"
                          + ("" if semeadura_safrinha else f" and second-window sowing on {sem_2a} (default)")
                          + ". Provide the summer crop's stage for an answer about what goes in after the harvest.")
    ctx = _contexto(area, sem_2a or E.SEMEADURAS[-1], solo_n)
    rk, diag = ctx["rk"], ctx["diag"]
    rk["restr"] = restr_n
    rk["irrig"] = irr_n if irr_n and irr_n["disponivel"] else None
    if cron:
        rk["colheita_produtor"] = dict(verao=verao_atual, colheita=cron["colheita"])
    avisos = list(diag["avisos"]) + avisos_cal
    if rk["irrig"] and rk.get("agua_ctx") is None:
        avisos.append("Irrigation provided, but there is no soil for the water balance: ignored.")
    dias = ctx["dias_solo_ndvi"]
    dias = float("nan") if dias is None else dias
    # the current rotation is always evaluated (for ganho_vs_atual), even outside `rotacoes`; it only appears if it is in `rotacoes`
    avaliar = None if sel is None else list(dict.fromkeys([ROTACOES[i] for i in sel] + [nome_atual]))
    try:
        res = E.pontuar(pesos_n, rk, aj_n, avaliar)
    except E.SemCandidatas as e:
        if sel is None:
            raise EntradaInvalida(str(e)) from e
        res = dict(tabela=pd.DataFrame(columns=["candidata"]), eliminadas=e.eliminadas, margens={}, aviso_renda=None)
    if res["aviso_renda"]:
        avisos.append(res["aviso_renda"])
    pedidas = None if sel is None else {ROTACOES[i] for i in sel}
    mostrar = lambda n: pedidas is None or n in pedidas  # noqa: E731
    no_agora = lambda n: E.CATALOGO[n]["verao"] == verao_atual  # noqa: E731
    elim = {n: m for n, m in res["eliminadas"].items() if mostrar(n)}

    def bloco(agora: bool) -> dict:
        nomes = [n for n in res["tabela"]["candidata"] if mostrar(n) and no_agora(n) == agora]
        tab = res["tabela"]
        res_b = dict(res, tabela=tab[tab["candidata"].isin(nomes + ([nome_atual] if not agora and mostrar(nome_atual) else []))]
                     .reset_index(drop=True))
        itens = []
        for pos, (_, linha) in enumerate(res_b["tabela"][res_b["tabela"]["candidata"].isin(nomes)].iterrows(), start=1):
            n = linha["candidata"]
            item = _item_ranking(pos, n, linha, res["margens"][n], n == nome_atual, rk, dias if n == nome_atual else float("nan"),
                                 E.por_que_comparado(res_b, n, nome_atual))
            item["ganho_vs_atual"] = _ganho_vs_atual(res, n, nome_atual)
            itens.append(_arredondar_ranking(item))
        el = [dict(**_ids(_SLUG_DE[n]), **_verao_segunda(n), rotacao=n, motivos=list(m)) for n, m in elim.items() if no_agora(n) == agora]
        return dict(ranking=itens, alternativas=[r for r in itens if not r["atual"]][:n_alternativas], eliminadas=el)

    agora, proxima = bloco(True), bloco(False)
    if sel is not None and not agora["ranking"] and not proxima["ranking"]:
        avisos.append("Every rotation requested in 'rotacoes' was eliminated by the rules or restrictions (see 'eliminadas').")
    atual = next((r for r in agora["ranking"] if r["atual"]), None)
    if atual is None and nome_atual in res["eliminadas"]:
        mot = res["eliminadas"][nome_atual]
        atual = dict(posicao=None, **_ids(rotacao_atual), rotacao=nome_atual, nota=None, atual=True, eliminada=True, motivos=list(mot))
        avisos.append(f"The current rotation ({nome_atual}) is eliminated ({'hard rules or farmer restrictions' if restr_n else 'hard rules'}): "
                      + " ".join(mot))
    elif atual is None:
        atual = dict(posicao=None, **_ids(rotacao_atual), rotacao=nome_atual, nota=None, atual=True, avaliada=False)
        avisos.append(f"The current rotation ({nome_atual}) is not in 'rotacoes': it was neither evaluated nor compared.")
    entrada = dict(semeadura_safrinha=sem_2a, pesos=pesos_n, rotacao_atual=rotacao_atual, estagio_verao=estagio_verao,
                   colheita_prevista=colheita_prevista, data_referencia=data_ref.isoformat(),
                   ajustes=ajustes or {}, n_alternativas=n_alternativas)
    if sel is not None:
        entrada["rotacoes"] = [dict(verao=E.CATALOGO[ROTACOES[i]]["verao"], segunda=E.CATALOGO[ROTACOES[i]]["segunda"]) for i in sel]
    if solo_n:
        entrada["analise_solo"] = {k: v for k, v in dict(solo_n, cad_mm_cm=solo_n.get("cad_mm_cm")).items() if v is not None}
        if "soc_g_kg" in solo_n:
            entrada["analise_solo"]["carbono_organico_g_kg"] = round(entrada["analise_solo"].pop("soc_g_kg"), 2)
    if restr_n:
        entrada["restricoes"] = restr_n["eco"]
    if irr_n:
        entrada["irrigacao"] = irr_n
    est = None
    if estagio_verao is not None:
        e = cal.ESTAGIOS[verao_atual][estagio_verao]
        est = dict(id=estagio_verao, nome=e["nome"], dias_tipicos_ate_colheita=e["dias"], fonte=cal.FONTE_ESTAGIOS)
    out = dict(
        entrada=entrada,
        cultura_atual=dict(id=verao_atual, nome=E.VERAO[verao_atual]["nome"]),
        estagio_verao=est,
        colheita_estimada=colheita,
        semeadura_2a=None if sem_2a is None else dict(data=sem_2a, origem=sem_origem),
        dias_ate_colheita=dias_ate,
        atual=atual,
        agora=agora, proxima_safra=proxima,
        ranking=agora["ranking"], alternativas=agora["alternativas"],
        eliminadas=agora["eliminadas"] + proxima["eliminadas"], avisos=avisos,
        metodologia=dict(formula="Score = Σ weight_i × criterion_i / Σ weight_i", criterios=_CRIT_METODO, versao=VERSAO))
    aplicados = _ajustes_aplicados(aj_n, solo_n, restr_n, irr_n)
    if aplicados:
        out["metodologia"]["ajustes_aplicados"] = aplicados
    if incluir_diagnostico:
        out["diagnostico"] = diag
    return _limpo(out)


# --------------------------------------------------------------------------- 4. options and warm-up
@lru_cache(maxsize=1)
def _talhoes_demo() -> list[dict]:
    demo = gpd.read_file(E.ROOT / "data/processed/ftw/candidatos_demo.geojson")
    out = [dict(id=E.TALHAO_ID, **_ponto_talhao(E.TALHAO_ID))]
    for tid in dict.fromkeys(demo["id"].astype(str)):
        if tid != E.TALHAO_ID:
            out.append(dict(id=tid, **_ponto_talhao(tid)))
    return out


def _ponto_talhao(tid: str) -> dict:
    gdf = E.gdf_talhoes()
    row = gdf[gdf["id"].astype(str) == tid].iloc[0]
    poly = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(4326).iloc[0]
    lat, lon = _centroide(poly)
    return dict(area_ha=round(float(row["area_ha"]), 2), lat=round(lat, 5), lon=round(lon, 5))


def _maiuscula(t: str) -> str:
    return t[0].upper() + t[1:]


def _combinacoes() -> list[dict]:
    """Every (summer, second-window) pair in the catalog. `semeaduras_validas`: second-crop sowing dates for which the pair passes the
    calendar and legal rules (empty = always eliminated, e.g. soybean in the second window)."""
    out = []
    for i, nome in ROTACOES.items():
        c = E.CATALOGO[nome]
        validas = [x for x in E.SEMEADURAS if not E.checar_regras(c, {"semeadura": x})]
        out.append(dict(id=i, **({"id_legado": _legado(i)} if _legado(i) else {}), nome=nome, verao=c["verao"], segunda=c["segunda"],
                        valida=bool(validas), semeaduras_validas=validas,
                        motivo_se_invalida=None if validas else " ".join(E.checar_regras(c, {"semeadura": E.SEMEADURA_PADRAO}))))
    return out


def opcoes() -> dict:
    """Catalog for building the form: summer and second-window crops, combinations (rotations), sowing dates, criteria, weights,
    income reference, region, demo fields."""
    ref = carregar_referencia()
    fontes = [dict(item=f"price {k}", fonte=v["fonte"], periodo=v.get("periodo"), estimativa=v.get("estimativa", False), url=v.get("url"))
              for k, v in ref["precos"].items()]
    fontes += [dict(item=f"cost {k}", fonte=v["fonte"], estimativa=v.get("estimativa", False), url=v.get("url"))
               for k, v in ref["custos"].items()]
    return _limpo(dict(
        culturas_verao=[dict(id=k, nome=v["nome"], tipo="grão", descricao_curta=v["descricao"],
                             estagios=[dict(id=e, nome=d["nome"], dias_ate_colheita=d["dias"]) for e, d in cal.ESTAGIOS[k].items()],
                             colheita_catalogo=v["colheita"]) for k, v in E.VERAO.items()],
        estagios_fonte=cal.FONTE_ESTAGIOS, dias_preparo_2a=cal.DIAS_PREPARO_2A,
        culturas_segunda=[dict(id=k, nome=_maiuscula(v["nome"]), tipo=v["tipo"], descricao_curta=_DESCRICAO[k]) for k, v in E.SEGUNDA.items()],
        combinacoes=_combinacoes(),
        rotacoes=[dict(id=i, **({"id_legado": _legado(i)} if _legado(i) else {}), nome=n,
                       descricao_curta=_DESCRICAO[E.CATALOGO[n]["segunda"]] if E.CATALOGO[n]["verao"] == "soja"
                       else f"{E.CATALOGO[n]['nome_verao']} in summer, then: {_DESCRICAO[E.CATALOGO[n]['segunda']]}")
                  for i, n in ROTACOES.items()],
        semeaduras=list(E.SEMEADURAS), semeadura_padrao=E.SEMEADURA_PADRAO,
        criterios=[dict(id=k, nome=v) for k, v in E.CRITERIOS.items()], pesos_padrao=dict(E.PESOS_PADRAO),
        renda_referencia=dict(
            precos={k: v["valor"] for k, v in ref["precos"].items()},
            custos={k: {l: v[l] for l in ("coe", "cot", "ct") if l in v} for k, v in ref["custos"].items()},
            linha_custo_padrao=ref["linha_custo_padrao"], fontes=fontes),
        regiao=_regiao_info(), talhoes_demo=_talhoes_demo()))


def aquecer() -> None:
    """Preloads heavy parquets/rasters/caches (call on API startup)."""
    E.gdf_talhoes()
    E._anuais()
    _regiao_info()
    rendimentos(None)
    _talhoes_demo()
    indicadores_para(-24.9555, -53.4552)  # Cascavel: carrega o lookup climático
    pam_produtividade("4104808")
    recomendar({"talhao_id": E.TALHAO_ID}, rotacao_atual="soja__milho_safrinha", incluir_diagnostico=False)
