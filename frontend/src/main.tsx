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
    [deletedCrop, setDeletedCrop] = useState<{ crop: Crop; index: number } | null>(null),
    [year, setYear] = useState("2025"),
    [period, setPeriod] = useState("12"),
    [layer, setLayer] = useState("Vegetação (NDVI)"),
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
      temperature: "Graus Celsius (°C)",
      language: "Português (Brasil)",
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
  function deleteCrop(id: Crop["id"]) {
    const index = crops.findIndex((crop) => crop.id === id);
    if (index < 0) return;
    setDeletedCrop({ crop: crops[index], index });
    setCrops((prev) => prev.filter((crop) => crop.id !== id));
  }

  function undoDeleteCrop() {
    if (!deletedCrop) return;
    const { crop, index } = deletedCrop;
    setCrops((prev) => {
      if (prev.some((item) => item.id === crop.id)) return prev;
      const restored = [...prev];
      restored.splice(Math.min(index, restored.length), 0, crop);
      return restored;
    });
    setDeletedCrop(null);
  }

  function saveFarm(e: React.FormEvent) {
    e.preventDefault();
    setFarm({ ...draft });
    toast("Alterações aplicadas nesta sessão.");
  }
  function compare() {
    if (!weights.some(Boolean)) {
      toast("Defina pelo menos uma prioridade maior que zero.");
      return;
    }
    setBusy(true);
    timer.current = setTimeout(() => {
      setApplied([...weights]);
      setBusy(false);
      toast("Comparação demonstrativa atualizada.");
    }, 600);
  }
  const chosen = scenarios.map((s) => score(s.notes, applied));
  const winner = chosen.indexOf(Math.max(...chosen));
  const navItems: [Page, string, string][] = [
    ["overview", "Visão Geral", A.imgIconeDeNavegacao],
    ["farm", "Minha Propriedade", A.imgIconeDeNavegacao1],
    ["climate", "Análise Climática", A.imgIconeDeNavegacao3],
    ["history", "Histórico de Cultivo", A.imgIconeDeNavegacao2],
    ["rotation", "Estratégias de Rotação", A.imgIconeDeNavegacao4],
  ];
  const open = (m: Modal) => setModal(m);
  function Logo() {
    return (
      <button
        className="brand"
        onClick={() => go("landing")}
        aria-label="NATIVA — início"
      >
        <img src={A.imgLogoNativaEnviada} alt="" />
        <strong>NATIVA</strong>
      </button>
    );
  }
  function Demo() {
    return (
      <p className="demo">
        DADOS DEMONSTRATIVOS{" "}
        <span>
          • Propriedade fictícia. Valores ilustrativos, não são medições reais
          nem recomendações validadas.
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
          aria-label={`${kind === "rain" ? "Precipitação" : kind === "temperature" ? "Temperatura" : kind === "moisture" ? "Umidade do solo" : "NDVI"} — valores demonstrativos de ${year}`}
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
                      : (max * (1 - i * 0.5)).toLocaleString("pt-BR")}
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
              ? ["Jul", "Ago", "Set", "Out", "Nov", "Dez"]
              : ["Jan", "Abr", "Jul", "Out", "Dez"]
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
          série fictícia
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
            alt="Vista aérea ilustrativa de campos agrícolas"
          />
          <img
            className="field-boundary"
            src={A.imgLimiteFicticio}
            alt="Limite fictício da propriedade"
          />
        </div>
        <select
          className="map-layer"
          aria-label="Camada do mapa"
          value={layer}
          onChange={(e) => setLayer(e.target.value)}
        >
          {[
            "Vegetação (NDVI)",
            "Umidade do solo",
            "Precipitação",
            "Temperatura",
          ].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <div className="map-controls">
          <button
            aria-label="Aproximar mapa"
            onClick={() => setZoom((v) => Math.min(2.4, v + 0.2))}
          >
            +
          </button>
          <button
            aria-label="Afastar mapa"
            onClick={() => setZoom((v) => Math.max(1, v - 0.2))}
          >
            −
          </button>
          <button
            aria-label="Centralizar propriedade"
            onClick={() => setZoom(1)}
          >
            ⌖
          </button>
        </div>
        <div className="map-farm">
          <strong>{farm.name}</strong>
          <small>{farm.area} ha • limite fictício</small>
        </div>
        <small className="map-disclaimer">
          Imagem ilustrativa • limites fictícios, sem georreferenciamento
        </small>
        <div className="map-legend">
          <span>
            {layer === "Vegetação (NDVI)"
              ? "NDVI · 0,2–0,9"
              : layer + " · exemplo"}
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
          aria-label={expanded ? "Fechar mapa ampliado" : "Ampliar mapa"}
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
            <h2>Como o clima está mudando?</h2>
            <p>
              Jan–Dez {year} · comparação entre meses · valores demonstrativos
            </p>
          </div>
          <select
            aria-label="Período dos gráficos"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="12">Últimos 12 meses</option>
            <option value="6">Últimos 6 meses</option>
          </select>
        </div>
        <div className="charts-three">
          {(["temperature", "rain", "moisture"] as const).map((kind, i) => (
            <div key={kind}>
              <div className="chart-title">
                <strong>
                  {["Temperatura", "Precipitação", "Umidade do solo"][i]}
                </strong>
                <small>{["°C", "mm/mês", "%"][i]}</small>
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
            "Temperatura média",
            settings.temperature.startsWith("Graus Fahrenheit")
              ? "76,6"
              : "24,8",
            settings.temperature.startsWith("Graus Fahrenheit") ? "°F" : "°C",
            "↗ +1,2 °C no histórico",
            "POWER",
          ],
          [
            "Precipitação acumulada",
            "142",
            "mm",
            "↘ −18% no histórico",
            "POWER",
          ],
          ["Umidade do solo", "32", "%", "↗ +4 p.p. no mês", "SMAP"],
          ["Índice de vegetação", "0,76", "NDVI", "↗ +0,08 no mês", "MODIS"],
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
            <small className="metric-source">NASA {m[4]} • exemplo</small>
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
            <h1>Sua propriedade, uma nova perspectiva.</h1>
            <p>
              Explore sua fazenda com dados da NASA e descubra oportunidades
              para suas próximas safras.
            </p>
          </div>
          <Btn onClick={() => go("rotation")}>＋ Nova Análise</Btn>
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
              {farm.latitude} / {farm.longitude} • coordenadas fictícias
            </small>
            <div className="current-context">
              <small>CULTIVO ATUAL</small>
              <strong>{farm.crop}</strong>
              <span>Talhão 01 · {farm.area} ha</span>
            </div>
            <hr />
            <h3>Um novo olhar para o próximo ciclo.</h3>
            <LinkButton onClick={() => go("farm")}>
              Ver minha propriedade →
            </LinkButton>
            <LinkButton onClick={() => open("sources")}>
              Fontes e limitações →
            </LinkButton>
          </aside>
        </div>
        <MetricCards />
        <button
          className="disclosure"
          aria-expanded={explain}
          onClick={() => setExplain(!explain)}
        >
          Entenda os indicadores <span>{explain ? "−" : "⌄"}</span>
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
            <h2>Planeje sua próxima safra.</h2>
            <p>
              Compare estratégias de rotação considerando o clima, o solo e as
              prioridades da sua propriedade.
            </p>
            <button className="button lime" onClick={() => go("rotation")}>
              Comparar estratégias →
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
          Calendário agrícola <span>{calendar ? "−" : "⌄"}</span>
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
            <h1>Minha Propriedade</h1>
            <p>As características da sua terra são o ponto de partida.</p>
          </div>
          <Btn type="submit">Salvar alterações</Btn>
        </div>
        <Demo />
        <div className="two-col">
          <div className="stack">
            <section className="panel">
              <h2>01 Localização</h2>
              <p>
                Informe onde você cultiva. Os campos marcados são opcionais.
              </p>
              <div className="fields-grid">
                <Field label="Nome da propriedade" name="name" />
                <Field
                  label="País"
                  name="country"
                  options={[
                    "Brasil",
                    "Argentina",
                    "Uruguai",
                    "Paraguai",
                    "Outro",
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
                  label="Área da propriedade (ha)"
                  name="area"
                  type="number"
                  min={0.01}
                  step="any"
                />
              </div>
              <div className="location-preview">
                <img
                  src={assets["13:478"].imgLocalizacaoDemonstrativa}
                  alt="Localização ilustrativa da fazenda"
                />
                <span>
                  ⌖ {draft.latitude}, {draft.longitude} • exemplo
                </span>
              </div>
            </section>
            <section className="panel">
              <h2>02 Características do solo</h2>
              <div className="fields-grid">
                <Field
                  label="Textura do solo"
                  name="texture"
                  options={[
                    "Argiloso",
                    "Arenoso",
                    "Franco",
                    "Siltoso",
                    "Não informado",
                  ]}
                />
                <Field
                  label="pH do solo ⓘ"
                  name="ph"
                  type="number"
                  min={0}
                  max={14}
                  step=".1"
                />
                <Field
                  label="Drenagem"
                  name="drainage"
                  options={["Moderada", "Boa", "Baixa", "Não informado"]}
                />
                <Field
                  label="Matéria orgânica (%) • opcional"
                  name="organic"
                  type="number"
                  min={0}
                  max={100}
                  step=".1"
                />
              </div>
            </section>
            <section className="panel">
              <h2>03 Recursos hídricos</h2>
              <div className="fields-grid">
                <Field
                  label="Disponibilidade de irrigação"
                  name="irrigation"
                  options={["Sim", "Não", "Não informado"]}
                />
                <Field
                  label="Tipo de irrigação"
                  name="irrigationType"
                  options={[
                    "Pivô central",
                    "Gotejamento",
                    "Aspersão",
                    "Não se aplica",
                    "Outro",
                  ]}
                />
                <div className="full">
                  <Field
                    label="Restrições de água • opcional"
                    name="waterRestriction"
                  />
                </div>
              </div>
            </section>
          </div>
          <aside className="stack">
            <section className="panel">
              <h2>Sua terra, em contexto</h2>
              <h3 className="farm-name">{farm.name}</h3>
              <p>
                {farm.city} • {farm.country}
              </p>
              <dl>
                <div>
                  <dt>Área total</dt>
                  <dd>{farm.area} ha</dd>
                </div>
                <div>
                  <dt>Talhões cadastrados</dt>
                  <dd>1 talhão</dd>
                </div>
                <div>
                  <dt>Informações preenchidas</dt>
                  <dd>{Object.values(draft).filter(Boolean).length} campos</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <h3>Por que pedimos estes dados?</h3>
              <p>
                Solo, água e localização ajudam a contextualizar os cenários de
                rotação.
              </p>
              <p>
                Você pode começar com o que sabe e completar os campos opcionais
                depois.
              </p>
              <small>ⓘ Alterações mantidas somente nesta sessão.</small>
            </section>
            <section className="panel">
              <h2>Análise de solo</h2>
              <h3>{report ? report.name : "Nenhum laudo anexado"}</h3>
              <p>
                Se tiver um laudo recente, adicione-o para consultar junto ao
                cadastro.
              </p>
              <label className="button upload">
                {report ? "Substituir laudo" : "Adicionar laudo"}
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setReport(f);
                      toast(
                        "Laudo selecionado localmente. Nenhum arquivo foi enviado.",
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
                  Remover arquivo
                </button>
              )}
              <small>
                Arquivo local • não enviado nem analisado automaticamente.
              </small>
            </section>
          </aside>
        </div>
        <p className="footnote">
          Seus dados ajudam a explorar possibilidades; não substituem uma
          avaliação agronômica local.
        </p>
      </form>
    );
  }
  function Timeline() {
    return (
      <section className="panel timeline-panel">
        <div className="section-heading">
          <div>
            <h2>Uma visão de cada safra</h2>
            <p>
              Talhão 01 • {farm.area} ha • plantio, desenvolvimento e colheita
            </p>
          </div>
          <select
            aria-label="Ano do calendário"
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
                Soja {Number(year) - 1}/{year.slice(2)}
              </strong>
              <div className="timeline-track">
                <span style={{ gridColumn: "1/3" }}>Desenvolvimento</span>
                <span className="harvest" style={{ gridColumn: "3/4" }}>
                  Colheita
                </span>
                <span style={{ gridColumn: "10/11" }}>Plantio</span>
                <span style={{ gridColumn: "11/13" }}>
                  Soja {year}/{String(Number(year) + 1).slice(2)}
                </span>
              </div>
            </div>
            <div className="timeline-row">
              <strong>Milho safrinha</strong>
              <div className="timeline-track">
                <span style={{ gridColumn: "3/4" }}>Plantio</span>
                <span style={{ gridColumn: "4/7" }}>Desenvolvimento</span>
                <span className="harvest" style={{ gridColumn: "7/8" }}>
                  Colheita
                </span>
                <span className="bare" style={{ gridColumn: "8/10" }}>
                  Solo descoberto
                </span>
              </div>
            </div>
          </div>
        </div>
        <div className="legend">
          <span>● Plantio</span>
          <span>● Desenvolvimento</span>
          <span className="warm">● Colheita</span>
          <span>● Solo descoberto</span>
        </div>
      </section>
    );
  }
  function History() {
    const fmt = (s: string) =>
      new Date(s + "T12:00:00").toLocaleDateString("pt-BR");
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Histórico de Cultivo</h1>
            <p>Cada safra conta uma parte da história da sua terra.</p>
          </div>
          <Btn onClick={() => open("addCrop")}>＋ Adicionar cultivo</Btn>
        </div>
        {deletedCrop && (
          <div
            role="status"
            aria-live="polite"
            style={{
              display: "flex", alignItems: "center", gap: 14,
              padding: "14px 18px", margin: "12px 0 18px",
              background: "#19383a", border: "1px solid #527568",
              borderRadius: 10, color: "#f1f7f4", flexWrap: "wrap",
            }}
          >
            <div style={{ flex: 1, minWidth: 180, display: "flex", flexDirection: "column", gap: 4 }}>
              <strong>Crop record deleted</strong>
              <span style={{ fontSize: 13, color: "#b4cdca" }}>
                {deletedCrop.crop.crop} • {deletedCrop.crop.season} was removed from your history.
              </span>
            </div>
            <button
              type="button"
              onClick={undoDeleteCrop}
              style={{ background: "transparent", border: "1px solid #a8ce83", color: "#c2e99d", borderRadius: 6, padding: "8px 14px", cursor: "pointer", fontWeight: 700 }}
            >
              Undo
            </button>
            <button
              type="button"
              onClick={() => setDeletedCrop(null)}
              aria-label="Dismiss notification"
              title="Dismiss notification"
              style={{ background: "transparent", border: "none", color: "#b4cdca", fontSize: 22, cursor: "pointer" }}
            >
              ×
            </button>
          </div>
        )}
        <Demo />
        <div className="grid-two">
          <section className="panel current-crop">
            <small>CULTIVO ATUAL • TALHÃO 01</small>
            <div>
              <h2>{farm.crop}</h2>
              <span>Em crescimento</span>
            </div>
            <p>Plantio: 15 out 2025 → Colheita prevista: 20 fev 2026</p>
          </section>
          <section className="panel">
            <h2>Seu histórico em números</h2>
            <div className="numbers">
              <div>
                <strong>{crops.length + 2}</strong>
                <small>cultivos registrados</small>
              </div>
              <div>
                <strong>3</strong>
                <small>anos de histórico</small>
              </div>
              <div>
                <strong>2</strong>
                <small>cultivos por ano</small>
              </div>
            </div>
          </section>
        </div>
        <Timeline />
        <section className="panel">
          <h2>Cultivos registrados</h2>
          <p>
            Valores demonstrativos • produtividade informada em sacas de 60 kg
            por hectare
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Cultura / safra",
                    "Plantio",
                    "Colheita",
                    "Área",
                    "Produtividade",
                    "Situação",
                    "Actions",
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
                      {c.status !== "Concluído" ? "*" : ""}
                    </td>
                    <td>{c.area} ha</td>
                    <td>
                      {c.yield ? c.yield + " sc/ha" : "Ainda não colhida"}
                    </td>
                    <td>
                      <span className="status">{c.status}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => deleteCrop(c.id)}
                        aria-label={`Delete ${c.crop} ${c.season}`}
                        title={`Delete ${c.crop} ${c.season}`}
                        style={{
                          background: "transparent", border: "none", color: "#f28c8c",
                          fontSize: 24, cursor: "pointer", padding: "3px 10px",
                          borderRadius: 6,
                        }}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <small>
            * Data prevista, não observada. Mostrando {crops.length} de{" "}
            {crops.length + 2} cultivos.
          </small>
        </section>
        <section className="callout">
          <div>
            <h3>O próximo ciclo começa com o que você já aprendeu.</h3>
            <p>Use seu histórico para explorar estratégias de rotação.</p>
          </div>
          <Btn onClick={() => go("rotation")}>Explorar estratégias →</Btn>
        </section>
      </>
    );
  }
  function Climate() {
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Análise Climática</h1>
            <p>Do histórico ao planejamento: entenda os sinais do clima.</p>
          </div>
        </div>
        <Demo />
        <div className="period-bar">
          <span>Período de análise</span>
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
          <small>● Histórico ilustrativo</small>
          <small className="warm">Estimativa ilustrativa</small>
          <small>Projeção ilustrativa</small>
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
                          "Temperatura média",
                          "Precipitação acumulada",
                          "Umidade do solo ⓘ",
                          "Vigor da vegetação ⓘ",
                        ][i]
                      }
                    </h2>
                    <p>
                      NASA {i === 2 ? "SMAP" : i === 3 ? "MODIS" : "POWER"} •
                      exemplo de série histórica
                    </p>
                  </div>
                  <strong className={"climate-number n" + i}>
                    {
                      [
                        year === "2025"
                          ? "24,8 °C"
                          : year === "2024"
                            ? "23,1 °C"
                            : "25,8 °C",
                        year === "2025"
                          ? "142 mm"
                          : year === "2024"
                            ? "132 mm"
                            : "148 mm",
                        "32%",
                        "0,76",
                      ][i]
                    }
                  </strong>
                </div>
                <Chart kind={kind} large />
                <p>
                  {
                    [
                      "Meses mais quentes podem aumentar a demanda por água.",
                      "A chuva se concentra entre outubro e março neste exemplo.",
                      "Água na camada superficial; não representa toda a zona de raízes.",
                      "NDVI indica atividade da vegetação, não rendimento da safra.",
                    ][i]
                  }
                </p>
              </section>
            ),
          )}
        </div>
        <div className="two-col">
          <section className="panel">
            <h2>Planeje com a sazonalidade</h2>
            <p>Padrão ilustrativo • não é previsão meteorológica</p>
            <div className="season wet">
              <strong>Out–Mar</strong>
              <div>
                Período mais chuvoso
                <small>Atenção à drenagem e à janela de plantio.</small>
              </div>
            </div>
            <div className="season dry">
              <strong>Mai–Ago</strong>
              <div>
                Período mais seco
                <small>Cobertura do solo ajuda a reduzir evaporação.</small>
              </div>
            </div>
          </section>
          <section className="panel">
            <h2>Antes de decidir</h2>
            <h3>Histórico</h3>
            <p>
              Observações passadas, aqui representadas por exemplos fictícios.
            </p>
            <h3 className="warm">Estimativas e projeções</h3>
            <p>
              São aproximações com incerteza. Linhas tracejadas não são
              observações.
            </p>
          </section>
        </div>
        <section className="callout">
          <div>
            <h3>ⓘ Fontes, resolução e limitações dos indicadores</h3>
            <p>
              Explore a diferença entre a escala do satélite e a escala do
              talhão.
            </p>
          </div>
          <LinkButton onClick={() => open("sources")}>
            Ver detalhes →
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
        aria-label="Comparação ilustrativa dos quatro critérios"
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
        <span className="radar-water">Água</span>
        <span className="radar-soil-label">Solo</span>
        <span className="radar-profit">Rentabilidade</span>
        <span className="radar-resilience">Resiliência</span>
      </div>
    );
  }
  function Rotation() {
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Estratégias de Rotação</h1>
            <p>
              Compare caminhos para a próxima safra, com as suas prioridades.
            </p>
          </div>
        </div>
        <Demo />
        <section className="panel priorities">
          <h2>01 O que importa mais para a sua próxima safra?</h2>
          <p>
            Ajuste os controles ou explore os três perfis predefinidos de
            prioridade.
          </p>
          <div className="sliders">
            {[
              "Economia de água",
              "Saúde do solo",
              "Rentabilidade",
              "Resiliência climática",
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
                  Menor <span>Maior</span>
                </small>
              </label>
            ))}
          </div>
          <div className="profile-buttons">
            {(
              [
                ["soil", "Solo equilibrado"],
                ["water", "Água e clima"],
                ["profit", "Rentabilidade"],
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
            <h2>02 Compare os cenários</h2>
            <p>Pontuações ilustrativas ponderadas pelos objetivos acima.</p>
          </div>
          <button className="button" onClick={compare} disabled={busy}>
            {busy ? "Comparando…" : "Comparar Estratégias"}
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
                  ? "MAIOR ADERÊNCIA AOS SEUS PESOS"
                  : i === 0
                    ? "Referência de comparação"
                    : "Alternativa para explorar"}
              </div>
              <h2>{s.name}</h2>
              <div className="score">
                <strong style={{ color: s.color }}>{chosen[i]}</strong>
                <small>/ 100</small>
                <small>aderência ilustrativa ⓘ</small>
              </div>
              <h3>{s.sequence}</h3>
              <small>CALENDÁRIO DO CENÁRIO • 12 MESES</small>
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
                  <dt>Água</dt>
                  <dd>{s.water}</dd>
                </div>
                <div>
                  <dt>Solo</dt>
                  <dd>{s.soil}</dd>
                </div>
                <div>
                  <dt>Clima</dt>
                  <dd>{s.climate}</dd>
                </div>
              </dl>
              <div className="benefit">
                <small>BENEFÍCIO POTENCIAL</small>
                <p>{s.benefit}</p>
              </div>
              <div className="risk">
                <small>PONTO DE ATENÇÃO</small>
                <p>{s.risk}</p>
              </div>
              <Btn onClick={() => open(i)} secondary={winner !== i}>
                Entender este cenário →
              </Btn>
            </article>
          ))}
        </div>
        <div className="grid-two compare-bottom">
          <section className="panel">
            <h2>Os objetivos, lado a lado</h2>
            <p>Escala relativa: 0–100 • maior = maior aderência</p>
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
            <h2>Por que esta estratégia foi sugerida?</h2>
            <p className="body-text">
              {scenarios[winner].name} teve maior aderência aos pesos deste
              exemplo.
            </p>
            <p>{scenarios[winner].detail}</p>
            <h3>Como a pontuação funciona</h3>
            <p>
              Média ponderada das quatro notas do cenário. Notas e pesos são
              demonstrativos e não representam um modelo validado.
            </p>
            <LinkButton onClick={() => open("sources")}>
              Ver premissas e limitações →
            </LinkButton>
          </section>
        </div>
        <p className="footnote">
          Nenhum cenário é uma recomendação absoluta. Confirme a viabilidade com
          assistência agronômica e dados locais antes de decidir.
        </p>
      </>
    );
  }
  function Settings() {
    return (
      <>
        <div className="page-heading">
          <div>
            <h1>Configurações</h1>
            <p>Controle suas preferências e a origem dos dados.</p>
          </div>
          <Btn onClick={() => toast("Preferências aplicadas nesta sessão.")}>
            Salvar ajustes
          </Btn>
        </div>
        <Demo />
        <div className="two-col">
          <div className="stack">
            <section className="panel">
              <h2>Preferências de leitura</h2>
              <dl className="preferences">
                <div>
                  <dt>Idioma</dt>
                  <dd>{settings.language}</dd>
                </div>
                <div>
                  <dt>Temperatura</dt>
                  <dd>
                    <select
                      aria-label="Unidade de temperatura"
                      value={settings.temperature}
                      onChange={(e) =>
                        setSettings((v) => ({
                          ...v,
                          temperature: e.target.value,
                        }))
                      }
                    >
                      <option>Graus Celsius (°C)</option>
                      <option>Graus Fahrenheit (°F)</option>
                    </select>
                  </dd>
                </div>
                <div>
                  <dt>Área e produtividade</dt>
                  <dd>Hectares • sacas de 60 kg / ha</dd>
                </div>
                <div>
                  <dt>Precipitação</dt>
                  <dd>Milímetros (mm)</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <h2>Fontes de referência</h2>
              <p className="warm">Nenhuma fonte está conectada nesta versão.</p>
              <dl className="source-list">
                <div>
                  <dt>NASA POWER</dt>
                  <dd>Clima • temperatura e precipitação</dd>
                </div>
                <div>
                  <dt>NASA SMAP</dt>
                  <dd>Umidade superficial do solo</dd>
                </div>
                <div>
                  <dt>NASA MODIS</dt>
                  <dd>Vegetação • exemplo de índice NDVI</dd>
                </div>
              </dl>
              <LinkButton onClick={() => open("sources")}>
                Consultar documentação e limitações →
              </LinkButton>
            </section>
          </div>
          <aside className="stack">
            <section className="panel green-panel">
              <h2>Você está no controle</h2>
              <p>
                Este é um ambiente demonstrativo. A fazenda, os cultivos, os
                indicadores e os cenários são fictícios.
              </p>
              <p>
                As alterações ficam apenas na memória desta sessão. Não há conta
                real, sincronização ou envio de documentos.
              </p>
              <small>
                NASA Space Apps Challenge 2026
                <br />
                Projeto NATIVA
              </small>
            </section>
            <section className="panel">
              <h2>Começar de novo</h2>
              <p>Volte à visão geral para explorar o fluxo.</p>
              <LinkButton onClick={() => go("overview")}>
                Voltar à visão geral →
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
              Como funciona
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
              Tecnologia
            </a>
            <button onClick={() => open("technology")}>Sobre nós</button>
          </div>
          <div>
            <button onClick={() => open("login")}>Entrar</button>
            <button className="button lime" onClick={() => go("signup")}>
              Cadastre-se →
            </button>
          </div>
        </nav>
        <section className="hero">
          <motion.img
            key={slide}
            className="hero-photo"
            src={heroImgs[slide]}
            alt="Paisagem agrícola ao nascer do sol"
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
            <small>INTELIGÊNCIA QUE VEM DO ESPAÇO</small>
            <h1>
              {
                [
                  "O futuro da sua\nlavoura começa aqui.",
                  "Um novo olhar\npara a sua terra.",
                  "Da observação\nà próxima safra.",
                ][slide]
              }
            </h1>
            <p>
              Transforme dados espaciais em decisões inteligentes para sua
              propriedade.
            </p>
            <div>
              <button className="button yellow" onClick={() => go("signup")}>
                Começar gratuitamente →
              </button>
              <button className="button outline" onClick={() => go("overview")}>
                Conhecer a plataforma
              </button>
            </div>
          </div>
          <div className="carousel-controls">
            <div>
              {heroImgs.map((_, i) => (
                <button
                  key={i}
                  aria-label={"Ir para imagem " + (i + 1)}
                  aria-pressed={slide === i}
                  className={slide === i ? "active" : ""}
                  onClick={() => setSlide(i)}
                />
              ))}
              <small>0{slide + 1} / 03</small>
            </div>
            <div>
              <button
                aria-label="Imagem anterior"
                onClick={() => setSlide((slide + 2) % 3)}
              >
                ‹
              </button>
              <button
                aria-label="Próxima imagem"
                onClick={() => setSlide((slide + 1) % 3)}
              >
                ›
              </button>
            </div>
          </div>
        </section>
        <section className="landing-intro" id="produto">
          <small>UM OLHAR COMPLETO. SEM COMPLICAÇÃO.</small>
          <h2>
            Conheça sua terra
            <br />
            como nunca antes.
          </h2>
          <p>
            Clima, solo e vegetação. Conectados para abrir novas
            <br />
            possibilidades no campo.
          </p>
          <button
            className="product-preview"
            onClick={() => go("overview")}
            aria-label="Explorar painel NATIVA"
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
                "Visão Geral",
                "Minha Propriedade",
                "Análise Climática",
                "Histórico de Cultivo",
                "Estratégias de Rotação",
              ].map((t) => (
                <span key={t}>{t}</span>
              ))}
            </aside>
            <div className="preview-main">
              <h3>Visão Geral da Propriedade</h3>
              <small>Sua terra, uma nova perspectiva</small>
              <div className="preview-metrics">
                {["24,8 °C", "142 mm", "32 %", "0,76 NDVI"].map((t) => (
                  <div key={t}>
                    {t}
                    <small>Indicador demonstrativo</small>
                  </div>
                ))}
              </div>
              <div className="preview-bottom">
                <img
                  className="preview-map"
                  src={L.imgMapaAgricola}
                  alt="Mapa agrícola ilustrativo"
                />
                <div>
                  <div className="preview-chart">
                    <img src={L.imgSerieClimaticaDemonstrativa} alt="" />
                    <img src={L.imgSerieClimaticaDemonstrativa1} alt="" />
                  </div>
                  <div className="preview-note">
                    Explore as oportunidades da sua próxima safra.
                  </div>
                </div>
              </div>
            </div>
          </button>
          <p className="green-text">
            Sua propriedade no centro. Dados que ampliam sua visão.
          </p>
          <small>Conheça a experiência →</small>
        </section>
        <section className="how-it-works" id="como-funciona">
          <small>SIMPLES DE USAR. AMPLO EM POSSIBILIDADES.</small>
          <h2>Da observação à decisão.</h2>
          <div className="steps">
            {[
              [
                "Localize sua propriedade.",
                "Comece pela sua terra. Informe onde você cultiva e o seu contexto.",
                L.imgIconeDoPasso1,
              ],
              [
                "Explore as condições ambientais.",
                "Veja clima, umidade e vegetação com uma nova perspectiva.",
                L.imgIconeDoPasso2,
              ],
              [
                "Compare estratégias de rotação.",
                "Explore caminhos para o próximo ciclo com as suas prioridades.",
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
            Comece pela nossa propriedade →
          </LinkButton>
        </section>
        <section className="space-section" id="tecnologia">
          <img
            src={L.imgFotografiaComZoomSuave1}
            alt="A Terra vista do espaço"
          />
          <div>
            <small>TECNOLOGIA NASA. CONTEXTO LOCAL.</small>
            <h2>
              Uma nova perspectiva
              <br />
              sobre sua lavoura.
            </h2>
            <h3>
              A observação da Terra nos ajuda a enxergar além do que está à
              vista.
            </h3>
            <p>
              A NATIVA utiliza dados de observação da NASA para explorar
              condições ambientais e apoiar decisões agrícolas, integrando o
              espaço, o contexto e a realidade da sua propriedade.
            </p>
            <LinkButton onClick={() => open("technology")}>
              Conheça nossa tecnologia →
            </LinkButton>
            <div className="source-chips">
              {["POWER", "SMAP", "MODIS"].map((s) => (
                <span key={s}>
                  {s}
                  <small>NASA · referência</small>
                </span>
              ))}
            </div>
          </div>
        </section>
        <section className="about-section">
          <div>
            <small>SOBRE O PROJETO</small>
            <h2>
              Tecnologia espacial.
              <br />
              Propósito no campo.
            </h2>
          </div>
          <div>
            <p>
              Desenvolvido para o NASA Space Apps Challenge 2026, a NATIVA
              explora novas formas de usar dados de observação da Terra para
              ampliar as possibilidades do produtor rural.
            </p>
            <LinkButton onClick={() => open("technology")}>
              Ciência aberta. Possibilidades para o campo.
            </LinkButton>
          </div>
        </section>
        <section className="landing-cta">
          <img src={L.imgFotografiaComZoomSuave2} alt="Campos de cultivo" />
          <div>
            <small>DO SEU CAMPO PARA O FUTURO.</small>
            <h2>
              Sua próxima safra começa
              <br />
              com uma decisão.
            </h2>
            <p>Descubra novas possibilidades para sua propriedade.</p>
            <button className="button yellow" onClick={() => go("signup")}>
              Começar gratuitamente →
            </button>
            <small>Explore a demonstração gratuitamente.</small>
          </div>
        </section>
        <footer>
          <Logo />
          <div>
            <button onClick={() => open("technology")}>Sobre o projeto</button>
            <button onClick={() => open("technology")}>Tecnologia</button>
            <button onClick={() => open("contact")}>Contato</button>
          </div>
          <small>NASA Space Apps Challenge 2026</small>
          <small>
            Protótipo demonstrativo • dados fictícios e cenários sem validação
            local.
          </small>
        </footer>
      </div>
    );
  }
  function Signup() {
    return (
      <div className="signup">
        <section className="signup-photo">
          <img src={L.imgFotografiaComZoomSuave2} alt="Fazenda ao amanhecer" />
          <Logo />
          <div>
            <h1>
              Sua terra merece
              <br />
              um novo olhar.
            </h1>
            <p>
              Da observação do espaço às possibilidades
              <br />
              da sua próxima safra.
            </p>
          </div>
        </section>
        <section className="signup-form">
          <button className="back-link" onClick={() => go("landing")}>
            Voltar ao início
          </button>
          <small>01 / 02 • SEU CADASTRO</small>
          <h1>
            Comece pela sua
            <br />
            propriedade.
          </h1>
          <p>Uma visão mais ampla começa com o seu contexto.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              go("onboard");
            }}
          >
            <label className="field">
              <span>Seu nome</span>
              <input
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>E-mail</span>
              <input type="email" placeholder="produtor@example.com" />
            </label>
            <Field label="Nome da propriedade" name="name" />
            <div className="signup-location">
              <Field label="Cidade / UF" name="city" />
              <Field
                label="Área (ha) • opcional"
                name="area"
                type="number"
                min={0.01}
                step="any"
              />
            </div>
            <button className="button yellow" type="submit">
              Continuar →
            </button>
            <small>
              Ambiente demonstrativo. Nenhuma conta será criada ou armazenada.
            </small>
          </form>
          <LinkButton onClick={() => open("login")}>
            Já conhece a NATIVA? Entrar
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
            Voltar ao cadastro
          </LinkButton>
        </header>
        <div className="onboard-grid">
          <section>
            <small>02 / 02 • SUA PROPRIEDADE</small>
            <h1>
              Vamos conhecer
              <br />a sua terra.
            </h1>
            <p>Confirme o contexto para explorar a plataforma.</p>
            <div className="onboard-map">
              <img
                src={assets["13:478"].imgLocalizacaoDemonstrativa}
                alt="Localização demonstrativa"
              />
              <span>
                ⌖ {draft.name}
                <small>
                  {draft.city} · {draft.area} ha · exemplo
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
                `Bem-vinda, ${userName.split(" ")[0]}. Explore sua propriedade!`,
              );
            }}
          >
            <Field
              label="Cultura atual"
              name="crop"
              options={["Soja", "Milho", "Sorgo", "Café", "Trigo", "Outra"]}
            />
            <Field
              label="Textura do solo"
              name="texture"
              options={["Argiloso", "Arenoso", "Franco", "Não informado"]}
            />
            <Field
              label="Disponibilidade de irrigação"
              name="irrigation"
              options={["Sim", "Não", "Não informado"]}
            />
            <button className="button yellow" type="submit">
              Explorar plataforma →
            </button>
            <small>
              Fluxo demonstrativo. As condições não representam uma fazenda
              real.
            </small>
          </form>
        </div>
      </div>
    );
  }
  function AddCrop() {
    const [value, setValue] = useState({
      crop: "Milho",
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
            setError("A colheita deve ocorrer após o plantio.");
            return;
          }
          setCrops((p) => [
            {
              ...value,
              id: Date.now(),
              season: value.plant.slice(0, 4),
              status: value.yield ? "Concluído" : "Planejado",
            },
            ...p,
          ]);
          setModal(null);
          toast("Cultivo adicionado nesta sessão.");
        }}
      >
        <h2>Adicionar cultivo</h2>
        <p>Registre um exemplo para explorar o histórico da propriedade.</p>
        <div className="fields-grid">
          <label className="field">
            <span>Cultura</span>
            <select
              value={value.crop}
              onChange={(e) =>
                setValue((v) => ({ ...v, crop: e.target.value }))
              }
            >
              {[
                "Milho",
                "Soja",
                "Sorgo",
                "Crotalária",
                "Braquiária",
                "Trigo",
              ].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Talhão</span>
            <select>
              <option>Talhão 01</option>
            </select>
          </label>
          {(["plant", "harvest", "area", "yield"] as const).map((key, i) => (
            <label className="field" key={key}>
              <span>
                {
                  [
                    "Data de plantio",
                    "Data de colheita • prevista",
                    "Área cultivada (ha)",
                    "Produtividade (sc/ha) • opcional",
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
        <p>As datas podem coexistir com outros cultivos no mesmo ano.</p>
        <button type="submit" className="button">
          Salvar cultivo
        </button>
        <small>Dados mantidos somente nesta sessão.</small>
      </form>
    );
  }
  function ModalContent() {
    if (modal === "addCrop") return <AddCrop />;
    if (modal === "map")
      return (
        <>
          <h2>Mapa • {layer}</h2>
          <p>Camada demonstrativa • valores e áreas sem georreferenciamento.</p>
          <Map expanded />
        </>
      );
    if (typeof modal === "number") {
      const s = scenarios[modal];
      return (
        <>
          <h2>{s.name}</h2>
          <h3>{s.sequence}</h3>
          <h3>Fundamento agronômico</h3>
          <p>{s.detail}</p>
          <h3>Benefício potencial</h3>
          <p>{s.benefit}</p>
          <h3>Riscos e condições</h3>
          <p>{s.risk}</p>
          <small>
            Hipóteses gerais, sem validação para esta propriedade fictícia.
          </small>
          <Btn onClick={() => open(null)}>Voltar</Btn>
        </>
      );
    }
    if (modal === "account")
      return (
        <>
          <h2>Sua conta</h2>
          <h3>Perfil de demonstração</h3>
          <p>
            Explore a experiência sem criar uma conta real. As alterações ficam
            somente nesta sessão.
          </p>
          <LinkButton onClick={() => go("settings")}>
            Configurações da conta →
          </LinkButton>
        </>
      );
    if (modal === "property")
      return (
        <>
          <h2>Selecionar propriedade</h2>
          <button className="property-choice" onClick={() => open(null)}>
            <strong>{farm.name} ✓</strong>
            <small>
              {farm.city} • {farm.area} ha
            </small>
          </button>
          <p>Uma propriedade está disponível nesta demonstração.</p>
          <LinkButton onClick={() => go("farm")}>
            Editar propriedade →
          </LinkButton>
        </>
      );
    if (modal === "login")
      return (
        <>
          <h2>Bem-vinda à NATIVA</h2>
          <p>
            Entre na experiência demonstrativa. Nenhuma autenticação ou conta
            real é necessária.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              go("overview");
            }}
          >
            <label className="field">
              <span>E-mail • opcional</span>
              <input type="email" placeholder="produtor@example.com" />
            </label>
            <button type="submit" className="button yellow">
              Explorar demonstração →
            </button>
          </form>
        </>
      );
    if (modal === "contact")
      return (
        <>
          <h2>Vamos conversar?</h2>
          <p>Formulário demonstrativo: esta versão não envia mensagens.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              toast("Demonstração concluída. Nenhuma mensagem foi enviada.");
              open(null);
            }}
          >
            <label className="field">
              <span>Seu nome</span>
              <input required placeholder="Seu nome" />
            </label>
            <label className="field">
              <span>Seu e-mail</span>
              <input required type="email" placeholder="produtor@example.com" />
            </label>
            <label className="field">
              <span>Sua mensagem</span>
              <textarea required placeholder="Quero conhecer a NATIVA." />
            </label>
            <button className="button yellow" type="submit">
              Concluir demonstração
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
          <Btn onClick={() => open(null)}>Entendi</Btn>
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
              aria-label="Fechar navegação"
              onClick={() => setMenu(false)}
            />
          )}
          <aside className={"sidebar " + (menu ? "shown" : "")}>
            <Logo />
            <small className="nav-section">PRINCIPAL</small>
            <nav>
              {navItems.map(([id, label, img], i) => (
                <React.Fragment key={id}>
                  {i === 3 && (
                    <small className="nav-section planning">PLANEJAMENTO</small>
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
                Configurações
              </button>
              <button onClick={() => open("help")}>
                <img src={A.imgIconeAjuda} alt="" />
                Ajuda
              </button>
              <LinkButton onClick={() => go("landing")}>
                Voltar ao início ↗
              </LinkButton>
            </div>
          </aside>
          <header className="topbar">
            <button
              className="mobile-menu"
              aria-label="Abrir navegação"
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
              aria-label="Minha conta"
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
          <button aria-label="Fechar notificação" onClick={() => setNotice("")}>
            ×
          </button>
        </div>
      )}
      {inDashboard && <span className="sr-only">Demonstração NATIVA</span>}
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
      aria-label="Detalhes NATIVA"
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
      <button className="close-modal" aria-label="Fechar" onClick={onClose}>
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
