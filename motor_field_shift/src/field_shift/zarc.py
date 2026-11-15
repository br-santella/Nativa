"""ZARC (Zoneamento Agrícola de Risco Climático, MAPA) lookup for the engine: informative only, it never changes scores.

For every candidate rotation the engine reports whether the sowing dates of its zoned crops are indicated by ZARC in the field's
municipality (risk class 20/30/40 %, share of soil classes indicated, ordinance). Outside ZARC the farmer loses subsidised rural
credit, Proagro and subsidised insurance, so the card warns about it.

Source: "Tábua de risco" 2025/2026 (dados.agricultura.gov.br, CC-BY). The compact table is built by `ingest/zarc_pr.py` into
data/processed/zarc/zarc_pr.parquet (Paraná, rainfed): per municipality × ZARC crop × ten-day period, the lowest risk over cycle
groups for each soil class, then `best` = lowest over soil classes and `share_soils` = share of soil classes indicated.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data/raw/zarc"
RAW_CSV = RAW_DIR / "tabua_2025_2026.csv"
RAW_PR = RAW_DIR / "tabua_2025_2026_pr.parquet"
TABLE = ROOT / "data/processed/zarc/zarc_pr.parquet"
SEASON = "2025/2026"
URL = ("https://dados.agricultura.gov.br/dataset/6d3d141c-885e-41a4-ab7f-dc8ff323b96f/resource/"
       "f9d597f9-0fee-47eb-9344-8642274ca9da/download/dados-abertos-tabua-de-risco-safra-2025-2026.csv")
SOURCE = f"ZARC {SEASON} (MAPA, tábua de risco, sequeiro)"
DECS = [f"dec{i}" for i in range(1, 37)]
NOT_INDICATED = 50  # sentinel above the 40 % class

# Engine crop -> ZARC crop name. Second-window crops that follow the chosen sowing date:
SECOND_SOWING = {
    "milho_safrinha": "Milho 2ª Safra",
    "milho_braquiaria": "Milho 2ª Safra consorciado com Braquiária",
    "sorgo": "Sorgo Granífero 2ª Safra",
    "feijao_safrinha": "Feijão 2ª Safra",
}
# Second-window crops with a fixed sowing date (field_shift.agua.balanco.SEMEADURA_TRIGO); oat + radish is checked as oat.
SECOND_FIXED = {"trigo": "Trigo", "aveia": "Aveia", "aveia_nabo": "Aveia"}
# Summer crops: ZARC crop and the engine's sowing assumption (soybean 15/10 = catalog `plantio_soja`; summer corn 01/10 is the
# middle of the 15/09–15/10 window in the catalog comment, an estimate).
SUMMER = {"soja": ("Soja", "15/10"), "milho_verao": ("Milho 1ª Safra", "01/10")}
CROP_LABEL = {"Milho 2ª Safra": "milho 2ª safra", "Milho 2ª Safra consorciado com Braquiária": "milho 2ª safra + braquiária",
              "Sorgo Granífero 2ª Safra": "sorgo 2ª safra", "Feijão 2ª Safra": "feijão 2ª safra", "Trigo": "trigo",
              "Aveia": "aveia", "Soja": "soja", "Milho 1ª Safra": "milho 1ª safra"}
ZONED = set(SECOND_SOWING.values()) | set(SECOND_FIXED.values()) | {v[0] for v in SUMMER.values()}


def decendio(ddmm: str) -> int:
    """Ten-day period of the year (1–36): days 1–10, 11–20 and 21–end of each month."""
    d, m = map(int, ddmm.split("/"))
    return (m - 1) * 3 + (0 if d <= 10 else 1 if d <= 20 else 2) + 1


def extract_pr(csv_path: Path = RAW_CSV, out: Path = RAW_PR) -> pd.DataFrame:
    """Keep only the Paraná rows of the national CSV (~220 MB) and save them as parquet."""
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", dtype=str)
    pr = df[df["UF"] == "PR"].reset_index(drop=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    pr.to_parquet(out)
    return pr


def build_table(pr: pd.DataFrame) -> pd.DataFrame:
    """Compact long table: geocodigo, crop, decendio, best (20/30/40, NOT_INDICATED), share_soils, portaria."""
    z = pr[pr["Nome_cultura"].isin(ZONED) & (pr["Cod_Outros_Manejos"] == "1")]
    v = z[DECS].fillna("0").astype(int).replace(0, NOT_INDICATED)  # empty cell = not indicated
    v[["geocodigo", "crop", "solo"]] = z[["geocodigo", "Nome_cultura", "Cod_Solo"]].to_numpy()
    per_soil = v.groupby(["geocodigo", "crop", "solo"])[DECS].min()  # best cycle group per soil class
    long = per_soil.reset_index().melt(id_vars=["geocodigo", "crop", "solo"], var_name="dec", value_name="cls")
    long["decendio"] = long["dec"].str[3:].astype(int)
    g = long.groupby(["geocodigo", "crop", "decendio"])["cls"]
    out = pd.DataFrame({"best": g.min(), "share_soils": g.apply(lambda s: float((s < NOT_INDICATED).mean()))}).reset_index()
    port = z.groupby(["geocodigo", "Nome_cultura"])["Portaria"].first().rename_axis(["geocodigo", "crop"]).rename("portaria")
    return out.merge(port.reset_index(), on=["geocodigo", "crop"], how="left")


@lru_cache(maxsize=1)
def table() -> pd.DataFrame | None:
    """Indexed compact table, or None when it was not built (the engine then keeps the generic ZARC warning)."""
    if not TABLE.exists():
        return None
    return pd.read_parquet(TABLE).set_index(["geocodigo", "crop", "decendio"]).sort_index()


def status(cod_ibge: str, crop: str, sowing: str) -> dict | None:
    """ZARC status of one crop sown on `sowing` (dd/mm) in the municipality. None if the table is unavailable."""
    t = table()
    if t is None:
        return None
    dec = decendio(sowing)
    base = dict(cultura=CROP_LABEL.get(crop, crop), cultura_zarc=crop, semeadura=sowing, decendio=dec)
    key = (str(cod_ibge), crop, dec)
    if key not in t.index:
        return dict(base, indicado=False, risco_pct=None, solos_indicados_pct=0.0, portaria=None,
                    motivo="cultura sem zoneamento no município")
    row = t.loc[key]
    ok = int(row["best"]) < NOT_INDICATED
    return dict(base, indicado=ok, risco_pct=int(row["best"]) if ok else None,
                solos_indicados_pct=round(100 * float(row["share_soils"])), portaria=row["portaria"],
                motivo=None if ok else "data de semeadura fora da janela do ZARC")


def rotation_status(c: dict, cod_ibge: str | None, sowing_2nd: str | None, fixed_sowing: str) -> dict | None:
    """ZARC check of a catalog rotation (`engine.CATALOGO` entry): summer crop at its assumed date and the second crop at the
    chosen (or fixed) date. `indicado` = all zoned crops indicated; None when nothing could be checked."""
    if cod_ibge is None or table() is None:
        return None
    checks = []
    zc, sow = SUMMER[c["verao"]]
    checks.append(status(cod_ibge, zc, sow))
    seg = c["segunda"]
    if seg in SECOND_SOWING and sowing_2nd:
        checks.append(status(cod_ibge, SECOND_SOWING[seg], sowing_2nd))
    elif seg in SECOND_FIXED:
        checks.append(status(cod_ibge, SECOND_FIXED[seg], fixed_sowing))
    checks = [x for x in checks if x is not None]
    not_zoned = seg not in SECOND_SOWING and seg not in SECOND_FIXED
    out = [x for x in checks if not x["indicado"]]
    return dict(indicado=not out, culturas=checks, segunda_sem_zoneamento=not_zoned, fonte=SOURCE)


def warning_text(zs: dict, municipio: str) -> str | None:
    """Card warning for the crops outside ZARC (None when everything checked is indicated)."""
    if zs is None:
        return None
    fora = [x for x in zs["culturas"] if not x["indicado"]]
    if not fora:
        return None
    partes = [f"{x['cultura']} semeado(a) em {x['semeadura']} ({x['motivo']})" for x in fora]
    return (f"Fora do {SOURCE.split(' (')[0]} em {municipio}: " + "; ".join(partes)
            + ". Sem ZARC não há acesso ao crédito rural com juros controlados, ao Proagro nem ao seguro rural subvencionado "
              "(aviso informativo: não muda a nota).")


def evidence_text(zs: dict, municipio: str) -> str | None:
    """One evidence line with the ZARC class of every checked crop."""
    if zs is None or not zs["culturas"]:
        return None
    partes = []
    for x in zs["culturas"]:
        if x["indicado"]:
            partes.append(f"{x['cultura']} em {x['semeadura']}: indicado, risco {x['risco_pct']}% "
                          f"({x['solos_indicados_pct']}% das classes de solo; {x['portaria']})")
        else:
            partes.append(f"{x['cultura']} em {x['semeadura']}: não indicado")
    extra = " A cobertura da 2ª janela não tem zoneamento ZARC." if zs["segunda_sem_zoneamento"] else ""
    return f"{SOURCE}, {municipio}: " + "; ".join(partes) + "." + extra
