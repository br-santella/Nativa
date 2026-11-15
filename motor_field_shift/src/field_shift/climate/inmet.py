"""INMET: annual historical data -> daily (Tmin, Tmax, rain) of the stations inside the bbox.

Day = local day (UTC-3): the CSV hours are UTC. A day with < MIN_HOURS valid hours -> NaN.
Zip contents are treated as data only (never executed).
"""
from __future__ import annotations

import io
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
MIN_HOURS = 20


def _num(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False).str.strip(), errors="coerce")
    return x.where(x > -9000)


def _f(txt: str) -> float:
    return float(txt.strip().replace(",", "."))


def _header(raw: bytes) -> dict | None:
    lines = raw[:2000].decode("latin-1").splitlines()[:8]
    d = {}
    for ln in lines:
        k, _, v = ln.partition(";")
        k = unicodedata.normalize("NFKD", k.strip().rstrip(":").upper()).encode("ascii", "ignore").decode()
        d[k] = v.strip().strip(";").strip()
    def pick(prefix: str) -> str:
        return next(v for k, v in d.items() if k.startswith(prefix))

    try:
        return dict(uf=d["UF"], estacao=pick("EST"), codigo=pick("CODIGO"),
                    lat=_f(pick("LATITUDE")), lon=_f(pick("LONGITUDE")), alt=_f(pick("ALTITUDE")))
    except Exception:  # noqa: BLE001
        return None


def _daily(raw: bytes, cod: str) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), sep=";", skiprows=8, encoding="latin-1", dtype=str,
                     index_col=False)
    cols = {c: c.upper() for c in df.columns}
    df = df.rename(columns=cols)
    c_data = next(c for c in df.columns if c.startswith("DATA"))
    c_hour = next(c for c in df.columns if c.startswith("HORA"))
    c_p = next(c for c in df.columns if c.startswith("PRECIPITA"))
    c_tx = next(c for c in df.columns if c.startswith("TEMPERATURA M") and "XIMA" in c and "HORA" in c)
    c_tn = next(c for c in df.columns if c.startswith("TEMPERATURA M") and "NIMA" in c and "HORA" in c)
    data = df[c_data].str.replace("-", "/", regex=False)
    hour = df[c_hour].str.extract(r"(\d{2})")[0].fillna("00")
    ts = pd.to_datetime(data + " " + hour, format="%Y/%m/%d %H", errors="coerce") - pd.Timedelta(hours=3)
    out = pd.DataFrame({"ts": ts, "p": _num(df[c_p]), "tx": _num(df[c_tx]), "tn": _num(df[c_tn])}).dropna(subset=["ts"])
    out["dia"] = out.ts.dt.floor("D")
    g = out.groupby("dia")
    res = pd.DataFrame({
        "chuva_mm": g["p"].sum(min_count=1), "n_p": g["p"].count(),
        "tmax": g["tx"].max(), "n_tx": g["tx"].count(),
        "tmin": g["tn"].min(), "n_tn": g["tn"].count(),
    })
    res.loc[res.n_p < MIN_HOURS, "chuva_mm"] = np.nan
    res.loc[res.n_tx < MIN_HOURS, "tmax"] = np.nan
    res.loc[res.n_tn < MIN_HOURS, "tmin"] = np.nan
    res = res[["chuva_mm", "tmin", "tmax"]].reset_index().rename(columns={"dia": "data"})
    res.insert(0, "codigo", cod)
    return res


def process_inmet(bbox, zips_dir: Path, proc_dir: Path, headers: dict, years=range(2000, 2026)):
    x0, y0, x1, y1 = bbox
    proc_dir.mkdir(parents=True, exist_ok=True)
    daily, stations = [], {}
    failures = []
    cache = proc_dir / "_inmet_ano"  # daily data per year already processed (idempotency)
    cache.mkdir(exist_ok=True)
    for year in years:
        pq = cache / f"{year}.parquet"
        ef = cache / f"{year}_estacoes.csv"
        if pq.exists() and ef.exists():
            daily.append(pd.read_parquet(pq))
            if ef.stat().st_size > 5:
                for r in pd.read_csv(ef, dtype={"codigo": str}).to_dict("records"):
                    stations[r["codigo"]] = dict(codigo=r["codigo"], nome=r["nome"], uf=r["uf"], lat=r["lat"],
                                                 lon=r["lon"], alt=r["alt"])
            continue
        d = zips_dir / str(year)
        d.mkdir(parents=True, exist_ok=True)
        zp = d / f"{year}.zip"
        try:
            with requests.get(BASE.format(year=year), headers=headers, timeout=120, stream=True) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                with open(zp, "wb") as fh:
                    for ch in r.iter_content(1 << 20):
                        fh.write(ch)
            parts, est_year = [], []
            with zipfile.ZipFile(zp) as z:
                for nome in z.namelist():
                    if not nome.upper().endswith(".CSV"):
                        continue
                    raw = z.read(nome)
                    h = _header(raw)
                    if not h or not (x0 <= h["lon"] <= x1 and y0 <= h["lat"] <= y1):
                        continue
                    parts.append(_daily(raw, h["codigo"]))
                    est_year.append(h)
            dd = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
                columns=["codigo", "data", "chuva_mm", "tmin", "tmax"])
            dd.to_parquet(pq, index=False)
            pd.DataFrame(est_year).rename(columns={"estacao": "nome"}).to_csv(ef, index=False)
            daily.append(dd)
            for h in est_year:
                stations[h["codigo"]] = dict(codigo=h["codigo"], nome=h["estacao"], uf=h["uf"], lat=h["lat"],
                                             lon=h["lon"], alt=h["alt"])
            print(f"INMET {year}: {len(est_year)} stations in the bbox", flush=True)
        except Exception as e:  # noqa: BLE001
            failures.append((year, f"{type(e).__name__}: {e}"))
            print(f"INMET {year} falhou: {e}", flush=True)
        finally:
            if zp.exists():
                zp.unlink()
    if not daily:
        raise RuntimeError(f"nenhum ano INMET processado: {failures}")
    day = pd.concat([d for d in daily if len(d)], ignore_index=True)
    day["data"] = pd.to_datetime(day["data"])
    day = day.dropna(how="all", subset=["chuva_mm", "tmin", "tmax"])
    day.to_parquet(proc_dir / "inmet_diario.parquet", index=False)
    est = pd.DataFrame(stations.values())
    cover_years = day.assign(ano=day.data.dt.year).groupby("codigo")["ano"].agg(["min", "max", "nunique"])
    est = est.merge(cover_years.rename(columns={"min": "ano_ini", "max": "ano_fim", "nunique": "n_anos"}),
                    left_on="codigo", right_index=True, how="left")
    est.to_csv(proc_dir / "inmet_estacoes.csv", index=False)
    print(est.to_string())
    if failures:
        print("Failed years:", failures)
