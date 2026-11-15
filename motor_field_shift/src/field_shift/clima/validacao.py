"""NASA POWER x INMET station validation (the POWER cell that contains the station)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DLAT, DLON = 0.5, 0.625


def celula_id(lat: float, lon: float) -> str:
    return f"cel_{round(lat / DLAT) * DLAT:+.3f}_{round(lon / DLON) * DLON:+.4f}"


def validar(proc: Path):
    est = pd.read_csv(proc / "inmet_estacoes.csv", dtype={"codigo": str})
    ine = pd.read_parquet(proc / "inmet_diario.parquet")
    pw = pd.read_parquet(proc / "power_diario.parquet", columns=["ponto_id", "data", "T2M_MIN", "PRECTOTCORR"])
    rows = []
    for e in est.itertuples():
        cid = celula_id(e.lat, e.lon)
        a = ine[ine.codigo == e.codigo].set_index("data")
        b = pw[pw.ponto_id == cid].set_index("data")
        if a.empty or b.empty:
            continue
        j = a.join(b, how="inner")
        r = dict(codigo=e.codigo, nome=e.nome, uf=e.uf, lat=e.lat, lon=e.lon, celula=cid,
                 anos_inmet=f"{a.index.year.min()}-{a.index.year.max()}")
        t = j.dropna(subset=["tmin", "T2M_MIN"])
        r["n_dias_tmin"] = len(t)
        if len(t) > 100:
            r["tmin_vies_C"] = float((t.T2M_MIN - t.tmin).mean())      # POWER - station
            r["tmin_corr"] = float(t.T2M_MIN.corr(t.tmin))
            r["tmin_rmse_C"] = float(np.sqrt(((t.T2M_MIN - t.tmin) ** 2).mean()))
            inv = t[t.index.month.isin([5, 6, 7, 8, 9])]
            r["tmin_vies_invernal_C"] = float((inv.T2M_MIN - inv.tmin).mean())
        # frost days per year (years with >= 330 days of valid Tmin at the station and in POWER)
        t2 = t.assign(ano=t.index.year)
        ok = t2.groupby("ano").size()
        anos_ok = ok[ok >= 330].index
        r["n_anos_geada"] = len(anos_ok)
        for lim in (2, 3):
            if len(anos_ok):
                tt = t2[t2.ano.isin(anos_ok)]
                est_d = (tt.tmin <= lim).groupby(tt.ano).sum()
                pw_d = (tt.T2M_MIN <= lim).groupby(tt.ano).sum()
                r[f"dias_le{lim}_estacao_ano"] = float(est_d.mean())
                r[f"dias_le{lim}_power_ano"] = float(pw_d.mean())
                r[f"anos_com_geada_le{lim}_estacao"] = float((est_d > 0).mean())
                r[f"anos_com_geada_le{lim}_power"] = float((pw_d > 0).mean())
                r[f"dias_le{lim}_corr_anual"] = float(est_d.corr(pw_d)) if len(est_d) > 2 else np.nan
        # monthly rain (months with >= 28 valid days in both)
        c = j.dropna(subset=["chuva_mm", "PRECTOTCORR"])
        m = c.groupby([c.index.year, c.index.month]).agg(est=("chuva_mm", "sum"), pw=("PRECTOTCORR", "sum"),
                                                          n=("chuva_mm", "size"))
        m = m[m.n >= 28]
        r["n_meses_chuva"] = len(m)
        if len(m) > 12:
            r["chuva_mensal_vies_mm"] = float((m.pw - m.est).mean())
            r["chuva_mensal_vies_pct"] = float((m.pw.sum() / m.est.sum() - 1) * 100)
            r["chuva_mensal_corr"] = float(m.pw.corr(m.est))
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(proc / "validacao_power_inmet.csv", index=False)
    pd.set_option("display.width", 250)
    print(out.round(2).to_string())
    if len(out):
        print("\nMEANS:", out[["tmin_vies_C", "tmin_vies_invernal_C", "tmin_corr", "dias_le2_estacao_ano", "dias_le2_power_ano",
                              "dias_le3_estacao_ano", "dias_le3_power_ano", "chuva_mensal_vies_pct",
                              "chuva_mensal_corr"]].mean().round(2).to_dict())
