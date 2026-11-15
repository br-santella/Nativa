"""Build the ZARC lookup table used by the engine (field_shift.zarc).

    uv run python ingest/zarc_pr.py

Downloads the ZARC 2025/2026 risk table (~220 MB CSV, open data, MAPA) to data/raw/zarc/ if missing, keeps the Paraná rows
(data/raw/zarc/tabua_2025_2026_pr.parquet) and writes the compact table data/processed/zarc/zarc_pr.parquet.
"""
import urllib.request

import pandas as pd

from field_shift import zarc as Z


def main() -> None:
    if not Z.RAW_PR.exists():
        Z.RAW_DIR.mkdir(parents=True, exist_ok=True)
        if not Z.RAW_CSV.exists():
            req = urllib.request.Request(Z.URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=1200) as r, open(Z.RAW_CSV, "wb") as f:
                f.write(r.read())
        Z.extract_pr()
    t = Z.build_table(pd.read_parquet(Z.RAW_PR))
    Z.TABLE.parent.mkdir(parents=True, exist_ok=True)
    t.to_parquet(Z.TABLE)
    print(f"{Z.TABLE}: {len(t)} rows, {t['geocodigo'].nunique()} municipalities, crops: {sorted(t['crop'].unique())}")


if __name__ == "__main__":
    main()
