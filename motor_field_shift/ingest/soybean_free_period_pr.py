"""Builds data/ref/vazio_sanitario_pr.json: the soybean sanitary void and sowing calendar of Paraná, by ADAPAR region.

Source: Portaria SDA/MAPA nº 1.579, of 9 April 2026 (calendar of the 2026/2027 crop), annex, Paraná rows. The portaria lists the
municipalities of each of the three Paraná regions; the dates of each region are confirmed by ADAPAR's own news page
(https://www.adapar.pr.gov.br/Noticia/Periodos-do-vazio-sanitario-da-Soja-para-safra-de-20262027-comecam-em-junho).

The annex table with the dates is an image in the PDF, so the dates are typed below (checked against the ADAPAR page) and only the
municipality lists are parsed from the PDF text. Footnotes 11, 12 and 13 of the annex are the three Paraná regions.

Usage:  uv run python ingest/vazio_sanitario_pr.py PORTARIA.pdf          (needs `pdftotext`, from poppler)
Update it every crop year: MAPA publishes a new portaria each April.
"""
import argparse
import json
import re
import subprocess
import unicodedata
from datetime import date
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
MUNICIPALITIES = ROOT / "data/raw/regiao/municipios_pr.geojson"
OUTPUT = ROOT / "data/ref/vazio_sanitario_pr.json"
SEASON = "2026/2027"
ORDINANCE = "Portaria SDA/MAPA nº 1.579, de 9 de abril de 2026"
ORDINANCE_URL = "https://www.abrasem.com.br/wp-content/uploads/2025/10/Portaria-SDA-n-1.579-DE-9-DE-ABRIL-DE-2026-Estabelece-os-periodos-de-vazio-sanitario-e-de-calendario-de-semeadura-de-soja-em-nivel-nacional.pdf"
URL_ADAPAR = "https://www.adapar.pr.gov.br/Noticia/Periodos-do-vazio-sanitario-da-Soja-para-safra-de-20262027-comecam-em-junho"
# footnote number in the annex -> region; dates "dd/mm" (the sowing window may cross the new year)
REGIONS = {
    "11": dict(region=1, name="Região 1 (Sul, Leste, Campos Gerais e Litoral)", void=("21/06", "19/09"), sowing=("20/09", "20/01")),
    "12": dict(region=2, name="Região 2 (Norte, Noroeste, Centro-Oeste e Oeste)", void=("02/06", "31/08"), sowing=("01/09", "31/12")),
    "13": dict(region=3, name="Região 3 (Sudoeste)", void=("12/06", "10/09"), sowing=("11/09", "10/01")),
}
FOOTER = re.compile(r"ASSOCIAÇÃO BRASILEIRA DE SEMENTES E MUDAS|SGCV Sul Lote|Fones/Fax")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def parse_lists(text: str) -> dict[str, list[str]]:
    """{footnote: [municipality names]} for the Paraná footnotes (11, 12, 13), cut between 'Adrianópolis' and the next state."""
    start = text.index("11Adrianópolis")
    end = text.index("14Barras")
    lines = [l.strip() for l in text[start:end].splitlines() if l.strip() and not FOOTER.search(l)]
    body = " ".join(lines)
    out = {}
    for m in re.finditer(r"(?<![\wÀ-ú])(1[123])(?=[A-ZÀ-Ú])(.*?)(?=(?<![\wÀ-ú])1[0-9](?=[A-ZÀ-Ú])|$)", body):
        names = m.group(2).strip().rstrip(".")
        names = re.sub(r"\s+e\s+([^,]+)$", r", \1", names)  # "... A, B e C" -> "..., C"
        out[m.group(1)] = [n.strip() for n in names.split(",") if n.strip()]
    return out


def main(pdf: Path) -> None:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    lists = parse_lists(text)
    mun = gpd.read_file(MUNICIPALITIES)
    by_name = {norm(r.nome): int(r.cod_ibge) for r in mun.itertuples()}
    regions, assigned = [], {}
    for score, info in REGIONS.items():
        names = lists[score]
        missing_items = [n for n in names if norm(n) not in by_name]
        if missing_items:
            raise SystemExit(f"ordinance municipalities with no IBGE match (region {info['region']}): {missing_items}")
        codes = sorted(by_name[norm(n)] for n in names)
        for c in codes:
            if c in assigned:
                raise SystemExit(f"municipality {c} appears in two regions")
            assigned[c] = info["region"]
        regions.append(dict(info, municipalities=codes, n_municipalities=len(codes)))
    no_region = sorted(set(by_name.values()) - set(assigned))
    if no_region:
        raise SystemExit(f"IBGE municipalities outside the 3 ordinance lists: {no_region}")
    ref = dict(queried_on=str(date.today()), season=SEASON, ordinance=ORDINANCE, ordinance_url=ORDINANCE_URL, adapar_url=URL_ADAPAR,
               note="datas conferidas na página da ADAPAR (o quadro de datas da portaria é imagem no PDF); listas de municípios "
                          "lidas do anexo da portaria. Muda a cada safra: atualizar todo ano em abril.",
               regions=regions)
    OUTPUT.write_text(json.dumps(ref, ensure_ascii=False, indent=1))
    print("written", OUTPUT, {r["region"]: r["n_municipalities"] for r in regions}, "total", len(assigned))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    main(ap.parse_args().pdf)
