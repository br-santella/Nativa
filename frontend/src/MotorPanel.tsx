import { useEffect, useState } from "react";
import { ApiError, health, pesosDosSliders, recomendacao } from "./api";
import type { Health, Recomendacao } from "./api";

// Talhão demo do motor (Toledo, PR) e rotação atual usados enquanto o formulário não alimenta a API.
const TALHAO_DEMO = "72638";
const ROTACAO_ATUAL = "soja__milho_safrinha";

const brl = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const nota = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Ranking real do motor para o talhão demo, com os pesos aplicados nos sliders da tela de Rotação. */
export default function MotorPanel({ weights }: { weights: number[] }) {
  const [api, setApi] = useState<Health | null>(null);
  const [res, setRes] = useState<Recomendacao | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro("");
    health()
      .then((h) => {
        if (!ativo) return null;
        setApi(h);
        return h.status === "ok" ? recomendacao({ talhao_id: TALHAO_DEMO }, ROTACAO_ATUAL, pesosDosSliders(weights)) : null;
      })
      .then((r) => ativo && setRes(r))
      .catch((e: unknown) => ativo && setErro(e instanceof ApiError ? e.message : String(e)))
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [weights]);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>03 Recomendação do motor (dados reais)</h2>
          <p>
            Talhão demo {TALHAO_DEMO} • Toledo, PR • rotação atual: soja → milho safrinha • pesos dos controles acima
          </p>
        </div>
        <small>
          API: {erro ? "indisponível" : !api ? "verificando…" : api.status === "ok" ? "conectada" : `degradada (${api.detalhe})`}
        </small>
      </div>

      {erro && <p className="error" role="alert">{erro}</p>}
      {carregando && !res && !erro && <p>Calculando…</p>}

      {res && (
        <>
          <ol>
            {res.ranking.slice(0, 3).map((x) => (
              <li key={x.id}>
                <strong>
                  {x.rotacao}
                  {x.atual ? " (atual)" : ""}
                </strong>{" "}
                — nota {nota(x.nota)}
                {x.margem && <> • margem R$ {brl(x.margem.total_r_ha)}/ha</>}
                {x.card && <p>{x.card.por_que}</p>}
              </li>
            ))}
          </ol>
          {res.atual && !res.ranking.slice(0, 3).some((x) => x.atual) && (
            <p>
              Rotação atual ({res.atual.rotacao}):{" "}
              {res.atual.eliminada ? "eliminada — " + (res.atual.motivos ?? []).join(" ") : `nota ${nota(res.atual.nota)}, posição ${res.atual.posicao}`}
            </p>
          )}
          <small>
            {res.eliminadas.length} rotações eliminadas por regras legais/calendário • valores estimados; não substituem o agrônomo.
          </small>
        </>
      )}
    </section>
  );
}
