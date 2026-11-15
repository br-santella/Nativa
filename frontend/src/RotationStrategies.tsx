// "Estratégias de Rotação": the engine's result explained to the farmer.
// 01 priorities (from the setup, editable) -> 02 the options chosen in the setup -> 03 current rotation vs one option.
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, health, recomendacao } from "./api";
import type { DataOrigem, Health, ItemRanking, Lang, Pesos, Recomendacao } from "./api";
import type { SetupInputs } from "./PropertyWizard";
import type { Farm } from "./data";
import { useLanguage } from "./i18n";
import { rotacaoDoHistorico } from "./rotacaoAtual";
import { CRITERIA, PRIORITIES, matchPriority } from "./priorities";
import type { PriorityId } from "./priorities";
import "./rotation-strategies.css";

const DEMO_FIELD = "72638";
const RECALC_DELAY_MS = 600;
const CURRENT_COLOR = "#9fb3b6";
const OPTION_COLOR = "#ffbf22";

type Crop = { crop: string; plant: string; harvest?: string };
type Props = {
  inputs?: SetupInputs;
  farm: Farm;
  crops: Crop[];
  /** Persists edited weights in the app state, so they survive leaving the page. */
  onPesosChange?: (pesos: Pesos) => void;
  onEditSetup: () => void;
  onSources: () => void;
};

/** Inputs used when the user reaches this page without going through the setup wizard. */
function fallbackInputs(farm: Farm, crops: Crop[]): SetupInputs {
  const lat = Number(farm.latitude), lon = Number(farm.longitude);
  const valid = farm.latitude.trim() !== "" && farm.longitude.trim() !== "" && Number.isFinite(lat) && Number.isFinite(lon);
  const current = rotacaoDoHistorico(crops);
  return {
    area: valid ? { lat, lon } : { talhao_id: DEMO_FIELD },
    rotacao_atual: current.id,
    pesos: PRIORITIES[0].pesos,
    n_alternativas: 3,
    data_referencia: new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" }),
    problemas_area: [],
    restricoes: { sem_comprador: [], maquinas: { plataforma_milho: true, semeadora_consorcio: true } },
    // "Não informado" leaves the field out, so the engine uses its default.
    irrigacao: (farm.irrigation === "Sim" ? { disponivel: true } : farm.irrigation === "Não" ? { disponivel: false } : undefined) as SetupInputs["irrigacao"],
    ...(current.colheitaPrevista ? { colheita_prevista: current.colheitaPrevista } : {}),
  };
}

const score = (v: number | null | undefined) => (v == null ? null : Math.round(v * 100));

export default function RotationStrategies({ inputs, farm, crops, onPesosChange, onEditSetup, onSources }: Props) {
  const { language } = useLanguage();
  const en = language === "en";
  const lang: Lang = en ? "en" : "pt-BR";
  const say = (pt: string, english: string) => (en ? english : pt);
  const tx = (text: { pt: string; en: string }) => (en ? text.en : text.pt);
  const money = (v: number) => `R$ ${Math.round(v).toLocaleString(en ? "en-US" : "pt-BR")}`;
  const signedMoney = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v))}`;

  const base = useMemo(() => inputs ?? fallbackInputs(farm, crops), [inputs, farm, crops]);

  // 01 · priorities: edits apply automatically after a short pause.
  const [pesos, setPesos] = useState<Pesos>(base.pesos);
  const [priority, setPriority] = useState<PriorityId | "custom">(() => matchPriority(base.pesos));
  const [committed, setCommitted] = useState<Pesos>(base.pesos);
  const persist = useRef(onPesosChange);
  persist.current = onPesosChange;
  // Last weights handed to the app state; pending edits are flushed when the page unmounts.
  const saved = useRef(JSON.stringify(base.pesos));
  const latest = useRef(pesos);
  latest.current = pesos;
  const save = (value: Pesos) => {
    const key = JSON.stringify(value);
    if (key === saved.current) return;
    saved.current = key;
    persist.current?.(value);
  };
  useEffect(() => {
    const id = setTimeout(() => { setCommitted(pesos); save(pesos); }, RECALC_DELAY_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pesos]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => save(latest.current), []);
  const chooseProfile = (id: PriorityId) => { setPriority(id); setPesos(PRIORITIES.find(p => p.id === id)!.pesos); };
  const setWeight = (id: keyof Pesos, value: number) => { setPriority("custom"); setPesos(current => ({ ...current, [id]: value })); };
  const pending = JSON.stringify(pesos) !== JSON.stringify(committed);

  // Engine call: one request per distinct body (weights, setup and language).
  const body = useMemo(() => ({ ...base, pesos: committed }), [base, committed]);
  const requestKey = JSON.stringify(body) + lang;
  const [api, setApi] = useState<Health | null>(null);
  const [res, setRes] = useState<Recomendacao | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    health(lang)
      .then(h => {
        if (!active) return null;
        setApi(h);
        if (h.status !== "ok") return null;
        return recomendacao({ area: body.area, rotacaoAtual: body.rotacao_atual, pesos: body.pesos, colheitaPrevista: body.colheita_prevista, irrigacao: body.irrigacao }, lang, body);
      })
      .then(r => { if (active) setRes(r); })
      .catch((e: unknown) => {
        if (!active) return;
        setRes(null);
        setError(e instanceof ApiError ? e : new ApiError(0, "erro", String(e)));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const current = res?.atual ?? null;
  const block = res?.agora ?? (res ? { ranking: res.ranking, alternativas: res.alternativas, eliminadas: res.eliminadas } : null);
  const options = block ? block.alternativas.slice(0, base.n_alternativas) : [];
  const evaluated = block?.ranking.length ?? 0;

  // 03 · comparison target (defaults to the best option).
  const [compareId, setCompareId] = useState<string | null>(null);
  const target = options.find(o => o.id === compareId) ?? options[0] ?? null;
  const compareRef = useRef<HTMLElement>(null);
  const compareWith = (id: string) => { setCompareId(id); compareRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  const origin = (o: DataOrigem["origem"]) => ({
    estagio: say("pelo estágio da lavoura", "from the crop stage"),
    informada: say("informada por você", "provided by you"),
    derivada: say("logo após a colheita prevista", "right after the expected harvest"),
    premissa: say("estimativa de calendário", "calendar estimate"),
  })[o] ?? o;

  const currentScore = score(current?.nota);
  const statusLine = error?.codigo === "sem_conexao" ? null : (loading || pending) && res ? say("Atualizando resultados…", "Updating results…") : null;

  return <div className="rs">
   {/* Context: what the engine is working with. */}
   <section className="rs-context" aria-label={say("Seus dados", "Your data")}>
    <div><span>{say("Sua área", "Your land")}</span><strong>{farm.name || say("Sua propriedade", "Your farm")}</strong><small>{[farm.city, farm.area && `${Number.isFinite(Number(farm.area)) ? Number(farm.area).toLocaleString(en ? "en-US" : "pt-BR", { maximumFractionDigits: 1 }) : farm.area} ha`].filter(Boolean).join(" · ")}</small></div>
    <div><span>{say("Rotação atual", "Current rotation")}</span><strong>{current?.rotacao ?? "—"}</strong><small>{res?.colheita_estimada ? say(`Colheita do verão ~${res.colheita_estimada.data}`, `Summer harvest ~${res.colheita_estimada.data}`) : say("Do seu cadastro", "From your setup")}</small></div>
    <div><span>{say("Semeadura da 2ª safra", "Second-crop sowing")}</span><strong>{res?.semeadura_2a?.data ?? "—"}</strong><small>{res?.semeadura_2a ? origin(res.semeadura_2a.origem) : ""}</small></div>
    <button type="button" className="rs-link-button" onClick={onEditSetup}>{say("Editar cadastro", "Edit setup")}</button>
   </section>

   {/* 01 · priorities */}
   <section className="rs-section">
    <header className="rs-heading"><span className="rs-step">01</span><div><h2>{say("O que mais importa na sua safra", "What matters most this season")}</h2><p>{say("Veio do seu cadastro. Se mudar aqui, os resultados se atualizam sozinhos.", "This comes from your setup. Change it here and the results update on their own.")}</p></div></header>
    <div className="rs-profiles">
     {PRIORITIES.map(p => <button key={p.id} type="button" className={"rs-profile" + (priority === p.id ? " is-selected" : "")} aria-pressed={priority === p.id} onClick={() => chooseProfile(p.id)}>
      <span className="rs-profile-icon" aria-hidden="true">{p.icon}</span><span><strong>{tx(p.title)}</strong><small>{tx(p.description)}</small></span>
     </button>)}
    </div>
    <details className="rs-adjust" open={priority === "custom"}>
     <summary>{priority === "custom" ? say("Ajuste do seu jeito · em uso", "Your own balance · in use") : say("Ajuste do seu jeito", "Make it your own")}</summary>
     <div className="rs-sliders">
      {CRITERIA.map(c => <label key={c.id} className="rs-slider">
       <span><strong>{tx(c.name)}</strong><output>{pesos[c.id]}<small>/10</small></output></span>
       <input type="range" min="0" max="10" value={pesos[c.id]} onChange={e => setWeight(c.id, Number(e.target.value))}/>
       <small>{tx(c.hint)}</small>
      </label>)}
     </div>
    </details>
   </section>

   {/* 02 · options */}
   <section className="rs-section">
    <header className="rs-heading"><span className="rs-step">02</span><div>
     <h2>{say("Suas opções", "Your options")}</h2>
     <p>{say(`As ${base.n_alternativas} alternativas com maior nota para as suas prioridades, ao lado da rotação que você usa hoje. A nota vai de 0 a 100 e junta os cinco critérios com os pesos acima.`,
      `The ${base.n_alternativas} alternatives with the highest score for your priorities, next to the rotation you use today. The score goes from 0 to 100 and combines the five criteria with the weights above.`)}</p>
    </div></header>
    {statusLine && <p className="rs-status" role="status">{statusLine}</p>}
    {!res ? <Placeholder error={error} degraded={api != null && api.status !== "ok"} en={en}/> : <>
     {current && <article className="rs-current">
      <div className="rs-current-label">{say("Sua rotação hoje", "Your rotation today")}</div>
      <h3>{current.rotacao}</h3>
      {current.eliminada
       ? <p className="rs-warning">{say("Eliminada pelas regras: ", "Ruled out: ")}{(current.motivos ?? []).join(" ")}</p>
       : <div className="rs-current-facts">
         <span><strong>{currentScore}</strong>/100</span>
         {current.posicao != null && evaluated > 0 && <span>{say(`${current.posicao}ª entre ${evaluated} avaliadas`, `#${current.posicao} of ${evaluated} evaluated`)}</span>}
         {current.margem && <span>{say("Margem estimada", "Estimated margin")} <strong>{money(current.margem.total_r_ha)}</strong>/ha</span>}
        </div>}
     </article>}
     {options.length === 0 && <p className="rs-empty">{say("O motor não encontrou alternativas válidas para esta área com o seu cadastro.", "The engine found no valid alternatives for this land with your setup.")}</p>}
     <ol className="rs-options">
      {options.map((o, i) => <OptionCard key={o.id} item={o} rank={i + 1} current={current} en={en} money={money} signedMoney={signedMoney} onCompare={() => compareWith(o.id)} selected={target?.id === o.id}/>)}
     </ol>
    </>}
   </section>

   {/* 03 · comparison */}
   {res && current && target && <section className="rs-section" ref={compareRef}>
    <header className="rs-heading"><span className="rs-step">03</span><div>
     <h2>{say("Compare lado a lado", "Compare side by side")}</h2>
     <p>{say("Sua rotação de hoje contra uma das opções, critério por critério.", "Your current rotation against one of the options, criterion by criterion.")}</p>
    </div></header>
    <div className="rs-pills" role="radiogroup" aria-label={say("Opção para comparar", "Option to compare")}>
     {options.map((o, i) => <label key={o.id}><input type="radio" name="compare" checked={target.id === o.id} onChange={() => setCompareId(o.id)}/><span>#{i + 1} {o.rotacao}</span></label>)}
    </div>
    <Comparison current={current} option={target} rank={options.indexOf(target) + 1} en={en} money={money} signedMoney={signedMoney}/>
   </section>}

   {/* Notes */}
   {res && res.avisos.length > 0 && <details className="rs-notes">
    <summary>{say(`Avisos do motor (${res.avisos.length})`, `Engine notes (${res.avisos.length})`)}</summary>
    <ul>{res.avisos.map(a => <li key={a}>{a}</li>)}</ul>
   </details>}
   <footer className="rs-footer">
    <p>{say("Valores estimados com dados NASA POWER, SoilGrids, MapBiomas e IBGE. Nenhum cenário é uma recomendação absoluta: confirme com assistência agronômica antes de decidir.",
     "Estimates based on NASA POWER, SoilGrids, MapBiomas and IBGE data. No scenario is an absolute recommendation: check with an agronomist before deciding.")}</p>
    <button type="button" className="rs-link-button" onClick={onSources}>{say("Ver premissas e limitações →", "See assumptions and limitations →")}</button>
   </footer>
  </div>;
}

function Placeholder({ error, degraded, en }: { error: ApiError | null; degraded: boolean; en: boolean }) {
  const say = (pt: string, english: string) => (en ? english : pt);
  if (error) return <p className="rs-error" role="alert">{error.codigo === "fora_da_regiao"
    ? `${error.message} ${say("Ajuste a área no cadastro para um ponto no Paraná.", "Set the land in your setup to a point in Paraná.")}`
    : error.codigo === "sem_conexao" ? say("Não foi possível conectar ao motor agora. Tente de novo em instantes.", "Could not reach the engine right now. Try again in a moment.") : error.message}</p>;
  if (degraded) return <p className="rs-error" role="alert">{say("O motor está sem os dados necessários no momento. Tente novamente mais tarde.", "The engine is missing the data it needs right now. Please try again later.")}</p>;
  return <div className="rs-loading" role="status"><span/>{say("Calculando as opções para a sua área…", "Working out the options for your land…")}</div>;
}

type MoneyFns = { money: (v: number) => string; signedMoney: (v: number) => string };

function Delta({ value, unit = "", en }: { value: number; unit?: string; en: boolean }) {
  const cls = value > 0 ? "is-up" : value < 0 ? "is-down" : "is-same";
  const text = value === 0 ? (en ? "same" : "igual") : `${value > 0 ? "+" : "−"}${Math.abs(value)}${unit}`;
  return <span className={"rs-delta " + cls}>{text}</span>;
}

function OptionCard({ item, rank, current, en, money, signedMoney, onCompare, selected }: { item: ItemRanking; rank: number; current: ItemRanking | null; en: boolean; onCompare: () => void; selected: boolean } & MoneyFns) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const [open, setOpen] = useState(false);
  const s = score(item.nota) ?? 0;
  const cs = current && !current.eliminada ? score(current.nota) : null;
  const marginDiff = item.margem && current?.margem ? item.margem.total_r_ha - current.margem.total_r_ha : null;
  const benefit = item.card?.beneficios[0];
  const attention = item.card?.riscos[0];
  return <li className={"rs-option" + (selected ? " is-compared" : "")}>
   <div className="rs-option-main">
    <span className="rs-rank" aria-label={say(`Opção ${rank}`, `Option ${rank}`)}>#{rank}</span>
    <div className="rs-option-title">
     <h3>{item.rotacao}</h3>
     <div className="rs-scoreline">
      <span className="rs-score"><strong>{s}</strong>/100</span>
      {cs != null && <span className="rs-vs">{say("vs. hoje", "vs. today")} <Delta value={s - cs} unit={say(" pts", " pts")} en={en}/></span>}
     </div>
     <div className="rs-bar" aria-hidden="true"><span style={{ width: `${s}%` }}/>{cs != null && <i style={{ left: `${cs}%` }} title={say("Sua rotação hoje", "Your rotation today")}/>}</div>
    </div>
    <div className="rs-money">
     <span>{say("Margem estimada", "Estimated margin")}</span>
     <strong>{item.margem ? `${money(item.margem.total_r_ha)}/ha` : "—"}</strong>
     {marginDiff != null && <small className={marginDiff >= 0 ? "is-up" : "is-down"}>{signedMoney(marginDiff)}/ha {say("vs. hoje", "vs. today")}</small>}
    </div>
   </div>
   <div className="rs-option-notes">
    {benefit && <p className="rs-benefit"><span aria-hidden="true">✓</span>{benefit}</p>}
    {attention && <p className="rs-attention"><span aria-hidden="true">!</span>{attention}</p>}
   </div>
   <div className="rs-mini-criteria">
    {CRITERIA.map(c => { const v = score(item.criterios?.[c.id]) ?? 0; return <div key={c.id} title={en ? c.hint.en : c.hint.pt}><span>{en ? c.name.en : c.name.pt}</span><div className="rs-mini-bar"><span style={{ width: `${v}%` }}/></div><small>{v}</small></div>; })}
   </div>
   {open && item.card && <div className="rs-details">
    <p>{item.card.por_que}</p>
    {item.card.evidencias.length > 0 && <><h4>{say("De onde vêm esses números", "Where these numbers come from")}</h4><ul>{item.card.evidencias.map(e => <li key={e}>{e}</li>)}</ul></>}
    {item.card.lacunas.length > 0 && <><h4>{say("O que ainda falta saber", "What is still unknown")}</h4><ul>{item.card.lacunas.map(e => <li key={e}>{e}</li>)}</ul></>}
   </div>}
   <div className="rs-option-actions">
    <button type="button" className="rs-link-button" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? say("Ocultar detalhes", "Hide details") : say("Ver detalhes", "See details")}</button>
    <button type="button" className="rs-compare-button" onClick={onCompare}>{say("Comparar com a de hoje →", "Compare with today’s →")}</button>
   </div>
  </li>;
}

function Comparison({ current, option, rank, en, money, signedMoney }: { current: ItemRanking; option: ItemRanking; rank: number; en: boolean } & MoneyFns) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const cs = score(current.nota), os = score(option.nota) ?? 0;
  const rows: { label: string; hint?: string; a: ReactNode; b: ReactNode; diff: ReactNode }[] = [];
  rows.push({ label: say("Nota geral", "Overall score"), hint: say("Média ponderada com as suas prioridades", "Weighted with your priorities"),
    a: cs != null ? <Bar value={cs} color={CURRENT_COLOR}/> : "—", b: <Bar value={os} color={OPTION_COLOR}/>, diff: cs != null ? <Delta value={os - cs} en={en}/> : null });
  for (const c of CRITERIA) {
    const a = score(current.criterios?.[c.id]), b = score(option.criterios?.[c.id]);
    rows.push({ label: en ? c.name.en : c.name.pt, hint: en ? c.hint.en : c.hint.pt,
      a: a != null ? <Bar value={a} color={CURRENT_COLOR}/> : "—", b: b != null ? <Bar value={b} color={OPTION_COLOR}/> : "—", diff: a != null && b != null ? <Delta value={b - a} en={en}/> : null });
  }
  const moneyRow = (label: string, hint: string, a?: number, b?: number) => rows.push({ label, hint,
    a: a != null ? <span className="rs-money-cell">{money(a)}</span> : "—", b: b != null ? <span className="rs-money-cell">{money(b)}</span> : "—",
    diff: a != null && b != null ? <span className={"rs-delta " + (b - a > 0 ? "is-up" : b - a < 0 ? "is-down" : "is-same")}>{signedMoney(b - a)}</span> : null });
  moneyRow(say("Renda da 2ª safra", "Second-crop income"), say("R$/ha, só a cultura que entra depois da colheita", "BRL/ha, only the crop after the harvest"), current.margem?.incremental_r_ha, option.margem?.incremental_r_ha);
  moneyRow(say("Margem da rotação no ano", "Yearly rotation margin"), say("R$/ha, verão + 2ª safra", "BRL/ha, summer + second crop"), current.margem?.total_r_ha, option.margem?.total_r_ha);

  return <div className="rs-compare">
   <div className="rs-compare-table" role="table" aria-label={say("Comparação critério por critério", "Criterion by criterion comparison")}>
    <div className="rs-compare-head" role="row">
     <span role="columnheader"/>
     <span role="columnheader"><em><i style={{ background: CURRENT_COLOR }}/>{say("Hoje", "Today")}</em><small>{current.rotacao}</small></span>
     <span role="columnheader"><em><i style={{ background: OPTION_COLOR }}/>{say(`Opção #${rank}`, `Option #${rank}`)}</em><small>{option.rotacao}</small></span>
     <span role="columnheader">{say("Diferença", "Difference")}</span>
    </div>
    {rows.map(r => <div className="rs-compare-row" role="row" key={r.label}>
     <span role="rowheader"><strong>{r.label}</strong>{r.hint && <small>{r.hint}</small>}</span>
     <span role="cell">{r.a}</span><span role="cell">{r.b}</span><span role="cell">{r.diff}</span>
    </div>)}
   </div>
   <div className="rs-compare-side">
    <Radar current={current} option={option} en={en}/>
    {option.card?.por_que && <div className="rs-what-changes"><h4>{say("O que muda, segundo o motor", "What changes, according to the engine")}</h4><p>{option.card.por_que}</p></div>}
    <div className="rs-lists">
     {(option.card?.beneficios.length ?? 0) > 0 && <div><h4>{say("Pontos a favor", "In favour")}</h4><ul className="rs-benefits">{option.card!.beneficios.map(b => <li key={b}>{b}</li>)}</ul></div>}
     {(option.card?.riscos.length ?? 0) > 0 && <div><h4>{say("Pontos de atenção", "Watch out for")}</h4><ul className="rs-risks">{option.card!.riscos.map(b => <li key={b}>{b}</li>)}</ul></div>}
    </div>
   </div>
  </div>;
}

function Bar({ value, color }: { value: number; color: string }) {
  return <span className="rs-cell-bar"><span className="rs-cell-track"><span style={{ width: `${value}%`, background: color }}/></span><b>{value}</b></span>;
}

/** Radar of the five criteria for the current rotation and the compared option. */
function Radar({ current, option, en }: { current: ItemRanking; option: ItemRanking; en: boolean }) {
  const c = 130, r = 92;
  const point = (i: number, v: number) => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / CRITERIA.length; return [c + Math.cos(a) * r * v, c + Math.sin(a) * r * v]; };
  const polygon = (values: number[]) => values.map((v, i) => point(i, v).join(",")).join(" ");
  const values = (it: ItemRanking) => CRITERIA.every(k => typeof it.criterios?.[k.id] === "number") ? CRITERIA.map(k => it.criterios![k.id]) : null;
  const a = current.eliminada ? null : values(current), b = values(option);
  return <svg className="rs-radar" viewBox="-40 -6 340 272" role="img" aria-label={en ? "Radar of the five criteria" : "Radar dos cinco critérios"}>
   {[0.25, 0.5, 0.75, 1].map(f => <polygon key={f} points={polygon(CRITERIA.map(() => f))} fill="none" stroke="#2d4a3f"/>)}
   {CRITERIA.map((k, i) => { const [x, y] = point(i, 1), [lx, ly] = point(i, 1.2); return <g key={k.id}><line x1={c} y1={c} x2={x} y2={y} stroke="#2d4a3f"/><text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="#a5b8a6">{en ? k.name.en : k.name.pt}</text></g>; })}
   {a && <polygon points={polygon(a)} fill={CURRENT_COLOR} fillOpacity={0.12} stroke={CURRENT_COLOR} strokeWidth={2} strokeDasharray="5 4"/>}
   {b && <polygon points={polygon(b)} fill={OPTION_COLOR} fillOpacity={0.16} stroke={OPTION_COLOR} strokeWidth={2}/>}
  </svg>;
}
