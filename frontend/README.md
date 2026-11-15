# NATIVA

Functional interface based on the NATIVA Figma design, for the AgroNautas / NASA Space Apps Challenge 2026 project.

## Run

Requires Node.js 20.19+ or 22.12+.

```bash
npm ci
npm run dev
```

Open the address printed by Vite. To build the static version:

```bash
npm run build
npm run preview
```

To open the built version, serve the `dist/` folder with an HTTP server. Do not open `index.html` through `file://`.

## Screens

- `/#landing`: landing page, carousel, technology and demo contact form.
- `/#signup` and `/#onboard`: two-step demo sign-up.
- `/#overview`: illustrative map, indicators, charts and expandable calendar.
- `/#farm`: property, soil and irrigation form, and local selection of a soil report.
- `/#history`: calendar and crop registration with date validation.
- `/#climate`: demo series with year selection.
- `/#rotation`: three scenarios, priority controls, comparison and details.
- `/#settings`: preferences and data references.

## Structure

- `src/main.tsx`: React application, navigation and interactions.
- `src/styles.css`: visual tokens and responsive layout in plain CSS.
- `src/data.ts`: demo data, scenarios and scoring formula.
- `src/assets.json`: references to the local images and vectors exported from Figma.
- `public/assets/`: original image and SVG files from the design.

There is no dependency on Tailwind or on paid export services.

## Features

Navigation between screens; forms with validation; property editing; crop registration; period and year filters; calendar expansion; map zoom and layer selection; modals; carousel; weighted scenario comparison; mobile menu; transitions that respect reduced motion.

Changes are kept in session memory. Reloading the page restores the example. Sign-up does not create real accounts, the contact form does not send messages and the selected soil report is not uploaded or interpreted.

## Data and backend

Only the "Compare os cenários" section of `/#rotation` (`src/EngineScenarios.tsx`) talks to the engine API (`motor_field_shift`, contract in `motor_field_shift/api/README.md`). Every other screen still uses the demo data in `src/data.ts`.

The API address is `VITE_API_URL` (default `http://localhost:8000`), baked in at build time; it is the URL the browser uses (production value: `motor_field_shift/deploy/README.md`).

Flow (`src/api.ts`): `GET /health`, then, if the status is `ok`, `POST /v1/recomendacao` with:

| Field | Source in the app |
|---|---|
| `area` | `{lat, lon}` from My Property (any point in Paraná); demo plot `{talhao_id: "72638"}` if the coordinates are invalid |
| `rotacao_atual` | derived from the crop history (`src/rotacaoAtual.ts`); default `soja__milho_safrinha` |
| `colheita_prevista` | harvest date (dd/mm) of the summer crop still in the field, when it is in the future; otherwise the engine uses the catalog assumption and says so in `avisos` |
| `pesos` | the four sliders (0–100) divided by 10; `pragas` fixed at 3 |
| `irrigacao` | "Disponibilidade de irrigação": Sim → `{disponivel: true}`, Não → `{disponivel: false}`, Não informado → omitted |

Every call sends `?lang=pt-BR|en` following the app language switcher, so the engine texts (rotation names, cards, warnings, errors) come back in the same language as the interface; switching the language fetches again.

The screen shows the current rotation and the two best alternatives of the `agora` block (same summer crop), the best option of the `proxima_safra` block (another summer crop), the 2nd-window sowing date the engine used, and the engine `avisos`.

Not sent yet: the soil fields of My Property (the engine's `analise_solo` needs clay + sand, AWC or a fertility field, which the form does not collect), `problemas_area`, `restricoes` and `ajustes`. Endpoints not used yet: `/v1/opcoes`, `/v1/diagnostico`, `/v1/clima`, `/v1/contexto`.

Sign-up, the contact form and the soil report upload are still demo-only (no account, message or upload).

Reference design: https://www.figma.com/design/NnT2Qj3CEQCMaquaWkEKUi/Untitled?node-id=0-1


### Interactive property map

The overview map defaults to Esri World Imagery. NASA GIBS overlays are available for daily average precipitation rate (IMERG, mm/h), daytime land surface temperature (MODIS; not air temperature), rolling 8-day NDVI, and surface soil moisture (SMAP). The layer selector includes an observation date and opacity control; the initial observation date is seven days before the current date to accommodate product processing delays. Imagery is not live, and thematic layers show observations rather than forecasts. Coverage can be missing because of clouds, unavailable observations or gaps in a product's archive.

NASA layers use their published Web Mercator native zoom levels (6–9) and automatically open at a regional scale. Zoom is capped at the selected layer’s native resolution, including keyboard, touch and wheel interaction. The zoom-in button is disabled at that limit; satellite zoom is additionally checked against Esri’s tile coverage for the visible area. Higher zoom is held until that check completes, and the map zooms back if the new area lacks imagery. Requests use `blankTile=false` so missing imagery is not rendered as the provider’s grey placeholder. Dates, official color legends and provider attribution remain visible. The selected layer/date/opacity are preserved when opening the enlarged map. No additional API key is required for these configured public endpoints.

Sources: [NASA GIBS access documentation](https://nasa-gibs.github.io/gibs-api-docs/access-basics/), [NASA layer catalog](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml), [Esri World Imagery](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer).
