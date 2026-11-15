import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, health, pesosDosSliders, recomendacao } from "./api";
import type { Area, Health, ItemRanking, Recomendacao } from "./api";
import { rotacaoDoHistorico } from "./rotacaoAtual";
import { t, locale } from "./i18n";

// Talhão demo do motor (Toledo, PR): usado só quando a fazenda não tem lat/lon válidas.
const TALHAO_DEMO = "72638";
const CORES = ["#93a8ad", "#a8c9a3", "#e9b857"]; // atual, 1ª e 2ª alternativas (mesmas cores do design)
const CRITERIOS = [
  ["renda", "Renda"],
  ["solo", "Solo"],
  ["agua", "Água"],
  ["pragas", "Pragas"],
  ["risco", "Risco climático"],
] as const;
type Criterios = NonNullable<ItemRanking["criterios"]>;

// Textos com valores interpolados não passam pelo dicionário de t(); escolhem o idioma aqui.
const emIngles = () => locale() === "en-US";
const pct = (v: number | null | undefined) => (v == null ? "—" : Math.round(v * 100).toString());
const moeda = (v: number) => v.toLocaleString(locale(), { maximumFractionDigits: 0 });

/** Critérios só entram no radar quando os cinco vêm numéricos (rotação eliminada chega com `criterios: {}`). */
function criteriosCompletos(it: ItemRanking): Criterios | null {
  const c = it.criterios;
  return !it.eliminada && c && CRITERIOS.every(([k]) => typeof c[k] === "number") ? c : null;
}

function areaDaFazenda(latitude: string, longitude: string): { area: Area; rotulo: string } {
  const lat = Number(latitude), lon = Number(longitude);
  if (latitude.trim() && longitude.trim() && Number.isFinite(lat) && Number.isFinite(lon))
    return { area: { lat, lon }, rotulo: `${emIngles() ? "Farm at" : "Fazenda em"} ${lat}, ${lon}` };
  return {
    area: { talhao_id: TALHAO_DEMO },
    rotulo: emIngles()
      ? `Demo plot ${TALHAO_DEMO} (farm without valid coordinates)`
      : `Talhão demo ${TALHAO_DEMO} (fazenda sem coordenadas válidas)`,
  };
}

/** Radar SVG dos 5 critérios (0–1) para cada rotação exibida. */
function Radar({ itens }: { itens: ItemRanking[] }) {
  const c = 150, r = 105;
  const ponto = (i: number, v: number) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / CRITERIOS.length;
    return [c + Math.cos(a) * r * v, c + Math.sin(a) * r * v];
  };
  const poligono = (vals: number[]) => vals.map((v, i) => ponto(i, v).join(",")).join(" ");
  return (
    <svg viewBox="-50 0 400 300" role="img" aria-label={t("Comparação dos cinco critérios do motor")} style={{ width: "100%", maxWidth: 340 }}>
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon key={f} points={poligono(CRITERIOS.map(() => f))} fill="none" stroke="#28464b" />
      ))}
      {CRITERIOS.map(([k, nome], i) => {
        const [x, y] = ponto(i, 1);
        const [lx, ly] = ponto(i, 1.22);
        return (
          <g key={k}>
            <line x1={c} y1={c} x2={x} y2={y} stroke="#28464b" />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="#9aadb0">
              {t(nome)}
            </text>
          </g>
        );
      })}
      {itens.map((it, n) => {
        const crit = criteriosCompletos(it);
        return crit ? (
          <polygon
            key={it.id}
            points={poligono(CRITERIOS.map(([k]) => crit[k]))}
            fill={CORES[n]}
            fillOpacity={0.12}
            stroke={CORES[n]}
            strokeWidth={2}
          />
        ) : null;
      })}
    </svg>
  );
}

function Card({ item, cor, melhor, rotulo }: { item: ItemRanking; cor: string; melhor: boolean; rotulo: string }) {
  const [aberto, setAberto] = useState(false);
  const riscos = item.card?.riscos ?? [];
  return (
    <article className={"scenario panel " + (melhor ? "recommended" : "")}>
      <div className="scenario-ribbon">{t(melhor ? "MAIOR ADERÊNCIA AOS SEUS PESOS" : rotulo)}</div>
      <h2>{item.rotacao}</h2>
      {item.eliminada ? (
        <div className="risk">
          <small>{t("ELIMINADA PELAS REGRAS")}</small>
          <p>{(item.motivos ?? []).join(" ")}</p>
        </div>
      ) : (
        <>
          <div className="score">
            <strong style={{ color: cor }}>{pct(item.nota)}</strong>
            <small>/ 100</small>
            <small>{t("nota do motor")}</small>
          </div>
          <dl>
            {CRITERIOS.map(([k, nome]) => (
              <div key={k}>
                <dt>{t(nome)}</dt>
                <dd>
                  {pct(item.criterios?.[k])}/100
                  {k === "renda" && item.margem ? ` • R$ ${moeda(item.margem.total_r_ha)}/ha` : ""}
                </dd>
              </div>
            ))}
          </dl>
          <div className="benefit">
            <small>{t("BENEFÍCIO POTENCIAL")}</small>
            <p>{item.card?.beneficios[0] ?? t("Sem benefício marcante nos critérios avaliados.")}</p>
          </div>
          <div className="risk">
            <small>{t("PONTO DE ATENÇÃO")}</small>
            <p>{riscos[riscos.length - 1] ?? "—"}</p>
          </div>
          <button className={melhor ? "button" : "button secondary"} onClick={() => setAberto(!aberto)}>
            {t(aberto ? "Ocultar detalhes" : "Entender este cenário →")}
          </button>
          {aberto && item.card && (
            <div>
              <p>{item.card.por_que}</p>
              <ul>
                {item.card.evidencias.map((e) => (
                  <li key={e}>
                    <small>{e}</small>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </article>
  );
}

/** Seção "Compare os cenários" com dados reais do motor: rotação atual + 2 melhores alternativas. */
export default function EngineScenarios({ weights, latitude, longitude, crops, onSources }: {
  weights: number[];
  latitude: string;
  longitude: string;
  crops: { crop: string; plant: string }[];
  onSources: () => void;
}) {
  const [api, setApi] = useState<Health | null>(null);
  const [res, setRes] = useState<Recomendacao | null>(null);
  const [erro, setErro] = useState<ApiError | null>(null);
  const [carregando, setCarregando] = useState(false);
  const { area, rotulo } = areaDaFazenda(latitude, longitude);
  const rotacao = rotacaoDoHistorico(crops);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(null);
    health()
      .then((h) => {
        if (!ativo) return null;
        setApi(h);
        return h.status === "ok" ? recomendacao(area, rotacao.id, pesosDosSliders(weights)) : null;
      })
      .then((r) => ativo && setRes(r))
      .catch((e: unknown) => {
        if (!ativo) return;
        setRes(null);
        setErro(e instanceof ApiError ? e : new ApiError(0, "erro", String(e)));
      })
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [weights, latitude, longitude, rotacao.id]);

  const degradada = api != null && api.status !== "ok";
  const statusApi =
    erro?.codigo === "sem_conexao"
      ? t("indisponível")
      : !api
        ? t("verificando…")
        : degradada
          ? `${t("degradada")} (${api.detalhe})`
          : t("conectada");
  const contexto = (
    <small>
      {rotulo} • {t("rotação atual:")} {rotacao.rotulo}{" "}
      {t(rotacao.doHistorico ? "(do histórico de cultivo)" : "(padrão: histórico sem uma safra completa)")} • API:{" "}
      {statusApi}
      {carregando && res ? ` • ${t("recalculando…")}` : ""}
    </small>
  );

  const atual = res?.atual;
  const itens = res ? [...(atual ? [atual] : []), ...res.alternativas.slice(0, atual ? 2 : 3)] : [];

  if (erro || !res || itens.length === 0) {
    let mensagem: ReactNode = <p>{t("Calculando…")}</p>;
    if (erro)
      mensagem = (
        <p className="error" role="alert">
          {erro.codigo === "fora_da_regiao"
            ? `${erro.message} ${t("Ajuste a latitude/longitude em Minha Propriedade para um ponto no Oeste do Paraná.")}`
            : erro.message}
        </p>
      );
    else if (degradada)
      mensagem = (
        <p className="error" role="alert">
          {t("O motor está sem os dados necessários no momento. Tente novamente mais tarde.")}
        </p>
      );
    else if (res) mensagem = <p>{t("O motor não retornou rotações válidas para esta área.")}</p>;
    return (
      <section className="panel">
        {contexto}
        {mensagem}
      </section>
    );
  }

  const notas = itens.map((x) => (x.eliminada ? -1 : x.nota ?? -1));
  const melhor = notas.indexOf(Math.max(...notas));
  const destaque = itens[melhor];

  return (
    <>
      {contexto}
      <div className="scenario-grid">
        {itens.map((it, i) => (
          <Card
            key={it.id}
            item={it}
            cor={CORES[i]}
            melhor={i === melhor}
            rotulo={it.atual ? "ROTAÇÃO ATUAL" : "ALTERNATIVA PARA EXPLORAR"}
          />
        ))}
      </div>
      <div className="grid-two compare-bottom">
        <section className="panel">
          <h2>{t("Os objetivos, lado a lado")}</h2>
          <p>{t("Critérios do motor em escala 0–100 • maior = melhor")}</p>
          <Radar itens={itens} />
          <div className="legend">
            {itens.map((it, i) => (
              <span key={it.id} style={{ color: CORES[i] }}>
                ■ {it.rotacao}
              </span>
            ))}
          </div>
        </section>
        <section className="panel green-panel">
          <h2>{t("Por que esta estratégia foi sugerida?")}</h2>
          <p className="body-text">
            {emIngles()
              ? `${destaque.rotacao} had the highest score with the chosen weights.`
              : `${destaque.rotacao} teve a maior nota com os pesos escolhidos.`}
          </p>
          <p>{destaque.card?.por_que}</p>
          <h3>{t("Como a pontuação funciona")}</h3>
          <p>
            {t(
              "Média ponderada de cinco critérios calculados pelo motor (renda, solo, água, pragas e risco climático) com dados NASA POWER, SoilGrids, MapBiomas e IBGE. Valores estimados; não substituem o agrônomo.",
            )}
          </p>
          <button className="text-link" onClick={onSources}>
            {t("Ver premissas e limitações →")}
          </button>
        </section>
      </div>
    </>
  );
}
