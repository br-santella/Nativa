// Cliente mínimo da API do motor (motor_field_shift). Contrato: docs/contratos.md (C3).
const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Pesos = { renda: number; solo: number; agua: number; pragas: number; risco: number };

export type Area = { talhao_id: string } | { lat: number; lon: number };

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
  nota: number | null;
  atual: boolean;
  criterios?: { renda: number; solo: number; agua: number; pragas: number; risco: number };
  margem?: { total_r_ha: number; incremental_r_ha: number };
  card?: Card;
  eliminada?: boolean;
  motivos?: string[];
};

export type Recomendacao = {
  ranking: ItemRanking[];
  atual: ItemRanking | null;
  alternativas: ItemRanking[];
  eliminadas: { id: string; rotacao: string; motivos: string[] }[];
  avisos: string[];
};

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

export const health = () => request<Health>("/health");

export const recomendacao = (area: Area, rotacaoAtual: string, pesos?: Pesos) =>
  request<Recomendacao>("/v1/recomendacao", {
    method: "POST",
    body: JSON.stringify({ area, rotacao_atual: rotacaoAtual, pesos, incluir_diagnostico: false }),
  });

/** Sliders do NATIVA (0–100: água, solo, rentabilidade, resiliência) -> pesos do motor (0–10). Ver docs/entradas.md. */
export function pesosDosSliders([agua, solo, renda, resiliencia]: number[]): Pesos {
  const p = (v: number) => Math.round(v) / 10;
  return { agua: p(agua), solo: p(solo), renda: p(renda), risco: p(resiliencia), pragas: 3 };
}
