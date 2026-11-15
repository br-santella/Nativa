"""Historical backtest (docs/validation.md, section 3).

    uv run python scripts/validation/backtest.py

Writes CSVs to data/processed/validation/ and docs/figuras/validation_backtest.png; prints the tables used in the doc.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from field_shift.validation import backtest as B  # noqa: E402

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/validation"
FIG = ROOT / "docs/figuras/validation_backtest.png"
YIELD_CROPS = ["soja", "milho_2safra", "milho_1safra", "trigo", "feijao_2safra", "aveia"]


def summary(s: pd.DataFrame, label: str) -> dict:
    return dict(estimator=label, n=len(s), engine_income_pick=s["engine_income_pick"].mean(),
                always_corn=s["always_milho_safrinha"].mean(), oracle=s["oracle"].mean(),
                regret=(s["oracle"] - s["engine_income_pick"]).mean(),
                hit_rate=(s["engine_income_choice"] == s["oracle_choice"]).mean(),
                share_corn=(s["engine_income_choice"] == "milho_safrinha").mean(),
                share_fallow=(s["engine_income_choice"] == "pousio").mean())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # a) yield expectation
    ya = pd.concat([B.yield_expectation(c) for c in YIELD_CROPS], ignore_index=True)
    ya.to_csv(OUT / "backtest_yield.csv", index=False)
    ym = pd.DataFrame([dict(crop=c, **B.yield_metrics(g)) for c, g in ya.groupby("crop", sort=False)])
    print("## a) Yield expectation (10-year mean vs realized)\n")
    print(ym.to_markdown(index=False, floatfmt=".3f"))

    # b) climate risk vs realized failures
    r = B.risk_vs_failures()
    print(f"\n## b) Off-season corn failures (yield ≤ {B.FAIL_DEV:.0%} vs trend), {r['n']} municipality-years {r['years']}, "
          f"base rate {r['base_failure']:.3f}\n")
    rows = [dict(signal=k, **r[k]) for k in ("frost", "dry_spell", "event")]
    print(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".3f"))
    print("\nmunicipal:", {k: round(v, 3) for k, v in r["municipal"].items()})
    r["by_year"].to_csv(OUT / "backtest_failures_by_year.csv")
    print(r["by_year"].round(2).T.to_markdown(floatfmt=".2f"))

    # c) decision backtest
    rows, per_strategy = [], None
    for bonus in (False, True):
        base = B.decision_backtest(with_bonus=bonus)
        variants = {"engine (10-y mean yield, last-year price)": base,
                    "trend yield, last-year price": B.decision_backtest(with_bonus=bonus, expectation="trend"),
                    "track record (5-y realized margin)": B.track_record(base, 5)}
        for label, d in variants.items():
            s = B.strategies(d)
            rows.append(dict(bonus=bonus, **summary(s, label)))
            if not bonus and label.startswith("engine"):
                per_strategy = s
                s.to_csv(OUT / "backtest_decisions.csv", index=False)
    dec = pd.DataFrame(rows)
    dec.to_csv(OUT / "backtest_decision_summary.csv", index=False)
    print("\n## c) Decision backtest (soybean bags/ha per year)\n")
    print(dec.to_markdown(index=False, floatfmt=".2f"))
    always = per_strategy[[c for c in per_strategy.columns if c.startswith("always_")]].mean().sort_values(ascending=False)
    print("\nFixed strategies, no bonus (bags/ha/yr):", always.round(2).to_dict())

    # Figure
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    bars = always.rename(lambda c: c.replace("always_", "")).to_dict()
    bars = {"oracle (ex-post best)": per_strategy["oracle"].mean(), **bars,
            "engine income pick": per_strategy["engine_income_pick"].mean()}
    names = list(bars)
    ax.barh(names[::-1], [bars[n] for n in names][::-1],
            color=["#c0392b" if n == "engine income pick" else "#7f8c8d" if n.startswith("oracle") else "#2e86c1" for n in names][::-1])
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("realized 2nd-crop margin, soybean bags/ha/yr (no bonus)")
    ax.set_title(f"Oeste PR, {per_strategy['year'].min()}–{per_strategy['year'].max()}, {len(per_strategy)} municipality-years",
                 fontsize=9)
    ax = axes[1]
    by = r["by_year"]
    ax.bar(by.index, by["failure"], color="#c0392b", alpha=0.6, label="share of municipalities with corn failure")
    ax.plot(by.index, by["frost"], "o-", color="#2e86c1", label="share with frost flag (POWER)")
    ax.plot(by.index, by["dry"], "s--", color="#e67e22", label="share with dry-spell flag (POWER)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Off-season corn: realized failures vs engine climate flags", fontsize=9)
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)
    print(f"\nfigure: {FIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
