"""Run the sensitivity analysis (docs/validation.md, section 1).

    uv run python scripts/validation/sensitivity.py [--draws 1000]

Writes CSVs to data/processed/validation/ and a summary figure to docs/figuras/validation_sensitivity.png;
prints the markdown tables used in the doc.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from field_shift.validation import sensitivity as sens  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/validation"
FIG = ROOT / "docs/figuras/validation_sensitivity.png"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=1000)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    oat, wext, mc, baselines = [], [], [], []
    for sc in sens.SCENARIOS:
        ctx = sens.build_context(sc)
        tab = sens.rank(ctx)
        baselines.append(tab.assign(scenario=sc.key, position=range(1, len(tab) + 1)))
        oat.append(sens.one_at_a_time(ctx))
        wext.append(sens.weight_extremes(ctx))
        mc.append(sens.weight_monte_carlo(ctx, n=args.draws))
    baselines, oat, wext, mc = (pd.concat(x, ignore_index=True) for x in (baselines, oat, wext, mc))
    baselines.to_csv(OUT / "sensitivity_baseline.csv", index=False)
    oat.to_csv(OUT / "sensitivity_oat.csv", index=False)
    wext.to_csv(OUT / "sensitivity_weights.csv", index=False)
    mc.to_csv(OUT / "sensitivity_weights_mc.csv", index=False)

    print("## Baseline (top-4 per scenario)\n")
    for k, g in baselines.groupby("scenario", sort=False):
        print(k, "|", " > ".join(f"{i} ({n:.3f})" for i, n in zip(g["id"][:4], g["nota"][:4])))

    # Parameter importance: across scenarios and both signs.
    imp = (oat.groupby(["param", "label", "group"])
           .agg(top1_flips=("top1_changed", "sum"), min_top3_jaccard=("top3_jaccard", "min"),
                min_tau=("kendall_tau", "min"), max_score_shift=("max_score_shift", "max"))
           .reset_index().sort_values(["top1_flips", "min_top3_jaccard", "min_tau"], ascending=[False, True, True]))
    imp.to_csv(OUT / "sensitivity_importance.csv", index=False)
    print("\n## Parameters that move the ranking (±20 %, 4 scenarios × 2 signs = 8 runs)\n")
    moving = imp[(imp.top1_flips > 0) | (imp.min_top3_jaccard < 1)]
    print(moving.to_markdown(index=False, floatfmt=".3f"))
    print(f"\nParameters tested: {imp.shape[0]}; moving top-1 or top-3: {moving.shape[0]}")
    flips = oat[oat.top1_changed][["scenario", "param", "factor", "new_top1"]]
    print("\n## Top-1 flips\n")
    print(flips.to_markdown(index=False))

    print("\n## Weight extremes (0 or 10, others default)\n")
    print(wext.to_markdown(index=False, floatfmt=".3f"))
    print(f"\n## Monte Carlo weights ({args.draws} draws, uniform 0–10)\n")
    print(mc[mc.top3_share > 0].to_markdown(index=False, floatfmt=".3f"))

    # Figure: min Kendall tau per parameter (worst case across scenarios/signs), 15 most sensitive.
    top = imp.sort_values("min_tau").head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    colors = ["#c0392b" if f > 0 else "#2e86c1" for f in top["top1_flips"]]
    ax.barh(top["label"], 1 - top["min_tau"], color=colors)
    ax.set_xlabel("1 − Kendall τ, worst case at ±20 % (higher = ranking changes more)")
    ax.set_title("Ranking sensitivity to estimated parameters\n(red = flips the top-1 in at least one scenario)")
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)
    print(f"\nfigure: {FIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
