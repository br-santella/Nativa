import { t as __text, t } from "./i18n";
import { motion, useReducedMotion } from "motion/react";
import './solution-story.css';
const flow = [
    { title: 'Começa com a sua terra.', text: 'Localização, cultura e histórico de plantio dão contexto à análise. Cada propriedade tem uma realidade.', detail: 'Entrada · propriedade e manejo' },
    { title: 'O espaço amplia o olhar.', text: 'A proposta é reunir observações de clima, umidade do solo e vegetação para ajudar a entender o que está mudando.', detail: 'Observação · NASA POWER, SMAP e MODIS como referências' },
    { title: 'Os dados encontram o próximo ciclo.', text: 'Compare possibilidades de rotação e períodos de plantio considerando as condições ambientais e as prioridades da propriedade.', detail: 'Análise · comparação de cenários' },
    { title: 'A decisão continua com quem cultiva.', text: 'Use os sinais para conversar com a assistência técnica, ajustar o planejamento e acompanhar a lavoura ao longo do tempo.', detail: 'Ação · planejamento e acompanhamento' },
];
export default function SolutionStory({ earth, field, onExplore }: {
    earth: string;
    field: string;
    onExplore: () => void;
}) {
    const reduced = useReducedMotion();
    const reveal = { initial: { opacity: reduced ? 1 : 0, y: reduced ? 0 : 24 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, amount: .25 }, transition: { duration: reduced ? 0 : .8 } };
    return <section className="solution-story" aria-labelledby="solution-title">
    <div className="solution-intro">
      <img src={earth} alt={__text("Ilustra\u00E7\u00E3o da Terra vista do espa\u00E7o com um sat\u00E9lite")} loading="lazy"/>
      <motion.div {...reveal} className="solution-intro-copy">
        <small className="solution-eyebrow">{__text("02 \u00B7 UMA NOVA PERSPECTIVA")}</small>
        <h2 id="solution-title">{__text("N\u00E3o controlamos o clima.")}<br />{__text("Podemos ampliar")}<br /><em>{__text("o nosso olhar.")}</em></h2>
        <p>{__text("Da observa\u00E7\u00E3o da Terra ao contexto da sua lavoura. Informa\u00E7\u00E3o para transformar incerteza em perguntas melhores \u2014 e decis\u00F5es mais conscientes.")}</p>
        <span className="solution-prototype">{__text("NATIVA \u00B7 proposta em desenvolvimento")}</span>
      </motion.div>
    </div>
    <div className="solution-flow">
      <div className="solution-flow-heading"><small className="solution-eyebrow">{__text("O CAMINHO DA INFORMA\u00C7\u00C3O")}</small><h2>{__text("Do seu campo.")}<br />{__text("Ao pr\u00F3ximo passo.")}</h2><p>{__text("Um fluxo pensado para apoiar o produtor, da localiza\u00E7\u00E3o da propriedade \u00E0 compara\u00E7\u00E3o de possibilidades.")}</p></div>
      <ol>{__text(flow.map((step, i) => <motion.li key={step.title} {...reveal}><span className="solution-number">{__text("0")}{__text(i + 1)}</span><div><small>{__text(step.detail)}</small><h3>{__text(step.title)}</h3><p>{__text(step.text)}</p></div></motion.li>))}</ol>
    </div>
    <div className="solution-gains">
      <img src={field} alt={__text("Lavouras ao p\u00F4r do sol")} loading="lazy"/>
      <div className="solution-gains-content">
        <motion.div {...reveal}><small className="solution-eyebrow">{__text("03 \u00B7 GANHOS POTENCIAIS")}</small><h2>{__text("Mais contexto hoje.")}<br /><em>{__text("Mais preparo amanh\u00E3.")}</em></h2><p className="solution-gains-lead">{__text("O valor est\u00E1 no que a informa\u00E7\u00E3o pode ajudar a mudar.")}</p></motion.div>
        <div className="solution-outcomes">
          {__text([
            ['Planejar com mais antecedência.', 'Identificar sinais ambientais relevantes para revisar o calendário e preparar alternativas.'],
            ['Usar recursos com mais critério.', 'Apoiar a discussão sobre água e insumos conforme o contexto da propriedade.'],
            ['Entender melhor os riscos.', 'Comparar possibilidades antes do próximo ciclo, em vez de depender de uma única estratégia.'],
            ['Cuidar da continuidade da produção.', 'Buscar mais resiliência no campo, com potencial de contribuir para o abastecimento e a renda.'],
        ].map(([title, text]) => <motion.div {...reveal} key={title}><h3>{__text(title)}</h3><p>{__text(text)}</p></motion.div>))}
        </div>
        <p className="solution-limits">{__text("Benef\u00EDcios potenciais, ainda n\u00E3o medidos pelo projeto. A demonstra\u00E7\u00E3o usa dados fict\u00EDcios; os resultados dependem de integra\u00E7\u00E3o com dados reais, valida\u00E7\u00E3o local e orienta\u00E7\u00E3o t\u00E9cnica. N\u00E3o h\u00E1 garantia de produtividade, economia ou redu\u00E7\u00E3o de pre\u00E7os.")}</p>
        <button className="button yellow" onClick={onExplore}>{__text("Explorar a demonstra\u00E7\u00E3o \u2192")}</button>
      </div>
    </div>
  </section>;
}
