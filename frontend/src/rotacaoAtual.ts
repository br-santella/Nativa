// Derives the current rotation (engine id "<verao>__<segunda>") from the NATIVA crop history.
// Summer = planted September to December; 2nd window = planted January to July of the following year.
// Valid ids: GET /v1/opcoes (combinacoes). If a summer crop is still in the field (no 2nd-window crop yet), the current
// rotation uses its summer crop and the 2nd crop of the last complete season, and its harvest goes as `colheita_prevista`.

export const ROTACAO_PADRAO = "soja__milho_safrinha";

type Cultivo = { crop: string; plant: string; harvest?: string };

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

export type RotacaoAtual = {
  id: string;
  rotulo: string;
  doHistorico: boolean;
  /** Expected harvest (dd/mm) of the summer crop still in the field, if any. */
  colheitaPrevista?: string;
};

const dia = (iso: string) => new Date(iso + "T12:00:00");
const valida = (d: Date) => !Number.isNaN(d.getTime());
const ddmm = (d: Date) => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;

export function rotacaoDoHistorico(cultivos: Cultivo[], hoje: Date = new Date()): RotacaoAtual {
  const datados = cultivos
    .map((c) => ({ crop: c.crop, data: dia(c.plant), colheita: c.harvest ? dia(c.harvest) : null }))
    .filter((c) => valida(c.data))
    .sort((a, b) => b.data.getTime() - a.data.getTime()); // most recent first

  let emCampo: { verao: string; colheita?: string } | undefined; // summer crop with no 2nd-window crop yet
  for (const v of datados) {
    const mes = v.data.getMonth() + 1;
    const verao = VERAO[v.crop];
    if (!verao || mes < 9) continue;
    const ano = v.data.getFullYear() + 1; // the 2nd window is in the year after the summer planting
    const naJanela = datados.filter((c) => c.data.getFullYear() === ano && c.data.getMonth() + 1 <= 7).map((c) => c.crop);
    const temDepois = datados.some((c) => c.data > v.data);
    let segunda: string | undefined;
    if (naJanela.includes("Milho") && naJanela.includes("Braquiária")) segunda = "milho_braquiaria";
    else segunda = naJanela.map((c) => SEGUNDA[c]).find(Boolean);
    if (!segunda && temDepois) segunda = "pousio"; // season is over and nothing was planted in the 2nd window
    if (!segunda) {
      // season still running: remember the crop in the field and use the previous season's 2nd crop
      if (!emCampo) {
        const futura = v.colheita && valida(v.colheita) && v.colheita >= hoje;
        emCampo = { verao, colheita: futura ? ddmm(v.colheita!) : undefined };
      }
      continue;
    }
    const veraoAtual = emCampo?.verao ?? verao;
    return {
      id: `${veraoAtual}__${segunda}`,
      rotulo: `${NOMES[veraoAtual]} → ${NOMES[segunda]}`,
      doHistorico: true,
      colheitaPrevista: emCampo?.colheita,
    };
  }
  if (emCampo) {
    const id = `${emCampo.verao}__milho_safrinha`;
    return { id, rotulo: `${NOMES[emCampo.verao]} → ${NOMES.milho_safrinha}`, doHistorico: false, colheitaPrevista: emCampo.colheita };
  }
  return { id: ROTACAO_PADRAO, rotulo: "soja → milho safrinha", doHistorico: false };
}
