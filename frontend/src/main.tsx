import React, {
  useState,
  useEffect,
  useRef,
  createContext,
  useContext,
} from "react";
import { createRoot } from "react-dom/client";
import { motion, useReducedMotion } from "motion/react";
import assets from "./assets.json";
import {
  months,
  initialFarm,
  initialCrops,
  series,
  scenarios,
  profiles,
  score,
  info,
} from "./data";
import type { Farm, Crop } from "./data";
import "./styles.css";

const A = assets.overview,
  L = assets["13:16"];
const path = (file: string) => "/assets/" + file;
type Page =
  | "landing"
  | "signup"
  | "onboard"
  | "overview"
  | "farm"
  | "history"
  | "climate"
  | "rotation"
  | "settings";
type Modal =
  | null
  | "sources"
  | "indicators"
  | "help"
  | "technology"
  | "addCrop"
  | "account"
  | "property"
  | "login"
  | "contact"
  | "map"
  | number;
const pages: Page[] = [
  "landing",
  "signup",
  "onboard",
  "overview",
  "farm",
  "history",
  "climate",
  "rotation",
  "settings",
];
function currentPage(): Page {
  const p = location.hash.slice(1) as Page;
  return pages.includes(p) ? p : "landing";
}

const DraftContext = createContext<{
  draft: Farm;
  setDraft: React.Dispatch<React.SetStateAction<Farm>>;
}>({ draft: initialFarm, setDraft: () => {} });
function Field({
  label,
  name,
  type = "text",
  options,
  min,
  max,
  step,
}: {
  label: string;
  name: keyof Farm;
  type?: string;
  options?: string[];
  min?: number;
  max?: number;
  step?: string;
}) {
  const { draft, setDraft } = useContext(DraftContext);
  return (
    <label className="field">
      <span>{label}</span>
      {options ? (
        <select
          value={draft[name]}
          onChange={(e) => setDraft((v) => ({ ...v, [name]: e.target.value }))}
        >
          {options.map((o) => (
            <option key={o}>{o}</option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          value={draft[name]}
          onChange={(e) => setDraft((v) => ({ ...v, [name]: e.target.value }))}
          min={min}
          max={max}
          step={step}
          required={name === "name" || name === "area"}
        />
      )}
    </label>
  );
}
function App() {
  const [page, setPage] = useState<Page>(currentPage),
    [modal, setModal] = useState<Modal>(null),
    [farm, setFarm] = useState<Farm>({ ...initialFarm }),
    [draft, setDraft] = useState<Farm>({ ...initialFarm }),
    [crops, setCrops] = useState<Crop[]>(initialCrops),
    [year, setYear] = useState("2025"),
    [period, setPeriod] = useState("12"),
    [layer, setLayer] = useState("Vegetation (NDVI)"),
    [zoom, setZoom] = useState(1),
    [menu, setMenu] = useState(false),
    [notice, setNotice] = useState(""),
    [weights, setWeights] = useState<number[]>(profiles.soil),
    [applied, setApplied] = useState<number[]>(profiles.soil),
    [busy, setBusy] = useState(false),
    [slide, setSlide] = useState(0),
    [report, setReport] = useState<File | null>(null),
    [calendar, setCalendar] = useState(false),
    [explain, setExplain] = useState(false),
    [userName, setUserName] = useState("Marina Silva"),
    [settings, setSettings] = useState({
      temperature: "Degrees Celsius (°C)",
      language: "English",
    });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const h = () => {
      setPage(currentPage());
      setMenu(false);
      setModal(null);
      window.scrollTo(0, 0);
    };
    addEventListener("hashchange", h);
    return () => removeEventListener("hashchange", h);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  function go(p: Page) {
    location.hash = p;
    if (page === p) {
      setMenu(false);
      setModal(null);
      window.scrollTo(0, 0);
    }
  }
  function toast(s: string) {
    setNotice(s);
  }
  function saveFarm(e: React.FormEvent) {
    e.preventDefault();
    setFarm({ ...draft });
    toast("Changes applied for this session.");
  }
  function compare() {
    if (!weights.some(Boolean)) {
      toast("Set at least one priority above zero.");
      return;
    }
    setBusy(true);
    timer.current = setTimeout(() => {
      setApplied([...weights]);
      setBusy(false);
      toast("Demo comparison updated.");
    }, 600);
  }
  const chosen = scenarios.map((s) => score(s.notes, applied));
  const winner = chosen.indexOf(Math.max(...chosen));
  const navItems: [Page, string, string][] = [
    ["overview", "Overview", A.imgIconeDeNavegacao],
    ["farm", "My Property", A.imgIconeDeNavegacao1],
    ["climate", "Climate Analysis", A.imgIconeDeNavegacao3],
    ["history", "Crop History", A.imgIconeDeNavegacao2],
    ["rotation", "Rotation Strategies", A.imgIconeDeNavegacao4],
  ];
  const open = (m: Modal) => setModal(m);
  function Logo() {
    return (
      <button
        className="brand"
        onClick={() => go("landing")}
        aria-label="NATIVA — home"
      >
        <img src={A.imgLogoNativaEnviada} alt="" />
        <strong>NATIVA</strong>
      </button>
    );
  }
  function Demo() {
    return (
      <p className="demo">
        DEMO DATA{" "}
        <span>
          • Fictitious property. Illustrative values, not real measurements
          or validated recommendations.
        </span>
      </p>
    );
  }
  function Btn({
    children,
    onClick,
    secondary = false,
    type = "button",
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    secondary?: boolean;
    type?: "button" | "submit";
  }) {
    return (
      <button
        type={type}
        className={secondary ? "button secondary" : "button"}
        onClick={onClick}
      >
        {children}
      </button>
    );
  }
  function LinkButton({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick: () => void;
  }) {
    return (
      <button className="text-link" onClick={onClick}>
        {children}
      </button>
    );
  }
  function Chart({
    kind = "temperature",
    large = false,
  }: {
    kind?: keyof typeof series;
    large?: boolean;
  }) {
    const vals = series[kind]
      .slice(period === "6" ? 6 : 0)
      .map((x) =>
        year === "2024" ? x * 0.93 : year === "2023" ? x * 1.04 : x,
      );
    const color = {
      temperature: "#efae38",
      rain: "#8ebdc6",
      moisture: "#a8c9a3",
      ndvi: "#8ca53b",
    }[kind];
    const max = { temperature: 35, rain: 300, moisture: 60, ndvi: 1 }[kind];
    const minimum = kind === "temperature" ? 15 : 0;
    const plotY = (v: number) => 125 - ((v - minimum) / (max - minimum)) * 110;
    const positions = vals
      .map((v, i) => `${(i / (vals.length - 1)) * 300},${plotY(v)}`)
      .join(" ");
    return (
      <div className={"chart " + (large ? "chart-large" : "")}>
        <svg
          viewBox="0 0 350 174"
          role="img"
          aria-label={`${kind === "rain" ? "Precipitation" : kind === "temperature" ? "Temperature" : kind === "moisture" ? "Soil moisture" : "NDVI"} — demo values for ${year}`}
        >
          <g transform="translate(34 8)">
            {[15, 70, 125].map((y, i) => (
              <g key={y}>
                <line x1="0" x2="306" y1={y} y2={y} stroke="#28464b" />
                <text x="-12" y={y + 3} textAnchor="end">
                  {kind === "temperature"
                    ? [35, 25, 15][i]
                    : i === 2
                      ? "0"
                      : (max * (1 - i * 0.5)).toLocaleString("en-US")}
                </text>
              </g>
            ))}
            {kind === "rain" ? (
              vals.map((v, i) => (
                <rect
                  key={i}
                  x={(i * 300) / vals.length + 2}
                  y={plotY(v)}
                  width={vals.length === 6 ? 13 : 9}
                  height={(v / max) * 110}
                  rx="3"
                  fill={color}
                >
                  <title>
                    {months[(period === "6" ? 6 : 0) + i]}: {v.toFixed(0)} mm
                  </title>
                </rect>
              ))
            ) : period === "12" &&
              year === "2025" &&
              !large &&
              kind !== "ndvi" ? (
              <image
                href={
                  kind === "temperature"
                    ? A.imgCurvaDeTemperatura
                    : A.imgCurvaDeUmidadeDoSolo
                }
                x="0"
                y={kind === "temperature" ? 55 : 54}
                width="306"
                height={kind === "temperature" ? 43 : 33}
              />
            ) : (
              <polyline
                points={positions}
                fill="none"
                stroke={color}
                strokeWidth="2.2"
              />
            )}
            {large && (
              <>
                <rect
                  x="275"
                  y="20"
                  width="31"
                  height="100"
                  fill="#9aadb0"
                  opacity=".08"
                />
                <path
                  d={`M 250 ${plotY(vals[vals.length - 1])} L 300 28`}
                  stroke={color}
                  strokeDasharray="3 4"
                  fill="none"
                  opacity=".6"
                />
              </>
            )}
            {(period === "6"
              ? ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
              : ["Jan", "Apr", "Jul", "Oct", "Dec"]
            ).map((m, i, arr) => (
              <text
                key={m}
                x={(i * 300) / (arr.length - 1)}
                y="151"
                textAnchor="middle"
              >
                {m}
              </text>
            ))}
          </g>
        </svg>
        <small>
          ● NASA{" "}
          {kind === "moisture" ? "SMAP" : kind === "ndvi" ? "MODIS" : "POWER"} ·
          fictitious series
        </small>
      </div>
    );
  }
  function Map({ expanded = false }: { expanded?: boolean }) {
    return (
      <div className={"farm-map " + (expanded ? "expanded" : "")}>
        <div className="map-image" style={{ transform: `scale(${zoom})` }}>
          <img
            src={A.imgPlanoGeografico}
            alt="Illustrative aerial view of farm fields"
          />
          <img
            className="field-boundary"
            src={A.imgLimiteFicticio}
            alt="Fictitious property boundary"
          />
        </div>
        <select
          className="map-layer"
          aria-label="Map layer"
          value={layer}
          onChange={(e) => setLayer(e.target.value)}
        >
          {[
            "Vegetation (NDVI)",
            "Soil moisture",
            "Precipitation",
            "Temperature",
          ].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <div className="map-controls">
          <button
            aria-label="Zoom in"
            onClick={() => setZoom((v) => Math.min(2.4, v + 0.2))}
          >
            +
          </button>
          <button
            aria-label="Zoom out"
            onClick={() => setZoom((v) => Math.max(1, v - 0.2))}
          >
            −
          </button>
          <button
            aria-label="Center on the property"
            onClick={() => setZoom(1)}
          >
            ⌖
          </button>
        </div>
        <div className="map-farm">
          <strong>{farm.name}</strong>
          <small>{farm.area} ha • fictitious boundary</small>
        </div>
        <small className="map-disclaimer">
          Illustrative image • fictitious boundaries, not georeferenced
        </small>
        <div className="map-legend">
          <span>
            {layer === "Vegetation (NDVI)"
              ? "NDVI · 0.2–0.9"
              : layer + " · example"}
          </span>
          <div>
            {["#c4ad70", "#c3d58b", "#90b66c", "#4d8153", "#315b3d"].map(
              (c) => (
                <i key={c} style={{ background: c }} />
              ),
            )}
          </div>
        </div>
        <button
          className="map-fullscreen"
          aria-label={expanded ? "Close enlarged map" : "Enlarge map"}
          onClick={() => open(expanded ? null : "map")}
        >
          <img src={A.imgTelaCheia} alt="" />
        </button>
      </div>
    );
  }
  function ClimateSummary() {
    return (
      <section className="panel climate-summary">
        <div className="section-heading">
          <div>
            <h2>How is the climate changing?</h2>
            <p>
              Jan–Dec {year} · month-to-month comparison · demo values
            </p>
          </div>
          <select
            aria-label="Chart period"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="12">Last 12 months</option>
            <option value="6">Last 6 months</option>
          </select>
        </div>
        <div className="charts-three">
          {(["temperature", "rain", "moisture"] as const).map((kind, i) => (
            <div key={kind}>
              <div className="chart-title">
                <strong>
                  {["Temperature", "Precipitation", "Soil moisture"][i]}
                </strong>
                <small>{["°C", "mm/month", "%"][i]}</small>
              </div>
              <Chart kind={kind} />
            </div>
          ))}
        </div>
      </section>
    );
  }
  function MetricCards() {
    return (
      <div className="metrics">
        {[
          [
            "Mean temperature",
            settings.temperature.startsWith("Degrees Fahrenheit")
              ? "76.6"
              : "24.8",
            settings.temperature.startsWith("Degrees Fahrenheit") ? "°F" : "°C",
            "↗ +1.2 °C vs history",
            "POWER",
          ],
          [
            "Accumulated precipitation",
            "142",
            "mm",
            "↘ −18% vs history",
            "POWER",
          ],
          ["Soil moisture", "32", "%", "↗ +4 p.p. this month", "SMAP"],
          ["Vegetation index", "0.76", "NDVI", "↗ +0.08 this month", "MODIS"],
        ].map((m, i) => (
          <button
            className="metric panel"
            key={m[0]}
            onClick={() => open("indicators")}
          >
            <span className="metric-title">{m[0]}</span>
            <div className="metric-value">
              <motion.strong
                data-node-id={["3:330", "3:336", "3:342", "3:348"][i]}
                initial={reduced ? false : { opacity: 0.8, y: 3 }}
                animate={
                  reduced
                    ? { opacity: 1, y: 0 }
                    : { opacity: [0.8, 1, 1], y: [3, 0, 0] }
                }
                transition={{
                  duration: 2,
                  times: [0, 0.325, 1],
                  ease: ["easeOut", "linear"],
                  repeat: Infinity,
                }}
              >
                {m[1]}
              </motion.strong>
              <small>{m[2]}</small>
            </div>
            <span className={"delta " + (i < 2 ? "warm" : "")}>{m[3]}</span>
            <small className="metric-source">NASA {m[4]} • example</small>
            {i === 0 ? (
              <img
                className="metric-spark"
                src={A.imgMinigraficoDeTemperatura}
                alt=""
              />
            ) : i === 1 ? (
              <div className="mini-bars">
                {[14, 24, 18, 35, 27, 42, 33].map((v, n) => (
                  <i key={n} style={{ height: v }} />
                ))}
              </div>
            ) : i === 2 ? (
              <div className="metric-ring">
                <img src={A.imgUmidadeCircular} alt="" />
                <img src={A.img32DeUmidade} alt="" />
              </div>
            ) : (
              <div className="ndvi-bars">
                {Array.from({ length: 9 }, (_, n) => (
                  <i key={n} style={{ opacity: n > 6 ? 0.25 : 1 }} />
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
    );
  }
  function Overview() {
    return (
      <>
        <div className="page-heading overview-heading">
          <div>
            <h1>Your property, a new perspective.</h1>
            <p>
              Explore your farm with NASA data and discover opportunities
              for your next seasons.
            </p>
          </div>
          <Btn onClick={() => go("rotation")}>＋ New Analysis</Btn>
        </div>
        <Demo />
        <div className="overview-map">
          <Map />
          <aside className="farm-context">
            <h2>{farm.name}</h2>
            <p>
              {farm.city} · {farm.country}
            </p>
            <small>
              {farm.latitude} / {farm.longitude} • fictitious coordinates
            </small>
            <div className="current-context">
              <small>CURRENT CROP</small>
              <strong>{farm.crop}</strong>
              <span>Field 01 · {farm.area} ha</span>
            </div>
            <hr />
            <h3>A fresh look at the next cycle.</h3>
            <LinkButton onClick={() => go("farm")}>
              See my property →
            </LinkButton>
            <LinkButton onClick={() => open("sources")}>
              Sources and limitations →
            </LinkButton>
          </aside>
        </div>
        <MetricCards />
        <button
          className="disclosure"
          aria-expanded={explain}
          onClick={() => setExplain(!explain)}
        >
          Understand the indicators <span>{explain ? "−" : "⌄"}</span>
        </button>
        {explain && (
          <div className="panel inline-info">
            {info.indicators.items.map(([t, d]) => (
              <div key={t}>
                <h3>{t}</h3>
                <p>{d}</p>
              </div>
            ))}
          </div>
        )}
        <section className="plan-banner">
          <div>
            <h2>Plan your next season.</h2>
            <p>
              Compare rotation strategies considering the climate, the soil and
              your property's priorities.
            </p>
            <button className="button lime" onClick={() => go("rotation")}>
              Compare strategies →
            </button>
          </div>
          <div className="banner-art">
            {[A.imgRotation, A.imgFieldRows, A.imgSprout, A.imgWarmAccent].map(
              (src, i) => (
                <img key={src} className={"art-" + i} src={src} alt="" />
              ),
            )}
          </div>
        </section>
        <ClimateSummary />
        <button
          className="disclosure"
          aria-expanded={calendar}
          onClick={() => setCalendar(!calendar)}
        >
          Crop calendar <span>{calendar ? "−" : "⌄"}</span>
        </button>
        {calendar && <Timeline />}
      </>
    );
  }

  function FarmPage() {
    return (
      <form onSubmit={saveFarm}>
        <div className="page-heading">
          <div>
            <h1>My Property</h1>
            <p>The characteristics of your land are the starting point.</p>
          </div>
          <Btn type="submit">Save changes</Btn>
        </div>
        <Demo />
        <div className="two-col">
          <div className="stack">
            <section className="panel">
              <h2>01 Location</h2>
              <p>
                Tell us where you farm. The marked fields are optional.
              </p>
              <div className="fields-grid">
                <Field label="Property name" name="name" />
                <Field
                  label="Country"
                  name="country"
                  options={[
                    "Brazil",
                    "Argentina",
                    "Uruguay",
                    "Paraguay",
                    "Other",
                  ]}
                />
                <div className="fields-grid">
                  <Field
                    label="Latitude"
                    name="latitude"
                    type="number"
                    min={-90}
                    max={90}
                    step="any"
                  />
                  <Field
                    label="Longitude"
                    name="longitude"
                    type="number"
                    min={-180}
                    max={180}
                    step="any"
                  />
                </div>
                <Field
                  label="Property area (ha)"
                  name="area"
                  type="number"
                  min={0.01}
                  step="any"
                />
              </div>
              <div className="location-preview">
                <img
                  src={assets["13:478"].imgLocalizacaoDemonstrativa}
                  alt="Illustrative farm location"
                />
                <span>
                  ⌖ {draft.latitude}, {draft.longitude} • example
                </span>
              </div>
            </section>
            <section className="panel">
              <h2>02 Soil characteristics</h2>
              <div className="fields-grid">
                <Field
                  label="Soil texture"
                  name="texture"
                  options={[
                    "Clayey",
                    "Sandy",
                    "Loam",
                    "Silty",
                    "Not provided",
                  ]}
                />
                <Field
                  label="Soil pH ⓘ"
                  name="ph"
                  type="number"
                  min={0}
                  max={14}
                  step=".1"
                />
                <Field
                  label="Drainage"
                  name="drainage"
                  options={["Moderate", "Good", "Poor", "Not provided"]}
                />
                <Field
                  label="Organic matter (%) • optional"
                  name="organic"
                  type="number"
                  min={0}
                  max={100}
                  step=".1"
                />
              </div>
            </section>
            <section className="panel">
              <h2>03 Water resources</h2>
              <div className="fields-grid">
                <Field
                  label="Irrigation availability"
                  name="irrigation"
                  options={["Yes", "No", "Not provided"]}
                />
                <Field
                  label="Irrigation type"
                  name="irrigationType"
                  options={[
                    "Center pivot",
                    "Drip",
                    "Sprinkler",
                    "Not applicable",
                    "Other",
                  ]}
                />
                <div className="full">
                  <Field
                    label="Water restrictions • optional"
                    name="waterRestriction"
                  />
                </div>
              </div>
            </section>
          </div>
          <aside className="stack">
            <section className="panel">
              <h2>Your land, in context</h2>
              <h3 className="farm-name">{farm.name}</h3>
              <p>
                {farm.city} • {farm.country}
              </p>
              <dl>
                <div>
                  <dt>Total area</dt>
                  <dd>{farm.area} ha</dd>
                </div>
                <div>
                  <dt>Registered fields</dt>
                  <dd>1 field</dd>
                </div>
                <div>
                  <dt>Information filled in</dt>
                  <dd>{Object.values(draft).filter(Boolean).length} fields</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <h3>Why do we ask for this data?</h3>
              <p>
                Soil, water and location help put the rotation scenarios in
                context.
              </p>
              <p>
                You can start with what you know and fill in the optional fields
                later.
              </p>
              <small>ⓘ Changes are kept for this session only.</small>
            </section>
            <section className="panel">
              <h2>Soil analysis</h2>
              <h3>{report ? report.name : "No report attached"}</h3>
              <p>
                If you have a recent report, add it to keep it with the
                registration.
              </p>
              <label className="button upload">
                {report ? "Replace report" : "Add report"}
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setReport(f);
                      toast(
                        "Report selected locally. No file was uploaded.",
                      );
                    }
                  }}
                />
              </label>
              {report && (
                <button
                  className="text-link"
                  type="button"
                  onClick={() => setReport(null)}
                >
                  Remove file
                </button>
              )}
              <small>
                Local file • not uploaded or analyzed automatically.
              </small>
            </section>
          </aside>
        </div>
        <p className="footnote">
          Your data helps explore possibilities; it does not replace a
          local agronomic assessment.
        </p>
      </form>
    );
  }
  function Timeline() {
    return (
      <section className="panel timeline-panel">
        <div className="section-heading">
          <div>
            <h2>A view of each season</h2>
            <p>
              Field 01 • {farm.area} ha • planting, development and harvest
            </p>
          </div>
          <select
            aria-label="Calendar year"
            value={year}
            onChange={(e) => setYear(e.target.value)}
          >
            {["2025", "2024", "2023"].map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="timeline-scroll">
          <div className="timeline">
            <div className="timeline-labels">
              <span />
              {months.map((m) => (
                <span key={m}>{m}</span>
              ))}
            </div>
            <div className="timeline-row">
              <strong>
                Soybean {Number(year) - 1}/{year.slice(2)}
              </strong>
              <div className="timeline-track">
                <span style={{ gridColumn: "1/3" }}>Development</span>
                <span className="harvest" style={{ gridColumn: "3/4" }}>
                  Harvest
                </span>
                <span style={{ gridColumn: "10/11" }}>Planting</span>
                <span style={{ gridColumn: "11/13" }}>
                  Soybean {year}/{String(Number(year) + 1).slice(2)}
                </span>
              </div>
            </div>
            <div className="timeline-row">
              <strong>Off-season corn</strong>
              <div className="timeline-track">
                <span style={{ gridColumn: "3/4" }}>Planting</span>
                <span style={{ gridColumn: "4/7" }}>Development</span>
                <span className="harvest" style={{ gridColumn: "7/8" }}>
                  Harvest
                </span>
                <span className="bare" style={{ gridColumn: "8/10" }}>
                  Bare soil
                </span>
              </div>
            </div>
          </div>
        </div>
        <div className="legend">
          <span>● Planting</span>
          <span>● Development</span>
          <span className="warm">● Harvest</span>
          <span>● Bare soil</span>
        </div>
      </section>
    );
  }
  function History() {
    const fmt = (s: string) =>
      new Date(s + "T12:00:00").toLocaleDateString("en-US");
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Crop History</h1>
            <p>Every season tells part of your land's story.</p>
          </div>
          <Btn onClick={() => open("addCrop")}>＋ Add crop</Btn>
        </div>
        <Demo />
        <div className="grid-two">
          <section className="panel current-crop">
            <small>CURRENT CROP • FIELD 01</small>
            <div>
              <h2>{farm.crop}</h2>
              <span>Growing</span>
            </div>
            <p>Planting: Oct 15, 2025 → Expected harvest: Feb 20, 2026</p>
          </section>
          <section className="panel">
            <h2>Your history in numbers</h2>
            <div className="numbers">
              <div>
                <strong>{crops.length + 2}</strong>
                <small>crops recorded</small>
              </div>
              <div>
                <strong>3</strong>
                <small>years of history</small>
              </div>
              <div>
                <strong>2</strong>
                <small>crops per year</small>
              </div>
            </div>
          </section>
        </div>
        <Timeline />
        <section className="panel">
          <h2>Recorded crops</h2>
          <p>
            Demo values • yield in 60 kg bags
            per hectare
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Crop / season",
                    "Planting",
                    "Harvest",
                    "Area",
                    "Yield",
                    "Status",
                  ].map((t) => (
                    <th key={t}>{t}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {crops.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.crop} • {c.season}
                    </td>
                    <td>{fmt(c.plant)}</td>
                    <td>
                      {fmt(c.harvest)}
                      {c.status !== "Completed" ? "*" : ""}
                    </td>
                    <td>{c.area} ha</td>
                    <td>
                      {c.yield ? c.yield + " bags/ha" : "Not harvested yet"}
                    </td>
                    <td>
                      <span className="status">{c.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <small>
            * Expected date, not observed. Showing {crops.length} of{" "}
            {crops.length + 2} crops.
          </small>
        </section>
        <section className="callout">
          <div>
            <h3>The next cycle starts with what you have already learned.</h3>
            <p>Use your history to explore rotation strategies.</p>
          </div>
          <Btn onClick={() => go("rotation")}>Explore strategies →</Btn>
        </section>
      </>
    );
  }
  function Climate() {
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Climate Analysis</h1>
            <p>From history to planning: understand the climate signals.</p>
          </div>
        </div>
        <Demo />
        <div className="period-bar">
          <span>Analysis period</span>
          <div>
            {["2023", "2024", "2025"].map((y) => (
              <button
                key={y}
                className={year === y ? "active" : ""}
                onClick={() => {
                  setYear(y);
                  setPeriod("12");
                }}
              >
                {y}
              </button>
            ))}
          </div>
          <small>● Illustrative history</small>
          <small className="warm">Illustrative estimate</small>
          <small>Illustrative projection</small>
        </div>
        <div className="grid-two climate-grid">
          {(["temperature", "rain", "moisture", "ndvi"] as const).map(
            (kind, i) => (
              <section className="panel" key={kind}>
                <div className="section-heading">
                  <div>
                    <h2>
                      {
                        [
                          "Mean temperature",
                          "Accumulated precipitation",
                          "Soil moisture ⓘ",
                          "Vegetation vigor ⓘ",
                        ][i]
                      }
                    </h2>
                    <p>
                      NASA {i === 2 ? "SMAP" : i === 3 ? "MODIS" : "POWER"} •
                      example historical series
                    </p>
                  </div>
                  <strong className={"climate-number n" + i}>
                    {
                      [
                        year === "2025"
                          ? "24.8 °C"
                          : year === "2024"
                            ? "23.1 °C"
                            : "25.8 °C",
                        year === "2025"
                          ? "142 mm"
                          : year === "2024"
                            ? "132 mm"
                            : "148 mm",
                        "32%",
                        "0.76",
                      ][i]
                    }
                  </strong>
                </div>
                <Chart kind={kind} large />
                <p>
                  {
                    [
                      "Warmer months can increase water demand.",
                      "Rain is concentrated between October and March in this example.",
                      "Water in the surface layer; it does not represent the whole root zone.",
                      "NDVI indicates vegetation activity, not crop yield.",
                    ][i]
                  }
                </p>
              </section>
            ),
          )}
        </div>
        <div className="two-col">
          <section className="panel">
            <h2>Plan with seasonality</h2>
            <p>Illustrative pattern • not a weather forecast</p>
            <div className="season wet">
              <strong>Oct–Mar</strong>
              <div>
                Wettest period
                <small>Watch drainage and the planting window.</small>
              </div>
            </div>
            <div className="season dry">
              <strong>May–Aug</strong>
              <div>
                Driest period
                <small>Soil cover helps reduce evaporation.</small>
              </div>
            </div>
          </section>
          <section className="panel">
            <h2>Before deciding</h2>
            <h3>History</h3>
            <p>
              Past observations, represented here by fictitious examples.
            </p>
            <h3 className="warm">Estimates and projections</h3>
            <p>
              They are approximations with uncertainty. Dashed lines are not
              observations.
            </p>
          </section>
        </div>
        <section className="callout">
          <div>
            <h3>ⓘ Sources, resolution and limitations of the indicators</h3>
            <p>
              Explore the difference between the satellite scale and the field
              scale.
            </p>
          </div>
          <LinkButton onClick={() => open("sources")}>
            See details →
          </LinkButton>
        </section>
      </>
    );
  }
  function Radar() {
    const R = assets["3:218"];
    return (
      <div
        className="radar-assets"
        role="img"
        aria-label="Illustrative comparison of the four criteria"
      >
        <div className="radar-shapes">
          {[
            R.imgEixoDeComparacao,
            R.imgEixoDeComparacao1,
            R.imgEixoDeComparacao2,
            R.imgEixoDeComparacao3,
            R.imgEixoDeComparacao4,
          ].map((src, i) => (
            <img
              key={src}
              className={"radar-axis axis-" + i}
              src={src}
              alt=""
            />
          ))}
          <img className="radar-current" src={R.imgAreaDoCenario} alt="" />
          <img className="radar-soil" src={R.imgAreaDoCenario1} alt="" />
          <img className="radar-climate" src={R.imgAreaDoCenario2} alt="" />
        </div>
        <span className="radar-water">Water</span>
        <span className="radar-soil-label">Soil</span>
        <span className="radar-profit">Profitability</span>
        <span className="radar-resilience">Resilience</span>
      </div>
    );
  }
  function Rotation() {
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Rotation Strategies</h1>
            <p>
              Compare paths for the next season, with your priorities.
            </p>
          </div>
        </div>
        <Demo />
        <section className="panel priorities">
          <h2>01 What matters most for your next season?</h2>
          <p>
            Adjust the controls or explore the three predefined priority
            profiles.
          </p>
          <div className="sliders">
            {[
              "Water savings",
              "Soil health",
              "Profitability",
              "Climate resilience",
            ].map((label, i) => (
              <label key={label}>
                <span>
                  {label}
                  <strong>{weights[i]}%</strong>
                </span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={weights[i]}
                  aria-label={label}
                  onChange={(e) =>
                    setWeights((prev) =>
                      prev.map((v, n) => (n === i ? +e.target.value : v)),
                    )
                  }
                />
                <small>
                  Lower <span>Higher</span>
                </small>
              </label>
            ))}
          </div>
          <div className="profile-buttons">
            {(
              [
                ["soil", "Balanced soil"],
                ["water", "Water and climate"],
                ["profit", "Profitability"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                className={
                  weights.every((v, i) => v === profiles[key][i])
                    ? "active"
                    : ""
                }
                onClick={() => setWeights([...profiles[key]])}
              >
                {label}
              </button>
            ))}
          </div>
        </section>
        <div className="section-heading scenarios-heading">
          <div>
            <h2>02 Compare the scenarios</h2>
            <p>Illustrative scores weighted by the goals above.</p>
          </div>
          <button className="button" onClick={compare} disabled={busy}>
            {busy ? "Comparing…" : "Compare Strategies"}
          </button>
        </div>
        <div className="scenario-grid">
          {scenarios.map((s, i) => (
            <article
              className={
                "scenario panel " + (winner === i ? "recommended" : "")
              }
              key={s.name}
            >
              <div className="scenario-ribbon">
                {winner === i
                  ? "BEST FIT FOR YOUR WEIGHTS"
                  : i === 0
                    ? "Comparison baseline"
                    : "Alternative to explore"}
              </div>
              <h2>{s.name}</h2>
              <div className="score">
                <strong style={{ color: s.color }}>{chosen[i]}</strong>
                <small>/ 100</small>
                <small>illustrative fit ⓘ</small>
              </div>
              <h3>{s.sequence}</h3>
              <small>SCENARIO CALENDAR • 12 MONTHS</small>
              <div className="mini-calendar">
                {months.map((m, n) => (
                  <div key={n}>
                    <span>{m[0]}</span>
                    <i
                      style={{
                        background:
                          n === 7 || n === 8
                            ? i === 0
                              ? "#e8e4d7"
                              : i === 2
                                ? "#e9bc6c"
                                : "#a8c477"
                            : "#365f44",
                      }}
                    />
                  </div>
                ))}
              </div>
              <small>{s.calendar}</small>
              <dl>
                <div>
                  <dt>Water</dt>
                  <dd>{s.water}</dd>
                </div>
                <div>
                  <dt>Soil</dt>
                  <dd>{s.soil}</dd>
                </div>
                <div>
                  <dt>Climate</dt>
                  <dd>{s.climate}</dd>
                </div>
              </dl>
              <div className="benefit">
                <small>POTENTIAL BENEFIT</small>
                <p>{s.benefit}</p>
              </div>
              <div className="risk">
                <small>POINT OF ATTENTION</small>
                <p>{s.risk}</p>
              </div>
              <Btn onClick={() => open(i)} secondary={winner !== i}>
                Understand this scenario →
              </Btn>
            </article>
          ))}
        </div>
        <div className="grid-two compare-bottom">
          <section className="panel">
            <h2>The goals, side by side</h2>
            <p>Relative scale: 0–100 • higher = better fit</p>
            <Radar />
            <div className="legend">
              {scenarios.map((s) => (
                <span key={s.name} style={{ color: s.color }}>
                  ■ {s.name}
                </span>
              ))}
            </div>
          </section>
          <section className="panel green-panel">
            <h2>Why was this strategy suggested?</h2>
            <p className="body-text">
              {scenarios[winner].name} had the best fit for the weights in this
              example.
            </p>
            <p>{scenarios[winner].detail}</p>
            <h3>How the score works</h3>
            <p>
              Weighted average of the scenario's four scores. Scores and weights are
              for demonstration and do not represent a validated model.
            </p>
            <LinkButton onClick={() => open("sources")}>
              See assumptions and limitations →
            </LinkButton>
          </section>
        </div>
        <p className="footnote">
          No scenario is an absolute recommendation. Confirm feasibility with
          agronomic assistance and local data before deciding.
        </p>
      </>
    );
  }
  function Settings() {
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Settings</h1>
            <p>Control your preferences and the origin of the data.</p>
          </div>
          <Btn onClick={() => toast("Preferences applied for this session.")}>
            Save settings
          </Btn>
        </div>
        <Demo />
        <div className="two-col">
          <div className="stack">
            <section className="panel">
              <h2>Display preferences</h2>
              <dl className="preferences">
                <div>
                  <dt>Language</dt>
                  <dd>{settings.language}</dd>
                </div>
                <div>
                  <dt>Temperature</dt>
                  <dd>
                    <select
                      aria-label="Temperature unit"
                      value={settings.temperature}
                      onChange={(e) =>
                        setSettings((v) => ({
                          ...v,
                          temperature: e.target.value,
                        }))
                      }
                    >
                      <option>Degrees Celsius (°C)</option>
                      <option>Degrees Fahrenheit (°F)</option>
                    </select>
                  </dd>
                </div>
                <div>
                  <dt>Area and yield</dt>
                  <dd>Hectares • 60 kg bags / ha</dd>
                </div>
                <div>
                  <dt>Precipitation</dt>
                  <dd>Millimeters (mm)</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <h2>Reference sources</h2>
              <p className="warm">No source is connected in this version.</p>
              <dl className="source-list">
                <div>
                  <dt>NASA POWER</dt>
                  <dd>Climate • temperature and precipitation</dd>
                </div>
                <div>
                  <dt>NASA SMAP</dt>
                  <dd>Surface soil moisture</dd>
                </div>
                <div>
                  <dt>NASA MODIS</dt>
                  <dd>Vegetation • example NDVI index</dd>
                </div>
              </dl>
              <LinkButton onClick={() => open("sources")}>
                See documentation and limitations →
              </LinkButton>
            </section>
          </div>
          <aside className="stack">
            <section className="panel green-panel">
              <h2>You are in control</h2>
              <p>
                This is a demo environment. The farm, the crops, the
                indicators and the scenarios are fictitious.
              </p>
              <p>
                Changes stay only in this session's memory. There is no real
                account, sync or document upload.
              </p>
              <small>
                NASA Space Apps Challenge 2026
                <br />
                NATIVA Project
              </small>
            </section>
            <section className="panel">
              <h2>Start over</h2>
              <p>Go back to the overview to explore the flow.</p>
              <LinkButton onClick={() => go("overview")}>
                Back to the overview →
              </LinkButton>
            </section>
          </aside>
        </div>
      </>
    );
  }
  function Landing() {
    const heroImgs = [
      L.imgFotografiaComZoomSuave,
      L.imgFotografiaComZoomSuave1,
      L.imgFotografiaComZoomSuave2,
    ];
    return (
      <div className="landing">
        <nav className="landing-nav">
          <Logo />
          <div>
            <a
              href="#como-funciona"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById("como-funciona")?.scrollIntoView({
                  behavior: reduced ? "instant" : "smooth",
                });
              }}
            >
              How it works
            </a>
            <a
              href="#tecnologia"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById("tecnologia")?.scrollIntoView({
                  behavior: reduced ? "instant" : "smooth",
                });
              }}
            >
              Technology
            </a>
            <button onClick={() => open("technology")}>About us</button>
          </div>
          <div>
            <button onClick={() => open("login")}>Log in</button>
            <button className="button lime" onClick={() => go("signup")}>
              Sign up →
            </button>
          </div>
        </nav>
        <section className="hero">
          <motion.img
            key={slide}
            className="hero-photo"
            src={heroImgs[slide]}
            alt="Farm landscape at sunrise"
            initial={reduced ? false : { scale: 1 }}
            animate={reduced ? { scale: 1 } : { scale: [1, 1.015] }}
            transition={{
              duration: 6,
              times: [0, 1],
              ease: "linear",
              repeat: Infinity,
            }}
          />
          <div className="hero-shade" />
          <div className="hero-content">
            <small>INTELLIGENCE FROM SPACE</small>
            <h1>
              {
                [
                  "The future of your\nfarm starts here.",
                  "A fresh look\nat your land.",
                  "From observation\nto the next season.",
                ][slide]
              }
            </h1>
            <p>
              Turn space data into smart decisions for your
              property.
            </p>
            <div>
              <button className="button yellow" onClick={() => go("signup")}>
                Start for free →
              </button>
              <button className="button outline" onClick={() => go("overview")}>
                Explore the platform
              </button>
            </div>
          </div>
          <div className="carousel-controls">
            <div>
              {heroImgs.map((_, i) => (
                <button
                  key={i}
                  aria-label={"Go to image " + (i + 1)}
                  aria-pressed={slide === i}
                  className={slide === i ? "active" : ""}
                  onClick={() => setSlide(i)}
                />
              ))}
              <small>0{slide + 1} / 03</small>
            </div>
            <div>
              <button
                aria-label="Previous image"
                onClick={() => setSlide((slide + 2) % 3)}
              >
                ‹
              </button>
              <button
                aria-label="Next image"
                onClick={() => setSlide((slide + 1) % 3)}
              >
                ›
              </button>
            </div>
          </div>
        </section>
        <section className="landing-intro" id="produto">
          <small>THE FULL PICTURE. NO COMPLICATIONS.</small>
          <h2>
            Know your land
            <br />
            like never before.
          </h2>
          <p>
            Climate, soil and vegetation. Connected to open new
            <br />
            possibilities in the field.
          </p>
          <button
            className="product-preview"
            onClick={() => go("overview")}
            aria-label="Explore the NATIVA dashboard"
          >
            <div className="preview-dots">
              <i />
              <i />
              <i />
            </div>
            <aside>
              <img src={L.imgLogoNoProduto} alt="" />
              <strong>NATIVA</strong>
              {[
                "Overview",
                "My Property",
                "Climate Analysis",
                "Crop History",
                "Rotation Strategies",
              ].map((t) => (
                <span key={t}>{t}</span>
              ))}
            </aside>
            <div className="preview-main">
              <h3>Property Overview</h3>
              <small>Your land, a new perspective</small>
              <div className="preview-metrics">
                {["24.8 °C", "142 mm", "32 %", "0.76 NDVI"].map((t) => (
                  <div key={t}>
                    {t}
                    <small>Demo indicator</small>
                  </div>
                ))}
              </div>
              <div className="preview-bottom">
                <img
                  className="preview-map"
                  src={L.imgMapaAgricola}
                  alt="Illustrative farm map"
                />
                <div>
                  <div className="preview-chart">
                    <img src={L.imgSerieClimaticaDemonstrativa} alt="" />
                    <img src={L.imgSerieClimaticaDemonstrativa1} alt="" />
                  </div>
                  <div className="preview-note">
                    Explore the opportunities of your next season.
                  </div>
                </div>
              </div>
            </div>
          </button>
          <p className="green-text">
            Your property at the center. Data that broadens your view.
          </p>
          <small>Discover the experience →</small>
        </section>
        <section className="how-it-works" id="como-funciona">
          <small>SIMPLE TO USE. RICH IN POSSIBILITIES.</small>
          <h2>From observation to decision.</h2>
          <div className="steps">
            {[
              [
                "Locate your property.",
                "Start with your land. Tell us where you farm and your context.",
                L.imgIconeDoPasso1,
              ],
              [
                "Explore the environmental conditions.",
                "See climate, moisture and vegetation from a new perspective.",
                L.imgIconeDoPasso2,
              ],
              [
                "Compare rotation strategies.",
                "Explore paths for the next cycle with your priorities.",
                L.imgIconeDoPasso3,
              ],
            ].map(([t, d, img], i) => (
              <article key={t}>
                <span>0{i + 1}</span>
                <img src={img} alt="" />
                <h3>{t}</h3>
                <p>{d}</p>
              </article>
            ))}
          </div>
          <LinkButton onClick={() => go("overview")}>
            Start with our property →
          </LinkButton>
        </section>
        <section className="space-section" id="tecnologia">
          <img
            src={L.imgFotografiaComZoomSuave1}
            alt="The Earth seen from space"
          />
          <div>
            <small>NASA TECHNOLOGY. LOCAL CONTEXT.</small>
            <h2>
              A new perspective
              <br />
              on your farm.
            </h2>
            <h3>
              Earth observation helps us see beyond what is in
              view.
            </h3>
            <p>
              NATIVA uses NASA observation data to explore
              environmental conditions and support farming decisions, bringing together
              space, context and the reality of your property.
            </p>
            <LinkButton onClick={() => open("technology")}>
              Discover our technology →
            </LinkButton>
            <div className="source-chips">
              {["POWER", "SMAP", "MODIS"].map((s) => (
                <span key={s}>
                  {s}
                  <small>NASA · reference</small>
                </span>
              ))}
            </div>
          </div>
        </section>
        <section className="about-section">
          <div>
            <small>ABOUT THE PROJECT</small>
            <h2>
              Space technology.
              <br />
              Purpose in the field.
            </h2>
          </div>
          <div>
            <p>
              Developed for the NASA Space Apps Challenge 2026, NATIVA
              explores new ways of using Earth observation data to
              broaden the possibilities of farmers.
            </p>
            <LinkButton onClick={() => open("technology")}>
              Open science. Possibilities for the field.
            </LinkButton>
          </div>
        </section>
        <section className="landing-cta">
          <img src={L.imgFotografiaComZoomSuave2} alt="Crop fields" />
          <div>
            <small>FROM YOUR FIELD TO THE FUTURE.</small>
            <h2>
              Your next season starts
              <br />
              with a decision.
            </h2>
            <p>Discover new possibilities for your property.</p>
            <button className="button yellow" onClick={() => go("signup")}>
              Start for free →
            </button>
            <small>Explore the demo for free.</small>
          </div>
        </section>
        <footer>
          <Logo />
          <div>
            <button onClick={() => open("technology")}>About the project</button>
            <button onClick={() => open("technology")}>Technology</button>
            <button onClick={() => open("contact")}>Contact</button>
          </div>
          <small>NASA Space Apps Challenge 2026</small>
          <small>
            Demo prototype • fictitious data and scenarios without local
            validation.
          </small>
        </footer>
      </div>
    );
  }
  function Signup() {
    return (
      <div className="signup">
        <section className="signup-photo">
          <img src={L.imgFotografiaComZoomSuave2} alt="Farm at dawn" />
          <Logo />
          <div>
            <h1>
              Your land deserves
              <br />
              a fresh look.
            </h1>
            <p>
              From observing space to the possibilities
              <br />
              of your next season.
            </p>
          </div>
        </section>
        <section className="signup-form">
          <button className="back-link" onClick={() => go("landing")}>
            Back to home
          </button>
          <small>01 / 02 • YOUR SIGN-UP</small>
          <h1>
            Start with your
            <br />
            property.
          </h1>
          <p>A broader view starts with your context.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              go("onboard");
            }}
          >
            <label className="field">
              <span>Your name</span>
              <input
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>E-mail</span>
              <input type="email" placeholder="farmer@example.com" />
            </label>
            <Field label="Property name" name="name" />
            <div className="signup-location">
              <Field label="City / State" name="city" />
              <Field
                label="Area (ha) • optional"
                name="area"
                type="number"
                min={0.01}
                step="any"
              />
            </div>
            <button className="button yellow" type="submit">
              Continue →
            </button>
            <small>
              Demo environment. No account will be created or stored.
            </small>
          </form>
          <LinkButton onClick={() => open("login")}>
            Already know NATIVA? Log in
          </LinkButton>
        </section>
      </div>
    );
  }
  function Onboard() {
    return (
      <div className="onboard">
        <header>
          <Logo />
          <LinkButton onClick={() => go("signup")}>
            Back to sign-up
          </LinkButton>
        </header>
        <div className="onboard-grid">
          <section>
            <small>02 / 02 • YOUR PROPERTY</small>
            <h1>
              Let's get to know
              <br />your land.
            </h1>
            <p>Confirm the context to explore the platform.</p>
            <div className="onboard-map">
              <img
                src={assets["13:478"].imgLocalizacaoDemonstrativa}
                alt="Demo location"
              />
              <span>
                ⌖ {draft.name}
                <small>
                  {draft.city} · {draft.area} ha · example
                </small>
              </span>
            </div>
          </section>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setFarm({ ...draft });
              go("overview");
              toast(
                `Welcome, ${userName.split(" ")[0]}. Explore your property!`,
              );
            }}
          >
            <Field
              label="Current crop"
              name="crop"
              options={["Soybean", "Corn", "Sorghum", "Coffee", "Wheat", "Other"]}
            />
            <Field
              label="Soil texture"
              name="texture"
              options={["Clayey", "Sandy", "Loam", "Not provided"]}
            />
            <Field
              label="Irrigation availability"
              name="irrigation"
              options={["Yes", "No", "Not provided"]}
            />
            <button className="button yellow" type="submit">
              Explore the platform →
            </button>
            <small>
              Demo flow. The conditions do not represent a real
              farm.
            </small>
          </form>
        </div>
      </div>
    );
  }
  function AddCrop() {
    const [value, setValue] = useState({
      crop: "Corn",
      plant: "2026-03-05",
      harvest: "2026-07-28",
      area: farm.area,
      yield: "",
    });
    const [error, setError] = useState("");
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (value.harvest < value.plant) {
            setError("The harvest must come after planting.");
            return;
          }
          setCrops((p) => [
            {
              ...value,
              id: Date.now(),
              season: value.plant.slice(0, 4),
              status: value.yield ? "Completed" : "Planned",
            },
            ...p,
          ]);
          setModal(null);
          toast("Crop added for this session.");
        }}
      >
        <h2>Add crop</h2>
        <p>Record an example to explore the property history.</p>
        <div className="fields-grid">
          <label className="field">
            <span>Crop</span>
            <select
              value={value.crop}
              onChange={(e) =>
                setValue((v) => ({ ...v, crop: e.target.value }))
              }
            >
              {[
                "Corn",
                "Soybean",
                "Sorghum",
                "Crotalaria",
                "Brachiaria",
                "Wheat",
              ].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Field</span>
            <select>
              <option>Field 01</option>
            </select>
          </label>
          {(["plant", "harvest", "area", "yield"] as const).map((key, i) => (
            <label className="field" key={key}>
              <span>
                {
                  [
                    "Planting date",
                    "Harvest date • expected",
                    "Planted area (ha)",
                    "Yield (bags/ha) • optional",
                  ][i]
                }
              </span>
              <input
                type={i < 2 ? "date" : "number"}
                min={i > 1 ? 0 : undefined}
                step={i > 1 ? "any" : undefined}
                value={value[key]}
                required={key !== "yield"}
                onChange={(e) =>
                  setValue((v) => ({ ...v, [key]: e.target.value }))
                }
              />
            </label>
          ))}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <p>The dates may overlap with other crops in the same year.</p>
        <button type="submit" className="button">
          Save crop
        </button>
        <small>Data kept for this session only.</small>
      </form>
    );
  }
  function ModalContent() {
    if (modal === "addCrop") return <AddCrop />;
    if (modal === "map")
      return (
        <>
          <h2>Map • {layer}</h2>
          <p>Demo layer • values and areas are not georeferenced.</p>
          <Map expanded />
        </>
      );
    if (typeof modal === "number") {
      const s = scenarios[modal];
      return (
        <>
          <h2>{s.name}</h2>
          <h3>{s.sequence}</h3>
          <h3>Agronomic rationale</h3>
          <p>{s.detail}</p>
          <h3>Potential benefit</h3>
          <p>{s.benefit}</p>
          <h3>Risks and conditions</h3>
          <p>{s.risk}</p>
          <small>
            General assumptions, not validated for this fictitious property.
          </small>
          <Btn onClick={() => open(null)}>Back</Btn>
        </>
      );
    }
    if (modal === "account")
      return (
        <>
          <h2>Your account</h2>
          <h3>Demo profile</h3>
          <p>
            Explore the experience without creating a real account. Changes stay
            in this session only.
          </p>
          <LinkButton onClick={() => go("settings")}>
            Account settings →
          </LinkButton>
        </>
      );
    if (modal === "property")
      return (
        <>
          <h2>Select property</h2>
          <button className="property-choice" onClick={() => open(null)}>
            <strong>{farm.name} ✓</strong>
            <small>
              {farm.city} • {farm.area} ha
            </small>
          </button>
          <p>One property is available in this demo.</p>
          <LinkButton onClick={() => go("farm")}>
            Edit property →
          </LinkButton>
        </>
      );
    if (modal === "login")
      return (
        <>
          <h2>Welcome to NATIVA</h2>
          <p>
            Enter the demo experience. No authentication or real account
            is needed.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              go("overview");
            }}
          >
            <label className="field">
              <span>Email • optional</span>
              <input type="email" placeholder="farmer@example.com" />
            </label>
            <button type="submit" className="button yellow">
              Explore the demo →
            </button>
          </form>
        </>
      );
    if (modal === "contact")
      return (
        <>
          <h2>Shall we talk?</h2>
          <p>Demo form: this version does not send messages.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              toast("Demo completed. No message was sent.");
              open(null);
            }}
          >
            <label className="field">
              <span>Your name</span>
              <input required placeholder="Your name" />
            </label>
            <label className="field">
              <span>Your email</span>
              <input required type="email" placeholder="farmer@example.com" />
            </label>
            <label className="field">
              <span>Your message</span>
              <textarea required placeholder="I would like to learn about NATIVA." />
            </label>
            <button className="button yellow" type="submit">
              Complete demo
            </button>
          </form>
        </>
      );
    if (modal && modal in info) {
      const data = info[modal as keyof typeof info];
      return (
        <>
          <h2>{data.title}</h2>
          <p>{data.subtitle}</p>
          {data.items.map(([t, d]) => (
            <section className="info-item" key={t}>
              <h3>{t}</h3>
              <p>{d}</p>
            </section>
          ))}
          <Btn onClick={() => open(null)}>Got it</Btn>
        </>
      );
    }
    return null;
  }
  const inDashboard = !["landing", "signup", "onboard"].includes(page);
  return (
    <DraftContext.Provider value={{ draft, setDraft }}>
      {page === "landing" ? (
        Landing()
      ) : page === "signup" ? (
        Signup()
      ) : page === "onboard" ? (
        Onboard()
      ) : (
        <div className="dashboard">
          {menu && (
            <button
              className="nav-shade"
              aria-label="Close navigation"
              onClick={() => setMenu(false)}
            />
          )}
          <aside className={"sidebar " + (menu ? "shown" : "")}>
            <Logo />
            <small className="nav-section">MAIN</small>
            <nav>
              {navItems.map(([id, label, img], i) => (
                <React.Fragment key={id}>
                  {i === 3 && (
                    <small className="nav-section planning">PLANNING</small>
                  )}
                  <button
                    className={page === id ? "selected" : ""}
                    onClick={() => go(id)}
                  >
                    <img src={img} alt="" />
                    {label}
                  </button>
                </React.Fragment>
              ))}
            </nav>
            <div className="sidebar-bottom">
              <button
                className={page === "settings" ? "selected" : ""}
                onClick={() => go("settings")}
              >
                <img src={A.imgIconeDeNavegacao5} alt="" />
                Settings
              </button>
              <button onClick={() => open("help")}>
                <img src={A.imgIconeAjuda} alt="" />
                Help
              </button>
              <LinkButton onClick={() => go("landing")}>
                Back to home ↗
              </LinkButton>
            </div>
          </aside>
          <header className="topbar">
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(true)}
            >
              ☰
            </button>
            <span className="mobile-brand">NATIVA</span>
            <button
              className="property-select"
              onClick={() => open("property")}
            >
              {farm.name} ⌄
            </button>
            <button
              className="account"
              aria-label="My account"
              onClick={() => open("account")}
            >
              <img src={A.imgIconeDeConta} alt="" />
            </button>
          </header>
          <main className="main-content">
            {page === "overview"
              ? Overview()
              : page === "farm"
                ? FarmPage()
                : page === "history"
                  ? History()
                  : page === "climate"
                    ? Climate()
                    : page === "rotation"
                      ? Rotation()
                      : Settings()}
          </main>
        </div>
      )}
      {modal !== null && (
        <Dialog onClose={() => open(null)} wide={modal === "map"}>
          <ModalContent />
        </Dialog>
      )}
      {notice && (
        <div className="toast" role="status">
          ✓ {notice}
          <button aria-label="Close notification" onClick={() => setNotice("")}>
            ×
          </button>
        </div>
      )}
      {inDashboard && <span className="sr-only">NATIVA demo</span>}
    </DraftContext.Provider>
  );
}
function Dialog({
  children,
  onClose,
  wide,
}: {
  children: React.ReactNode;
  onClose: () => void;
  wide: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => {
      d?.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "modal-wide" : "")}
      aria-label="NATIVA details"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
    >
      <button className="close-modal" aria-label="Close" onClick={onClose}>
        ×
      </button>
      {children}
    </dialog>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
