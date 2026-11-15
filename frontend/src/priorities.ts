// Priority profiles and criteria shared by the setup wizard and the Rotation strategies page.
import type { Pesos } from "./api";

type Text = { pt: string; en: string };

export type PriorityId = "balanced" | "income" | "soil" | "risk";

export const PRIORITIES: { id: PriorityId; icon: string; title: Text; short: Text; description: Text; pesos: Pesos }[] = [
  {
    id: "balanced", icon: "✦",
    title: { pt: "Um pouco de equilíbrio", en: "A little balance" },
    short: { pt: "Equilíbrio", en: "Balance" },
    description: { pt: "Olhar para renda, solo, água e riscos juntos.", en: "Consider income, soil, water and risks together." },
    pesos: { renda: 5, solo: 5, agua: 5, pragas: 5, risco: 5 },
  },
  {
    id: "income", icon: "↗",
    title: { pt: "Mais retorno para a lavoura", en: "More return from my crops" },
    short: { pt: "Mais retorno", en: "More return" },
    description: { pt: "Dar mais atenção ao resultado financeiro.", en: "Give more attention to financial returns." },
    pesos: { renda: 9, solo: 3, agua: 3, pragas: 3, risco: 5 },
  },
  {
    id: "soil", icon: "❋",
    title: { pt: "Cuidar da terra para o futuro", en: "Care for the land’s future" },
    short: { pt: "Cuidar da terra", en: "Care for the land" },
    description: { pt: "Priorizar o solo e o uso da água.", en: "Focus on soil health and water use." },
    pesos: { renda: 4, solo: 9, agua: 8, pragas: 5, risco: 5 },
  },
  {
    id: "risk", icon: "◌",
    title: { pt: "Mais tranquilidade no próximo ciclo", en: "More peace of mind next season" },
    short: { pt: "Mais tranquilidade", en: "More peace of mind" },
    description: { pt: "Dar mais peso aos riscos climáticos e pragas.", en: "Give more weight to climate risks and pests." },
    pesos: { renda: 4, solo: 4, agua: 5, pragas: 8, risco: 9 },
  },
];

/** The profile whose weights match exactly, or "custom" after manual adjustments. */
export function matchPriority(pesos: Pesos): PriorityId | "custom" {
  const keys = Object.keys(pesos) as (keyof Pesos)[];
  return PRIORITIES.find(p => keys.every(k => p.pesos[k] === pesos[k]))?.id ?? "custom";
}

export type CriterionId = keyof Pesos;

/** The engine's five criteria (0–1 in the response), with a plain-language hint for each. */
export const CRITERIA: { id: CriterionId; name: Text; hint: Text }[] = [
  { id: "renda", name: { pt: "Renda", en: "Income" }, hint: { pt: "Lucro estimado por hectare", en: "Estimated profit per hectare" } },
  { id: "solo", name: { pt: "Saúde do solo", en: "Soil health" }, hint: { pt: "Cobertura, palha e nitrogênio para a terra", en: "Cover, straw and nitrogen for the land" } },
  { id: "agua", name: { pt: "Água", en: "Water" }, hint: { pt: "Menos falta d’água na 2ª safra", en: "Less water stress in the second crop" } },
  { id: "pragas", name: { pt: "Quebra de pragas", en: "Pest break" }, hint: { pt: "Interrompe o ciclo de pragas e doenças", en: "Breaks the pest and disease cycle" } },
  { id: "risco", name: { pt: "Risco climático", en: "Climate risk" }, hint: { pt: "Menos chance de geada e veranico", en: "Lower chance of frost and dry spells" } },
];
