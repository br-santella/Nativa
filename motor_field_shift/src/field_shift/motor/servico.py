"""Camada de serviço do motor Field Shift (sem FastAPI): aceita qualquer polígono do Oeste do PR.

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
from functools import lru_cache
from pathlib import Path
from urllib.error import URLError

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry

from field_shift.app import engine as E
from field_shift.clima.lookup import indicadores_para
from field_shift.pam import produtividade as pam_produtividade
from field_shift.pam.produtividade import texto as pam_texto
from field_shift.regiao import dentro_da_regiao, historico_mapbiomas, relevo
from field_shift.regiao.recorte import REGIAO
from field_shift.renda import carregar_referencia, fonte_custo, fonte_preco, rendimentos
from field_shift.solo.solo import texto as solo_texto

VERSAO = "0.1.0"
AREA_MAX_HA = 5000.0
PONTO_AREA_HA = 100.0
CRS_M = 32722  # UTM 22S (m), para áreas e quadrado do ponto


class ForaDaRegiao(Exception):
    """Área (ou parte dela) fora do Oeste do PR."""


class EntradaInvalida(Exception):
    """Entrada inválida: geometria, semeadura, rotação, pesos, ajustes, área > 5000 ha etc."""


class ErroConsultaExterna(Exception):
    """Timeout ou falha de ligação ao consultar APIs externas (NASA POWER / SoilGrids)."""


# slug -> nome do catálogo do engine
ROTACOES: dict[str, str] = {
    "milho_safrinha": "Soja → milho safrinha",
    "milho_braquiaria": "Soja → milho safrinha + braquiária",
    "trigo": "Soja → trigo",
    "aveia": "Soja → aveia (cobertura/palha)",
    "milheto_crotalaria": "Soja → milheto/crotalária (cobertura)",
    "pousio": "Soja → pousio",
    "soja_safrinha": "Soja → soja safrinha",
}
_SLUG_DE = {v: k for k, v in ROTACOES.items()}

_DESCRICAO = {
    "milho_safrinha": "Milho na segunda safra, após a soja; rotação mais comum no Oeste do PR.",
    "milho_braquiaria": "Milho safrinha consorciado com braquiária: grãos mais palhada para o plantio direto.",
    "trigo": "Trigo de inverno após a soja; sensível a geada no florescimento.",
    "aveia": "Aveia para cobertura/palha (e eventual grão) no inverno.",
    "milheto_crotalaria": "Cobertura de milheto e crotalária: palhada e fixação de nitrogênio, sem venda de grão.",
    "pousio": "Sem cultura na segunda janela; solo exposto e sem renda adicional.",
    "soja_safrinha": "Soja sobre soja no mesmo ano agrícola; proibida pela regulação (sempre eliminada).",
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

_CUSTO_ALIAS = {"milho": "milho_2safra"}


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
            raise ForaDaRegiao(f"O ponto (lat {lat:.5f}, lon {lon:.5f}) está fora do Oeste do Paraná; o motor só cobre essa região.")
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
        raise ForaDaRegiao("A área não está inteiramente dentro do Oeste do Paraná (confira a ordem [lon, lat] das coordenadas).")
    return dict(origem=origem, talhao_id=tid, poly=poly, area_ha=ha, lat=lat, lon=lon)


# --------------------------------------------------------------------------- 2. diagnóstico
def _validar_semeadura(s) -> str:
    if s not in E.SEMEADURAS:
        raise EntradaInvalida(f"semeadura_safrinha inválida: {s!r}. Opções: {E.SEMEADURAS}.")
    return s


def _rotacao_detectada(tid: str | None) -> dict:
    vazio = dict(rotacao=None, fonte=None, dias_solo_descoberto=None)
    if tid is None or not (E.ROOT / f"data/processed/timelapse/ndvi_hls_{tid}.csv").exists():
        return vazio
    nd = E.carregar_ndvi(tid)
    picos = E.picos_por_ano_agricola(nd)
    return dict(rotacao=_SLUG_DE.get(E.detectar_rotacao(picos)),
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


def _contexto(area: dict, semeadura: str) -> dict:
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
        raise ForaDaRegiao("Centroide sem indicadores climáticos pré-calculados (fora do Oeste do PR).")

    try:
        rk = E.enriquecer(rk, dict(poly=poly))
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

    if a["origem"] == "ponto":
        avisos.append(f"Ponto convertido em quadrado de ~{PONTO_AREA_HA:.0f} ha centrado nele; relevo, histórico e solo "
                      "valem para esse quadrado, não para a lavoura real.")
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
                        texto=solo_texto(s), fonte="SoilGrids (ISRIC), média no polígono")
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


def diagnosticar(area: dict, semeadura_safrinha: str = "01/02") -> dict:
    """Diagnóstico da área (relevo, solo 0–30 cm + CAD, histórico MapBiomas, clima da célula, PAM do município).

    Lança EntradaInvalida (geometria/semeadura/área > 5000 ha), ForaDaRegiao ou ErroConsultaExterna."""
    return _contexto(area, semeadura_safrinha)["diag"]


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
    """Aceita {"precos": {soja, milho, trigo}, "custos": {soja, milho|milho_2safra, trigo, aveia, milheto_crotalaria,
    braquiaria_consorcio, pousio}, "linha_custo": coe|cot|ct}; devolve o formato do engine (preco/custo/linha_custo)."""
    if aj is None:
        return {}
    if not isinstance(aj, dict):
        raise EntradaInvalida("'ajustes' deve ser um objeto.")
    ref = carregar_referencia()
    desconhecidas = set(aj) - {"precos", "custos", "linha_custo"}
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
    lc = aj.get("linha_custo")
    if lc is not None:
        if lc not in ("coe", "cot", "ct"):
            raise EntradaInvalida("linha_custo deve ser 'coe', 'cot' ou 'ct'.")
        out["linha_custo"] = lc
    return out


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


def _item_ranking(pos, nome, linha, marg, atual, rk, dias_ndvi, por_que_cmp=None) -> dict:
    card = E.montar_card(linha, atual, rk, dias_ndvi, marg, por_que_cmp)
    itens = []
    for i in marg["itens"]:
        itens.append(dict(
            cultura=i["rotulo"], rendimento_sc_ha=i["sc_ha"], preco=i["preco"], custo=i["custo"], margem_r_ha=i["margem"],
            fonte=(f"rendimento IBGE PAM ({rk.get('rend_local')}, {i['anos']}); preço {fonte_preco(i)}; custo {fonte_custo(i, marg['linha_custo'])}"
                   if i["sc_ha"] is not None else f"custo {fonte_custo(i, marg['linha_custo'])} (sem venda)")))
    avisos = []
    if marg["total"] < 0:
        avisos.append("Margem total negativa com os preços e custos usados.")
    margem = dict(total_r_ha=marg["total"], incremental_r_ha=marg["incremental"], escala_S_r_ha=marg["escala_S"], itens=itens, ano_ruim_r_ha=marg["total_ano_ruim"],
                  bonus_proxima_soja_r_ha=marg["bonus"], linha_custo=marg["linha_custo"])
    return dict(
        posicao=pos, id=_SLUG_DE[nome], rotacao=nome, nota=float(linha["nota"]), atual=atual,
        criterios={k: float(linha[k]) for k in E.CRITERIOS},
        contribuicoes={k: float(v) for k, v in linha["contrib"].items()}, margem=margem,
        card=dict(por_que=card["por_que"], evidencias=card["evidencia"], beneficios=card["beneficios"],
                  lacunas=card["lacunas"], riscos=card["revisar"], avisos=avisos))


def recomendar(area: dict, semeadura_safrinha: str = "01/02", pesos: dict | None = None,
               rotacao_atual: str | None = None, ajustes: dict | None = None,
               n_alternativas: int = 3, incluir_diagnostico: bool = True) -> dict:
    """Ranking das rotações para a área.

    pesos: renda, solo, agua, pragas, risco (0–10; faltantes = padrão {renda 5, demais 3}; todos 0 = pesos iguais).
    rotacao_atual: slug de ROTACOES; None = detectada pelo NDVI (talhões demo com série) ou "milho_safrinha" com aviso.
    ajustes (todas opcionais):
      "precos": {"soja"|"milho"|"trigo": R$/saca de 60 kg}
      "custos": {"soja"|"milho"|"trigo"|"aveia"|"milheto_crotalaria"|"braquiaria_consorcio"|"pousio": R$/ha}
                ("milho" = milho 2ª safra)
      "linha_custo": "coe" (custo variável, padrão) | "cot" | "ct"  (CONAB; vale para soja, milho e trigo)
    n_alternativas: 1–6 melhores rotações excluindo a atual. Se a atual estiver eliminada pelas regras duras
    (ex.: soja_safrinha), `atual` traz {"eliminada": True, "motivos": [...]}, sem posição nem nota."""
    semeadura_safrinha = _validar_semeadura(semeadura_safrinha)
    pesos_n = _normalizar_pesos(pesos)
    aj_n = _normalizar_ajustes(ajustes)
    if rotacao_atual is not None and rotacao_atual not in ROTACOES:
        raise EntradaInvalida(f"rotacao_atual desconhecida: {rotacao_atual!r}. Opções: {list(ROTACOES)}.")
    if isinstance(n_alternativas, bool) or not isinstance(n_alternativas, int) or not 1 <= n_alternativas <= 6:
        raise EntradaInvalida("n_alternativas deve ser um inteiro entre 1 e 6.")
    ctx = _contexto(area, semeadura_safrinha)
    rk, diag = ctx["rk"], ctx["diag"]
    avisos = list(diag["avisos"])
    if rotacao_atual is None:
        det = diag["rotacao_detectada"]["rotacao"]
        if det:
            rotacao_atual = det
        else:
            rotacao_atual = "milho_safrinha"
            avisos.append("Rotação atual não informada nem detectável por NDVI para esta área: assumida 'milho_safrinha'.")
    dias = ctx["dias_solo_ndvi"]
    dias = float("nan") if dias is None else dias
    res = E.pontuar(pesos_n, rk, aj_n)
    if res["aviso_renda"]:
        avisos.append(res["aviso_renda"])
    nome_atual = ROTACOES[rotacao_atual]
    ranking = []
    for pos, (_, linha) in enumerate(res["tabela"].iterrows(), start=1):
        n = linha["candidata"]
        ranking.append(_item_ranking(pos, n, linha, res["margens"][n], n == nome_atual,
                                     rk, dias if n == nome_atual else float("nan"),
                                     E.por_que_comparado(res, n, nome_atual)))
    eliminadas = [dict(id=_SLUG_DE[n], rotacao=n, motivos=list(m)) for n, m in res["eliminadas"].items()]
    atual = next((r for r in ranking if r["atual"]), None)
    ranking = [_arredondar_ranking(r) for r in ranking]
    if atual is not None:
        atual = next(r for r in ranking if r["atual"])
    if atual is None:
        mot = res["eliminadas"].get(nome_atual, [])
        atual = dict(posicao=None, id=rotacao_atual, rotacao=nome_atual, nota=None, atual=True, eliminada=True, motivos=list(mot))
        avisos.append(f"A rotação atual ({nome_atual}) é eliminada pelas regras duras: " + " ".join(mot))
    out = dict(
        entrada=dict(semeadura_safrinha=semeadura_safrinha, pesos=pesos_n, rotacao_atual=rotacao_atual,
                     ajustes=ajustes or {}, n_alternativas=n_alternativas),
        ranking=ranking, atual=atual,
        alternativas=[r for r in ranking if not r["atual"]][:n_alternativas],
        eliminadas=eliminadas, avisos=avisos,
        metodologia=dict(formula="Nota = Σ peso_i × critério_i / Σ peso_i", criterios=_CRIT_METODO, versao=VERSAO))
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


def opcoes() -> dict:
    """Catálogo para montar o formulário: rotações, semeaduras, critérios, pesos, referência de renda, região, talhões demo."""
    ref = carregar_referencia()
    fontes = [dict(item=f"preço {k}", fonte=v["fonte"], periodo=v.get("periodo"), url=v.get("url")) for k, v in ref["precos"].items()]
    fontes += [dict(item=f"custo {k}", fonte=v["fonte"], estimativa=v.get("estimativa", False), url=v.get("url"))
               for k, v in ref["custos"].items()]
    return _limpo(dict(
        rotacoes=[dict(id=s, nome=n, descricao_curta=_DESCRICAO[s]) for s, n in ROTACOES.items()],
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
    recomendar({"talhao_id": E.TALHAO_ID}, incluir_diagnostico=False)