export const months = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
];
export const initialFarm = {
  name: "Fazenda Boa Vista",
  city: "Sorriso, MT",
  country: "Brasil",
  latitude: "-12.55",
  longitude: "-55.72",
  area: "120",
  texture: "Argiloso",
  ph: "5.8",
  drainage: "Moderada",
  organic: "3.2",
  irrigation: "Sim",
  irrigationType: "Pivô central",
  waterRestriction: "Limite de captação no período seco",
  crop: "Soja",
};
export type Farm = typeof initialFarm;
export const initialCrops = [
  {
    id: 1,
    crop: "Soja",
    season: "2025/26",
    plant: "2025-10-15",
    harvest: "2026-02-20",
    area: "120",
    yield: "",
    status: "Em crescimento",
  },
  {
    id: 2,
    crop: "Milho",
    season: "2025",
    plant: "2025-03-05",
    harvest: "2025-07-28",
    area: "120",
    yield: "98",
    status: "Concluído",
  },
  {
    id: 3,
    crop: "Soja",
    season: "2024/25",
    plant: "2024-10-12",
    harvest: "2025-02-22",
    area: "120",
    yield: "58",
    status: "Concluído",
  },
  {
    id: 4,
    crop: "Milho",
    season: "2024",
    plant: "2024-03-10",
    harvest: "2024-07-30",
    area: "120",
    yield: "92",
    status: "Concluído",
  },
];
export type Crop = (typeof initialCrops)[number];
export const series = {
  temperature: [25, 26.2, 25, 23.8, 21.5, 20.5, 21.5, 23.8, 27, 28.2, 26, 25],
  rain: [220, 190, 170, 110, 60, 25, 15, 25, 75, 140, 190, 230],
  moisture: [38, 40, 39, 34, 29, 25, 24, 25, 29, 34, 38, 40],
  ndvi: [0.7, 0.76, 0.68, 0.5, 0.62, 0.7, 0.6, 0.4, 0.32, 0.5, 0.62, 0.74],
};
export const scenarios = [
  {
    name: "Rotação atual",
    sequence: "Soja → Milho → Pousio",
    calendar: "Soja / Milho / Pousio",
    water: "Maior demanda",
    soil: "Cobertura limitada",
    climate: "Exposição na seca",
    benefit: "Aproveita a estrutura e a experiência já disponíveis.",
    risk: "Solo descoberto no intervalo entre safras.",
    detail:
      "O pousio pode deixar o solo sem cobertura, aumentando a exposição à erosão e à perda de água por evaporação. A intensidade depende das condições locais.",
    notes: [48, 52, 82, 62],
    color: "#93a8ad",
  },
  {
    name: "Conservação do solo",
    sequence: "Soja → Milho + braquiária",
    calendar: "Soja / Milho + Braquiária / Cobertura",
    water: "Menor perda por evaporação",
    soil: "Mais cobertura e palhada",
    climate: "Proteção no período seco",
    benefit: "Mantém cobertura e diversifica o sistema radicular.",
    risk: "Exige manejo da cobertura e ajuste da semeadura.",
    detail:
      "A palhada e as raízes da braquiária podem proteger a superfície, favorecer infiltração e contribuir para a matéria orgânica ao longo do tempo. O resultado depende da implantação e do manejo.",
    notes: [84, 92, 74, 82],
    color: "#a8c9a3",
  },
  {
    name: "Adaptação climática",
    sequence: "Sorgo → Crotalária → Soja",
    calendar: "Sorgo / Crotalária / Soja",
    water: "Menor demanda potencial",
    soil: "Diversificação de raízes",
    climate: "Maior tolerância à seca",
    benefit: "Diversifica culturas e a exposição ao risco climático.",
    risk: "Depende de mercado, sementes e janela de plantio.",
    detail:
      "O sorgo apresenta tolerância relativa ao déficit hídrico. A crotalária pode contribuir para a ciclagem de nutrientes, com resposta dependente da espécie, do solo e do manejo.",
    notes: [88, 78, 65, 90],
    color: "#e9b857",
  },
];
export const profiles = {
  soil: [80, 90, 60, 75],
  water: [100, 20, 20, 100],
  profit: [0, 0, 100, 0],
};
export function score(notes: number[], weights: number[]) {
  const total = weights.reduce((a, b) => a + b, 0);
  return total
    ? Math.round(notes.reduce((s, n, i) => s + n * weights[i], 0) / total)
    : 0;
}
export const info = {
  sources: {
    title: "Fontes, escala e incerteza",
    subtitle:
      "Referências de produtos NASA. Todos os valores desta experiência são fictícios.",
    items: [
      [
        "NASA POWER",
        "Meteorologia em grade: temperatura e precipitação. A escala regional não substitui uma estação local.",
      ],
      [
        "NASA SMAP",
        "Umidade na camada superficial do solo. A conversão para percentual é ilustrativa e não descreve toda a zona de raízes.",
      ],
      [
        "NASA MODIS / NDVI",
        "Índice espectral relacionado ao vigor vegetal. Nuvens, resolução e época do ano afetam a leitura.",
      ],
      [
        "Sem validação agronômica",
        "Cenários ilustrativos: confirme a adequação com assistência técnica local.",
      ],
    ],
  },
  indicators: {
    title: "O que os indicadores significam?",
    subtitle: "Uma leitura simples para apoiar a exploração.",
    items: [
      [
        "NDVI",
        "Índice de −1 a 1 relacionado ao vigor vegetal. Não equivale à produtividade.",
      ],
      [
        "Umidade do solo",
        "Água na camada superficial. A umidade das raízes pode ser diferente.",
      ],
      [
        "pH do solo",
        "Indica acidez ou alcalinidade. A interpretação depende da cultura e da análise laboratorial.",
      ],
    ],
  },
  help: {
    title: "Da órbita à sua terra",
    subtitle: "Um roteiro rápido para explorar a NATIVA.",
    items: [
      [
        "1. Conheça a propriedade",
        "Explore os indicadores e o mapa ilustrativo.",
      ],
      [
        "2. Registre seu contexto",
        "Veja os campos de solo, água e histórico de cultivo.",
      ],
      [
        "3. Compare possibilidades",
        "Explore os perfis solo, água/clima e rentabilidade ou ajuste suas prioridades.",
      ],
    ],
  },
  technology: {
    title: "Tecnologia espacial. Propósito no campo.",
    subtitle: "Da observação do espaço às possibilidades da sua próxima safra.",
    items: [
      [
        "Dados em perspectiva",
        "Referências NASA POWER, SMAP e MODIS contextualizam indicadores de clima, umidade superficial e vegetação.",
      ],
      [
        "Da observação à decisão",
        "Localize sua propriedade, explore condições ambientais e compare estratégias de rotação.",
      ],
      [
        "Sobre esta demonstração",
        "Os cenários e indicadores são ilustrativos. Nenhum produto NASA está conectado nesta versão.",
      ],
    ],
  },
};
