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

The frontend does not connect to a backend. There is no real authentication, database, AI agent or live connection to NASA. All indicators and scenarios are labeled as demo data, as in the Figma design.

The demo score is:

```
score = round(sum(criterion_score × weight) / sum(weights))
```

Criteria: water, soil, profitability and resilience. The default profile produces 59 / 84 / 81. Water and climate produces 57 / 83 / 86. Profitability produces 82 / 74 / 65. All-zero weights are rejected by the interface. The scores are not a validated agronomic model.

Reference design: https://www.figma.com/design/NnT2Qj3CEQCMaquaWkEKUi/Untitled?node-id=0-1
