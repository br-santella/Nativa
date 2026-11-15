// Cliente mínimo da API do motor (motor_field_shift). Contrato: docs/contratos.md (C3).
const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Pesos = { renda: number; solo: number; agua: number; pragas: number; risco: number };

export type Area = { talhao_id: string } | { lat: number; lon: number } | { geometry: { type: string; coordinates: unknown[] } };

export type Card = {
  por_que: string;
  evidencias: string[];
  beneficios: string[];
  lacunas: string[];
  riscos: string[];
  avisos: string[];
};

export type ItemRanking = {
  posicao: number | null;
  id: string;
  rotacao: string;
  /** Summer crop and second crop of the rotation (ids from GET /v1/opcoes, names in the response language). */
  verao?: { id: string; nome: string };
  segunda?: { id: string; nome: string };
  nota: number | null;
  atual: boolean;
  criterios?: { renda: number; solo: number; agua: number; pragas: number; risco: number };
  margem?: { total_r_ha: number; incremental_r_ha: number };
  card?: Card;
  eliminada?: boolean;
  motivos?: string[];
};

export type Eliminada = { id: string; rotacao: string; motivos: string[] };

/** Ranking of one set of combinations; `posicao` restarts at 1 in each block. */
export type Bloco = { ranking: ItemRanking[]; alternativas: ItemRanking[]; eliminadas: Eliminada[] };

export type DataOrigem = { data: string; origem: "estagio" | "informada" | "premissa" | "derivada" };

export type Recomendacao = {
  cultura_atual: { id: string; nome: string } | null;
  colheita_estimada: DataOrigem | null;
  semeadura_2a: DataOrigem | null;
  dias_ate_colheita: number | null;
  /** Same summer crop as the current rotation: what goes in after this harvest. */
  agora: Bloco | null;
  /** Other summer crop: decision for the next season, compared to the current rotation. */
  proxima_safra: Bloco | null;
  atual: ItemRanking | null;
  /** Compatibility aliases of `agora`. */
  ranking: ItemRanking[];
  alternativas: ItemRanking[];
  eliminadas: Eliminada[];
  avisos: string[];
};

export type Irrigacao = { disponivel: boolean };

export type EntradaRecomendacao = {
  area: Area;
  rotacaoAtual: string;
  pesos?: Pesos;
  colheitaPrevista?: string;
  irrigacao?: Irrigacao;
};

/** API language: the response is translated on the server (`?lang` wins over the browser's Accept-Language). */
export type Lang = "pt-BR" | "en";

export type Health = { status: "ok" | "degradado"; dados_carregados: boolean; versao: string; detalhe: string | null };

export class ApiError extends Error {
  constructor(public status: number, public codigo: string, mensagem: string) {
    super(mensagem);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(BASE + path, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch {
    throw new ApiError(0, "sem_conexao", `Não foi possível conectar à API em ${BASE}.`);
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const codigo = body?.erro ?? "erro_http";
    const mensagem = body?.mensagem ?? (Array.isArray(body?.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ") : `HTTP ${r.status}`);
    throw new ApiError(r.status, codigo, mensagem);
  }
  return body as T;
}

export const health = (lang: Lang) => request<Health>(`/health?lang=${lang}`);

export const recomendacao = (e: EntradaRecomendacao, lang: Lang, inputs?: Record<string, unknown>) =>
  request<Recomendacao>(`/v1/recomendacao?lang=${lang}`, {
    method: "POST",
    body: JSON.stringify({
      ...inputs,
      area: e.area,
      rotacao_atual: e.rotacaoAtual,
      pesos: e.pesos,
      colheita_prevista: e.colheitaPrevista,
      irrigacao: e.irrigacao,
      incluir_diagnostico: false,
    }),
  });

/** Sliders do NATIVA (0–100: água, solo, rentabilidade, resiliência) -> pesos do motor (0–10). Ver docs/entradas.md. */
export function pesosDosSliders([agua, solo, renda, resiliencia]: number[]): Pesos {
  const p = (v: number) => Math.round(v) / 10;
  return { agua: p(agua), solo: p(solo), renda: p(renda), risco: p(resiliencia), pragas: 3 };
}

export type MonitoringIndicator = { source: string; unit: string; value: number | null; delta: number | null; start: string | null; end: string | null; series: { date: string; value: number | null }[] };
export type Monitoring = { indicators: Record<string, MonitoringIndicator> };
export function getMonitoring(lat: number, lon: number, signal: AbortSignal) {
  return request<Monitoring>(`/v1/monitoramento?lat=${lat}&lon=${lon}`, { signal });
}
