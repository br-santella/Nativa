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

Only the Rotation strategies page (`/#rotation`, `src/RotationStrategies.tsx`) talks to the engine API (`motor_field_shift`, contract in `motor_field_shift/api/README.md`). Every other screen still uses the demo data in `src/data.ts`.

The API address is `VITE_API_URL` (default `http://localhost:8000`), baked in at build time; it is the URL the browser uses (production value: `motor_field_shift/deploy/README.md`).

Flow (`src/api.ts`): `GET /health`, then, if the status is `ok`, `POST /v1/recomendacao`. After the setup wizard (`/#demo`, `src/PropertyWizard.tsx`), the body is the wizard's answers (area, current rotation, stage or harvest, reference date, sowing date, known issues, soil analysis, prices, buyers, equipment, irrigation, number of alternatives) with the weights of the page. Without the wizard, the page builds it from the farm data:

| Field | Source in the app |
|---|---|
| `area` | `{lat, lon}` from My Property (any point in Paraná); demo plot `{talhao_id: "72638"}` if the coordinates are invalid |
| `rotacao_atual` | derived from the crop history (`src/rotacaoAtual.ts`); default `soja__milho_safrinha` |
| `colheita_prevista` | harvest date (dd/mm) of the summer crop still in the field, when it is in the future; otherwise the engine uses the catalog assumption and says so in `avisos` |
| `pesos` | the five weights (0–10) of the page, starting from the wizard profile; balanced profile (all 5) without the wizard |
| `irrigacao` | "Disponibilidade de irrigação": Sim → `{disponivel: true}`, Não → `{disponivel: false}`, Não informado → omitted |

Every call sends `?lang=pt-BR|en` following the app language switcher, so the engine texts (rotation names, cards, warnings, errors) come back in the same language as the interface; switching the language fetches again.

The page has three sections: the priorities (the four profiles of the wizard plus the five weights; a change re-runs the engine after 0.6 s), the alternatives of the `agora` block (same summer crop, as many as `n_alternativas`) as cards in a grid (up to 4 in one row, 5 or 6 in two rows), compared with the current rotation, where each criterion is shown as a phrase by score band (`src/priorities.ts`) with an arrow against the current rotation, and an approximate 12-month calendar built from the engine's harvest and sowing dates plus typical cycle lengths (`src/rotationCalendar.ts`, display only), and a comparison in three columns: the current rotation card, the gains and losses of switching (overall score, each criterion, second-crop income, yearly margin, the card's `por_que`), and the card of the chosen alternative, with previous/next to switch alternatives. It also shows the estimated harvest, the second-window sowing date the engine used and the engine `avisos`.

Not sent: the soil fields of My Property (the soil analysis is sent only from the wizard). Endpoints not used: `/v1/opcoes`, `/v1/diagnostico`, `/v1/clima`, `/v1/contexto`.

Sign-up, the contact form and the soil report upload are still demo-only (no account, message or upload).

Reference design: https://www.figma.com/design/NnT2Qj3CEQCMaquaWkEKUi/Untitled?node-id=0-1


### Interactive property map

The overview map defaults to Esri World Imagery. NASA GIBS overlays are available for daily average precipitation rate (IMERG, mm/h), daytime land surface temperature (MODIS; not air temperature), rolling 8-day NDVI, and surface soil moisture (SMAP). The layer selector includes an observation date and opacity control; the initial observation date is seven days before the current date to accommodate product processing delays. Imagery is not live, and thematic layers show observations rather than forecasts. Coverage can be missing because of clouds, unavailable observations or gaps in a product's archive.

NASA layers use their published Web Mercator native zoom levels (6–9) and automatically open at a regional scale. Zoom is capped at the selected layer’s native resolution, including keyboard, touch and wheel interaction. The zoom-in button is disabled at that limit; satellite zoom is additionally checked against Esri’s tile coverage for the visible area. Higher zoom is held until that check completes, and the map zooms back if the new area lacks imagery. Requests use `blankTile=false` so missing imagery is not rendered as the provider’s grey placeholder. Dates, official color legends and provider attribution remain visible. The selected layer/date/opacity are preserved when opening the enlarged map. No additional API key is required for these configured public endpoints.

Sources: [NASA GIBS access documentation](https://nasa-gibs.github.io/gibs-api-docs/access-basics/), [NASA layer catalog](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml), [Esri World Imagery](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer).
