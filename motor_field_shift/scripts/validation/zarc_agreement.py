"""ZARC agreement (docs/validation.md, section 2).

    uv run python scripts/validation/zarc_agreement.py

Builds the engine's ZARC table if missing (ingest/zarc_pr.py: ~220 MB CSV, Paraná rows), compares it with the engine (soil-aware
risk, same code path as a field) for the 399 municipalities of Paraná, writes CSVs to data/processed/validation/ and a figure to
docs/figuras/validation_zarc.png, and prints the tables used in the doc.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from field_shift import zarc as RZ  # noqa: E402
from field_shift.app import engine as E  # noqa: E402
from field_shift.validation import zarc as Z  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/validation"
FIG = ROOT / "docs/figuras/validation_zarc.png"


def ensure_data() -> None:
    """Build the engine's ZARC table (downloads the CSV if needed) when it is missing."""
    if not RZ.TABLE.exists() or not RZ.RAW_PR.exists():
        import runpy
        runpy.run_path(str(ROOT / "ingest/zarc_pr.py"), run_name="__main__")


def by_date(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby(["crop", "sowing"], sort=False)
            .agg(n=("geocodigo", "size"), zarc_indicated=("zarc_indicated", "mean"), engine_valid=("engine_valid", "mean"),
                 engine_loss_mean=("engine_loss", "mean"), engine_loss_le40=("engine_within", "mean"),
                 zarc_class_when_indicated=("zarc_class", lambda s: s[s < Z.OUT_CLASS].mean()))
            .reset_index())


def directional(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for crop, g in df.groupby("crop"):
        out, ok = g[~g["zarc_indicated"]], g[g["zarc_indicated"]]
        rows.append(dict(crop=crop, spearman_loss_vs_class=spearmanr(g["engine_loss"], g["zarc_class"]).statistic,
                         zarc_out_engine_loss_gt40=(out["engine_loss"] > 0.40).mean() if len(out) else float("nan"),
                         n_zarc_out=len(out), zarc_ok_engine_loss_le40=(ok["engine_loss"] <= 0.40).mean(), n_zarc_ok=len(ok)))
    return pd.DataFrame(rows)


def main() -> None:
    ensure_data()
    OUT.mkdir(parents=True, exist_ok=True)
    sw = Z.second_window_table()
    fx = Z.fixed_date_table()
    sw.to_csv(OUT / "zarc_second_window.csv", index=False)
    fx.to_csv(OUT / "zarc_fixed_dates.csv", index=False)

    for reg, g in (("Paraná", sw), ("Oeste", sw[sw["oeste"]])):
        print(f"\n## {reg}: municipalities {g['geocodigo'].nunique()}\n")
        s = pd.DataFrame(Z.summarize(g)).T
        s.to_csv(OUT / f"zarc_summary_{reg.lower().replace('á', 'a')}.csv")
        print(s.to_markdown(floatfmt=".2f"))
        print()
        print(by_date(g).to_markdown(index=False, floatfmt=".2f"))
        print()
        print(directional(g).to_markdown(index=False, floatfmt=".2f"))
        f = fx if reg == "Paraná" else fx[fx["oeste"]]
        print()
        print(f.groupby("crop").agg(sowing=("sowing", "first"), zarc_indicated=("zarc_class", lambda s: (s < Z.OUT_CLASS).mean()),
                                    zarc_share_soils=("zarc_share_soils", "mean"), engine_loss_mean=("engine_loss", "mean"))
              .to_markdown(floatfmt=".2f"))

    corn = sw[sw["crop"] == "milho_safrinha"].groupby("municipio").agg(indicated=("zarc_indicated", "max"),
                                                                        min_loss=("engine_loss", "min"))
    nz = corn[~corn["indicated"]]
    print(f"\nMunicipalities with no 2nd-season corn zoning at any engine date: {len(nz)}; engine minimum loss there: "
          f"median {nz['min_loss'].median():.2f}, range {nz['min_loss'].min():.2f}–{nz['min_loss'].max():.2f}")

    # Figure: corn and sorghum, share of municipalities indicated by ZARC vs share with engine loss ≤ 40 %.
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, (reg, g) in zip(axes, (("Paraná (399 municipalities)", sw), ("Oeste (50 municipalities)", sw[sw["oeste"]]))):
        t = by_date(g)
        for crop, color in (("milho_safrinha", "#c0392b"), ("sorgo", "#2e86c1")):
            u = t[t["crop"] == crop]
            ax.plot(u["sowing"], u["zarc_indicated"], "-o", color=color, label=f"{crop}: ZARC indicated")
            ax.plot(u["sowing"], u["engine_loss_le40"], "--s", color=color, label=f"{crop}: engine loss ≤ 40 %")
        ax.set_title(reg)
        ax.set_xlabel("2nd-season sowing date")
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("share of municipalities")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle(f"ZARC {Z.SEASON} vs engine (rainfed, best soil class)")
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)
    print(f"\nfigure: {FIG.relative_to(ROOT)}; engine sowing dates: {E.SOWINGS_2ND}")


if __name__ == "__main__":
    main()
