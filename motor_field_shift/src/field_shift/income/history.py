"""Track record of the second crop: realized margin of the last seasons in the municipality (used in the income score).

For each sold second crop with a historical cost series (off-season corn, corn + brachiaria, wheat), and each of the last
`SEASONS` harvest years with data:

    realized margin = municipal yield (IBGE PAM, year Y) × Paraná realized price (PAM: Σ production value / Σ production, year Y)
                      − CONAB variable cost (≈COE, Londrina-PR sheet of year Y) [− brachiaria establishment cost]

expressed in **bags of soybean per hectare** (÷ Paraná soybean realized price of the same year), so seasons with different
price levels can be compared without a deflator. The bonus on the following soybean is not included.

Why: in the historical backtest (docs/validation.md §3) a decision based on the 5-season track record recovered most of the
gap to the ex-post best choice (8.6 vs 8.9 bags/ha/yr), while the price snapshot alone lost 3.4 bags/ha/yr against always
planting corn. The card shows it next to the current-price margin so the farmer sees the spread of good and bad seasons.

Income score (docs/validation.md §6.2): for off-season corn, corn + brachiaria and wheat, the second-crop margin that enters the
income criterion is the track-record mean × the soybean price in use, instead of the current-price estimate (yield trend × current
price − current cost). Out of sample (Oeste, 2010–2025) it chose better in 13 of 16 seasons (+1.26 soybean bags/ha/yr, 90 %
season-bootstrap interval +0.60 to +2.05), with no fitted parameter. The current-price estimate stays when the farmer typed
their own price, cost or yield for that crop, or picked a cost line other than COE (the record is built on the COE).
"""
from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from field_shift.i18n import Msg
from field_shift.pam.productivity import series

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw"
PAM_PR = RAW / "ibge/pam_pr.parquet"
SEASONS = 5
KG_PER_BAG = 60.0
CONAB_PLACE = "Londrina"
# second crop (engine name) -> (PAM yield crop, PAM price crop, CONAB cost file)
GRAIN = {"milho_safrinha": ("milho_2safra", "milho_total", "milho_2safra"),
         "milho_braquiaria": ("milho_2safra", "milho_total", "milho_2safra"),
         "trigo": ("trigo", "trigo", "trigo")}
LABEL = {"milho_safrinha": "milho safrinha", "milho_braquiaria": "milho safrinha + braquiária", "trigo": "trigo"}


def _conab_line(f: Path, sheet: str, label: str = "CUSTO VARIÁVEL") -> float | None:
    """First number to the right of the first cell containing `label` (layouts change across CONAB sheets)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = pd.read_excel(f, sheet_name=sheet, header=None)
    for _, row in d.iterrows():
        cells = list(row)
        for i, c in enumerate(cells):
            if isinstance(c, str) and label.lower() in c.lower():
                for v in cells[i + 1:]:
                    if isinstance(v, (int, float, np.floating)) and not pd.isna(v):
                        return float(v)
    return None


@lru_cache(maxsize=None)
def conab_costs(crop: str, place: str = CONAB_PLACE) -> pd.Series:
    """CONAB variable cost (≈COE, BRL/ha) per harvest year for a Paraná location. Sheets with a month suffix (wheat) keep the
    last one of the year. Empty when the file is missing."""
    f = RAW / f"renda/conab_{crop}.xls"
    if not f.exists():
        return pd.Series(dtype=float, name=crop)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        names = [s for s in pd.ExcelFile(f).sheet_names if s.startswith(place)]
    out = {}
    for s in names:
        year = int(s.split("-PR-")[1][:4])
        v = _conab_line(f, s)
        if v is not None:
            out[year] = v
    return pd.Series(out, name=crop, dtype=float).sort_index()


@lru_cache(maxsize=None)
def pr_prices(crop: str) -> pd.Series:
    """Paraná realized price (BRL per 60 kg bag) per year: Σ production value / Σ production over all municipalities (PAM)."""
    p = pd.read_parquet(PAM_PR)
    p = p[(p["cultura"] == crop) & p["variavel"].isin(["valor_mil_reais", "producao_t"])].dropna(subset=["valor"])
    w = p.pivot_table(index="ano", columns="variavel", values="valor", aggfunc="sum")
    w = w[(w.get("producao_t", 0) > 0)].dropna()
    return (w["valor_mil_reais"] * 1000 / (w["producao_t"] * 1000 / KG_PER_BAG)).rename(crop)


def _extra_cost_bags(nome: str) -> float:
    """Brachiaria establishment cost in soybean bags (current reference cost ÷ current soybean price; no historical series)."""
    if nome != "milho_braquiaria":
        return 0.0
    from field_shift.income.income import load_reference
    ref = load_reference()
    return ref["costs"]["braquiaria_consorcio"]["coe"] / ref["prices"]["soja"]["value"]


@lru_cache(maxsize=512)
def track_record(cod_ibge: str | None, nome: str, seasons: int = SEASONS) -> dict | None:
    """Realized second-crop margin (soybean bags/ha) of the last `seasons` harvest years with data, or None when the crop has no
    cost series or the municipality has fewer than 3 such seasons."""
    if cod_ibge is None or nome not in GRAIN:
        return None
    ycrop, pcrop, ccrop = GRAIN[nome]
    y = series(cod_ibge, ycrop) / KG_PER_BAG
    pr, soy, cost = pr_prices(pcrop), pr_prices("soja"), conab_costs(ccrop)
    extra = _extra_cost_bags(nome)
    rows = []
    for year in sorted(y.index, reverse=True):
        if year in pr.index and year in soy.index and year in cost.index:
            m = float(y[year] * pr[year] / soy[year] - cost[year] / soy[year] - extra)
            rows.append(dict(ano=int(year), rendimento_sc_ha=round(float(y[year]), 1), margem_sc_soja_ha=round(m, 1)))
        if len(rows) == seasons:
            break
    if len(rows) < 3:
        return None
    rows = rows[::-1]
    v = np.array([r["margem_sc_soja_ha"] for r in rows])
    return dict(cultura=LABEL[nome], safras=rows, media_sc_soja_ha=round(float(v.mean()), 1),
                min_sc_soja_ha=round(float(v.min()), 1), max_sc_soja_ha=round(float(v.max()), 1),
                negativas=int((v < 0).sum()),
                fonte=(f"IBGE PAM (rendimento do município; preço realizado do PR = valor/produção) e custo variável CONAB "
                       f"{CONAB_PLACE}-PR de cada safra; em sacas de soja/ha (÷ preço realizado da soja no PR no mesmo ano); "
                       f"sem o bônus na soja seguinte"))


def _uses_current_price(itens: list[dict], keys: list[str], cost_line: str) -> bool:
    """True when the farmer gave their own data for the second crop (price, cost or yield) or a cost line other than COE: then
    the current-price estimate is the more specific one and the track record does not replace it."""
    own = any(i.get("preco_usuario") or i.get("custo_usuario") or i.get("prod_usuario") for i in itens if i["chave"] in keys)
    return own or cost_line != "coe"


def apply_to_income(margins: dict, catalog: dict, cod_ibge: str | None) -> dict:
    """Set the income basis of each candidate. For second crops with a track record (and no farmer data for them), the
    second-crop margin in `incremental` is replaced by the track-record mean × the soybean price in use; the current-price
    value is kept in `incremental_preco_atual`. Adds `base_renda` ("historico" | "preco_atual") and `historico_sc_soja_ha`."""
    for name, m in margins.items():
        c = catalog[name]
        m["incremental_preco_atual"] = m["incremental"]
        m["base_renda"], m["historico_sc_soja_ha"], m["historico_safras"] = "preco_atual", None, None
        tr = track_record(cod_ibge, c["segunda"])
        if tr is None or _uses_current_price(m["itens"], c["renda_itens"], m["linha_custo"]):
            continue
        current = sum(i["margem"] for i in m["itens"] if i["chave"] in c["renda_itens"] and not i.get("extra"))
        m["incremental"] = m["incremental"] - current + tr["media_sc_soja_ha"] * m["preco_soja"]
        m["base_renda"], m["historico_sc_soja_ha"] = "historico", tr["media_sc_soja_ha"]
        m["historico_safras"] = {r["ano"]: r["margem_sc_soja_ha"] for r in tr["safras"]}
    return margins


def text(tr: dict | None, in_score: bool = False) -> str | None:
    """Evidence line of the card."""
    if tr is None:
        return None
    years = ", ".join(f"{r['ano']}: {r['margem_sc_soja_ha']:+.0f}" for r in tr["safras"]).replace(".", ",")
    usage = ("A média entra na nota de renda no lugar da margem a preço atual (acertou mais nas safras passadas)." if in_score
             else "Informativo: não entra na nota (há preço, custo ou produtividade informados pelo produtor).")
    values = [tr["cultura"].replace(".", ","), years, f"{tr['media_sc_soja_ha']:.1f}".replace(".", ","), tr["fonte"], usage]
    if tr["negativas"]:
        return Msg("Histórico de renda do {0} no município (margem realizada, sc de soja/ha): {1}; média {2}; margem negativa em "
                   "{5} de {6}. Fonte: {3}. {4}", *values, str(tr["negativas"]), str(len(tr["safras"])))
    return Msg("Histórico de renda do {0} no município (margem realizada, sc de soja/ha): {1}; média {2}. Fonte: {3}. {4}",
               *values)
