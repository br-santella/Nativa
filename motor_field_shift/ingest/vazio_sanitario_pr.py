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
MUNICIPIOS = ROOT / "data/raw/regiao/municipios_pr.geojson"
SAIDA = ROOT / "data/ref/vazio_sanitario_pr.json"
SAFRA = "2026/2027"
PORTARIA = "Portaria SDA/MAPA nº 1.579, de 9 de abril de 2026"
URL_PORTARIA = "https://www.abrasem.com.br/wp-content/uploads/2025/10/Portaria-SDA-n-1.579-DE-9-DE-ABRIL-DE-2026-Estabelece-os-periodos-de-vazio-sanitario-e-de-calendario-de-semeadura-de-soja-em-nivel-nacional.pdf"
URL_ADAPAR = "https://www.adapar.pr.gov.br/Noticia/Periodos-do-vazio-sanitario-da-Soja-para-safra-de-20262027-comecam-em-junho"
# footnote number in the annex -> region; dates "dd/mm" (the sowing window may cross the new year)
REGIOES = {
    "11": dict(regiao=1, nome="Região 1 (Sul, Leste, Campos Gerais e Litoral)", vazio=("21/06", "19/09"), semeadura=("20/09", "20/01")),
    "12": dict(regiao=2, nome="Região 2 (Norte, Noroeste, Centro-Oeste e Oeste)", vazio=("02/06", "31/08"), semeadura=("01/09", "31/12")),
    "13": dict(regiao=3, nome="Região 3 (Sudoeste)", vazio=("12/06", "10/09"), semeadura=("11/09", "10/01")),
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
    listas = parse_lists(text)
    mun = gpd.read_file(MUNICIPIOS)
    by_name = {norm(r.nome): int(r.cod_ibge) for r in mun.itertuples()}
    regioes, atribuido = [], {}
    for nota, info in REGIOES.items():
        nomes = listas[nota]
        faltando = [n for n in nomes if norm(n) not in by_name]
        if faltando:
            raise SystemExit(f"municípios da portaria sem correspondência no IBGE (região {info['regiao']}): {faltando}")
        codigos = sorted(by_name[norm(n)] for n in nomes)
        for c in codigos:
            if c in atribuido:
                raise SystemExit(f"município {c} aparece em duas regiões")
            atribuido[c] = info["regiao"]
        regioes.append(dict(info, municipios=codigos, n_municipios=len(codigos)))
    sem_regiao = sorted(set(by_name.values()) - set(atribuido))
    if sem_regiao:
        raise SystemExit(f"municípios do IBGE fora das 3 listas da portaria: {sem_regiao}")
    ref = dict(consulta=str(date.today()), safra=SAFRA, portaria=PORTARIA, url_portaria=URL_PORTARIA, url_adapar=URL_ADAPAR,
               observacao="datas conferidas na página da ADAPAR (o quadro de datas da portaria é imagem no PDF); listas de municípios "
                          "lidas do anexo da portaria. Muda a cada safra: atualizar todo ano em abril.",
               regioes=regioes)
    SAIDA.write_text(json.dumps(ref, ensure_ascii=False, indent=1))
    print("gravado", SAIDA, {r["regiao"]: r["n_municipios"] for r in regioes}, "total", len(atribuido))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    main(ap.parse_args().pdf)
