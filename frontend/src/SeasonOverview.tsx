import { useEffect, useState } from "react";
import type { Crop, Farm } from "./data";
import type { SetupInputs } from "./PropertyWizard";
import { recomendacao } from "./api";
import type { Pesos } from "./api";
import type { Area, Recomendacao } from "./api";
import { rotacaoDoHistorico } from "./rotacaoAtual";
import options from "./setup-options.json";
import { t, useLanguage } from "./i18n";

type Props = { farm: Farm; crops: Crop[]; pesos: Pesos; setupInputs?: SetupInputs; onNavigate: (page: "farm" | "history" | "rotation") => void };

export default function SeasonOverview({ farm, crops, pesos, setupInputs, onNavigate }: Props) {
  const { language } = useLanguage();
  const en = language === "en";
  const say = (pt: string, english: string) => en ? english : pt;
  const rotation = rotacaoDoHistorico(crops);
  const rotationId = setupInputs?.rotacao_atual ?? rotation.id;
  const rotationName = options.combinacoes.find(item => item.id === rotationId)?.nome ?? rotation.rotulo;
  const [result, setResult] = useState<Recomendacao | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let active = true;
    setResult(null);
    setStatus("loading");
    const valid = farm.latitude.trim() !== "" && farm.longitude.trim() !== "" &&
      Number.isFinite(Number(farm.latitude)) && Number.isFinite(Number(farm.longitude)) &&
      Math.abs(Number(farm.latitude)) <= 90 && Math.abs(Number(farm.longitude)) <= 180;
    const area: Area | undefined = setupInputs?.area ?? (valid ? { lat: Number(farm.latitude), lon: Number(farm.longitude) } : undefined);
    if (!area) {
      setStatus("error");
      return;
    }
    const irrigacao = farm.irrigation === "Sim" ? { disponivel: true } : farm.irrigation === "Não" ? { disponivel: false } : undefined;
    recomendacao({
      area, rotacaoAtual: rotationId,
      pesos,
      colheitaPrevista: setupInputs ? setupInputs.colheita_prevista : rotation.colheitaPrevista,
      irrigacao,
    }, en ? "en" : "pt-BR", setupInputs)
      .then(data => { if (active) { setResult(data); setStatus("ready"); } })
      .catch(() => { if (active) setStatus("error"); });
    return () => { active = false; };
  }, [farm.latitude, farm.longitude, farm.irrigation, setupInputs, pesos, rotationId, rotation.colheitaPrevista, en]);

  const current = result?.atual;
  const alternatives = result?.agora?.alternativas ?? result?.alternativas ?? [];
  const alternative = alternatives.find(item => !item.eliminada && item.nota != null);
  const gain = alternative?.nota != null && current?.nota != null && !current.eliminada
    ? Math.round((alternative.nota - current.nota) * 100) : null;
  const soil = !current?.eliminada && typeof current?.criterios?.solo === "number"
    ? Math.max(0, Math.min(100, Math.round(current.criterios.solo * 100))) : null;
  const recordedSeason = [...crops].filter(crop => crop.crop === farm.crop).sort((a, b) => b.plant.localeCompare(a.plant))[0]?.season;
  const reference = setupInputs?.data_referencia;
  const startYear = reference ? Number(reference.slice(0, 4)) - (Number(reference.slice(5, 7)) < 9 ? 1 : 0) : null;
  const season = startYear ? `${startYear}/${String(startYear + 1).slice(-2)}` : recordedSeason;
  const pending = say("Calculando a análise da rotação…", "Calculating the rotation analysis…");

  return <section className="season-overview" aria-labelledby="annual-season-title">
    <header className="season-heading">
      <div className="season-heading-title"><span className="season-step" aria-hidden="true">02</span><div><h2 id="annual-season-title">{say("Safra anual", "Annual season")}</h2><p>{say("Entenda sua rotação hoje e veja onde há espaço para melhorar o próximo ciclo.", "Understand your current rotation and explore opportunities for the next growing cycle.")}</p></div></div>
      {season && <span className="season-period">{season}</span>}
    </header>
    <div className="season-rotation">
      <div><small>{say("ROTAÇÃO ATUAL", "CURRENT ROTATION")}</small><h3>{t(rotationName)}</h3></div>
      <span>{setupInputs ? say("Informada por você", "Provided by you") : rotation.doHistorico ? say("Do histórico de cultivo", "From crop history") : say("Referência inicial · confirme sua rotação", "Initial assumption · confirm your rotation")}</span>
    </div>
    {status === "error" && <p className="season-status" role="status">{say("A análise da rotação está indisponível no momento. Os dados cadastrados continuam abaixo; a avaliação e as alternativas aparecem quando o motor estiver disponível.", "Rotation analysis is currently unavailable. Your recorded details are shown below; the assessment and alternatives appear when the engine is available.")}</p>}
    <div className="season-analysis-grid">
      <article className="season-analysis-card season-soil">
        <div className="season-card-ribbon">{say("Seus dados · ponto de partida", "Your data · starting point")}</div>
        <h3>{say("Saúde do solo", "Soil health")}</h3>
        <dl>
          <div><dt>pH</dt><dd>{farm.ph || "—"}</dd></div>
          <div><dt>{say("Matéria orgânica", "Organic matter")}</dt><dd>{farm.organic ? `${farm.organic}%` : "—"}</dd></div>
          <div><dt>{say("Textura", "Texture")}</dt><dd>{t(farm.texture || "Não informado")}</dd></div>
        </dl>
        {soil != null && <div className="season-soil-score"><div><span>{say("Critério solo da rotação", "Rotation soil criterion")}</span><strong>{soil}/100</strong></div><progress value={soil} max="100" /></div>}
        <small>{say("Dados cadastrados. A pontuação compara rotações; não substitui uma análise de solo.", "Recorded data. The score compares rotations; it does not replace a soil test.")}</small>
        <footer className="season-card-footer"><button type="button" onClick={() => onNavigate("farm")}>{say("Ver dados da propriedade →", "View property details →")}</button></footer>
      </article>
      <article className="season-analysis-card season-current">
        <div className="season-card-ribbon">{say("Sua rotação hoje · referência", "Your rotation today · reference")}</div>
        <h3>{say("Análise da rotação atual", "Current rotation assessment")}</h3>
        {status === "loading" ? <p role="status">{pending}</p> : current ? <>
          {current.eliminada ? <p className="warm">{say("Rotação limitada pelas regras do motor.", "Rotation excluded by engine rules.")}</p> : current.nota != null && <p className="season-score">{Math.round(current.nota * 100)}<small>/100</small></p>}
          <p>{current.card?.por_que ?? current.motivos?.join(" ") ?? say("Sem avaliação detalhada para esta rotação.", "No detailed assessment for this rotation.")}</p>
          {!!current.card?.riscos.length && <div className="season-attention"><small>{say("PONTO DE ATENÇÃO", "POINT TO CONSIDER")}</small><p>{current.card.riscos[current.card.riscos.length - 1]}</p></div>}
        </> : <p>{say("Aguardando avaliação da rotação atual.", "Waiting for the current rotation assessment.")}</p>}
        <footer className="season-card-footer"><button type="button" onClick={() => onNavigate("history")}>{say("Consultar histórico de cultivo →", "View crop history →")}</button></footer>
      </article>
      <article className="season-analysis-card season-improvement">
        <div className="season-card-ribbon">{say("Explore o próximo ciclo", "Explore the next growing cycle")}</div>
        <h3>{say("Potencial de melhoria", "Potential for improvement")}</h3>
        {status === "loading" ? <p>{pending}</p> : alternative ? <>
          {gain != null && gain > 0 && <p className="season-score">+{gain}<small>{say("pontos", "points")}</small></p>}
          <h4>{alternative.rotacao}</h4>
          <p>{alternative.card?.beneficios[0] ?? alternative.card?.por_que ?? say("Explore esta alternativa na comparação de estratégias.", "Explore this alternative in the strategy comparison.")}</p>
          <small>{gain != null && gain > 0 ? say("Diferença de pontuação em relação à rotação atual, com suas prioridades.", "Score difference from the current rotation, using your priorities.") : say("Alternativa para explorar; não há ganho de pontuação confirmado sobre a rotação atual.", "An alternative to explore; no score improvement over the current rotation is confirmed.")}</small>
        </> : <p>{status === "ready" ? say("Nenhuma alternativa válida retornada para este contexto.", "No valid alternative returned for this context.") : say("As oportunidades aparecem após a comparação das rotações.", "Opportunities appear after comparing rotations.")}</p>}
        <footer className="season-card-footer"><button type="button" onClick={() => onNavigate("rotation")}>{say("Comparar estratégias →", "Compare strategies →")}</button></footer>
      </article>
    </div>
  </section>;
}
