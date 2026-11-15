# Plan: migrate all code to English + bilingual API (pt-BR / en)

Status: **queued** (created 15/11/2026, to run when credits are back).
Tracked in [`pendencias.md`](pendencias.md) → "Code in English + bilingual API".

## Prompt to start the work

> Execute `motor_field_shift/docs/plan_english_migration.md` phase by phase, in this
> session (no subagents). Run the full test suite after every phase and stop if
> anything breaks.

## Goal

1. Every identifier, comment, docstring, log/internal error message, test name and
   module/package name in `motor_field_shift/` (src, api, ingest, scripts, tests) is
   in English.
2. The public API keeps working **byte-for-byte the same in pt-BR by default** (no
   frontend break).
3. The API can answer in English on request.

## Out of scope / kept in Portuguese

- Existing public API field names (`rotacao_atual`, `analise_solo`, `proxima_safra`,
  …) — CLAUDE.md rule. Open decision D1 below.
- Agronomic content shown to the user in pt-BR (catalog, card texts) stays as the
  pt-BR source; English becomes a translation alongside it.
- Data files in `data/raw`, `data/processed` (outside git).

## Open decisions (ask the user at the start, one question)

- **D1 — field names with `lang=en`**: (a) only texts/labels are translated, keys stay
  PT (recommended: one schema, no frontend fork); (b) `lang=en` also renames the keys.
- **D2 — JSON keys in `data/ref/*.json`** (`precos_custos.json`,
  `vazio_sanitario_pr.json`): rename to English together with the loaders
  (recommended, they are internal) or keep.

## Phase 0 — safety net (before touching code)

1. Settle the current branch `fix/pendencias-motor` (uncommitted work exists: ask the
   user whether to commit it first). Create `refactor/english-code` from it.
2. Baseline: `uv run pytest -q` and `uv run ruff check .` → record pass/fail counts
   in this file.
3. **Golden snapshots**: write `tests/golden/` with the JSON responses of every API
   route (`/opcoes`, `/talhoes/demo`, the POST routes with the demo fields and the
   examples in `api/README.md`, `/v1/plano`) produced by the *current* code through
   FastAPI `TestClient`. Add `tests/test_golden_api.py` that compares the live
   response to the snapshot (ignoring only volatile fields such as timestamps).
   This is the "nothing broke" guarantee for the whole migration.

## Phase 1 — rename modules and packages (one commit per package)

Use `git mv` + update imports; run tests after each one.

| Current | New |
|---|---|
| `field_shift/agua/balanco.py` | `field_shift/water/balance.py` |
| `field_shift/clima/indicadores.py`, `lookup.py` | `field_shift/climate/indicators.py`, `lookup.py` |
| `field_shift/contexto/` | `field_shift/context/` |
| `field_shift/solo/solo.py` | `field_shift/soil/soil.py` |
| `field_shift/renda/renda.py` | `field_shift/income/income.py` |
| `field_shift/motor/servico.py` | `field_shift/engine/service.py` (check clash with `app/engine.py`; if so use `field_shift/core/service.py`) |
| `field_shift/talhoes/` | `field_shift/fields/` |
| `field_shift/regiao/` | `field_shift/region/` |
| `field_shift/pam/produtividade.py` | `field_shift/pam/productivity.py` (PAM is an acronym, keep) |
| `field_shift/app/estado_area.py` | `field_shift/app/field_state.py` |
| `field_shift/calendario.py` | `field_shift/calendar.py` → **avoid stdlib clash**: `crop_calendar.py` |
| `api/field_shift_api/rotas.py` | `api/field_shift_api/routes.py` |
| `ingest/zarc_pr.py` etc. | check each name |

Test files follow their modules (`test_servico.py` → `test_service.py`,
`test_estado_area.py` → `test_field_state.py`, `test_rotacoes.py` → `test_rotations.py`).

## Phase 2 — identifiers, comments, docstrings, messages (file by file)

Order: leaves first (water, climate, soil, pam, income, region, fields), then
`app/field_state.py`, `app/engine.py`, `engine/service.py` (1040 lines, split into
several commits), then `api/`, `ingest/`, `scripts/`, tests.

Rules:
- Functions, variables, classes, constants, exceptions
  (`ForaDaRegiao` → `OutOfRegion`, `EntradaInvalida` → `InvalidInput`,
  `ErroConsultaExterna` → `ExternalQueryError`).
- Pydantic models in `schemas.py`: rename the **Python attribute** to English and keep
  the public name with `Field(alias="rotacao_atual")` +
  `model_config = ConfigDict(populate_by_name=True)`, and serialize with
  `by_alias=True`. Golden tests prove the JSON is unchanged.
- User-facing strings (cards, catalog, HTTP error `detail`) are **not** translated in
  place: they move to the i18n catalog in Phase 3, pt-BR text unchanged.
- Enum *values* sent on the wire stay as they are; enum *names* go to English.
- After each file: `uv run pytest -q && uv run ruff check .`.
- Grep check at the end: no Portuguese identifiers left, e.g.
  `rg -n "\b(def|class) \w*(cao|coes|ncia|mento|safra|talhao|solo|renda|agua)\w*" src api ingest scripts tests`.

## Phase 3 — bilingual API (pt-BR default, en optional)

1. Module `field_shift/i18n.py`:
   - `Locale = Literal["pt-BR", "en"]`, `DEFAULT_LOCALE = "pt-BR"`.
   - `t(key, locale, **params)` reading `field_shift/locales/pt_BR.json` and
     `en.json`; missing key in `en` falls back to pt-BR and logs a warning.
   - Catalog/crop labels, card titles/texts, reasons, warnings, error messages.
2. Locale selection in the API (FastAPI dependency `get_locale`):
   query `?lang=pt-BR|en` > header `Accept-Language` > default `pt-BR`.
   Response header `Content-Language`. Unknown values → pt-BR.
3. The engine produces message **keys + params**; text rendering happens at the
   response edge, so the engine stays language-agnostic.
4. Exception handlers in `main.py` translate `detail` too.
5. `/opcoes` returns labels in the requested language.
6. D1 = (b) only: key renaming layer at serialization (`by_alias` per locale).
7. English translations of the agronomic texts: write them, list the ones that need
   a human check in `pendencias.md`.

## Phase 4 — tests

- All existing tests pass (renamed).
- Golden tests pass unchanged for pt-BR (default, `?lang=pt-BR`, no header).
- New golden snapshots for `?lang=en` and `Accept-Language: en-US`.
- `tests/test_i18n.py`: every key in `pt_BR.json` exists in `en.json` and vice versa;
  placeholders match; fallback; locale parsing (`en-US`, `pt`, `xx`, empty).
- Numbers/structure identical between pt-BR and en responses (only text differs).
- `uv run ruff check .`, full `uv run pytest`.
- Restart the API and smoke test with `curl` in both languages.

## Phase 5 — docs

- `README.md`, `api/README.md`, `docs/motor.md`, `docs/arquitetura.md`,
  `docs/entradas.md`: new module paths and the `lang` / `Accept-Language` option.
- Regenerate API examples.
- Update `pendencias.md` and this file's status.

## Results log

(fill in during execution: baseline counts, commits, final counts)
