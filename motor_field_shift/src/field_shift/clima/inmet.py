"""INMET: dados históricos anuais -> diário (Tmin, Tmax, chuva) das estações dentro do bbox.

Dia = dia local (UTC-3): os horários do CSV são UTC. Dia com < MIN_HORAS horas válidas -> NaN.
Conteúdo dos zips é tratado só como dados (nunca executado).
"""
from __future__ import annotations

import io
import unicodedata
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
MIN_HORAS = 20


def _num(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False).str.strip(), errors="coerce")
    return x.where(x > -9000)


def _f(txt: str) -> float:
    return float(txt.strip().replace(",", "."))


def _cabecalho(raw: bytes) -> dict | None:
    linhas = raw[:2000].decode("latin-1").splitlines()[:8]
    d = {}
    for ln in linhas:
        k, _, v = ln.partition(";")
        k = unicodedata.normalize("NFKD", k.strip().rstrip(":").upper()).encode("ascii", "ignore").decode()
        d[k] = v.strip().strip(";").strip()
    def pega(prefixo: str) -> str:
        return next(v for k, v in d.items() if k.startswith(prefixo))

    try:
        return dict(uf=d["UF"], estacao=pega("EST"), codigo=pega("CODIGO"),
                    lat=_f(pega("LATITUDE")), lon=_f(pega("LONGITUDE")), alt=_f(pega("ALTITUDE")))
    except Exception:  # noqa: BLE001
        return None


def _diario(raw: bytes, cod: str) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), sep=";", skiprows=8, encoding="latin-1", dtype=str,
                     index_col=False)
    cols = {c: c.upper() for c in df.columns}
    df = df.rename(columns=cols)
    c_data = next(c for c in df.columns if c.startswith("DATA"))
    c_hora = next(c for c in df.columns if c.startswith("HORA"))
    c_p = next(c for c in df.columns if c.startswith("PRECIPITA"))
    c_tx = next(c for c in df.columns if c.startswith("TEMPERATURA M") and "XIMA" in c and "HORA" in c)
    c_tn = next(c for c in df.columns if c.startswith("TEMPERATURA M") and "NIMA" in c and "HORA" in c)
    data = df[c_data].str.replace("-", "/", regex=False)
    hora = df[c_hora].str.extract(r"(\d{2})")[0].fillna("00")
    ts = pd.to_datetime(data + " " + hora, format="%Y/%m/%d %H", errors="coerce") - pd.Timedelta(hours=3)
    out = pd.DataFrame({"ts": ts, "p": _num(df[c_p]), "tx": _num(df[c_tx]), "tn": _num(df[c_tn])}).dropna(subset=["ts"])
    out["dia"] = out.ts.dt.floor("D")
    g = out.groupby("dia")
    res = pd.DataFrame({
        "chuva_mm": g["p"].sum(min_count=1), "n_p": g["p"].count(),
        "tmax": g["tx"].max(), "n_tx": g["tx"].count(),
        "tmin": g["tn"].min(), "n_tn": g["tn"].count(),
    })
    res.loc[res.n_p < MIN_HORAS, "chuva_mm"] = np.nan
    res.loc[res.n_tx < MIN_HORAS, "tmax"] = np.nan
    res.loc[res.n_tn < MIN_HORAS, "tmin"] = np.nan
    res = res[["chuva_mm", "tmin", "tmax"]].reset_index().rename(columns={"dia": "data"})
    res.insert(0, "codigo", cod)
    return res


def processar_inmet(bbox, zips_dir: Path, proc_dir: Path, headers: dict, anos=range(2000, 2026)):
    x0, y0, x1, y1 = bbox
    proc_dir.mkdir(parents=True, exist_ok=True)
    diarios, estacoes = [], {}
    falhas = []
    cache = proc_dir / "_inmet_ano"  # diário por ano já processado (idempotência)
    cache.mkdir(exist_ok=True)
    for ano in anos:
        pq = cache / f"{ano}.parquet"
        ef = cache / f"{ano}_estacoes.csv"
        if pq.exists() and ef.exists():
            diarios.append(pd.read_parquet(pq))
            if ef.stat().st_size > 5:
                for r in pd.read_csv(ef, dtype={"codigo": str}).to_dict("records"):
                    estacoes[r["codigo"]] = dict(codigo=r["codigo"], nome=r["nome"], uf=r["uf"], lat=r["lat"],
                                                 lon=r["lon"], alt=r["alt"])
            continue
        d = zips_dir / str(ano)
        d.mkdir(parents=True, exist_ok=True)
        zp = d / f"{ano}.zip"
        try:
            with requests.get(BASE.format(ano=ano), headers=headers, timeout=120, stream=True) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                with open(zp, "wb") as fh:
                    for ch in r.iter_content(1 << 20):
                        fh.write(ch)
            partes, est_ano = [], []
            with zipfile.ZipFile(zp) as z:
                for nome in z.namelist():
                    if not nome.upper().endswith(".CSV"):
                        continue
                    raw = z.read(nome)
                    h = _cabecalho(raw)
                    if not h or not (x0 <= h["lon"] <= x1 and y0 <= h["lat"] <= y1):
                        continue
                    partes.append(_diario(raw, h["codigo"]))
                    est_ano.append(h)
            dd = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
                columns=["codigo", "data", "chuva_mm", "tmin", "tmax"])
            dd.to_parquet(pq, index=False)
            pd.DataFrame(est_ano).rename(columns={"estacao": "nome"}).to_csv(ef, index=False)
            diarios.append(dd)
            for h in est_ano:
                estacoes[h["codigo"]] = dict(codigo=h["codigo"], nome=h["estacao"], uf=h["uf"], lat=h["lat"],
                                             lon=h["lon"], alt=h["alt"])
            print(f"INMET {ano}: {len(est_ano)} estações no bbox", flush=True)
        except Exception as e:  # noqa: BLE001
            falhas.append((ano, f"{type(e).__name__}: {e}"))
            print(f"INMET {ano} falhou: {e}", flush=True)
        finally:
            if zp.exists():
                zp.unlink()
    if not diarios:
        raise RuntimeError(f"nenhum ano INMET processado: {falhas}")
    dia = pd.concat([d for d in diarios if len(d)], ignore_index=True)
    dia["data"] = pd.to_datetime(dia["data"])
    dia = dia.dropna(how="all", subset=["chuva_mm", "tmin", "tmax"])
    dia.to_parquet(proc_dir / "inmet_diario.parquet", index=False)
    est = pd.DataFrame(estacoes.values())
    anos_cob = dia.assign(ano=dia.data.dt.year).groupby("codigo")["ano"].agg(["min", "max", "nunique"])
    est = est.merge(anos_cob.rename(columns={"min": "ano_ini", "max": "ano_fim", "nunique": "n_anos"}),
                    left_on="codigo", right_index=True, how="left")
    est.to_csv(proc_dir / "inmet_estacoes.csv", index=False)
    print(est.to_string())
    if falhas:
        print("Anos com falha:", falhas)
