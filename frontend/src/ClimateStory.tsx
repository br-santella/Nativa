import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import './climate-story.css';

const documentarySource = "https://mst.org.br/2024/05/09/enchente-no-sul-arrasa-lavouras-de-arroz-organico-do-mst/";
const documentaryPhotos = [{"file": "rs-arroz-viamao.webp", "label": "Arroz inundado · Viamão (RS), maio/2024 · Foto: MST-RS", "original": "https://mst.org.br/wp-content/uploads/2024/05/image-23-1024x770.jpg"}, {"file": "rs-maquinas-viamao.webp", "label": "Lavoura e máquinas atingidas · Viamão (RS), maio/2024 · Foto: MST-RS", "original": "https://mst.org.br/wp-content/uploads/2024/05/image-24.jpg"}, {"file": "rs-estufas-eldorado.webp", "label": "Estufas inundadas · Eldorado do Sul (RS), maio/2024 · Foto: MST-RS", "original": "https://mst.org.br/wp-content/uploads/2024/05/image-26.jpg"}];
const sources = {
  inmet: { label: 'INMET · balanço do El Niño 2023–2024', url: 'https://portal.inmet.gov.br/noticias/el-ni%C3%B1o-saiba-como-foi-a-atua%C3%A7%C3%A3o-do-fen%C3%B4meno-no-brasil' },
  ibgeSafra: { label: 'IBGE · estimativa da safra, novembro de 2024', url: 'https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/42191-em-novembro-ibge-preve-safra-de-294-3-milhoes-de-toneladas-para-2024-e-de-314-8-milhoes-de-toneladas-para-2025' },
  emater: { label: 'Emater/RS-Ascar · relatório de maio de 2024, pp. 9–11 e 23', url: 'https://www.estado.rs.gov.br/upload/arquivos/202406/relatorio-sisperdas-evento-enchentes-em-maio-2024.pdf' },
  ibgePrecos: { label: 'IBGE · IPCA de maio de 2024, divulgado em 11/06/2024', url: 'https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/40340-ipca-foi-de-0-46-em-maio' },
  contextoPrecos: { label: 'Agência Gov / IBGE · contexto da alta da batata, 11/06/2024', url: 'https://agenciagov.ebc.com.br/noticias/202406/inflacao-acumulada-maio-menor-que-ano-passado' },
  mcti: { label: 'MCTI · estudo de atribuição das chuvas no RS, 03/06/2024', url: 'https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/2024/06/mudanca-climatica-dobrou-a-probabilidade-de-ocorrencia-de-chuvas-extremas-no-sul-do-brasil/' },
};
const cases = [
  { place: 'BRASIL · EL NIÑO 2023–2024', title: 'O mesmo fenômeno. Extremos diferentes.', metric: '−12%', caption: 'na produção estimada de soja em Mato Grosso em 2024, frente a 2023.', text: 'Enquanto o Sul enfrentava excesso de chuva, falta de água e calor afetavam lavouras no Centro-Oeste.', source: 'INMET · IBGE, estimativa de novembro de 2024', refs: ['inmet', 'ibgeSafra'] },
  { place: 'RIO GRANDE DO SUL · MAIO DE 2024', title: 'A colheita que a água levou.', metric: '2,7 milhões', caption: 'de toneladas de soja perdidas, segundo estimativa da Emater/RS-Ascar.', text: 'Em Agudo, o relatório também registrou perdas em lavouras de arroz. A água atingiu a safra que ainda estava no campo.', source: 'Emater/RS-Ascar · levantamento de maio de 2024', refs: ['emater'] },
  { place: 'BRASIL · PREÇOS AO CONSUMIDOR · MAIO DE 2024', title: 'O impacto não para na porteira.', metric: '+20,61%', caption: 'no preço da batata-inglesa no Brasil em um mês, pelo IPCA.', text: 'As chuvas no RS atingiram parte da produção. A transição entre safras também reduziu a oferta — a alta não teve uma causa única.', source: 'IBGE · maio de 2024 em relação a abril', refs: ['ibgePrecos', 'contextoPrecos'] },
  { place: 'RIO GRANDE DO SUL · ABASTECIMENTO · 22/05/2024', title: 'Do campo à mesa da escola.', metric: '380 escolas', caption: 'abertas relataram dificuldade para obter ao menos um alimento normalmente adquirido.', text: 'Proteínas, frutas e hortaliças estavam entre os itens afetados. Lavouras perdidas e acessos interrompidos atingiam também a alimentação da população.', source: 'Emater/RS-Ascar · dados da SEDUC em 22/05/2024', refs: ['emater'] },
] as const;
// Text windows do not overlap: only the photographs crossfade.
const windows = [[0, .025, .075, .10], [.105, .14, .245, .275], [.28, .315, .455, .485], [.49, .525, .645, .675], [.68, .715, .815, .845], [.85, .89, 1, 1]];
function interpolate(p: number, xs: number[], ys: number[]) {
  if (p <= xs[0]) return ys[0];
  for (let i = 1; i < xs.length; i++) if (p <= xs[i]) return ys[i - 1] + (ys[i] - ys[i - 1]) * (p - xs[i - 1]) / (xs[i] - xs[i - 1]);
  return ys[ys.length - 1];
}
function Scene({ progress, index, children }: { progress: number; index: number; children: React.ReactNode }) {
  const opacity = interpolate(progress, windows[index], [0, 1, 1, index === 5 ? 1 : 0]);
  const y = interpolate(progress, windows[index], [18, 0, 0, -18]);
  return <div className={`climate-scene climate-scene-${index}`} style={{ opacity, visibility: opacity > 0 ? "visible" : "hidden", transform: `translateY(${y}px)` }} aria-hidden="true">{children}</div>;
}
function Photo({ progress, src, range, initial = false }: { progress: number; src: string; range: number[]; initial?: boolean }) {
  const opacity = interpolate(progress, range, [initial ? 1 : 0, 1, 1, 0]);
  const y = interpolate(progress, [0, 1], [2, -4]);
  const [failed, setFailed] = useState(false);
  return <div className="climate-photo" style={{ opacity, transform: `translateY(${y}%)` }}>
    {failed ? <span className="climate-image-placeholder">Imagem de apoio indisponível · paisagem agrícola</span> : <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />}
  </div>;
}
function Evidence({ item }: { item: typeof cases[number] }) {
  return <div className="climate-evidence"><small className="climate-case-place">{item.place}</small><h2>{item.title}</h2><strong className="climate-case-metric">{item.metric}</strong><p className="climate-case-caption">{item.caption}</p><p className="climate-case-text">{item.text}</p><small className="climate-case-source">{item.source}</small></div>;
}
export default function ClimateStory({ calmImage }: { calmImage: string }) {
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const [p, setProgress] = useState(0);
  useEffect(() => {
    if (reduced) return;
    let frame = 0;
    const update = () => { frame = 0; const el = ref.current; if (el) { const rect = el.getBoundingClientRect(); setProgress(Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - innerHeight)))); } };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update(); addEventListener('scroll', schedule, { passive: true }); addEventListener('resize', schedule);
    return () => { cancelAnimationFrame(frame); removeEventListener('scroll', schedule); removeEventListener('resize', schedule); };
  }, [reduced]);
  const darkness = interpolate(p, [0, .15, .4, .65, .85, .91], [.15, .56, .59, .72, .9, 1]);
  return <>
    <section ref={ref} id="produto" className={`climate-story${reduced ? ' climate-story-reduced' : ''}`} aria-labelledby="climate-story-title">
      {!reduced && <div className="climate-accessible">
        <h2 id="climate-story-title">Quando o clima muda, a vida muda junto.</h2>
        <p>Por gerações, aprendemos a cultivar seguindo os ciclos da natureza.</p>
        {cases.map(item => <article key={item.title}><h3>{item.title}</h3><p>{item.place}</p><p>{item.metric} {item.caption}</p><p>{item.text}</p><p>{item.source}</p></article>)}
        <p>Como planejar a próxima safra quando o clima se torna imprevisível?</p>
      </div>}
      {reduced ? <div className="climate-static">
        <article style={{ backgroundImage: `linear-gradient(#010e1155,#010e11cc),url(${calmImage})` }}><small>01 / O PROBLEMA</small><h2 id="climate-story-title">Por gerações, aprendemos a cultivar seguindo os ciclos da natureza.</h2></article>
        {cases.map(item => <article key={item.title}><Evidence item={item}/></article>)}
        <article><h2>Como planejar a <em>próxima safra</em> quando o clima se torna imprevisível?</h2></article>
      </div> : <div className="climate-sticky">
        <div className="climate-images" aria-hidden="true">
          <Photo progress={p} src={calmImage} range={[0,.025,.09,.16]} initial />
          <Photo progress={p} src="/assets/story-drought.webp" range={[.09,.16,.25,.32]} />
          <Photo progress={p} src="/assets/rs-arroz-viamao.webp" range={[.26,.32,.39,.46]} />
          <Photo progress={p} src="/assets/rs-maquinas-viamao.webp" range={[.39,.46,.59,.67]} />
          <Photo progress={p} src="/assets/rs-estufas-eldorado.webp" range={[.60,.68,.78,.89]} />
        </div>
        <div className="climate-darkness" style={{ opacity: darkness }}/><div className="climate-vignette"/>
        <div className="climate-chapter" aria-hidden="true"><span>01</span> O PROBLEMA</div>
        <Scene progress={p} index={0}><h2>Por gerações, aprendemos a cultivar seguindo os ciclos da natureza.</h2><span className="climate-scroll-cue">Mas a mudança já faz parte da nossa história <i>↓</i></span></Scene>
        {cases.map((item, i) => <Scene key={item.title} progress={p} index={i + 1}><Evidence item={item}/></Scene>)}
        <Scene progress={p} index={5}><h2>Como planejar a <em>próxima safra</em> quando o clima se torna imprevisível?</h2></Scene>
        <span className="climate-photo-note" aria-hidden="true">{p < .26 ? "Paisagem e seca: imagens de apoio" : p < .43 ? documentaryPhotos[0].label : p < .64 ? documentaryPhotos[1].label : documentaryPhotos[2].label}</span>
      </div>}
    </section>
    <div className="climate-sources"><details><summary>Fontes e contexto dos casos reais</summary><div className="climate-sources-body">
      <p>Casos históricos de 2023–2024. Estimativas, locais e períodos acompanham cada dado; não são projeções para a próxima safra.</p>
      <p>O El Niño é um fenômeno natural. Sua atuação e as mudanças climáticas contribuíram para intensificar as chuvas de 2024 no RS; o desastre envolveu múltiplos fatores. A alta de um alimento não pode ser atribuída apenas às enchentes.</p>
      <p>Na produção de soja em Mato Grosso, a comparação é a estimativa do IBGE de novembro de 2024 frente a 2023, não uma perda isolada atribuída apenas ao El Niño. As perdas de soja no RS são estimativas do levantamento de maio de 2024 da Emater/RS-Ascar.</p>
      <ul>{Object.entries(sources).map(([key, source]) => <li key={key}><a href={source.url} target="_blank" rel="noreferrer">{source.label} ↗</a></li>)}</ul>
      <p>As cenas das enchentes usam fotografias documentais do Rio Grande do Sul em maio de 2024, com crédito MST-RS. A localidade da fotografia está na legenda e pode ser diferente da descrita no texto. Paisagem e seca permanecem como apoio visual. Os textos são sínteses das fontes, não depoimentos.</p>
      <p><a href={documentarySource} target="_blank" rel="noreferrer">Origem das fotografias · reportagem de 09/05/2024 ↗</a></p>
      <ul>{documentaryPhotos.map(photo => <li key={photo.file}><a href={photo.original} target="_blank" rel="noreferrer">{photo.label} ↗</a></li>)}</ul>
    </div></details></div>
  </>;
}
