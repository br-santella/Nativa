import { t as __text, t } from "./i18n";
import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import './climate-story.css';
const documentarySource = "https://mst.org.br/2024/05/09/enchente-no-sul-arrasa-lavouras-de-arroz-organico-do-mst/";
const documentaryPhotos = [{ "file": "rs-arroz-viamao-ia.webp", "label": "Arroz inundado · Viamão (RS), maio/2024 · Foto: MST-RS · aprimorada com IA", "original": "https://mst.org.br/wp-content/uploads/2024/05/image-23-1024x770.jpg" }, { "file": "rs-maquinas-viamao-ia.webp", "label": "Lavoura e máquinas atingidas · Viamão (RS), maio/2024 · Foto: MST-RS · aprimorada com IA", "original": "https://mst.org.br/wp-content/uploads/2024/05/image-24.jpg" }, { "file": "rs-estufas-eldorado-ia.webp", "label": "Estufas inundadas · Eldorado do Sul (RS), maio/2024 · Foto: MST-RS · aprimorada com IA", "original": "https://mst.org.br/wp-content/uploads/2024/05/image-26.jpg" }];
const sources = {
    inmet: { label: 'INMET · balanço do El Niño 2023–2024', url: 'https://portal.inmet.gov.br/noticias/el-ni%C3%B1o-saiba-como-foi-a-atua%C3%A7%C3%A3o-do-fen%C3%B4meno-no-brasil' },
    ibgeSafra: { label: 'IBGE · estimativa da safra, novembro de 2024', url: 'https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/42191-em-novembro-ibge-preve-safra-de-294-3-milhoes-de-toneladas-para-2024-e-de-314-8-milhoes-de-toneladas-para-2025' },
    emater: { label: 'Emater/RS-Ascar · relatório de maio de 2024, pp. 9–11 e 23', url: 'https://www.estado.rs.gov.br/upload/arquivos/202406/relatorio-sisperdas-evento-enchentes-em-maio-2024.pdf' },
    ibgePrecos: { label: 'IBGE · IPCA de maio de 2024, divulgado em 11/06/2024', url: 'https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/40340-ipca-foi-de-0-46-em-maio' },
    contextoPrecos: { label: 'Agência Gov / IBGE · contexto da alta da batata, 11/06/2024', url: 'https://agenciagov.ebc.com.br/noticias/202406/inflacao-acumulada-maio-menor-que-ano-passado' },
    mcti: { label: 'MCTI · estudo de atribuição das chuvas no RS, 03/06/2024', url: 'https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/2024/06/mudanca-climatica-dobrou-a-probabilidade-de-ocorrencia-de-chuvas-extremas-no-sul-do-brasil/' },
};
const cases = [
    { place: 'RIO GRANDE DO SUL · MAIO DE 2024', title: 'A colheita que a água levou.', metric: '2,7 milhões', caption: 'de toneladas de soja perdidas, segundo estimativa da Emater/RS-Ascar.', text: 'Em Agudo, o relatório também registrou perdas em lavouras de arroz. A água atingiu a safra que ainda estava no campo.', source: 'Emater/RS-Ascar · levantamento de maio de 2024', refs: ['emater'] },
    { place: 'BRASIL · PREÇOS AO CONSUMIDOR · MAIO DE 2024', title: 'Do campo à mesa, o impacto continua.', metric: '+20,61%', caption: 'no preço da batata-inglesa no Brasil em um mês, pelo IPCA.', text: 'As chuvas no RS atingiram parte da produção. A transição entre safras também reduziu a oferta — a alta não teve uma causa única.', source: 'IBGE · maio de 2024 em relação a abril', refs: ['ibgePrecos', 'contextoPrecos'] },
] as const;
// Text windows do not overlap: only the photographs crossfade.
const windows = [[0, .025, .10, .14], [.15, .20, .44, .49], [.50, .55, .77, .82], [.83, .89, 1, 1]];
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
    const opacity = interpolate(progress, windows[index], [0, 1, 1, index === windows.length - 1 ? 1 : 0]);
    const y = interpolate(progress, windows[index], [18, 0, 0, -18]);
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
export default function ClimateStory({ calmImage }: {
    calmImage: string;
}) {
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
    const darkness = interpolate(p, [0, .15, .4, .65, .85, .91], [.15, .56, .59, .72, .9, 1]);
    return <>
    <section ref={ref} id="produto" className={`climate-story${reduced ? ' climate-story-reduced' : ''}`} aria-labelledby="climate-story-title">
      {__text(!reduced && <div className="climate-accessible">
        <h2 id="climate-story-title">{__text("Quando o clima muda, a vida muda junto.")}</h2>
        <p>{__text("Por gera\u00E7\u00F5es, aprendemos a cultivar seguindo os ciclos da natureza.")}</p>
        {__text(cases.map(item => <article key={item.title}><h3>{__text(item.title)}</h3><p>{__text(item.place)}</p><p>{__text(item.metric)} {__text(item.caption)}</p><p>{__text(item.text)}</p><p>{__text(item.source)}</p></article>))}
        <p>{__text("Como planejar a pr\u00F3xima safra quando o clima se torna imprevis\u00EDvel?")}</p>
      </div>)}
      {__text(reduced ? <div className="climate-static">
        <article style={{ backgroundImage: `linear-gradient(#010e1155,#010e11cc),url(${calmImage})` }}><small>{__text("01 / O PROBLEMA")}</small><h2 id="climate-story-title">{__text("Por gera\u00E7\u00F5es, aprendemos a cultivar seguindo os ciclos da natureza.")}</h2></article>
        {__text(cases.map(item => <article key={item.title}><Evidence item={item}/></article>))}
        <article><h2>{__text("Como planejar a")}<em>{__text("pr\u00F3xima safra")}</em>{__text("quando o clima se torna imprevis\u00EDvel?")}</h2></article>
      </div> : <div className="climate-sticky">
        <div className="climate-images" aria-hidden="true">
          <Photo progress={p} src={calmImage} range={[0, .025, .10, .20]} initial/>
          <Photo progress={p} src="/assets/rs-arroz-viamao-ia.webp" range={[.10, .20, .34, .43]}/>
          <Photo progress={p} src="/assets/rs-maquinas-viamao-ia.webp" range={[.34, .43, .60, .69]}/>
          <Photo progress={p} src="/assets/rs-estufas-eldorado-ia.webp" range={[.60, .69, .78, .89]}/>
        </div>
        <div className="climate-darkness" style={{ opacity: darkness }}/><div className="climate-vignette"/>
        <div className="climate-chapter" aria-hidden="true"><span>{__text("01")}</span>{__text("O PROBLEMA")}</div>
        <Scene progress={p} index={0}><h2>{__text("Por gera\u00E7\u00F5es, aprendemos a cultivar seguindo os ciclos da natureza.")}</h2><span className="climate-scroll-cue">{__text("Mas a mudan\u00E7a j\u00E1 faz parte da nossa hist\u00F3ria")}<i>{__text("\u2193")}</i></span></Scene>
        {__text(cases.map((item, i) => <Scene key={item.title} progress={p} index={i + 1}><Evidence item={item}/></Scene>))}
        <Scene progress={p} index={3}><h2>{__text("Como planejar a")}<em>{__text("pr\u00F3xima safra")}</em>{__text("quando o clima se torna imprevis\u00EDvel?")}</h2></Scene>
        <span className="climate-photo-note" aria-hidden="true">{__text(p < .15 ? "Paisagem: imagem de apoio · aprimorada com IA" : p < .39 ? documentaryPhotos[0].label : p < .65 ? documentaryPhotos[1].label : documentaryPhotos[2].label)}</span>
      </div>)}
    </section>
    <div className="climate-sources"><details><summary>{__text("Fontes e contexto dos casos reais")}</summary><div className="climate-sources-body">
      <p>{__text("Casos hist\u00F3ricos de 2023\u20132024. Estimativas, locais e per\u00EDodos acompanham cada dado; n\u00E3o s\u00E3o proje\u00E7\u00F5es para a pr\u00F3xima safra.")}</p>
      <p>{__text("O El Ni\u00F1o \u00E9 um fen\u00F4meno natural. Sua atua\u00E7\u00E3o e as mudan\u00E7as clim\u00E1ticas contribu\u00EDram para intensificar as chuvas de 2024 no RS; o desastre envolveu m\u00FAltiplos fatores. A alta de um alimento n\u00E3o pode ser atribu\u00EDda apenas \u00E0s enchentes.")}</p>
      <p>{__text("Na produ\u00E7\u00E3o de soja em Mato Grosso, a compara\u00E7\u00E3o \u00E9 a estimativa do IBGE de novembro de 2024 frente a 2023, n\u00E3o uma perda isolada atribu\u00EDda apenas ao El Ni\u00F1o. As perdas de soja no RS s\u00E3o estimativas do levantamento de maio de 2024 da Emater/RS-Ascar.")}</p>
      <ul>{__text(Object.entries(sources).map(([key, source]) => <li key={key}><a href={source.url} target="_blank" rel="noreferrer">{__text(source.label)}{__text("\u2197")}</a></li>))}</ul>
      <p>{__text("As cenas das enchentes usam vers\u00F5es aprimoradas com IA de fotografias documentais do Rio Grande do Sul em maio de 2024, com cr\u00E9dito MST-RS. O tratamento melhora a nitidez, mas pode reconstruir detalhes; os originais est\u00E3o vinculados abaixo. A localidade da fotografia est\u00E1 na legenda e pode ser diferente da descrita no texto. A paisagem inicial \u00E9 uma imagem de apoio visual aprimorada com IA. Os textos s\u00E3o s\u00EDnteses das fontes, n\u00E3o depoimentos.")}</p>
      <p><a href={documentarySource} target="_blank" rel="noreferrer">{__text("Origem das fotografias \u00B7 reportagem de 09/05/2024 \u2197")}</a></p>
      <ul>{__text(documentaryPhotos.map(photo => <li key={photo.file}><a href={photo.original} target="_blank" rel="noreferrer">{__text(photo.label)}{__text("\u2197")}</a></li>))}</ul>
    </div></details></div>
  </>;
}
