"""SMAP: umidade do solo recente no talhão (NASA SMAP L4, SPL4SMGP v8, ~9 km, 3 h, latência ~2-3 dias).

Lê só o pixel do talhão via HTTPS com requisição por faixa (earthaccess.open + h5py), sem baixar o arquivo
de ~145 MB. O próprio produto traz o percentil em relação à climatologia SMAP (`sm_rootzone_pctl`,
`sm_surface_pctl`), então não é preciso montar climatologia própria. Credenciais Earthdata em ~/.netrc.
Cache por pixel, 24 h. Classe: < 20 abaixo do normal; 20–80 normal; > 80 acima.
"""
from __future__ import annotations

import concurrent.futures as cf
from datetime import datetime, timedelta, timezone
from typing import Any

from . import _base as B

URL = "https://nsidc.org/data/spl4smgp/versions/8"
SOURCE = B.source("NASA SMAP L4 Global 3-hourly 9 km Surface and Root Zone Soil Moisture (SPL4SMGP v8, NSIDC DAAC)", URL)
TIMEOUT_S = 90
EASE_X0, EASE_Y0, EASE_RES = -17367530.445161, 7314540.830638, 9008.055210146
NL, NC = 1624, 3856


def pixel_ease2(lat: float, lon: float) -> tuple[int, int]:
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, 6933, always_xy=True).transform(lon, lat)
    col, row = int((x - EASE_X0) / EASE_RES), int((EASE_Y0 - y) / EASE_RES)
    if not (0 <= row < NL and 0 <= col < NC):
        raise ValueError("ponto fora da grade EASE-Grid 2.0 do SMAP")
    return row, col


def class_(pctl: float) -> str:
    return "abaixo do normal" if pctl < 20 else "acima do normal" if pctl > 80 else "normal"


def _read_pixel(granule, row: int, col: int) -> dict[str, Any]:
    import earthaccess
    import h5py

    fs = earthaccess.open([granule])
    with h5py.File(fs[0], "r") as f:
        g = f["Geophysical_Data"]

        def v(nome):
            x = float(g[nome][row, col])
            return None if x < -9000 else round(x, 4)

        return {"sm_rootzone": v("sm_rootzone"), "sm_rootzone_pctl": v("sm_rootzone_pctl"),
                "sm_surface": v("sm_surface"),
                "arquivo": granule["umm"]["GranuleUR"].split(".h5")[0]}


def _granule_date(g) -> datetime:
    t = g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def _fetch(lat: float, lon: float) -> dict[str, Any]:
    import earthaccess

    row, col = pixel_ease2(lat, lon)
    earthaccess.login(strategy="netrc")
    now = datetime.now(timezone.utc)
    box = (lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05)

    def find(end: datetime, days: int):
        r = earthaccess.search_data(short_name="SPL4SMGP", bounding_box=box,
                                    temporal=((end - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                              end.strftime("%Y-%m-%dT%H:%M:%SZ")))
        return sorted(r, key=_granule_date)

    recent = find(now, 6)
    if not recent:
        raise LookupError("nenhum granulo SPL4SMGP nos últimos 6 dias")
    last_item = recent[-1]
    t_last = _granule_date(last_item)
    out = {"referencia_utc": t_last.isoformat(), "pixel_ease2": {"linha": row, "coluna": col}}
    out["atual"] = _read_pixel(last_item, row, col)
    ant = [g for g in find(t_last - timedelta(days=7) + timedelta(hours=2), 1)]
    if ant:
        try:
            out["ha_7_dias"] = _read_pixel(ant[0], row, col)
            out["ha_7_dias"]["referencia_utc"] = _granule_date(ant[0]).isoformat()
        except Exception:
            pass
    return out


def query_source(lat: float, lon: float, cache_only: bool = False) -> dict[str, Any]:
    def _fn():
        row, col = pixel_ease2(lat, lon)
        key = f"smap_{row}_{col}"
        if cache_only:
            raw = B.read_cache(key, B.TTL_SMAP)
            if raw is None:
                raise LookupError("sem cache; consulte GET /v1/contexto")
            cache = True
        else:
            with cf.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(B.com_cache, key, B.TTL_SMAP, lambda: _fetch(lat, lon))
                try:
                    raw, cache = fut.result(timeout=TIMEOUT_S)
                except cf.TimeoutError:
                    raise TimeoutError(f"SMAP não respondeu em {TIMEOUT_S} s") from None
        a = raw["atual"]
        pc = a.get("sm_rootzone_pctl")
        out: dict[str, Any] = {"do_cache": cache, **raw}
        if pc is None:
            out["texto"] = "SMAP sem valor válido de umidade da zona de raízes no pixel do talhão."
        else:
            cl = class_(pc)
            out["classe"] = cl
            out["texto"] = (f"SMAP (NASA, {raw['referencia_utc'][:10]}): umidade na zona de raízes em {a['sm_rootzone']:.2f} m³/m³, "
                            f"percentil {pc:.0f} da climatologia SMAP ({cl}). Pixel de ~9 km; modelo de assimilação, "
                            "não medida no talhão.")
            h = raw.get("ha_7_dias")
            if h and h.get("sm_rootzone_pctl") is not None:
                out["tendencia_7d_percentil"] = round(pc - h["sm_rootzone_pctl"], 1)
        return out

    return B.insurance("smap", SOURCE, _fn)
