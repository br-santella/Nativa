"""Camada de serviço do motor Field Shift (sem FastAPI): aceita qualquer polígono do Paraná.

Funções públicas: opcoes(), diagnosticar(area, semeadura), recomendar(area, ...), aquecer().
Exceções: ForaDaRegiao, EntradaInvalida, ErroConsultaExterna. Todas as saídas são JSON-serializáveis (NaN -> None).

`area` (exatamente uma forma):
  {"geometry": <GeoJSON Polygon/MultiPolygon ou Feature>}  EPSG:4326, ordem [lon, lat]
  {"lat": float, "lon": float}  ponto -> quadrado de ~100 ha (1000 m x 1000 m, UTM 22S) centrado no ponto
  {"talhao_id": "72638"}        talhão demo do FTW (id do parquet FTW)
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
from field_shift.app import estado_area as EA
from field_shift.clima.lookup import indicadores_para
from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import texto as pam_texto
from field_shift.regiao import dentro_da_regiao, dentro_do_oeste, historico_mapbiomas, relevo
from field_shift.regiao.recorte import REGIAO
from field_shift.renda import carregar_referencia, fonte_custo, fonte_preco, rendimentos
from field_shift.solo.solo import FONTE_ANALISE, texto as solo_texto

VERSAO = "0.1.0"
AREA_MAX_HA = 5000.0
PONTO_AREA_HA = 100.0
CRS_M = 32722  # UTM 22S (m), para áreas e quadrado do ponto


# Shown when the area centroid is in Paraná but outside the Oeste mesoregion (the reference region of costs, prices and calendar).
AVISOS_FORA_DO_OESTE = [
    "Área fora do Oeste do Paraná: os custos de produção e os preços usados na renda são a referência do Oeste do PR "
    "(SEAB/DERAL e CONAB) e podem diferir na sua região.",
    "Área fora do Oeste do Paraná: o calendário (vazio sanitário da soja 02/06–31/08 e semeadura da soja 01/09–31/12) foi "
    "pesquisado para o Oeste e pode diferir por região; confirme a portaria vigente da ADAPAR e o ZARC do município.",
]


class ForaDaRegiao(Exception):
    """Área (ou parte dela) fora do Paraná."""


class EntradaInvalida(Exception):
    """Entrada inválida: geometria, semeadura, rotação, pesos, ajustes, área > 5000 ha etc."""


class ErroConsultaExterna(Exception):
    """Timeout ou falha de ligação ao consultar APIs externas (NASA POWER / SoilGrids)."""


# Rotação = par (cultura de verão, cultura da 2ª janela). id estável "<verao>__<segunda>" (ex.: soja__milho_safrinha) -> nome do catálogo.
# Os slugs antigos da API (só soja no verão: milho_safrinha, trigo...) seguem aceitos em E.LEGADO (milho_safrinha = soja__milho_safrinha).
ROTACOES: dict[str, str] = dict(E.NOME_DE)
_SLUG_DE = dict(E.ID_DE)
CULTURAS_VERAO = tuple(E.VERAO)
CULTURAS_SEGUNDA = tuple(E.SEGUNDA)

_DESCRICAO = {  # por cultura da 2ª janela
    "milho_safrinha": "Milho na segunda safra, após a soja; rotação mais comum no Oeste do PR.",
    "milho_braquiaria": "Milho safrinha consorciado com braquiária: grãos mais palhada para o plantio direto.",
    "trigo": "Trigo de inverno após a soja; sensível a geada no florescimento.",
    "aveia": "Aveia para cobertura/palha (e eventual grão) no inverno.",
    "milheto_crotalaria": "Cobertura de milheto e crotalária: palhada e fixação de nitrogênio, sem venda de grão.",
    "pousio": "Sem cultura na segunda janela; solo exposto e sem renda adicional.",
    "soja_safrinha": "Soja sobre soja no mesmo ano agrícola; proibida pela regulação (sempre eliminada).",
    "sorgo": "Sorgo granífero na segunda safra: tolerante à seca, sem cigarrinha do milho; usa o maquinário e o canal de venda de grãos.",
    "feijao_safrinha": "Feijão de 2ª safra: ciclo curto e boa renda em ano bom, mas sensível a geada e veranico e hospedeiro do mofo-branco.",
    "nabo_forrageiro": "Cobertura de nabo forrageiro: ciclagem de nutrientes e supressão de daninhas, palha de decomposição rápida; sem venda de grão.",
    "aveia_nabo": "Mix de cobertura aveia + nabo forrageiro: palha duradoura e ciclagem de nutrientes, sem venda de grão.",
}

_CRIT_METODO = {
    "renda": "Margem incremental da 2ª safra (rendimento PAM do município × preço SEAB/DERAL − custo CONAB; cobertura/pousio = "
             "−custo estimado; mais o bônus de palhada/N na soja seguinte), na escala S = max(margem da soja do município, "
             "R$ 1.000/ha): renda = clip(0,5 + incremental / (2·S), 0, 1). Incremental +S = 1,0; zero = 0,5; −S = 0.",
    "solo": "Média de cobertura de palha, fixação de N e (1 − dias de solo descoberto/180); valores de catálogo "
            "(estimativas de referência, validar com agrônomo/Embrapa).",
    "agua": "Média nos 34 anos (1991–2024) de ΣETa/ΣETc na fase crítica da 2ª cultura, por balanço hídrico diário "
            "(NASA POWER + CAD do solo do polígono, SoilGrids); depende da data de semeadura. Pousio = 1,0.",
    "pragas": "Potencial de quebra de ciclo de pragas e doenças por rotação; valor de catálogo (0–1), estimativa a validar.",
    "risco": "Π(1 − p) dos riscos climáticos da 2ª cultura (geada, veranico) em 1991–2024, célula NASA POWER ~50 km; "
             "sem risco considerado = 1,0.",
}

_CUSTO_ALIAS = {"milho": "milho_2safra", "milho_verao": "milho_1safra", "feijao": "feijao_2safra"}
_PRODUTIVIDADE = ("soja", "milho_2safra", "trigo", "milho_1safra", "feijao_2safra", "sorgo")


# --------------------------------------------------------------------------- utilidades
def _limpo(o):
    """Converte para tipos nativos JSON: numpy -> python, NaN/inf -> None, tuplas -> listas, chaves -> str."""
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
        raise EntradaInvalida(f"{nome} deve ser numérico (recebido: {v!r}).")
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
    mun = gpd.read_file(REGIAO.parent / "municipios_pr.geojson")
    return dict(nome="Paraná (IBGE 41)", bbox=b, n_municipios=int(len(mun)))


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


# --------------------------------------------------------------------------- 1. resolver a área
def _poligono_geojson(g) -> BaseGeometry:
    if not isinstance(g, dict):
        raise EntradaInvalida("'geometry' deve ser um objeto GeoJSON (Polygon, MultiPolygon ou Feature).")
    if g.get("type") == "Feature":
        g = g.get("geometry")
        if not isinstance(g, dict):
            raise EntradaInvalida("Feature sem geometria.")
    if g.get("type") not in ("Polygon", "MultiPolygon"):
        raise EntradaInvalida(f"Tipo de geometria não suportado: {g.get('type')!r} (use Polygon, MultiPolygon ou Feature).")
    try:
        poly = shape(g)
    except Exception as e:  # coordenadas malformadas
        raise EntradaInvalida(f"Geometria GeoJSON malformada: {e}") from e
    if poly.is_empty:
        raise EntradaInvalida("Geometria vazia.")
    minx, miny, maxx, maxy = poly.bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise EntradaInvalida("Coordenadas não finitas.")
    if not (-180 <= minx and maxx <= 180 and -90 <= miny and maxy <= 90):
        raise EntradaInvalida("Coordenadas fora de EPSG:4326 (esperado [lon, lat] em graus).")
    if not poly.is_valid:
        from shapely.validation import explain_validity
        raise EntradaInvalida(f"Geometria inválida: {explain_validity(poly)}.")
    return poly


def _resolver_area(area: dict) -> dict:
    if not isinstance(area, dict):
        raise EntradaInvalida("'area' deve ser um objeto com 'geometry', 'lat'+'lon' ou 'talhao_id'.")
    forma_geom, forma_ponto, forma_tid = "geometry" in area, ("lat" in area or "lon" in area), "talhao_id" in area
    if sum([forma_geom, forma_ponto, forma_tid]) != 1:
        raise EntradaInvalida("'area' deve ter exatamente uma forma: {'geometry'}, {'lat','lon'} ou {'talhao_id'}.")
    tid = None
    if forma_tid:
        tid = str(area["talhao_id"])
        gdf = E.gdf_talhoes()
        row = gdf[gdf["id"].astype(str) == tid]
        if row.empty:
            raise EntradaInvalida(f"talhao_id {tid!r} não encontrado entre os talhões demo.")
        poly = gpd.GeoSeries([row.iloc[0].geometry], crs=gdf.crs).to_crs(4326).iloc[0]
        origem, lat, lon = "talhao_id", *_centroide(poly)
    elif forma_ponto:
        if not ("lat" in area and "lon" in area):
            raise EntradaInvalida("Ponto exige 'lat' e 'lon'.")
        lat, lon = _num(area["lat"], "lat", -90, 90), _num(area["lon"], "lon", -180, 180)
        if not dentro_da_regiao(Point(lon, lat)):
            raise ForaDaRegiao(f"O ponto (lat {lat:.5f}, lon {lon:.5f}) está fora do Paraná; o motor só cobre o estado.")
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
        raise EntradaInvalida(f"Área de {ha:.0f} ha excede o limite de {AREA_MAX_HA:.0f} ha.")
    if not dentro_da_regiao(poly):
        raise ForaDaRegiao("A área não está inteiramente dentro do Paraná (confira a ordem [lon, lat] das coordenadas).")
    return dict(origem=origem, talhao_id=tid, poly=poly, area_ha=ha, lat=lat, lon=lon)


# --------------------------------------------------------------------------- 2. diagnóstico
def _validar_semeadura(s) -> str:
    if s not in E.SEMEADURAS:
        raise EntradaInvalida(f"semeadura_safrinha inválida: {s!r}. Opções: {E.SEMEADURAS}.")
    return s


def _legado(id_: str | None) -> str | None:
    """Slug antigo da API (só soja no verão, as 7 rotações originais): soja__milho_safrinha -> milho_safrinha; None para as demais."""
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
    raise EntradaInvalida(f"{campo} desconhecida: {x!r}. Opções: {list(ROTACOES)} (ou os slugs antigos {list(E.LEGADO)}).")


def _normalizar_rotacoes(r) -> list[str] | None:
    """Valida `rotacoes` ([{'verao','segunda'}], enums do catálogo, sem duplicatas, não vazia). Devolve os ids na ordem dada, ou None."""
    if r is None:
        return None
    if not isinstance(r, (list, tuple)) or not r:
        raise EntradaInvalida("'rotacoes' deve ser uma lista não vazia de {'verao', 'segunda'}.")
    ids = []
    for x in r:
        if not isinstance(x, dict) or set(x) != {"verao", "segunda"}:
            raise EntradaInvalida(f"Cada rotação deve ser {{'verao': ..., 'segunda': ...}} (recebido: {x!r}).")
        if x["verao"] not in CULTURAS_VERAO:
            raise EntradaInvalida(f"verao desconhecida: {x['verao']!r}. Opções: {list(CULTURAS_VERAO)}.")
        if x["segunda"] not in CULTURAS_SEGUNDA:
            raise EntradaInvalida(f"segunda desconhecida: {x['segunda']!r}. Opções: {list(CULTURAS_SEGUNDA)}.")
        ids.append(E.id_rotacao(x["verao"], x["segunda"]))
    if len(set(ids)) != len(ids):
        raise EntradaInvalida("'rotacoes' tem combinações duplicadas.")
    return ids


def _rotacao_detectada(tid: str | None) -> dict:
    vazio = dict(rotacao=None, fonte=None, dias_solo_descoberto=None)
    if tid is None or not (E.ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv").exists():
        return vazio
    nd = E.carregar_ndvi(tid)
    picos = E.picos_por_ano_agricola(nd)
    return dict(rotacao=_legado(_SLUG_DE.get(E.detectar_rotacao(picos))),
                fonte="NDVI HLS Sentinel-2/Landsat (NASA): picos de verde por ano agrícola (set–ago) = " + json.dumps(picos),
                dias_solo_descoberto=E.dias_solo_por_ano(nd), picos_por_ano_agricola=picos)


def _carregar_cache_nasa() -> dict | None:
    """Lê data/nasa_normalizado.json do disco se existir (suporta dict com metadados ou lista de registos)."""
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


def _contexto(area: dict, semeadura: str, analise_solo: dict | None = None, fert: dict | None = None) -> dict:
    """Calcula tudo que diagnosticar/recomendar precisam; devolve dict com `rk` (clima enriquecido) e `diag` (saída)."""
    semeadura = _validar_semeadura(semeadura)
    a = _resolver_area(area)
    poly = a["poly"]
    avisos = []
    try:
        rel = relevo(poly)
    except ValueError as e:
        raise EntradaInvalida(f"Sem dados de relevo para a área: {e}") from e

    cache_nasa = _carregar_cache_nasa()
    try:
        rk, origem = E.obter_clima(a["lat"], a["lon"], semeadura)
    except (TimeoutError, URLError, ConnectionError, requests.RequestException) as e:
        raise ErroConsultaExterna(
            f"Timeout ou falha de ligação ao consultar dados climáticos da NASA: {e}"
        ) from e

    if rk.get("modo") != "regiao":
        raise ForaDaRegiao("Centroide sem indicadores climáticos pré-calculados (fora do Paraná).")

    try:
        rk = E.enriquecer(rk, dict(poly=poly), analise_solo)
    except (TimeoutError, URLError, ConnectionError, requests.RequestException) as e:
        raise ErroConsultaExterna(
            f"Timeout ou falha de ligação ao consultar dados externos de solo/clima: {e}"
        ) from e

    usou_cache_disco = cache_nasa is not None or "cache" in str(origem).lower()
    if cache_nasa is not None:
        dt_consulta = cache_nasa.get("data_consulta") or cache_nasa.get("consultado_em")
        detalhe = f" (consultado em {dt_consulta})" if dt_consulta else ""
        avisos.append(f"Cache local NASA utilizado: data/nasa_normalizado.json{detalhe}.")
    elif "cache" in str(origem).lower():
        avisos.append(f"Cache local NASA utilizado: {origem}.")

    if analise_solo is None and fert is not None and rk["solo"] is not None:
        avisos.append("Análise de solo só com fertilidade (sem argila/areia nem CAD): textura e CAD seguem o SoilGrids.")
    if not dentro_do_oeste(Point(a["lon"], a["lat"])):
        avisos += AVISOS_FORA_DO_OESTE
    if a["origem"] == "ponto":
        avisos.append(f"Ponto convertido em quadrado de ~{PONTO_AREA_HA:.0f} ha centrado nele; relevo, histórico e solo "
                      "valem para esse quadrado, não para a lavoura real.")
    if rk["solo"] is not None:
        avisos += rk["solo"].get("avisos", [])
    if rk["solo"] is None:
        avisos.append("Sem dados de solo (SoilGrids) para a área: o critério água usa a estimativa por chuva/ET0 da célula.")
    if rk["rend"]["_origem"].startswith("média"):
        avisos.append("Sem PAM do município: rendimento = " + rk["rend"]["_origem"] + ".")
    hist = historico_mapbiomas(poly)
    historico = [dict(ano=int(r.ano), classe=int(r.classe), nome_classe=r.nome_classe,
                      fracao_dominante=None if pd.isna(r.fracao_dominante) else float(r.fracao_dominante))
                 for r in hist.itertuples()]
    ultimos = [h for h in historico if h["ano"] >= max(x["ano"] for x in historico) - 2]
    if ultimos and not any(h["nome_classe"] and ("Soja" in h["nome_classe"] or "Temporária" in h["nome_classe"]
                                                  or "Agri" in h["nome_classe"] or "Lavoura" in h["nome_classe"])
                           for h in ultimos):
        avisos.append("O MapBiomas dos últimos anos não indica lavoura na área; confira o polígono.")
    rel_out = dict(rel, texto=f"Declividade média {rel['declividade_media']:.1f}% ({rel['classe_embrapa']}), "
                              f"altitude média {rel['altitude_media']:.0f} m.")
    solo_out = None
    if rk["solo"]:
        s = rk["solo"]
        solo_out = dict(p30=s["p30"], prof=s["prof"], cad_mm_cm=s["cad_mm_cm"], cad_mm_0_30=s["cad_mm_0_30"],
                        cad_mm_0_60=s["cad_mm_0_60"], classe_textura=s["classe_textura"], cad_metodo=s["cad_metodo"],
                        texto=solo_texto(s), fonte=s.get("fonte") or "SoilGrids (ISRIC), média no polígono")
        if s.get("fonte") == FONTE_ANALISE:
            solo_out["profundidade_amostra_cm"] = s["amostra_profundidade_cm"]
    fert_out = None
    if fert:
        fert_out = dict(valores=fert["valores"], classes=fert["classes"], v_pct_origem=fert["v_origem"], severidade_acidez=fert["severidade_acidez"],
                        nao_informados=fert["ausentes"], fonte="análise de solo do produtor; classes: " + EA.FONTE_MANUAL)
        if fert.get("argila_faixa_g_kg"):
            fert_out["argila_faixa_g_kg"] = fert["argila_faixa_g_kg"]
            fert_out["argila_origem"] = fert["argila_origem"]
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
    if fert_out:
        diag["fertilidade"] = fert_out
    return dict(rk=rk, diag=_limpo(diag), dias_solo_ndvi=diag["rotacao_detectada"]["dias_solo_descoberto"])


def diagnosticar(area: dict, semeadura_safrinha: str = "01/02", analise_solo: dict | None = None) -> dict:
    """Diagnóstico da área (relevo, solo 0–30 cm + CAD, histórico MapBiomas, clima da célula, PAM do município).
    `analise_solo` (opcional, ver `recomendar`) substitui o SoilGrids no bloco solo.

    Lança EntradaInvalida (geometria/semeadura/área/análise de solo inválidas), ForaDaRegiao ou ErroConsultaExterna."""
    fis, fert = _separar_fertilidade(_normalizar_analise_solo(analise_solo))
    return _contexto(area, semeadura_safrinha, fis, fert)["diag"]


# Arredondamento só na serialização (o cálculo e a ordem do ranking usam precisão total).
def _arred(o, casas: int):
    if isinstance(o, dict):
        return {k: _arred(v, casas) for k, v in o.items()}
    return None if o is None else round(float(o), casas)


def _arredondar_ranking(item: dict) -> dict:
    """nota, criterios e contribuicoes com 3 casas; valores em R$ com 0 casas; rendimentos/preços/probabilidades 3 casas."""
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


# --------------------------------------------------------------------------- 3. recomendação
def _normalizar_ajustes(aj) -> dict:
    """Aceita {"precos": {soja, milho, trigo, feijao, sorgo}, "custos": {soja, milho|milho_2safra, milho_verao|milho_1safra,
    trigo, feijao|feijao_2safra, sorgo, aveia, milheto_crotalaria, braquiaria_consorcio, pousio, nabo_forrageiro, aveia_nabo},
    "linha_custo": coe|cot|ct}; devolve o formato do engine (preco/custo/linha_custo)."""
    if aj is None:
        return {}
    if not isinstance(aj, dict):
        raise EntradaInvalida("'ajustes' deve ser um objeto.")
    ref = carregar_referencia()
    desconhecidas = set(aj) - {"precos", "custos", "linha_custo", "produtividade"}
    if desconhecidas:
        raise EntradaInvalida(f"Chaves de ajustes desconhecidas: {sorted(desconhecidas)}.")
    out: dict = {}
    for k, v in (aj.get("precos") or {}).items():
        if k not in ref["precos"]:
            raise EntradaInvalida(f"Preço desconhecido: {k!r}. Opções: {sorted(ref['precos'])}.")
        out.setdefault("preco", {})[k] = _num(v, f"preço {k}", 0)
    for k, v in (aj.get("custos") or {}).items():
        kk = _CUSTO_ALIAS.get(k, k)
        if kk not in ref["custos"]:
            raise EntradaInvalida(f"Custo desconhecido: {k!r}. Opções: {sorted(ref['custos']) + ['milho']}.")
        out.setdefault("custo", {})[kk] = _num(v, f"custo {k}", 0)
    prod = aj.get("produtividade")
    if prod is not None:
        if not isinstance(prod, dict):
            raise EntradaInvalida("'ajustes.produtividade' deve ser um objeto {cultura: sc/ha}.")
        if "milho" in prod and "milho_2safra" in prod:
            raise EntradaInvalida("Informe a produtividade do milho 2ª safra em 'milho' OU 'milho_2safra', não nas duas.")
        for k, v in prod.items():
            kk = _CUSTO_ALIAS.get(k, k)
            if kk not in _PRODUTIVIDADE:
                raise EntradaInvalida(f"Produtividade desconhecida: {k!r}. Opções: ['soja', 'milho', 'milho_2safra', 'milho_verao', "
                                      "'milho_1safra', 'trigo', 'feijao', 'feijao_2safra', 'sorgo'].")
            if kk in out.get("produtividade", {}):
                raise EntradaInvalida(f"Produtividade de {kk} informada duas vezes (alias).")
            f = _num(v, f"produtividade {k}", 0, 500)
            if f <= 0:
                raise EntradaInvalida(f"produtividade {k} deve ser maior que zero (recebido: {f}).")
            out.setdefault("produtividade", {})[kk] = f
    lc = aj.get("linha_custo")
    if lc is not None:
        if lc not in ("coe", "cot", "ct"):
            raise EntradaInvalida("linha_custo deve ser 'coe', 'cot' ou 'ct'.")
        out["linha_custo"] = lc
    return out


_CAMPOS_FERT = set(EA.CAMPOS_FERTILIDADE)  # fertilidade (opcional): p_mg_dm3, k/ca/mg/al/ctc_cmolc_dm3, v_pct
_CAMPOS_SOLO = {"argila_pct", "areia_pct", "materia_organica_pct", "carbono_organico_g_kg", "ph", "cad_mm_cm", "profundidade_cm"} | _CAMPOS_FERT


def _normalizar_problemas_area(p) -> list[str] | None:
    """Valida `problemas_area` (lista fechada de catalog/vocabulario.yaml; sem duplicatas). None/[] = não informado."""
    if p is None:
        return None
    if not isinstance(p, (list, tuple)):
        raise EntradaInvalida(f"'problemas_area' deve ser uma lista (opções: {list(EA.PROBLEMAS)}).")
    for x in p:
        if x not in EA.PROBLEMAS:
            raise EntradaInvalida(f"problema_area desconhecido: {x!r}. Opções: {list(EA.PROBLEMAS)}.")
    return list(dict.fromkeys(p)) or None


def _separar_fertilidade(solo_n: dict | None) -> tuple[dict | None, dict | None]:
    """Divide a análise validada em (parte física/CAD que substitui o SoilGrids | None, fertilidade interpretada | None)."""
    if not solo_n:
        return None, None
    fert = EA.preparar_fertilidade({k: v for k, v in solo_n.items() if k in _CAMPOS_FERT}, solo_n.get("argila_pct"))
    fis = {k: v for k, v in solo_n.items() if k not in _CAMPOS_FERT}
    return (fis if ("argila_pct" in fis or "cad_mm_cm" in fis) else None), fert


def _normalizar_analise_solo(a) -> dict | None:
    """Valida a análise de solo do produtor. Devolve {argila_pct, areia_pct, soc_g_kg, ph, cad_mm_cm, profundidade_cm}
    (só o que veio; `profundidade_cm` padrão 20) ou None. Exige argila+areia OU cad_mm_cm OU algum campo de fertilidade
    (p_mg_dm3, k_cmolc_dm3, ca_cmolc_dm3, mg_cmolc_dm3, al_cmolc_dm3, v_pct, ctc_cmolc_dm3: todos opcionais, nada é estimado
    quando faltam)."""
    if a is None:
        return None
    if not isinstance(a, dict):
        raise EntradaInvalida("'analise_solo' deve ser um objeto.")
    desc = set(a) - _CAMPOS_SOLO
    if desc:
        raise EntradaInvalida(f"Campos desconhecidos em analise_solo: {sorted(desc)}. Opções: {sorted(_CAMPOS_SOLO)}.")
    a = {k: v for k, v in a.items() if v is not None}
    out: dict = {}
    for k in ("argila_pct", "areia_pct"):
        if k in a:
            out[k] = _num(a[k], k, 0, 100)
    if ("argila_pct" in out) != ("areia_pct" in out):
        raise EntradaInvalida("Informe argila_pct e areia_pct juntos (ou apenas cad_mm_cm).")
    if "argila_pct" in out and out["argila_pct"] + out["areia_pct"] > 100:
        raise EntradaInvalida("argila_pct + areia_pct não pode passar de 100.")
    if "materia_organica_pct" in a and "carbono_organico_g_kg" in a:
        raise EntradaInvalida("Informe materia_organica_pct OU carbono_organico_g_kg, não os dois.")
    if "materia_organica_pct" in a:
        out["soc_g_kg"] = _num(a["materia_organica_pct"], "materia_organica_pct", 0, 100) / 1.724 * 10.0
    if "carbono_organico_g_kg" in a:
        out["soc_g_kg"] = _num(a["carbono_organico_g_kg"], "carbono_organico_g_kg", 0, 580)
    if "ph" in a:
        out["ph"] = _num(a["ph"], "ph", 3, 9)
    if "cad_mm_cm" in a:
        out["cad_mm_cm"] = _num(a["cad_mm_cm"], "cad_mm_cm", 0.3, 3)
    for k, (lo, hi) in EA.CAMPOS_FERTILIDADE.items():
        if k in a:
            out[k] = _num(a[k], k, lo, hi)
    if "argila_pct" not in out and "cad_mm_cm" not in out and not any(k in out for k in _CAMPOS_FERT):
        raise EntradaInvalida("analise_solo exige argila_pct e areia_pct, ou cad_mm_cm, ou algum campo de fertilidade.")
    out["profundidade_cm"] = _num(a["profundidade_cm"], "profundidade_cm", 1, 200) if "profundidade_cm" in a else 20.0
    return out


_SEM_COMPRADOR = {"milho": "milho", "milho_2safra": "milho", "trigo": "trigo", "sorgo": "sorgo", "feijao": "feijao", "aveia_grao": "aveia_grao"}


def _normalizar_restricoes(r) -> dict | None:
    """Valida `restricoes`. Devolve {'excluidas': {nomes do catálogo}, 'maquinas': {...}, 'sem_comprador': {...},
    'eco': formato de entrada normalizado} ou None."""
    if r is None:
        return None
    if not isinstance(r, dict):
        raise EntradaInvalida("'restricoes' deve ser um objeto.")
    desc = set(r) - {"culturas_excluidas", "maquinas", "sem_comprador"}
    if desc:
        raise EntradaInvalida(f"Campos desconhecidos em restricoes: {sorted(desc)}.")
    exc = r.get("culturas_excluidas") or []
    sem = r.get("sem_comprador") or []
    maq = r.get("maquinas") or {}
    if not isinstance(exc, list) or not isinstance(sem, list) or not isinstance(maq, dict):
        raise EntradaInvalida("restricoes: 'culturas_excluidas' e 'sem_comprador' são listas; 'maquinas' é um objeto.")
    exc = [_resolver_id(x, "Rotação excluída") for x in exc]  # ids novos ou slugs antigos (= soja__<slug>)
    for x in sem:
        if x not in _SEM_COMPRADOR:
            raise EntradaInvalida(f"sem_comprador desconhecido: {x!r}. Opções: {sorted(_SEM_COMPRADOR)}.")
    for k, v in maq.items():
        if k not in E.CUSTO_MAQUINA:
            raise EntradaInvalida(f"Máquina desconhecida: {k!r}. Opções: {sorted(E.CUSTO_MAQUINA)}.")
        if not isinstance(v, bool):
            raise EntradaInvalida(f"maquinas.{k} deve ser true ou false.")
    return dict(excluidas={ROTACOES[x] for x in exc}, maquinas=dict(maq), sem_comprador={_SEM_COMPRADOR[x] for x in sem},
                eco=dict(culturas_excluidas=list(dict.fromkeys(exc)), maquinas=dict(maq),
                         sem_comprador=list(dict.fromkeys(sem))))


def _normalizar_irrigacao(i) -> dict | None:
    """Valida `irrigacao`: {disponivel: bool, custo_r_mm_ha (padrão 4,0), lamina_max_mm_dia (padrão 6)}."""
    if i is None:
        return None
    if not isinstance(i, dict):
        raise EntradaInvalida("'irrigacao' deve ser um objeto.")
    desc = set(i) - {"disponivel", "custo_r_mm_ha", "lamina_max_mm_dia"}
    if desc:
        raise EntradaInvalida(f"Campos desconhecidos em irrigacao: {sorted(desc)}.")
    if not isinstance(i.get("disponivel"), bool):
        raise EntradaInvalida("irrigacao.disponivel é obrigatório e deve ser true ou false.")
    custo = E.CUSTO_IRRIGACAO_PADRAO if i.get("custo_r_mm_ha") is None else _num(i["custo_r_mm_ha"], "custo_r_mm_ha", 0, 100)
    lam = E.LAMINA_MAX_PADRAO if i.get("lamina_max_mm_dia") is None else _num(i["lamina_max_mm_dia"], "lamina_max_mm_dia", 0, 30)
    if lam <= 0:
        raise EntradaInvalida("lamina_max_mm_dia deve ser maior que zero.")
    return dict(disponivel=i["disponivel"], custo_r_mm_ha=custo, lamina_max_mm_dia=lam)


def _normalizar_pesos(pesos) -> dict:
    out = dict(E.PESOS_PADRAO)
    if pesos is None:
        return out
    if not isinstance(pesos, dict):
        raise EntradaInvalida("'pesos' deve ser um objeto.")
    for k, v in pesos.items():
        if k not in E.CRITERIOS:
            raise EntradaInvalida(f"Peso desconhecido: {k!r}. Critérios: {list(E.CRITERIOS)}.")
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
            fonte=(f"rendimento informado pelo produtor; preço {fonte_preco(i)}; custo {fonte_custo(i, marg['linha_custo'])}"
                   if i.get("prod_usuario") else
                   f"rendimento IBGE PAM ({E.local_rend(rk, i['chave'])}, {i['anos']}); preço {fonte_preco(i)}; custo {fonte_custo(i, marg['linha_custo'])}"
                   if i["sc_ha"] is not None else
                   f"custo extra: {i['detalhe']} (sem venda)" if i.get("extra") else
                   f"custo {fonte_custo(i, marg['linha_custo'])} (sem venda)")))
    avisos = []
    if marg["total"] < 0:
        avisos.append("Margem total negativa com os preços e custos usados.")
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
    """Uma frase por ajuste/entrada opcional usada (vai em metodologia.ajustes_aplicados)."""
    o = []
    if aj.get("preco"):
        o.append("Preços informados pelo produtor (" + ", ".join(f"{k} R$ {v:g}/sc" for k, v in aj["preco"].items())
                 + ") substituem a média de 12 meses da SEAB/DERAL.")
    if aj.get("custo"):
        o.append("Custos informados pelo produtor (" + ", ".join(f"{k} R$ {v:g}/ha" for k, v in aj["custo"].items())
                 + ") substituem o custo CONAB.")
    if aj.get("linha_custo"):
        o.append(f"Linha de custo CONAB '{aj['linha_custo']}' em vez do padrão.")
    if aj.get("produtividade"):
        o.append("Produtividade informada pelo produtor (" + ", ".join(f"{k} {v:g} sc/ha" for k, v in aj["produtividade"].items())
                 + ") substitui o rendimento PAM do município; o ano ruim escala proporcionalmente (próprio × p20/média da PAM); "
                 "a soja informada também muda a escala S da renda.")
    if solo:
        o.append("Análise de solo do produtor substitui o SoilGrids no diagnóstico e na CAD do balanço hídrico"
                 + (" (CAD informada diretamente)." if "cad_mm_cm" in solo else " (CAD por Saxton & Rawls com a análise)."))
    if restr:
        e = restr["eco"]
        if e["culturas_excluidas"]:
            o.append("Rotações excluídas pelo produtor: " + ", ".join(e["culturas_excluidas"]) + ".")
        if e["sem_comprador"]:
            o.append("Sem comprador local (eliminam as rotações que dependem da venda): " + ", ".join(e["sem_comprador"])
                     + ("; aveia_grao não tem efeito, pois a aveia é tratada como cobertura sem venda." if "aveia_grao" in e["sem_comprador"] else "."))
        sem = [k for k, v in e["maquinas"].items() if v is False]
        if sem:
            o.append("Máquinas que o produtor não tem (" + ", ".join(sem) + "): a rotação não é eliminada, ganha aviso e custo extra "
                     "de terceirização (estimativas, validar).")
    if irr and irr["disponivel"]:
        o.append(f"Irrigação disponível (R$ {irr['custo_r_mm_ha']:g}/mm/ha, lâmina máx. {irr['lamina_max_mm_dia']:g} mm/dia): irriga "
                 "milho, milho+braquiária, trigo, sorgo e feijão quando a depleção passa de p (0,55; feijão 0,45); água sobe, veranico não conta no risco e a "
                 "margem desconta lâmina × custo. O ganho de produtividade da irrigação não é modelado; cobertura e pousio não são irrigados.")
    return o


_FONTE_RENDA = "dado: rendimento IBGE PAM × preço SEAB/DERAL − custo CONAB (ou os valores informados pelo produtor)"
_FONTE_SOLO = "estimativa de catálogo, validar com agrônomo/Embrapa"


def _ganho_vs_atual(res: dict, nome: str, nome_atual: str) -> dict | None:
    """Como a candidata melhora (ou piora) a produção em relação à rotação atual. None se for a própria atual ou se a atual
    foi eliminada (sem margem para comparar). Valores com sinal: positivo = a candidata ganha."""
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
        fonte=f"soja seguinte: {c['bonus_fonte']} (preço da soja SEAB/DERAL)",
        renda_2a_safra=dict(r_ha=float(round(renda_2a)), origem=_FONTE_RENDA),
        margem_total=dict(r_ha=float(round(m["total"] - ma["total"])), origem=_FONTE_RENDA + "; inclui o bônus na soja seguinte"),
        solo=dict(dias_descobertos=c["dias_descobertos"] - ca["dias_descobertos"],
                  cobertura=round(c["cobertura"] - ca["cobertura"], 2), origem=_FONTE_SOLO + " (dias negativos = menos solo descoberto)"),
        agua=dict(criterio=round(float(t.loc[nome, "agua"] - t.loc[nome_atual, "agua"]), 3),
                  origem="dado: balanço hídrico diário com NASA POWER e CAD do solo"),
        risco_climatico=dict(criterio=round(float(t.loc[nome, "risco"] - t.loc[nome_atual, "risco"]), 3),
                             origem="dado: geada e veranico em NASA POWER (1991–2024)"))


def _data_referencia(d) -> date | None:
    if d is None or isinstance(d, date):
        return d
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        raise EntradaInvalida(f"data_referencia deve ser uma data ISO (AAAA-MM-DD); recebido: {d!r}.") from None


def _normalizar_entradas(semeadura_safrinha, pesos, rotacao_atual, ajustes, analise_solo, restricoes, irrigacao, rotacoes,
                         problemas_area) -> dict:
    """Valida e normaliza as entradas de `recomendar` (mesma ordem de erros)."""
    if rotacao_atual is None:
        raise EntradaInvalida("'rotacao_atual' é obrigatória (id '<verao>__<segunda>', ex.: soja__milho_safrinha).")
    if semeadura_safrinha is not None:
        semeadura_safrinha = _validar_semeadura(semeadura_safrinha)
    pesos_n = _normalizar_pesos(pesos)
    aj_n = _normalizar_ajustes(ajustes)
    solo_n = _normalizar_analise_solo(analise_solo)
    solo_fis, fert_n = _separar_fertilidade(solo_n)
    probs_n = _normalizar_problemas_area(problemas_area)
    restr_n = _normalizar_restricoes(restricoes)
    irr_n = _normalizar_irrigacao(irrigacao)
    sel = _normalizar_rotacoes(rotacoes)
    rotacao_atual = _resolver_id(rotacao_atual, "rotacao_atual")
    nome_atual = ROTACOES[rotacao_atual]
    return dict(pesos_n=pesos_n, aj_n=aj_n, solo_n=solo_n, solo_fis=solo_fis, fert_n=fert_n, probs_n=probs_n, restr_n=restr_n,
                irr_n=irr_n, sel=sel, rotacao_atual=rotacao_atual, nome_atual=nome_atual,
                verao_atual=E.CATALOGO[nome_atual]["verao"])


def _cronologia_e_contexto(area, inp: dict, semeadura_safrinha, estagio_verao, colheita_prevista, data_referencia) -> dict:
    """Cronologia da safra atual (colheita estimada, semeadura da 2ª janela) e contexto da área (`rk` pronto para `E.pontuar`)."""
    verao_atual, restr_n, irr_n = inp["verao_atual"], inp["restr_n"], inp["irr_n"]
    data_ref = _data_referencia(data_referencia) or date.today()
    try:
        cron = cal.resolver(verao_atual, estagio_verao, colheita_prevista, data_ref, semeadura_safrinha)
    except ValueError as e:
        raise EntradaInvalida(str(e)) from e
    avisos_cal = []
    if cron:
        colheita = dict(data=cron["colheita"], origem=cron["origem"])
        dias_ate = cron["dias_ate_colheita"]
        sem_2a = cron["semeadura_2a"]  # None = colheita tarde demais
        sem_origem = "informada" if semeadura_safrinha else "derivada"
        if colheita_prevista is not None and estagio_verao is not None:
            avisos_cal.append("colheita_prevista e estagio_verao informados: vale a colheita_prevista.")
        if semeadura_safrinha:
            avisos_cal.append(f"semeadura_safrinha {semeadura_safrinha} informada: vale no lugar da derivada da colheita "
                              f"(primeira data >= colheita: {cal.semeadura_derivada(cron['data']) or 'nenhuma'}).")
        if sem_2a is None:
            avisos_cal.append(f"Colheita de {E.VERAO[verao_atual]['nome'].lower()} estimada em ~{cron['colheita']}, depois da última "
                              f"semeadura considerada ({E.SEMEADURAS[-1]}): tarde demais para a safrinha; só as culturas de "
                              "data fixa (inverno e cobertura) seguem avaliadas.")
    else:
        colheita = dict(data=E.VERAO[verao_atual]["colheita"], origem="premissa")
        dias_ate = None
        sem_2a = semeadura_safrinha or E.SEMEADURA_PADRAO
        sem_origem = "informada" if semeadura_safrinha else "premissa"
        avisos_cal.append(f"Sem estagio_verao nem colheita_prevista: colheita de {E.VERAO[verao_atual]['nome'].lower()} assumida em "
                          f"~{colheita['data']} (premissa do catálogo, estimativa)"
                          + ("" if semeadura_safrinha else f" e semeadura da 2ª janela em {sem_2a} (padrão)")
                          + ". Informe o estágio da cultura de verão para uma resposta sobre o que entra depois da colheita.")
    ctx = _contexto(area, sem_2a or E.SEMEADURAS[-1], inp["solo_fis"], inp["fert_n"])
    rk, diag = ctx["rk"], ctx["diag"]
    probs_n, fert_n = inp["probs_n"], inp["fert_n"]
    if probs_n or fert_n:  # só existe se o produtor informou; sem isso o motor roda exatamente como antes
        rk["estado_area"] = dict(problemas=probs_n or [], fert=fert_n)
    rk["restr"] = restr_n
    rk["irrig"] = irr_n if irr_n and irr_n["disponivel"] else None
    if cron:
        rk["colheita_produtor"] = dict(verao=verao_atual, colheita=cron["colheita"])
    avisos = list(diag["avisos"]) + avisos_cal
    if rk["irrig"] and rk.get("agua_ctx") is None:
        avisos.append("Irrigação informada, mas sem solo para o balanço hídrico: ignorada.")
    dias = ctx["dias_solo_ndvi"]
    dias = float("nan") if dias is None else dias
    return dict(cron=cron, colheita=colheita, dias_ate=dias_ate, sem_2a=sem_2a, sem_origem=sem_origem, data_ref=data_ref, ctx=ctx,
                rk=rk, diag=diag, avisos=avisos, dias=dias)


def recomendar(area: dict, semeadura_safrinha: str | None = None, pesos: dict | None = None,
               rotacao_atual: str | None = None, ajustes: dict | None = None,
               n_alternativas: int = 3, incluir_diagnostico: bool = True, analise_solo: dict | None = None,
               restricoes: dict | None = None, irrigacao: dict | None = None, rotacoes: list[dict] | None = None,
               estagio_verao: str | None = None, colheita_prevista: str | None = None, data_referencia=None,
               problemas_area: list[str] | None = None) -> dict:
    """O que pode entrar depois da colheita do verão e como isso melhora a produção, mais o que mudar na próxima safra.

    rotacao_atual (OBRIGATÓRIA): id de ROTACOES ("soja__milho_safrinha") ou slug antigo ("milho_safrinha" = soja__milho_safrinha).
    estagio_verao (opcional): estágio da cultura de verão da rotação atual (calendario.ESTAGIOS; soja: vegetativo, floracao,
      formacao_vagens, enchimento_graos, maturacao, colhida; milho verão: vegetativo, pendoamento, grao_leitoso, grao_farinaceo,
      maturacao, colhida). colheita estimada = data_referencia + dias típicos do estágio.
    colheita_prevista (opcional, dd/mm): vence o estágio. data_referencia (opcional, date ou ISO; padrão hoje).
    semeadura_safrinha (opcional): sem ela, é a primeira data de SEMEADURAS >= colheita estimada (+ preparo); com ela, vence a
      derivada mas não pode ser anterior à colheita. Sem estágio nem colheita: premissa do catálogo (colheita) e 01/02 (semeadura).
      Colheita depois da última data de SEMEADURAS: as culturas de 2ª janela que seguem a semeadura são eliminadas.

    Saída: `agora` (mesmo verão da atual: ranking, alternativas, eliminadas) e `proxima_safra` (outro verão), cada item com
    `ganho_vs_atual`. `ranking`, `alternativas` e `eliminadas` no topo são alias de `agora` (eliminadas = união dos dois blocos).

    rotacoes (opcional): [{"verao": "soja"|"milho_verao", "segunda": <cultura da 2ª janela>}]; se vier, avalia e ranqueia só
      essas (enums fechados do catálogo; não vazia, sem duplicatas); cada par cai no bloco do seu verão. Sem `rotacoes`, avalia
      todas as combinações do catálogo. Combinação eliminada pelas regras volta em `eliminadas` com motivo (não é erro).

    pesos: renda, solo, agua, pragas, risco (0–10; faltantes = padrão {renda 5, demais 3}; todos 0 = pesos iguais).
    ajustes (todas opcionais):
      "precos": {"soja"|"milho"|"trigo": R$/saca de 60 kg}
      "custos": {"soja"|"milho"|"milho_verao"|"trigo"|"feijao"|"sorgo"|"aveia"|"milheto_crotalaria"|"braquiaria_consorcio"|
                "pousio"|"nabo_forrageiro"|"aveia_nabo": R$/ha} ("milho" = milho 2ª safra; "milho_verao" = milho 1ª safra)
      "linha_custo": "coe" (custo variável, padrão) | "cot" | "ct"  (CONAB; vale para soja, milho e trigo)
      "produtividade": {"soja"|"milho"|"milho_2safra"|"milho_verao"|"trigo"|"feijao"|"sorgo": sc/ha > 0}  substitui o rendimento PAM do município; o ano ruim
                escala proporcionalmente (próprio × p20/média da PAM); a soja informada também muda a escala S da renda
    analise_solo (opcional): {"argila_pct", "areia_pct", "materia_organica_pct"|"carbono_organico_g_kg", "ph", "cad_mm_cm",
      "profundidade_cm"}; exige argila+areia ou cad_mm_cm (ou só fertilidade). Substitui o SoilGrids no diagnóstico e na CAD do balanço
      hídrico. Fertilidade (opcional, qualquer subconjunto): p_mg_dm3, k_cmolc_dm3, ca_cmolc_dm3, mg_cmolc_dm3, al_cmolc_dm3, v_pct,
      ctc_cmolc_dm3. Se informada: custo de calagem e adubação P/K na margem, penalidade (critério solo) para cultura sensível em solo
      ácido/pobre e bônus para cobertura recicladora; se NÃO informada, não entra na análise (sem estimativa nem padrão).
    problemas_area (opcional): lista fechada ["nematoide", "mofo_branco", "cigarrinha", "compactacao"] (catalog/vocabulario.yaml);
      ajusta os critérios pragas e solo por cultura em três níveis (favorece/neutro/penaliza), só onde há fonte lida
      (tabela e fontes em field_shift.app.estado_area; sem fonte o efeito é neutro). Sem ela, nada muda.
    restricoes (opcional): {"culturas_excluidas": [slugs], "maquinas": {"plataforma_milho": bool, "semeadora_consorcio": bool},
      "sem_comprador": ["milho"|"trigo"|"aveia_grao"]}. Excluída/sem comprador -> eliminada; máquina false -> aviso + custo
      extra de terceirização (estimativa); máquina omitida = tem.
    irrigacao (opcional): {"disponivel": bool, "custo_r_mm_ha": 4,0, "lamina_max_mm_dia": 6}. Irriga milho, milho+braquiária,
      trigo, sorgo e feijão da 2ª janela (não cobertura/pousio nem o verão): água sobe, veranico não conta no risco, margem desconta lâmina × custo. O ganho de
      produtividade da irrigação NÃO é modelado.
    n_alternativas: 1–6 melhores rotações de cada bloco, excluindo a atual. Se a atual estiver eliminada pelas regras duras
    (ex.: soja__soja_safrinha ou colheita tarde demais), `atual` traz {"eliminada": True, "motivos": [...]}, sem posição nem nota
    (e sem `ganho_vs_atual` nos itens). Com `rotacoes` que não inclui a atual, `atual` traz {"avaliada": False}."""
    inp = _normalizar_entradas(semeadura_safrinha, pesos, rotacao_atual, ajustes, analise_solo, restricoes, irrigacao, rotacoes,
                               problemas_area)
    if isinstance(n_alternativas, bool) or not isinstance(n_alternativas, int) or not 1 <= n_alternativas <= 6:
        raise EntradaInvalida("n_alternativas deve ser um inteiro entre 1 e 6.")
    pesos_n, aj_n, solo_n, solo_fis, fert_n = inp["pesos_n"], inp["aj_n"], inp["solo_n"], inp["solo_fis"], inp["fert_n"]
    probs_n, restr_n, irr_n, sel = inp["probs_n"], inp["restr_n"], inp["irr_n"], inp["sel"]
    rotacao_atual, nome_atual, verao_atual = inp["rotacao_atual"], inp["nome_atual"], inp["verao_atual"]
    base = _cronologia_e_contexto(area, inp, semeadura_safrinha, estagio_verao, colheita_prevista, data_referencia)
    cron, colheita, dias_ate, sem_2a, sem_origem = base["cron"], base["colheita"], base["dias_ate"], base["sem_2a"], base["sem_origem"]
    data_ref, ctx, rk, diag, avisos, dias = base["data_ref"], base["ctx"], base["rk"], base["diag"], base["avisos"], base["dias"]
    # a atual é sempre avaliada (para o ganho_vs_atual), mesmo fora de `rotacoes`; só aparece se estiver em `rotacoes`
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
        avisos.append("Todas as rotações pedidas em 'rotacoes' foram eliminadas pelas regras ou restrições (veja 'eliminadas').")
    atual = next((r for r in agora["ranking"] if r["atual"]), None)
    if atual is None and nome_atual in res["eliminadas"]:
        mot = res["eliminadas"][nome_atual]
        atual = dict(posicao=None, **_ids(rotacao_atual), rotacao=nome_atual, nota=None, atual=True, eliminada=True, motivos=list(mot))
        avisos.append(f"A rotação atual ({nome_atual}) é eliminada ({'regras duras ou restrições do produtor' if restr_n else 'regras duras'}): "
                      + " ".join(mot))
    elif atual is None:
        atual = dict(posicao=None, **_ids(rotacao_atual), rotacao=nome_atual, nota=None, atual=True, avaliada=False)
        avisos.append(f"A rotação atual ({nome_atual}) não está em 'rotacoes': não foi avaliada nem comparada.")
    entrada = dict(semeadura_safrinha=sem_2a, pesos=pesos_n, rotacao_atual=rotacao_atual, estagio_verao=estagio_verao,
                   colheita_prevista=colheita_prevista, data_referencia=data_ref.isoformat(),
                   ajustes=ajustes or {}, n_alternativas=n_alternativas)
    if sel is not None:
        entrada["rotacoes"] = [dict(verao=E.CATALOGO[ROTACOES[i]]["verao"], segunda=E.CATALOGO[ROTACOES[i]]["segunda"]) for i in sel]
    if probs_n:
        entrada["problemas_area"] = probs_n
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
        metodologia=dict(formula="Nota = Σ peso_i × critério_i / Σ peso_i", criterios=_CRIT_METODO, versao=VERSAO))
    aplicados = _ajustes_aplicados(aj_n, solo_fis, restr_n, irr_n) + EA.ajustes_aplicados(rk.get("estado_area"), solo_n is not None)
    if aplicados:
        out["metodologia"]["ajustes_aplicados"] = aplicados
    if incluir_diagnostico:
        out["diagnostico"] = diag
    return _limpo(out)


# --------------------------------------------------------------------------- 4. opções e aquecimento
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
    """Todos os pares (verão, 2ª janela) do catálogo. `semeaduras_validas`: semeaduras da 2ª cultura em que o par passa nas regras de
    calendário e legais (vazia = sempre eliminado, ex.: soja na 2ª janela)."""
    out = []
    for i, nome in ROTACOES.items():
        c = E.CATALOGO[nome]
        validas = [x for x in E.SEMEADURAS if not E.checar_regras(c, {"semeadura": x})]
        out.append(dict(id=i, **({"id_legado": _legado(i)} if _legado(i) else {}), nome=nome, verao=c["verao"], segunda=c["segunda"],
                        valida=bool(validas), semeaduras_validas=validas,
                        motivo_se_invalida=None if validas else " ".join(E.checar_regras(c, {"semeadura": E.SEMEADURA_PADRAO}))))
    return out


def opcoes() -> dict:
    """Catálogo para montar o formulário: culturas de verão e da 2ª janela, combinações (rotações), semeaduras, critérios, pesos,
    referência de renda, região, talhões demo."""
    ref = carregar_referencia()
    fontes = [dict(item=f"preço {k}", fonte=v["fonte"], periodo=v.get("periodo"), estimativa=v.get("estimativa", False), url=v.get("url"))
              for k, v in ref["precos"].items()]
    fontes += [dict(item=f"custo {k}", fonte=v["fonte"], estimativa=v.get("estimativa", False), url=v.get("url"))
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
                       else f"{E.CATALOGO[n]['nome_verao']} no verão, depois: {_DESCRICAO[E.CATALOGO[n]['segunda']]}")
                  for i, n in ROTACOES.items()],
        semeaduras=list(E.SEMEADURAS), semeadura_padrao=E.SEMEADURA_PADRAO,
        criterios=[dict(id=k, nome=v) for k, v in E.CRITERIOS.items()], pesos_padrao=dict(E.PESOS_PADRAO),
        renda_referencia=dict(
            precos={k: v["valor"] for k, v in ref["precos"].items()},
            custos={k: {l: v[l] for l in ("coe", "cot", "ct") if l in v} for k, v in ref["custos"].items()},
            linha_custo_padrao=ref["linha_custo_padrao"], fontes=fontes),
        regiao=_regiao_info(), talhoes_demo=_talhoes_demo()))


def aquecer() -> None:
    """Pré-carrega parquets/rasters/caches pesados (chamar no startup da API)."""
    E.gdf_talhoes()
    E._anuais()
    _regiao_info()
    rendimentos(None)
    _talhoes_demo()
    indicadores_para(-24.9555, -53.4552)  # Cascavel: carrega o lookup climático
    pam_produtividade("4104808")
    recomendar({"talhao_id": E.TALHAO_ID}, rotacao_atual="soja__milho_safrinha", incluir_diagnostico=False)
