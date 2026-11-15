"""PAM x climate analysis: does 2nd-season corn (SIDRA 839) yield less in years with frost or a dry spell in the second season?

For each Oeste do PR municipality: annual 2nd-season corn yield (kg/ha, 2003–2025) vs annual climate indicators of the
municipality centroid (indicadores_anuais.parquet, points `mun_*`):
  frost: geada_safrinha_semeadura_1502_le3 (min T ≤ 3 °C during grain fill; typical sowing 15/02);
  dry spell: veranico_safrinha_ge15 (≥ 15 consecutive days with rain < 1 mm in Mar–Apr).
Convention: season Y (Jul/Y–Jun/Y+1) -> second crop harvested in Y+1 = PAM year. So PAM_year = Y + 1.
Yield deviation = (yield − municipality linear trend) / trend, in %. Mean drop = mean deviation in years
WITHOUT the event − mean in years WITH the event (positive = yields less with the event).
Output: data/processed/pam/analise_pam_clima.csv and analise_pam_clima.png.
Usage: uv run python -m field_shift.pam.climate_analysis
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/processed/pam"
ANNUAL = ROOT / "data/processed/clima_pr/indicadores_anuais.parquet"
PAM = ROOT / "data/raw/ibge/pam_pr.parquet"
TOLEDO = "4127700"
IND = {"geada": "geada_safrinha_semeadura_1502_le3", "veranico": "veranico_safrinha_ge15"}


def build() -> pd.DataFrame:
    p = pd.read_parquet(PAM)
    p = p[(p.cultura == "milho_2safra") & (p.variavel == "rendimento_kg_ha")].dropna(subset=["valor"])
    p = p.rename(columns={"valor": "rend"})[["cod_ibge", "ano", "rend"]]
    a = pd.read_parquet(ANNUAL, columns=["ponto_id", "ano", "indicador", "valor"])
    a = a[a.ponto_id.str.startswith("mun_") & a.indicador.isin(IND.values())]
    a = a.pivot_table(index=["ponto_id", "ano"], columns="indicador", values="valor").reset_index()
    a["cod_ibge"] = a.ponto_id.str[4:]
    a["ano_pam"] = a["ano"] + 1
    a = a.rename(columns={v: k for k, v in IND.items()})
    d = p.merge(a[["cod_ibge", "ano_pam", "geada", "veranico"]], left_on=["cod_ibge", "ano"], right_on=["cod_ibge", "ano_pam"])
    dev = []
    for cod, g in d.groupby("cod_ibge"):
        g = g.sort_values("ano")
        if len(g) < 10:
            continue
        c = np.polyfit(g.ano, g.rend, 1)
        tend = np.polyval(c, g.ano)
        dev.append(g.assign(tendencia=tend, desvio_pct=100 * (g.rend - tend) / tend))
    d = pd.concat(dev)
    d["geada"] = d["geada"] > 0
    d["veranico"] = d["veranico"] > 0
    d["algum"] = d.geada | d.veranico
    return d


def summarize(d: pd.DataFrame, label: str) -> list[dict]:
    out = []
    for ev in ("geada", "veranico", "algum"):
        com, sow_date = d[d[ev]], d[~d[ev]]
        if len(com) == 0:
            out.append(dict(escopo=label, evento=ev, n_com=0, n_sem=len(sow_date))); continue
        out.append(dict(escopo=label, evento=ev, n_com=len(com), n_sem=len(sow_date),
                        desvio_com_pct=com.desvio_pct.mean(), desvio_sem_pct=sow_date.desvio_pct.mean(),
                        queda_pct_pontos=sow_date.desvio_pct.mean() - com.desvio_pct.mean(),
                        mediana_com=com.desvio_pct.median(), mediana_sem=sow_date.desvio_pct.median()))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = build()
    res = pd.DataFrame(summarize(d, f"Oeste do PR ({d.cod_ibge.nunique()} municípios)") + summarize(d[d.cod_ibge == TOLEDO], "Toledo"))
    res.to_csv(OUT / "analise_pam_clima.csv", index=False)
    d.to_csv(OUT / "analise_pam_clima_detalhe.csv", index=False)
    print(res.round(2).to_string(index=False))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for a, (title, g) in zip(ax, [("Oeste do PR (todos os municípios)", d), ("Toledo", d[d.cod_ibge == TOLEDO])]):
        groups = [("sem evento", g[~g.algum]), ("só geada", g[g.geada & ~g.veranico]),
                  ("só veranico", g[g.veranico & ~g.geada]), ("geada + veranico", g[g.geada & g.veranico])]
        groups = [(n, x) for n, x in groups if len(x)]
        a.bar([f"{n}\n(n={len(x)})" for n, x in groups], [x.desvio_pct.mean() for n, x in groups],
              color=["#4c78a8", "#e45756", "#f58518", "#72b7b2"][:len(groups)])
        a.axhline(0, color="k", lw=0.8); a.set_title(title); a.tick_params(axis="x", labelsize=8)
    ax[0].set_ylabel("Desvio do rendimento do milho 2ª safra\nvs tendência do município (%)")
    fig.suptitle("PAM x clima: milho 2ª safra, 2003–2025 (geada ≤3 °C c/ semeadura 15/02; veranico ≥15 d mar–abr)", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "analise_pam_clima.png", dpi=130)
    print("saved to", OUT)


if __name__ == "__main__":
    main()
