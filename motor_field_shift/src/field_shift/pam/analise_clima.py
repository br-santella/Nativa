"""Análise PAM x clima: o milho 2ª safra (SIDRA 839) rende menos em anos com geada ou veranico no safrinha?

Para cada município do Oeste do PR: rendimento anual do milho 2ª safra (kg/ha, 2003–2025) vs indicadores anuais do
clima do centróide do município (indicadores_anuais.parquet, pontos `mun_*`):
  geada: geada_safrinha_semeadura_1502_le3 (T mín ≤ 3 °C no enchimento; semeadura típica 15/02);
  veranico: veranico_safrinha_ge15 (≥ 15 dias seguidos com chuva < 1 mm em mar–abr).
Convenção: safra Y (jul/Y–jun/Y+1) -> safrinha colhida em Y+1 = ano do PAM. Logo ano_PAM = Y + 1.
Desvio do rendimento = (rendimento − tendência linear do município) / tendência, em %. Queda média = média dos desvios nos
anos SEM evento − média nos anos COM evento (positivo = rende menos com evento).
Saída: data/processed/pam/analise_pam_clima.csv e analise_pam_clima.png.
Uso: uv run python -m field_shift.pam.analise_clima
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/processed/pam"
ANUAIS = ROOT / "data/processed/clima_pr/indicadores_anuais.parquet"
PAM = ROOT / "data/raw/ibge/pam_pr.parquet"
TOLEDO = "4127700"
IND = {"geada": "geada_safrinha_semeadura_1502_le3", "veranico": "veranico_safrinha_ge15"}


def montar() -> pd.DataFrame:
    p = pd.read_parquet(PAM)
    p = p[(p.cultura == "milho_2safra") & (p.variavel == "rendimento_kg_ha")].dropna(subset=["valor"])
    p = p.rename(columns={"valor": "rend"})[["cod_ibge", "ano", "rend"]]
    a = pd.read_parquet(ANUAIS, columns=["ponto_id", "ano", "indicador", "valor"])
    a = a[a.ponto_id.str.startswith("mun_") & a.indicador.isin(IND.values())]
    a = a.pivot_table(index=["ponto_id", "ano"], columns="indicador", values="valor").reset_index()
    a["cod_ibge"] = a.ponto_id.str[4:]
    a["ano_pam"] = a["ano"] + 1
    a = a.rename(columns={v: k for k, v in IND.items()})
    d = p.merge(a[["cod_ibge", "ano_pam", "geada", "veranico"]], left_on=["cod_ibge", "ano"], right_on=["cod_ibge", "ano_pam"])
    desv = []
    for cod, g in d.groupby("cod_ibge"):
        g = g.sort_values("ano")
        if len(g) < 10:
            continue
        c = np.polyfit(g.ano, g.rend, 1)
        tend = np.polyval(c, g.ano)
        desv.append(g.assign(tendencia=tend, desvio_pct=100 * (g.rend - tend) / tend))
    d = pd.concat(desv)
    d["geada"] = d["geada"] > 0
    d["veranico"] = d["veranico"] > 0
    d["algum"] = d.geada | d.veranico
    return d


def resumir(d: pd.DataFrame, rotulo: str) -> list[dict]:
    out = []
    for ev in ("geada", "veranico", "algum"):
        com, sem = d[d[ev]], d[~d[ev]]
        if len(com) == 0:
            out.append(dict(escopo=rotulo, evento=ev, n_com=0, n_sem=len(sem))); continue
        out.append(dict(escopo=rotulo, evento=ev, n_com=len(com), n_sem=len(sem),
                        desvio_com_pct=com.desvio_pct.mean(), desvio_sem_pct=sem.desvio_pct.mean(),
                        queda_pct_pontos=sem.desvio_pct.mean() - com.desvio_pct.mean(),
                        mediana_com=com.desvio_pct.median(), mediana_sem=sem.desvio_pct.median()))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = montar()
    res = pd.DataFrame(resumir(d, f"Oeste do PR ({d.cod_ibge.nunique()} municípios)") + resumir(d[d.cod_ibge == TOLEDO], "Toledo"))
    res.to_csv(OUT / "analise_pam_clima.csv", index=False)
    d.to_csv(OUT / "analise_pam_clima_detalhe.csv", index=False)
    print(res.round(2).to_string(index=False))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for a, (titulo, g) in zip(ax, [("Oeste do PR (todos os municípios)", d), ("Toledo", d[d.cod_ibge == TOLEDO])]):
        grupos = [("sem evento", g[~g.algum]), ("só geada", g[g.geada & ~g.veranico]),
                  ("só veranico", g[g.veranico & ~g.geada]), ("geada + veranico", g[g.geada & g.veranico])]
        grupos = [(n, x) for n, x in grupos if len(x)]
        a.bar([f"{n}\n(n={len(x)})" for n, x in grupos], [x.desvio_pct.mean() for n, x in grupos],
              color=["#4c78a8", "#e45756", "#f58518", "#72b7b2"][:len(grupos)])
        a.axhline(0, color="k", lw=0.8); a.set_title(titulo); a.tick_params(axis="x", labelsize=8)
    ax[0].set_ylabel("Desvio do rendimento do milho 2ª safra\nvs tendência do município (%)")
    fig.suptitle("PAM x clima: milho 2ª safra, 2003–2025 (geada ≤3 °C c/ semeadura 15/02; veranico ≥15 d mar–abr)", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "analise_pam_clima.png", dpi=130)
    print("salvo em", OUT)


if __name__ == "__main__":
    main()
