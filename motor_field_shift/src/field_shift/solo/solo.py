"""solo(poligono) -> dict com SoilGrids médio no polígono (data/raw/soilgrids_oeste_pr/, gerado por ingest/solo_pam_oeste_pr.py).

UNIDADES FÍSICAS (já convertidas na ingestão; SoilGrids 2.0 guarda inteiros escalados):
  clay, sand, silt: % (g/100 g)   [SoilGrids: g/kg  -> /10]
  soc: g/kg de C orgânico         [SoilGrids: dg/kg -> /10]
  phh2o: pH em água               [SoilGrids: pH×10 -> /10]
  bdod: g/cm³                     [SoilGrids: cg/cm³ -> /100]
Profundidades: 0-5, 5-15, 15-30, 30-60 cm. Médias 0-30 e 0-60 ponderadas pela espessura (5, 10, 15, 30 cm).

CAD (capacidade de água disponível, mm de água por cm de solo) = (θ33 kPa − θ1500 kPa) × 10.
O SoilGrids NÃO publica wv0033/wv1500 no servidor (latest/data), então usamos a pedotransferência de
Saxton & Rawls (2006) com areia, argila e matéria orgânica (MO = 1,724 × C orgânico).
AVISO: Saxton & Rawls foi calibrada em solos de clima temperado (base USDA); em latossolos tropicais
muito argilosos e com microagregação (Oeste do PR) tende a ERRAR, em geral subestimando θ33 e a CAD
(argila oxídica retém menos água a 1500 kPa do que o previsto pela argila). Tratar a CAD como estimativa a validar
(ex.: com análise de solo / Embrapa).

Entrada: shapely Polygon/MultiPolygon em EPSG:4326 (ou ponto buffer). Fora da cobertura do raster -> fallback API SoilGrids.
"""
from __future__ import annotations

import json
import urllib.request
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parents[3]
SG = ROOT / "data/raw/soilgrids_oeste_pr"
PROPS = ["clay", "sand", "silt", "soc", "phh2o", "bdod"]
PROFS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]
ESPESSURA = np.array([5.0, 10.0, 15.0, 30.0])  # cm
ESCALAS = {
    "clay": 10.0,
    "sand": 10.0,
    "silt": 10.0,
    "soc": 10.0,
    "phh2o": 10.0,
    "bdod": 100.0,
}


def cad_mm_cm(areia_pct, argila_pct, soc_g_kg):
    """CAD (mm/cm) por Saxton & Rawls (2006), vetorizado. Areia/argila em %, C orgânico em g/kg."""
    s, c = np.asarray(areia_pct) / 100.0, np.asarray(argila_pct) / 100.0
    om = 1.724 * np.asarray(soc_g_kg) / 10.0  # % de matéria orgânica
    t1500 = (-0.024 * s + 0.487 * c + 0.006 * om + 0.005 * s * om - 0.013 * c * om + 0.068 * s * c + 0.031)
    t1500 = t1500 + (0.14 * t1500 - 0.02)
    t33 = (-0.251 * s + 0.195 * c + 0.011 * om + 0.006 * s * om - 0.027 * c * om + 0.452 * s * c + 0.299)
    t33 = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)
    return np.maximum(t33 - t1500, 0.0) * 10.0  # cm³/cm³ × 10 = mm/cm


@lru_cache(maxsize=None)
def _src_path(prop: str) -> Path:
    return SG / f"{prop}.tif"


def _media_poligono(prop: str, g) -> np.ndarray | None:
    """Média por banda (4 profundidades) dos pixels cujo centro cai no polígono (fallback: pixels tocados)."""
    path = _src_path(prop)
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        win = from_bounds(*g.bounds, transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(Window(0, 0, src.width, src.height))
        if win.width <= 0 or win.height <= 0:
            return None
        dados = src.read(window=win)
        tr = src.window_transform(win)
    m = ~geometry_mask([g], out_shape=dados.shape[1:], transform=tr)
    if not m.any():
        m = ~geometry_mask([g], out_shape=dados.shape[1:], transform=tr, all_touched=True)
    v = dados[:, m]
    if v.size == 0 or np.isnan(v).all():
        return None
    return np.nanmean(v, axis=1)


def _pond(v: np.ndarray, n: int) -> float:
    return float(np.sum(v[:n] * ESPESSURA[:n]) / ESPESSURA[:n].sum())


def _fallback_soilgrids(poligono) -> dict[str, np.ndarray] | None:
    """Consulta a API REST do SoilGrids 2.0 no ponto representativo interno ao polígono."""
    pt = poligono.representative_point()
    props_q = "&".join(f"property={p}" for p in PROPS)
    profs_q = "&".join(f"depth={d}" for d in PROFS)
    url = (
        f"https://rest.isric.org/soilgrids/v2.0/properties/query"
        f"?lon={pt.x:.6f}&lat={pt.y:.6f}&{props_q}&{profs_q}&value=mean"
    )
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

    layers = payload.get("properties", {}).get("layers", [])
    med: dict[str, np.ndarray] = {}
    for layer in layers:
        nome = layer.get("name")
        if nome not in PROPS:
            continue
        por_prof = {}
        for d in layer.get("depths", []):
            label = d.get("label")
            val = d.get("values", {}).get("mean")
            if label in PROFS and val is not None:
                por_prof[label] = float(val) / ESCALAS[nome]
        if len(por_prof) != len(PROFS):
            return None
        med[nome] = np.array([por_prof[d] for d in PROFS], dtype=float)

    if any(p not in med for p in PROPS):
        return None
    return med


def _montar(med: dict[str, np.ndarray], fonte: str = "raster") -> dict:
    """Monta o dict padronizado de solo a partir de {prop: array(4 profundidades)}."""
    prof = {p: dict(zip(PROFS, map(float, v))) for p, v in med.items()}
    p30 = {p: _pond(v, 3) for p, v in med.items()}
    p60 = {p: _pond(v, 4) for p, v in med.items()}
    cad_l = cad_mm_cm(med["sand"], med["clay"], med["soc"])  # por camada
    cad = {d: float(c) for d, c in zip(PROFS, cad_l)}
    cad["0-30"], cad["0-60"] = _pond(cad_l, 3), _pond(cad_l, 4)
    argila = p30["clay"]
    classe = "muito argiloso" if argila >= 60 else "argiloso" if argila >= 35 else "médio" if argila >= 15 else "arenoso"
    return dict(
        prof=prof,
        p30=p30,
        p60=p60,
        cad_mm_cm=cad,
        cad_mm_0_30=cad["0-30"] * 30,
        cad_mm_0_60=cad["0-60"] * 60,
        cad_metodo="Saxton & Rawls (2006) com areia, argila e MO (SoilGrids); wv0033/wv1500 indisponíveis",
        classe_textura=classe,
        fonte=fonte,
    )


def solo(poligono) -> dict | None:
    """Propriedades médias no polígono por profundidade e ponderadas em 0-30 e 0-60 cm, mais a CAD.

    Retorna dict:
      prof: {prop: {'0-5cm': x, ...}}, p30: {prop: média 0-30}, p60: {prop: média 0-60},
      cad_mm_cm: {'0-5cm':.., ..., '0-30': .., '0-60': ..},
      cad_mm_0_30, cad_mm_0_60 (mm totais), cad_metodo, classe_textura, fonte.
    None se fora do raster e o fallback SoilGrids também falhar."""
    med = {}
    for p in PROPS:
        r = _media_poligono(p, poligono)
        if r is None:
            med = None
            break
        med[p] = r

    if med is not None:
        return _montar(med, fonte="raster")

    med_fb = _fallback_soilgrids(poligono)
    if med_fb is None:
        return None
    return _montar(med_fb, fonte="soilgrids_api")


FONTE_ANALISE = "análise de solo do produtor"
MO_PADRAO_PCT = 2.0  # MO assumida só se a análise não traz MO/C orgânico, não há CAD informada e não há SoilGrids (estimativa)


def solo_de_analise(a: dict, soc_fallback_g_kg: float | None = None) -> dict:
    """Monta o bloco `solo` (mesmo formato de `solo()`) a partir da análise do produtor, já validada pelo serviço.

    `a`: argila_pct, areia_pct (ambos ou nenhum), soc_g_kg (C orgânico, g/kg; opcional), ph, cad_mm_cm, profundidade_cm.
    CAD: `cad_mm_cm` informada vale direto; senão Saxton & Rawls com areia, argila e MO (se a análise não trouxe MO, usa a do
    SoilGrids passada em `soc_fallback_g_kg`, ou 2% de MO). A amostra (padrão 0–20 cm) é tomada como representativa de todas as
    camadas (0–60 cm). Devolve dict com a chave extra `avisos` (lista) e `fonte`."""
    avisos = []
    argila, areia, soc = a.get("argila_pct"), a.get("areia_pct"), a.get("soc_g_kg")
    if a.get("cad_mm_cm") is not None:
        cad_v, metodo = float(a["cad_mm_cm"]), "CAD informada pelo produtor (mm/cm)"
    else:
        if soc is None:
            if soc_fallback_g_kg is not None:
                soc = float(soc_fallback_g_kg)
                avisos.append("A análise não traz matéria orgânica: usado o C orgânico do SoilGrids na CAD (Saxton & Rawls).")
            else:
                soc = MO_PADRAO_PCT / 1.724 * 10.0
                avisos.append(f"A análise não traz matéria orgânica: assumido {MO_PADRAO_PCT:g}% de MO na CAD (Saxton & Rawls).")
        cad_v = float(cad_mm_cm(areia, argila, soc))
        metodo = "Saxton & Rawls (2006) com areia, argila e MO da análise do produtor"
    cad = {d: cad_v for d in PROFS}
    cad["0-30"] = cad["0-60"] = cad_v
    silt = None if argila is None else 100.0 - argila - areia
    props = dict(clay=argila, sand=areia, silt=silt, soc=soc if a.get("soc_g_kg") is not None else None,
                 phh2o=a.get("ph"), bdod=None)
    prof = {k: {d: v for d in PROFS} for k, v in props.items()}
    classe = None if argila is None else ("muito argiloso" if argila >= 60 else "argiloso" if argila >= 35
                                          else "médio" if argila >= 15 else "arenoso")
    return dict(prof=prof, p30=dict(props), p60=dict(props), cad_mm_cm=cad, cad_mm_0_30=cad_v * 30, cad_mm_0_60=cad_v * 60,
                cad_metodo=metodo, classe_textura=classe, fonte=FONTE_ANALISE, amostra_profundidade_cm=a.get("profundidade_cm", 20.0),
                avisos=avisos)


def texto(s: dict) -> str:
    p = s["p30"]
    if s.get("fonte") == FONTE_ANALISE:
        partes = [f"{n} {p[k]:.{d}f}{u}" for n, k, d, u in (("argila", "clay", 0, "%"), ("areia", "sand", 0, "%"),
                                                            ("C orgânico", "soc", 1, " g/kg"), ("pH", "phh2o", 1, ""))
                  if p.get(k) is not None]
        return (f"Análise do produtor ({s['amostra_profundidade_cm']:g} cm, extrapolada ao perfil): " + ", ".join(partes)
                + (", " if partes else "") + f"CAD {s['cad_mm_cm']['0-30']:.2f} mm/cm ({s['cad_mm_0_60']:.0f} mm em 60 cm).")
    return (f"Argila {p['clay']:.0f}%, areia {p['sand']:.0f}%, C orgânico {p['soc']:.1f} g/kg, pH {p['phh2o']:.1f} (0–30 cm); "
            f"CAD {s['cad_mm_cm']['0-30']:.2f} mm/cm ({s['cad_mm_0_60']:.0f} mm em 60 cm).")