// "Entender este cenário": one option explained in layers, from a plain summary to the engine's technical notes.
// Summary -> how the score is built (vs. today) -> how far to trust it -> benefits and attention -> collapsed details.
import { useEffect, useRef } from "react";
import type { Bloco, ItemRanking } from "./api";
import { CRITERIA, levelLabel } from "./priorities";

type Props = {
  item: ItemRanking;
  /** Today's rotation, for the comparison markers (null when `item` is today's rotation or it was ruled out). */
  current: ItemRanking | null;
  block: Bloco | null;
  rank: number;
  evaluated: number;
  en: boolean;
  money: (v: number) => string;
  onClose: () => void;
  /** Closes the window and opens the side-by-side comparison with today's rotation. */
  onCompare?: () => void;
};

const pct = (v: number) => Math.round(v * 100);

export default function ScenarioDetail({ item, current, block, rank, evaluated, en, money, onClose, onCompare }: Props) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  const baseline = !item.atual && current && !current.eliminada ? current : null;
  const uncertainty = item.incerteza;
  const card = item.card;
  const seasons = Object.entries(uncertainty?.nota_por_safra ?? {}).sort(([a], [b]) => a.localeCompare(b));
  const stability = block?.estabilidade;
  const firstIn = stability ? stability.primeiro.find(p => p.id === item.id)?.safras ?? 0 : null;
  const tie = block?.empate_tecnico && block.empate_tecnico.ids.includes(item.id) ? block.empate_tecnico : null;
  const income = item.historico_renda?.safras ?? [];
  const incomeMax = Math.max(1, ...income.map(s => Math.abs(s.margem_sc_soja_ha)));
  const climate = uncertainty?.risco_climatico;
  const incomeRange = uncertainty?.renda;
  const noClimateRisk = !climate && item.criterios != null && item.criterios.risco >= 1;
  const estimated = (uncertainty?.criterios_estimados ?? []).map(id => CRITERIA.find(c => c.id === id)).filter(Boolean);
  const attention = [...(card?.riscos ?? []), ...(card?.avisos ?? [])];
  const secondName = item.segunda?.id === "pousio" ? say("Pousio", "Fallow") : item.segunda?.nome;
  // Engine enums: `confianca` is "baixa" or "não validada" ("not validated" in English); `mercado.nivel` stays in Portuguese.
  const confidence = (level: string) => ({ baixa: say("confiança baixa", "low confidence"), low: say("confiança baixa", "low confidence"),
    "não validada": say("ainda não validado", "not validated yet"), "not validated": say("ainda não validado", "not validated yet") })[level] ?? level;
  const marketLevel = card?.mercado && ({ alto: say("alto", "high"), "médio": say("médio", "medium"), medio: say("médio", "medium"), baixo: say("baixo", "low") })[card.mercado.nivel];

  function climateLine(p: number) {
    if (p <= 0) return say("Nenhum evento adverso nos anos analisados", "No adverse event in the years analysed");
    const every = Math.max(1, Math.round(1 / p));
    return every <= 1 ? say(`Evento adverso em ${pct(p)}% dos anos`, `Adverse event in ${pct(p)}% of years`)
      : say(`Evento adverso em ~1 a cada ${every} anos (${pct(p)}%)`, `Adverse event in ~1 of every ${every} years (${pct(p)}%)`);
  }

  return <dialog ref={ref} className="modal sd" aria-labelledby="sd-title"
    onCancel={e => { e.preventDefault(); onClose(); }}
    onClick={e => {
      if (e.target !== e.currentTarget) return;
      const r = e.currentTarget.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose();
    }}>
   <button type="button" className="close-modal" aria-label={say("Fechar", "Close")} onClick={onClose}>×</button>

   {/* Summary */}
   <header className="sd-head">
    <div>
     <span className="sd-eyebrow">{item.atual ? say("Sua rotação hoje", "Your rotation today") : say(`Opção #${rank}`, `Option #${rank}`)}</span>
     <h2 id="sd-title">{item.verao && secondName ? <>{item.verao.nome} <span aria-hidden="true">→</span> {secondName}</> : item.rotacao}</h2>
     <div className="sd-badges">
      {item.zarc && <span className={"sd-badge " + (item.zarc.indicado ? "is-good" : "is-warn")}>{item.zarc.indicado ? say("✓ Indicado pelo ZARC", "✓ Recommended by ZARC") : say("! Fora do ZARC na data prevista", "! Outside ZARC on the planned date")}</span>}
      {marketLevel && <span className="sd-badge">{say("Mercado local", "Local market")}: {marketLevel}</span>}
      {tie && <span className="sd-badge is-warn">{say("Empate técnico", "Technical tie")}</span>}
     </div>
    </div>
    <div className="sd-score"><strong>{item.nota == null ? "—" : pct(item.nota)}</strong><span>/ 100</span>
     {item.posicao != null && evaluated > 0 && <small>{say(`${item.posicao}ª de ${evaluated} avaliadas`, `#${item.posicao} of ${evaluated} evaluated`)}</small>}</div>
   </header>
   {card?.por_que && <p className="sd-why">{card.por_que}</p>}
   {tie && <p className="sd-note">{tie.texto}</p>}

   {/* How the score is built */}
   {item.criterios && <section className="sd-section" aria-labelledby="sd-score-title">
    <div className="sd-section-head"><h3 id="sd-score-title">{say("Como a nota se forma", "How the score is built")}</h3>
     {baseline && <span className="sd-legend"><i className="is-option"/>{say("este cenário", "this scenario")}<i className="is-today"/>{say("rotação de hoje", "today’s rotation")}</span>}</div>
    <ul className="sd-bars">
     {CRITERIA.map(c => {
       const value = item.criterios![c.id];
       const before = baseline?.criterios?.[c.id];
       return <li key={c.id}>
        <span className="sd-bar-label">{en ? c.name.en : c.name.pt}<small>{en ? levelLabel(c.id, value).en : levelLabel(c.id, value).pt}</small></span>
        <span className="sd-bar" role="img" aria-label={`${pct(value)} / 100${before != null ? say(`, hoje ${pct(before)}`, `, today ${pct(before)}`) : ""}`}>
         <span className="sd-bar-fill" style={{ width: `${pct(value)}%` }}/>
         {before != null && <span className="sd-bar-today" style={{ left: `${pct(before)}%` }}/>}
        </span>
        <span className="sd-bar-value">{pct(value)}{before != null && pct(value) !== pct(before) && <small className={pct(value) > pct(before) ? "is-up" : "is-down"}>{pct(value) > pct(before) ? "+" : "−"}{Math.abs(pct(value) - pct(before))}</small>}</span>
       </li>;
     })}
    </ul>
    {item.margem && <p className="sd-foot">{say("Margem estimada da rotação", "Estimated rotation margin")}: <strong>{money(item.margem.total_r_ha)}/ha</strong> {say("por ano", "per year")}</p>}
   </section>}

   {/* How far to trust it */}
   {(seasons.length > 0 || firstIn != null || climate || income.length > 0 || incomeRange) && <section className="sd-section" aria-labelledby="sd-trust-title">
    <div className="sd-section-head"><h3 id="sd-trust-title">{say("Quão confiável é este resultado", "How far to trust this result")}</h3></div>
    <div className="sd-trust">
     {seasons.length > 0 && <div className="sd-tile">
      <small>{say("Nota em cada safra recente", "Score in each recent season")}</small>
      <div className="sd-mini" role="img" aria-label={seasons.map(([y, v]) => `${y}: ${pct(v)}`).join(", ")}>
       {seasons.map(([year, v]) => <span key={year} className="sd-mini-col"><b style={{ height: `${pct(v)}%` }}/><em>{pct(v)}</em><i>{year.slice(2)}</i></span>)}
      </div>
      {uncertainty?.nota_faixa && uncertainty.nota_faixa[1] != null && <p>{say(`Variou de ${pct(uncertainty.nota_faixa[0])} a ${pct(uncertainty.nota_faixa[1]!)} conforme o ano.`, `It ranged from ${pct(uncertainty.nota_faixa[0])} to ${pct(uncertainty.nota_faixa[1]!)} depending on the year.`)}</p>}
     </div>}
     {firstIn != null && stability && <div className="sd-tile">
      <small>{say("Quantas vezes seria a 1ª opção", "How often it would rank first")}</small>
      <div className="sd-dots" role="img" aria-label={say(`${firstIn} de ${stability.safras.length} safras`, `${firstIn} of ${stability.safras.length} seasons`)}>
       {stability.safras.map((year, i) => <span key={year} className={i < firstIn ? "is-on" : ""}/>)}
      </div>
      <p><strong>{say(`${firstIn} de ${stability.safras.length} safras`, `${firstIn} of ${stability.safras.length} seasons`)}</strong> {say("repetindo a renda de cada ano", "repeating each year’s income")}</p>
     </div>}
     {income.length > 0 && <div className="sd-tile">
      <small>{say("Renda da 2ª safra em cada ano", "Second-crop income each year")}</small>
      <div className="sd-mini is-signed" role="img" aria-label={income.map(s => `${s.ano}: ${s.margem_sc_soja_ha}`).join(", ")}>
       {income.map(s => <span key={s.ano} className={"sd-mini-col" + (s.margem_sc_soja_ha < 0 ? " is-loss" : "")}><b style={{ height: `${Math.abs(s.margem_sc_soja_ha) / incomeMax * 50}%` }}/><i>{String(s.ano).slice(2)}</i></span>)}
      </div>
      {incomeRange?.origem === "historico" && incomeRange.faixa_r_ha[1] != null && <p><strong>{money(incomeRange.faixa_r_ha[0])} {say("a", "to")} {money(incomeRange.faixa_r_ha[1])}/ha</strong> {say("a mais que só soja, conforme o ano", "more than soybean alone, depending on the year")}</p>}
      <p>{say("Barras em sacas de soja por hectare", "Bars in soybean bags per hectare")}{income.some(s => s.margem_sc_soja_ha < 0) && say(`; deu prejuízo em ${income.filter(s => s.margem_sc_soja_ha < 0).map(s => s.ano).join(", ")}.`, `; it lost money in ${income.filter(s => s.margem_sc_soja_ha < 0).map(s => s.ano).join(", ")}.`)}</p>
     </div>}
     {incomeRange?.origem === "custo_fixo" && <div className="sd-tile">
      <small>{say("Renda da 2ª safra", "Second-crop income")}</small>
      <p className="sd-big">{say("Não varia com o ano", "Does not vary by year")}</p>
      <p>{say(`Sem venda de grão: entra só o custo de implantação (${money(incomeRange.incremental_r_ha)}/ha).`, `No grain is sold: only the establishment cost counts (${money(incomeRange.incremental_r_ha)}/ha).`)}</p>
     </div>}
     {incomeRange?.origem === "ano_ruim_p20" && <div className="sd-tile">
      <small>{say("Num ano ruim (1 a cada 5)", "In a bad year (1 in 5)")}</small>
      <p className="sd-big">{say("Renda a mais", "Extra income")}: {money(incomeRange.faixa_r_ha[0])}/ha</p>
      {uncertainty?.nota_faixa && <p>{say(`A nota cairia para ${pct(uncertainty.nota_faixa[0])}.`, `The score would drop to ${pct(uncertainty.nota_faixa[0])}.`)}</p>}
     </div>}
     {climate && <div className="sd-tile">
      <small>{say("Risco de clima", "Climate risk")}</small>
      <p className="sd-big">{climateLine(climate.probabilidade)}</p>
      {climate.eventos.length > 0 && <p>{climate.eventos.join(" · ")}</p>}
      <details className="sd-why-more"><summary>{confidence(climate.confianca)}</summary><p>{climate.texto}</p></details>
     </div>}
     {noClimateRisk && <div className="sd-tile">
      <small>{say("Risco de clima", "Climate risk")}</small>
      <p className="sd-big">{say("Sem risco de quebra", "No crop-failure risk")}</p>
      <p>{say("Não há grão para colher, então geada e seca não causam perda de safra.", "There is no grain to harvest, so frost and drought cause no crop loss.")}</p>
     </div>}
    </div>
    {estimated.length > 0 && <p className="sd-foot">{say("Usam valores estimados do catálogo: ", "Based on catalog estimates: ")}{estimated.map(c => en ? c!.name.en : c!.name.pt).join(", ")}.</p>}
   </section>}

   {/* Benefits and attention */}
   {card && <section className="sd-section sd-two">
    <div><h3 className="is-good">{say("Benefícios", "Benefits")}</h3>
     {card.beneficios.length ? <ul>{card.beneficios.map(b => <li key={b}>{b}</li>)}</ul> : <p>{say("Sem benefício marcante nos critérios avaliados.", "No notable benefit in the criteria evaluated.")}</p>}
     {card.mercado && <p className="sd-foot">{card.mercado.texto}</p>}</div>
    <div><h3 className="is-warn">{say("Pontos de atenção", "Points of attention")}</h3>
     {attention.length ? <ul>{attention.map(a => <li key={a}>{a}</li>)}</ul> : <p>—</p>}</div>
   </section>}

   {/* Technical notes, collapsed */}
   {card && (card.evidencias.length > 0 || card.lacunas.length > 0) && <section className="sd-section sd-tech">
    {card.evidencias.length > 0 && <details><summary>{say("De onde vêm esses números", "Where these numbers come from")} <span>({card.evidencias.length})</span></summary><ul>{card.evidencias.map(e => <li key={e}>{e}</li>)}</ul></details>}
    {card.lacunas.length > 0 && <details><summary>{say("O que ainda falta saber", "What is still unknown")} <span>({card.lacunas.length})</span></summary><ul>{card.lacunas.map(e => <li key={e}>{e}</li>)}</ul></details>}
   </section>}

   <footer className="sd-footer">
    <p>{say("Estimativa de apoio à decisão: confirme com o agrônomo antes de mudar a rotação.", "Decision-support estimate: check with your agronomist before changing the rotation.")}</p>
    {onCompare && <button type="button" className="rs-card-button is-primary" onClick={onCompare}>{say("Comparar com a de hoje →", "Compare with today’s →")}</button>}
   </footer>
  </dialog>;
}
