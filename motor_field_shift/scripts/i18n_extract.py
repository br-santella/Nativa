"""Extract the user-facing Portuguese text templates of the engine/API into src/field_shift/i18n/en.json.

    uv run python scripts/i18n_extract.py          # add new templates (English = null), report obsolete ones
    uv run python scripts/i18n_extract.py --prune  # also drop templates no longer found in the code/data

A template is a Portuguese string literal or f-string of the API code path, with every `{expression}` replaced by a
positional placeholder `{0}`, `{1}`... (the value is translated recursively at runtime). Data texts (data/ref JSON,
catalog/vocabulario.yaml, catalog/crops.yaml) are extracted too. tests/test_i18n.py fails when a template has no English translation.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src/field_shift/i18n/en.json"
CODE = [ROOT / "src/field_shift", ROOT / "api/field_shift_api"]
SKIP = {"app/mvp.py", "income/update.py", "i18n/__init__.py"}  # Streamlit UI, data producer, the translator itself
SKIP_DIRS = {"validation", "ftw", "mapbiomas", "fields"}  # offline analysis scripts, not on the API path
DATA = [ROOT / "data/ref/precos_custos.json", ROOT / "data/ref/vazio_sanitario_pr.json", ROOT.parent / "catalog/vocabulario.yaml",
        ROOT.parent / "catalog/crops.yaml"]
PT = re.compile(r"[ãõçáéíóúâêôàÁÉÍÓÚÃÕÇ]|\b(de|da|do|das|dos|para|com|sem|não|que|em|por|uma|um|se|ou|no|na|é|ao|aos|mais|já|só|cada|"
                r"soja|milho|trigo|aveia|sorgo|feijão|pousio|safrinha|verão|nota|renda|solo|água|pragas|risco|colheita|semeadura|"
                r"estimativa|validar|fonte|ano|anos|dias|safra|região|média|cultura|janela|informado|informada|informados|ressalva|calagem|"
                r"pelo|pela|produtor|custo|extra|economia|contra|lugar|área|preço|nota|classes|fertilidade|adubação|cobertura|nabo|"
                r"forrageiro|braquiária|milheto|crotalária|alto|baixo|médio|indicado|venda|sem|rotação|atual|melhor|pior)\b", re.I)


def _skip(f: Path) -> bool:
    rel = f.relative_to(ROOT / "src/field_shift").as_posix() if (ROOT / "src/field_shift") in f.parents else ""
    return rel in SKIP or (rel.split("/")[0] in SKIP_DIRS)


def template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value
    elif isinstance(node, ast.JoinedStr):
        parts, i = [], 0
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(v.value.replace("{", "{{").replace("}", "}}"))
            else:
                parts.append("{%d}" % i)
                i += 1
        s = "".join(parts)
    else:
        return None
    literal = re.sub(r"\{\d+\}", "", s)
    if not PT.search(literal) or not re.search(r"[A-Za-zÀ-ú]{3}", literal):
        return None
    return s


def from_code() -> dict[str, str]:
    out = {}
    for base in CODE:
        for f in sorted(base.rglob("*.py")):
            if _skip(f):
                continue
            tree = ast.parse(f.read_text(encoding="utf-8"))
            skip = set()
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
                        and isinstance(n.body[0], ast.Expr):
                    skip.add(id(n.body[0].value))  # docstrings
                if isinstance(n, ast.JoinedStr):
                    skip.update(id(v) for v in n.values)
                if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in {"info", "warning", "error", "exception", "debug"}:
                    skip.update(id(a) for a in n.args)  # log messages
                if isinstance(n, ast.Call):  # OpenAPI texts (Field/route descriptions): the schema stays in Portuguese
                    skip.update(id(k.value) for k in n.keywords if k.arg in {"description", "summary"})
            for n in ast.walk(tree):
                # Msg("template", *values): the template is always a catalog key, even without Portuguese words
                if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "Msg" and n.args \
                        and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    out.setdefault(n.args[0].value, f"{f.relative_to(ROOT).as_posix()}:{n.lineno}")
                    skip.add(id(n.args[0]))
                if id(n) in skip:
                    continue
                t = template(n)
                if t:
                    out.setdefault(t, f"{f.relative_to(ROOT).as_posix()}:{n.lineno}")
    return out


def from_data() -> dict[str, str]:
    out = {}

    def walk(o, src):
        if isinstance(o, dict):
            for v in o.values():
                walk(v, src)
        elif isinstance(o, list):
            for v in o:
                walk(v, src)
        elif isinstance(o, str) and " " in o.strip() and re.search(r"[A-Za-zÀ-ú]{2}", o) and not o.startswith("http"):
            out.setdefault(o.replace("{", "{{").replace("}", "}}"), src)

    for f in DATA:
        if f.exists():
            walk(json.loads(f.read_text()) if f.suffix == ".json" else yaml.safe_load(f.read_text()), f.name)
    return out


# Words chosen inside f-string expressions ({'melhora' if wins else 'piora'}): too short for the Portuguese heuristic.
EXTRA = ["melhora", "piora", "atende melhor", "atende pior", "quebra melhor", "quebra menos", "reduz", "aumenta",
         "alto", "médio", "medio", "baixo", "favorece", "penaliza", "neutro", "indicado", "nematoide", "mofo-branco",
         # crop slugs shown with '_' -> ' ' (c['segunda'].replace('_', ' '))
         "milho verao", "aveia nabo", "milho safrinha", "milho braquiaria", "milheto crotalaria", "nabo forrageiro",
         "feijao safrinha", "soja safrinha",
         # pieces joined with ", " ("soja 50 sc/ha, trigo 36 sc/ha")
         "{0} {1} sc/ha",
         # fertility classes ("P baixo", "K muito alto") and short soybean-free-period region names
         "muito baixo", "muito alto", *[f"{n} {c}" for n in ("P", "K", "V", "AL")
           for c in ("muito baixo", "baixo", "medio", "alto", "muito alto")],
         "P {0} ({1} kg P2O5/ha)", "K {0} ({1} kg K2O/ha)", "V% {0} derivada de (Ca+Mg+K)/CTC",
         "Região 1", "Região 2", "Região 3",
         # one-word crop names of catalog/crops.yaml (data strings need a space to be extracted)
         "Cevada", "Aveia-branca"]


def extract() -> dict[str, str]:
    return {**from_data(), **from_code(), **{w: "EXTRA" for w in EXTRA}}


def main() -> None:
    found = extract()
    cat = json.loads(CATALOG.read_text()) if CATALOG.exists() else {}
    new = [t for t in found if t not in cat]
    obsolete = [t for t in cat if t not in found]
    for t in new:
        cat[t] = None
    if "--prune" in sys.argv:
        for t in obsolete:
            del cat[t]
    CATALOG.write_text(json.dumps(dict(sorted(cat.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    missing = sum(v is None for v in cat.values())
    print(f"{len(found)} templates; {len(new)} new; {len(obsolete)} obsolete{' (pruned)' if '--prune' in sys.argv else ''}; "
          f"{missing} without English")


if __name__ == "__main__":
    main()
