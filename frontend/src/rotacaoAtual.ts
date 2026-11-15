// Deduz a rotação atual (id do motor "<verao>__<segunda>") a partir do histórico de cultivos do NATIVA.
// Verão = plantio de setembro a dezembro; 2ª janela = plantio de janeiro a julho do ano seguinte.
// Ids válidos: GET /v1/opcoes (combinacoes).

export const ROTACAO_PADRAO = "soja__milho_safrinha";

type Cultivo = { crop: string; plant: string };

const VERAO: Record<string, string> = { Soja: "soja", Milho: "milho_verao" };
const SEGUNDA: Record<string, string> = {
  Milho: "milho_safrinha",
  Trigo: "trigo",
  Sorgo: "sorgo",
  "Crotalária": "milheto_crotalaria",
};

const NOMES: Record<string, string> = {
  soja: "soja",
  milho_verao: "milho verão",
  milho_safrinha: "milho safrinha",
  milho_braquiaria: "milho safrinha + braquiária",
  trigo: "trigo",
  sorgo: "sorgo",
  milheto_crotalaria: "milheto/crotalária",
  pousio: "pousio",
};

export type RotacaoAtual = { id: string; rotulo: string; doHistorico: boolean };

export function rotacaoDoHistorico(cultivos: Cultivo[]): RotacaoAtual {
  const datados = cultivos
    .map((c) => ({ crop: c.crop, data: new Date(c.plant + "T12:00:00") }))
    .filter((c) => !Number.isNaN(c.data.getTime()))
    .sort((a, b) => b.data.getTime() - a.data.getTime()); // mais recente primeiro

  for (const v of datados) {
    const mes = v.data.getMonth() + 1;
    const verao = VERAO[v.crop];
    if (!verao || mes < 9) continue;
    const ano = v.data.getFullYear() + 1; // a 2ª janela é no ano seguinte ao plantio do verão
    const naJanela = datados.filter((c) => c.data.getFullYear() === ano && c.data.getMonth() + 1 <= 7).map((c) => c.crop);
    const temDepois = datados.some((c) => c.data > v.data);
    let segunda: string | undefined;
    if (naJanela.includes("Milho") && naJanela.includes("Braquiária")) segunda = "milho_braquiaria";
    else segunda = naJanela.map((c) => SEGUNDA[c]).find(Boolean);
    if (!segunda && temDepois) segunda = "pousio"; // safra já passou e nada foi plantado na 2ª janela
    if (!segunda) continue; // safra ainda em andamento: usa a anterior
    return { id: `${verao}__${segunda}`, rotulo: `${NOMES[verao]} → ${NOMES[segunda]}`, doHistorico: true };
  }
  return { id: ROTACAO_PADRAO, rotulo: "soja → milho safrinha", doHistorico: false };
}
