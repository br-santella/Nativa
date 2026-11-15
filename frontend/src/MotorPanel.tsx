import { useEffect, useState } from "react";
import { ApiError, health, pesosDosSliders, recomendacao } from "./api";
import type { Area, Health, Recomendacao } from "./api";

// Talhão demo do motor (Toledo, PR): usado só quando a fazenda não tem lat/lon válidas.
const TALHAO_DEMO = "72638";
// Rotação atual fixa enquanto o histórico de cultivos não alimenta a API.
const ROTACAO_ATUAL = "soja__milho_safrinha";

const brl = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const nota = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Coordenadas da fazenda (texto do formulário) -> área do motor; sem lat/lon válidas, usa o talhão demo. */
function areaDaFazenda(latitude: string, longitude: string): { area: Area; rotulo: string } {
  const lat = Number(latitude), lon = Number(longitude);
  if (latitude.trim() && longitude.trim() && Number.isFinite(lat) && Number.isFinite(lon))
    return { area: { lat, lon }, rotulo: `Fazenda em ${lat}, ${lon}` };
  return { area: { talhao_id: TALHAO_DEMO }, rotulo: `Talhão demo ${TALHAO_DEMO} (fazenda sem coordenadas válidas)` };
}

/** Ranking real do motor para a localização da fazenda, com os pesos aplicados nos sliders da tela de Rotação. */
export default function MotorPanel({ weights, latitude, longitude }: { weights: number[]; latitude: string; longitude: string }) {
  const [api, setApi] = useState<Health | null>(null);
  const [res, setRes] = useState<Recomendacao | null>(null);
  const [erro, setErro] = useState<ApiError | null>(null);
  const { area, rotulo } = areaDaFazenda(latitude, longitude);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(null);
    health()
      .then((h) => {
        if (!ativo) return null;
        setApi(h);
        return h.status === "ok" ? recomendacao(area, ROTACAO_ATUAL, pesosDosSliders(weights)) : null;
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
  }, [weights, latitude, longitude]);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>03 Recomendação do motor (dados reais)</h2>
          <p>
            {rotulo} • rotação atual: soja → milho safrinha • pesos dos controles acima
          </p>
        </div>
        <small>
          API: {erro?.codigo === "sem_conexao" ? "indisponível" : !api ? "verificando…" : api.status === "ok" ? "conectada" : `degradada (${api.detalhe})`}
        </small>
      </div>

      {erro && (
        <p className="error" role="alert">
          {erro.codigo === "fora_da_regiao"
            ? `${erro.message} Ajuste a latitude/longitude em Minha Propriedade para um ponto no Oeste do Paraná.`
            : erro.message}
        </p>
      )}
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
