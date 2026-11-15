"""Satellite check (docs/validation.md, section 5): MapBiomas + HLS NDVI of real fields.

    uv run python scripts/validation/satellite.py [--refetch]

First run downloads the HLS NDVI of ~335 fields (~10 min, Planetary Computer, no login) to
data/processed/validation/satellite_ndvi_fields.parquet; later runs reuse it. Writes CSVs and docs/figuras/validation_satellite.png.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from field_shift.app import engine as E  # noqa: E402
from field_shift.validation import satellite as S  # noqa: E402

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "docs/figuras/validation_satellite.png"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()

    print("## MapBiomas (FTW fields, 2019–2024)\n")
    print(json.dumps(S.mapbiomas_summary(), indent=1))

    fields = S.sample_fields()
    if args.refetch or not S.NDVI_FILE.exists():
        S.fetch_ndvi(fields)
    ndvi = pd.read_parquet(S.NDVI_FILE)
    print(f"\n## HLS: {ndvi['id'].nunique()} fields, {len(fields)} sampled ({fields['area_ha'].sum():.0f} ha), "
          f"{ndvi['data'].nunique()} dates, {len(ndvi)} field-observations")

    fy = S.field_years(ndvi)
    fy.to_csv(S.OUT / "satellite_field_years.csv", index=False)
    print(f"field-years kept (clear gap ≤ 45 d): {len(fy)}")

    by_year = fy.groupby("year").agg(fields=("id", "size"), share_double=("double", "mean"),
                                     bare_days_median=("bare_days", "median"))
    print("\n### Rotation practised (engine peak rule)\n")
    print(by_year.to_markdown(floatfmt=".2f"))
    per_field = fy.groupby("id")["double"].mean()
    print(f"\nfields double-cropped in every observed year: {(per_field == 1).mean():.2f}; never: {(per_field == 0).mean():.2f}; "
          f"engine detection (median ≥ 2 peaks) = soy → off-season corn: {(fy.groupby('id')['peaks'].median() >= 2).mean():.2f}")

    bare = fy.groupby("double").agg(n=("id", "size"), bare_year_median=("bare_days", "median"), bare_year_mean=("bare_days", "mean"),
                                    bare_2nd_window_median=("bare_days_2nd_window", "median"))
    print("\n### Bare-soil days (NDVI < 0.35)\n")
    print(bare.to_markdown(floatfmt=".1f"))
    print(f"\ncatalog dias_descobertos: off-season corn {E.SEGUNDA['milho_safrinha']['dias_descobertos']}, "
          f"fallow {E.SEGUNDA['pousio']['dias_descobertos']} (difference "
          f"{E.SEGUNDA['pousio']['dias_descobertos'] - E.SEGUNDA['milho_safrinha']['dias_descobertos']})")

    eff = S.following_soy_effect(fy)
    eff.to_csv(S.OUT / "satellite_following_soy.csv", index=False)
    print("\n### Following soybean after a double-crop vs single-crop year\n")
    print(eff.to_markdown(index=False, floatfmt=".3f"))

    # Figure: median NDVI curve of double vs single years + bare days distribution
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    for flag, color, lab in ((True, "#2e86c1", "double-crop years"), (False, "#c0392b", "single-crop years")):
        curves = []
        for (fid, y0), _ in fy[fy["double"] == flag].groupby(["id", "y0"]):
            s = S.daily_series(ndvi[ndvi["id"] == fid])[pd.Timestamp(y0, 9, 1):pd.Timestamp(y0 + 1, 8, 31)]
            curves.append(pd.Series(s.values[:365], index=range(min(365, len(s)))))
        if curves:
            m = pd.concat(curves, axis=1).median(axis=1)
            ax.plot(m.index, m.values, color=color, label=f"{lab} (n={len(curves)})")
    ax.axhline(E.LIMIAR_SOLO, color="gray", ls=":", label="bare-soil threshold 0.35")
    ax.set_xticks([0, 61, 122, 181, 242, 303, 364], ["Sep", "Nov", "Jan", "Mar", "May", "Jul", "Aug"])
    ax.set_ylabel("median NDVI (HLS)")
    ax.legend(fontsize=7)
    ax.set_title("Field-years around field 72638 (Toledo), 2019/20–2024/25", fontsize=9)
    ax = axes[1]
    ax.hist([fy.loc[fy["double"], "bare_days"], fy.loc[~fy["double"], "bare_days"]], bins=20,
            color=["#2e86c1", "#c0392b"], label=["double crop", "single crop"])
    ax.set_xlabel("bare-soil days per agricultural year (NDVI < 0.35)")
    ax.set_ylabel("field-years")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)
    print(f"\nfigure: {FIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
