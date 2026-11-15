import { t as __text, t } from "./i18n";
import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import './climate-story.css';
const sources = {"soja": {"label": "Seab / Deral · soja no Paraná · 30/01/2025", "url": "https://www.agricultura.pr.gov.br/Noticia/Previsao-de-safra-indica-213-milhoes-de-toneladas-de-soja-e-aumento-na-producao-de-feijao"}, "trigo": {"label": "Seab / Deral · trigo no Paraná · 24/10/2024", "url": "https://www.agricultura.pr.gov.br/Noticia/Perspectivas-sao-boas-para-primeira-safra-de-verao-no-Parana-diz-Deral"}, "english": {"label": "Cultivar · notícia em inglês sobre a soja no Paraná", "url": "https://revistacultivar.com/index.php/news/pre-harvest-2024-25-soybean-production-should-fall-4"}};
const cases = [{"place": "PARANÁ · SOJA · SAFRA 2024/25", "title": "O clima mudou. A expectativa de colheita também.", "metric": "1 milhão", "caption": "de toneladas a menos na previsão de soja do Paraná, frente à estimativa inicial.", "text": "Em janeiro de 2025, o Deral revisou a previsão de 22,3 para 21,3 milhões de toneladas após condições climáticas adversas. Oeste, Noroeste e Centro-Oeste estavam entre as regiões mais afetadas.", "source": "Seab / Deral · estimativa de 30/01/2025"}, {"place": "PARANÁ · TRIGO · SAFRA 2023/24", "title": "Seca e geadas comprometem o próximo ciclo.", "metric": "−38%", "caption": "na previsão de produção de trigo do Paraná em relação ao potencial inicial.", "text": "Em outubro de 2024, o Deral estimou 2,3 milhões de toneladas, ante 3,7 milhões previstas inicialmente. A seca foi o principal impacto; geadas também reduziram a qualidade dos grãos.", "source": "Seab / Deral · estimativa de 24/10/2024"}] as const;
// Text windows do not overlap: only the photographs crossfade.
const windows = [[0, .02, .34, .40], [.41, .46, .73, .79], [.80, .87, 1, 1]];
function interpolate(p: number, xs: number[], ys: number[]) {
    if (p <= xs[0])
        return ys[0];
    for (let i = 1; i < xs.length; i++)
        if (p <= xs[i])
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (p - xs[i - 1]) / (xs[i] - xs[i - 1]);
    return ys[ys.length - 1];
}
function Scene({ progress, index, children }: {
    progress: number;
    index: number;
    children: React.ReactNode;
}) {
    const opacity = interpolate(progress, windows[index], [index === 0 ? 1 : 0, 1, 1, index === windows.length - 1 ? 1 : 0]);
    const y = interpolate(progress, windows[index], [index === 0 ? 0 : 18, 0, 0, -18]);
    return <div className={`climate-scene climate-scene-${index}`} style={{ opacity, visibility: opacity > 0 ? "visible" : "hidden", transform: `translateY(${y}px)` }} aria-hidden="true">{__text(children)}</div>;
}
function Photo({ progress, src, range, initial = false }: {
    progress: number;
    src: string;
    range: number[];
    initial?: boolean;
}) {
    const opacity = interpolate(progress, range, [initial ? 1 : 0, 1, 1, 0]);
    const y = interpolate(progress, [0, 1], [2, -4]);
    const [failed, setFailed] = useState(false);
    return <div className="climate-photo" style={{ opacity, transform: `translateY(${y}%)` }}>
    {__text(failed ? <span className="climate-image-placeholder">{__text("Imagem de apoio indispon\u00EDvel \u00B7 paisagem agr\u00EDcola")}</span> : <img src={src} alt={__text("")} loading="lazy" decoding="async" onError={() => setFailed(true)}/>)}
  </div>;
}
function Evidence({ item }: {
    item: typeof cases[number];
}) {
    return <div className="climate-evidence"><small className="climate-case-place">{__text(item.place)}</small><h2>{__text(item.title)}</h2><strong className="climate-case-metric">{__text(item.metric)}</strong><p className="climate-case-caption">{__text(item.caption)}</p><p className="climate-case-text">{__text(item.text)}</p><small className="climate-case-source">{__text(item.source)}</small></div>;
}
export default function ClimateStory() {
    const ref = useRef<HTMLElement>(null);
    const reduced = useReducedMotion();
    const [p, setProgress] = useState(0);
    useEffect(() => {
        if (reduced)
            return;
        let frame = 0;
        const update = () => { frame = 0; const el = ref.current; if (el) {
            const rect = el.getBoundingClientRect();
            setProgress(Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - innerHeight))));
        } };
        const schedule = () => { if (!frame)
            frame = requestAnimationFrame(update); };
        update();
        addEventListener('scroll', schedule, { passive: true });
        addEventListener('resize', schedule);
        return () => { cancelAnimationFrame(frame); removeEventListener('scroll', schedule); removeEventListener('resize', schedule); };
    }, [reduced]);
    const darkness = interpolate(p, [0, .3, .6, .8, .9], [.56, .59, .72, .9, 1]);
    return <>
    <section ref={ref} id="produto" className={`climate-story${reduced ? ' climate-story-reduced' : ''}`} aria-labelledby="climate-story-title">
      {__text(!reduced && <div className="climate-accessible">
        <h2 id="climate-story-title">{__text("Quando o clima muda, a vida muda junto.")}</h2>
        {__text(cases.map(item => <article key={item.title}><h3>{__text(item.title)}</h3><p>{__text(item.place)}</p><p>{__text(item.metric)} {__text(item.caption)}</p><p>{__text(item.text)}</p><p>{__text(item.source)}</p></article>))}
        <p>{__text("Como planejar a pr\u00F3xima safra quando o clima se torna imprevis\u00EDvel?")}</p>
      </div>)}
      {__text(reduced ? <div className="climate-static"><h2 id="climate-story-title" className="climate-accessible">{__text("Quando o clima muda, a vida muda junto.")}</h2>
        {__text(cases.map(item => <article key={item.title}><Evidence item={item}/></article>))}
        <article><h2>{__text("Como planejar a")}{" "}<em>{__text("pr\u00F3xima safra")}</em>{" "}{__text("quando o clima se torna imprevis\u00EDvel?")}</h2></article>
      </div> : <div className="climate-sticky">
        <div className="climate-images" aria-hidden="true">
          <Photo progress={p} src="/assets/story-drought-ia.webp" range={[0, 0, .56, .87]} initial/>
        </div>
        <div className="climate-darkness" style={{ opacity: darkness }}/><div className="climate-vignette"/>
        <div className="climate-chapter" aria-hidden="true"><span>{__text("01")}</span>{__text("O PROBLEMA")}</div>
        {__text(cases.map((item, i) => <Scene key={item.title} progress={p} index={i}><Evidence item={item}/></Scene>))}
        <Scene progress={p} index={2}><h2>{__text("Como planejar a")}{" "}<em>{__text("pr\u00F3xima safra")}</em>{" "}{__text("quando o clima se torna imprevis\u00EDvel?")}</h2></Scene>
        <span className="climate-photo-note" aria-hidden="true">{__text("Imagem de apoio sobre seca · aprimorada com IA · não é registro dos casos citados")}</span>
      </div>)}
    </section>
    <div className="climate-sources"><details><summary>{__text("Fontes e contexto dos casos reais")}</summary><div className="climate-sources-body">
      <p>{__text("Dois casos do estado do Paraná. Os números são estimativas do Deral nas datas indicadas, comparadas às previsões iniciais de cada safra; não são previsões atuais nem resultados finais de colheita. A imagem de seca é ilustrativa e foi aprimorada com IA.")}</p>
      <ul>{Object.entries(sources).map(([key, source]) => <li key={key}><a href={source.url} target="_blank" rel="noreferrer">{__text(source.label)} ↗</a></li>)}</ul>
    </div></details></div>
  </>;
}
