"""Pydantic schemas (input and output) of the API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from field_shift import calendario

Semeadura = Literal["15/01", "01/02", "15/02", "01/03", "15/03"]
# Closed catalog enums (mirror field_shift.app.engine; a test checks this). Rotation = pair (summer, second window).
CulturaVerao = Literal["soja", "milho_verao"]
CulturaSegunda = Literal[
    "milho_safrinha",
    "milho_braquiaria",
    "trigo",
    "aveia",
    "milheto_crotalaria",
    "pousio",
    "soja_safrinha",
    "sorgo",
    "feijao_safrinha",
    "nabo_forrageiro",
    "aveia_nabo",
]
# Old API slugs (soybean in summer only): milho_safrinha = soja__milho_safrinha.
SLUGS_LEGADOS = ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio", "soja_safrinha")
IDS_ROTACAO = tuple(f"{v}__{s}" for v in CulturaVerao.__args__ for s in CulturaSegunda.__args__)
RotacaoSlug = Literal[IDS_ROTACAO + SLUGS_LEGADOS]  # new id "<verao>__<segunda>" or old slug
# Summer-crop stages (mirror field_shift.calendario.ESTAGIOS; a test checks this). The stage must match the current rotation's summer crop.
EstagioVerao = Literal[
    "vegetativo", "floracao", "formacao_vagens", "enchimento_graos", "maturacao", "colhida", "pendoamento", "grao_leitoso", "grao_farinaceo"
]
CulturaCusto = Literal[
    "soja",
    "milho",
    "milho_2safra",
    "milho_verao",
    "milho_1safra",
    "trigo",
    "feijao",
    "feijao_2safra",
    "sorgo",
    "aveia",
    "milheto_crotalaria",
    "braquiaria_consorcio",
    "pousio",
    "nabo_forrageiro",
    "aveia_nabo",
]
CulturaProdutividade = Literal["soja", "milho", "milho_2safra", "milho_verao", "trigo", "feijao", "sorgo"]
SemComprador = Literal["milho", "trigo", "sorgo", "feijao", "aveia_grao"]
Peso = Annotated[float, Field(ge=0, le=10)]

POLIGONO_EXEMPLO: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [
        [
            [-53.3045, -24.9045],
            [-53.2955, -24.9045],
            [-53.2955, -24.8955],
            [-53.3045, -24.8955],
            [-53.3045, -24.9045],
        ]
    ],
}


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------
class Area(BaseModel):
    """Area to analyze. Provide EXACTLY ONE of the forms: `geometry`, `lat`+`lon` or `talhao_id`."""

    geometry: dict[str, Any] | None = Field(
        None,
        description="GeoJSON Polygon, MultiPolygon or Feature in EPSG:4326 (lon, lat). Max. 5000 ha.",
    )
    lat: float | None = Field(None, ge=-90, le=90, description="Latitude (becomes a ~100 ha square).")
    lon: float | None = Field(None, ge=-180, le=180, description="Longitude (becomes a ~100 ha square).")
    talhao_id: str | None = Field(None, description="Id of a demo field (see GET /v1/talhoes/demo).")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"talhao_id": "72638"}]},
    )

    @model_validator(mode="after")
    def _uma_forma(self) -> "Area":
        ponto = self.lat is not None or self.lon is not None
        if ponto and (self.lat is None or self.lon is None):
            raise ValueError("for a point, provide 'lat' and 'lon' together")
        formas = sum([self.geometry is not None, ponto, self.talhao_id is not None])
        if formas != 1:
            raise ValueError("provide exactly one area form: 'geometry', 'lat'+'lon' or 'talhao_id'")
        return self

    def para_servico(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class Ajustes(BaseModel):
    """The farmer's own prices and costs (they override the reference values)."""

    precos: dict[Literal["soja", "milho", "trigo", "feijao", "sorgo"], Annotated[float, Field(ge=0)]] | None = Field(
        None, description="Price in BRL per 60 kg bag. 'milho' applies to summer and off-season corn."
    )
    custos: dict[CulturaCusto, Annotated[float, Field(ge=0)]] | None = Field(
        None,
        description=(
            "Cost per crop in BRL/ha ('milho' is an alias of 'milho_2safra'; 'milho_verao' of 'milho_1safra'; 'feijao' of "
            "'feijao_2safra')."
        ),
    )
    linha_custo: Literal["coe", "cot", "ct"] | None = Field(
        None, description="'coe' (effective operating cost), 'cot' (total operating cost) or 'ct' (total cost)."
    )

    produtividade: dict[CulturaProdutividade, Annotated[float, Field(gt=0, le=500)]] | None = Field(
        None,
        description=(
            "Own yield in bags/ha (soja, milho = 2nd season, milho_verao = 1st season, trigo, feijao, sorgo); 'milho' is an alias "
            "of 'milho_2safra'. Replaces the municipal PAM yield in the margin; the bad-year scenario scales "
            "proportionally (own × PAM p20/average). The soybean value also changes the income scale S."
        ),
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"precos": {"soja": 125.0, "milho": 58.0, "trigo": 82.0}},
                {"produtividade": {"soja": 70.0, "milho": 120.0, "trigo": 50.0}},
            ]
        },
    )


class AnaliseSolo(BaseModel):
    """The farmer's soil analysis. Replaces SoilGrids in the diagnosis and in the water-balance available water capacity.
    Provide argila_pct and areia_pct (together), or cad_mm_cm."""

    argila_pct: float | None = Field(None, ge=0, le=100, description="Clay (%).")
    areia_pct: float | None = Field(None, ge=0, le=100, description="Sand (%). Sand + clay ≤ 100.")
    materia_organica_pct: float | None = Field(None, ge=0, le=100, description="Organic matter (%). Alternative to carbono_organico_g_kg.")
    carbono_organico_g_kg: float | None = Field(None, ge=0, le=580, description="Organic carbon (g/kg). Alternative to materia_organica_pct.")
    ph: float | None = Field(None, ge=3, le=9, description="pH in water (3 to 9).")
    cad_mm_cm: float | None = Field(
        None, ge=0.3, le=3, description="Available water capacity (mm of water per cm of soil, 0.3 to 3). If present, it is used directly."
    )
    profundidade_cm: float | None = Field(
        None, ge=1, le=200, description="Sample depth (cm; default 20, i.e. 0–20 cm). The sample is taken as representative of the profile."
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "ph": 5.4, "cad_mm_cm": 1.4},
                {"argila_pct": 45, "areia_pct": 30, "carbono_organico_g_kg": 18},
            ]
        },
    )

    @model_validator(mode="after")
    def _minimo(self) -> "AnaliseSolo":
        if (self.argila_pct is None) != (self.areia_pct is None):
            raise ValueError("provide 'argila_pct' and 'areia_pct' together")
        if self.argila_pct is None and self.cad_mm_cm is None:
            raise ValueError("provide 'argila_pct' and 'areia_pct', or 'cad_mm_cm'")
        if self.argila_pct is not None and self.argila_pct + self.areia_pct > 100:
            raise ValueError("argila_pct + areia_pct cannot exceed 100")
        if self.materia_organica_pct is not None and self.carbono_organico_g_kg is not None:
            raise ValueError("provide 'materia_organica_pct' OR 'carbono_organico_g_kg', not both")
        return self


class Maquinas(BaseModel):
    """Machines the farmer has. Omitted = has it. `false` does not eliminate the rotation: it adds a warning and an extra outsourcing cost."""

    plataforma_milho: bool | None = Field(
        None, description="Corn harvest header (required by summer corn, off-season corn and corn+brachiaria; one cost per harvest)."
    )
    semeadora_consorcio: bool | None = Field(None, description="Intercrop seeder/extra seed box (required by corn+brachiaria).")

    model_config = ConfigDict(extra="forbid")


class Restricoes(BaseModel):
    """The farmer's execution and market restrictions."""

    culturas_excluidas: list[RotacaoSlug] | None = Field(
        None,
        description=(
            "Rotations the farmer does not want to or cannot do (id '<verao>__<segunda>' or old slug, meaning soybean in summer); "
            "they go to 'eliminadas' (reason: excluded by the farmer)."
        ),
    )
    maquinas: Maquinas | None = None
    sem_comprador: list[SemComprador] | None = Field(
        None,
        description=(
            "Cash crops without a local buyer. 'milho' eliminates the rotations with corn (summer or off-season); 'trigo', 'sorgo' and "
            "'feijao' eliminate the ones that sell that crop; 'aveia_grao' is accepted but has no effect (oat is treated as a "
            "cover crop, without grain sale)."
        ),
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "culturas_excluidas": ["trigo"],
                    "maquinas": {"plataforma_milho": True, "semeadora_consorcio": False},
                    "sem_comprador": ["aveia_grao"],
                }
            ]
        },
    )


class Irrigacao(BaseModel):
    """Irrigation available in the area. Irrigates second-window corn, corn+brachiaria, wheat, sorghum and beans (not cover crops, fallow or the summer crop)."""

    disponivel: bool = Field(..., description="Is there irrigation in the area?")
    custo_r_mm_ha: Annotated[float, Field(ge=0, le=100)] | None = Field(
        None, description="Cost per mm applied per ha (BRL; default 4.0, estimate to be validated)."
    )
    lamina_max_mm_dia: Annotated[float, Field(gt=0, le=30)] | None = Field(
        None, description="Maximum depth per day (mm; default 6)."
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"disponivel": True, "custo_r_mm_ha": 4.5, "lamina_max_mm_dia": 6}]},
    )


class Pesos(BaseModel):
    """Importance of each criterion, from 0 to 10. Omitted ones use the default (renda 5, others 3)."""

    renda: Peso | None = None
    solo: Peso | None = None
    agua: Peso | None = None
    pragas: Peso | None = None
    risco: Peso | None = None

    model_config = ConfigDict(extra="forbid")


class RotacaoSelecionada(BaseModel):
    """A requested rotation: summer crop + second-window crop (closed enums; see GET /v1/opcoes)."""

    verao: CulturaVerao = Field(..., description="Summer crop (1st season).")
    segunda: CulturaSegunda = Field(..., description="Second-window crop (off-season, winter or cover).")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"verao": "soja", "segunda": "milho_safrinha"}]})


class DiagnosticoIn(BaseModel):
    area: Area
    semeadura_safrinha: Semeadura = Field("01/02", description="Off-season sowing date (dd/mm).")
    analise_solo: AnaliseSolo | None = Field(None, description="The farmer's soil analysis (replaces SoilGrids in the soil block).")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02"},
                {"area": {"geometry": POLIGONO_EXEMPLO}, "semeadura_safrinha": "15/02"},
                {"area": {"lat": -24.95, "lon": -53.45}},
            ]
        }
    )


class ContextoIn(BaseModel):
    area: Area
    semeadura_safrinha: Semeadura = Field("01/02", description="Off-season sowing date (dd/mm); used in the per-phase ENSO history.")

    model_config = ConfigDict(json_schema_extra={"examples": [{"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02"}]})


class RecomendacaoIn(BaseModel):
    area: Area
    rotacao_atual: RotacaoSlug = Field(
        ...,
        description="REQUIRED. Rotation the farmer uses today (id '<verao>__<segunda>' or old slug = soybean in summer). "
        "Its summer crop defines the `agora` block; combinations with another summer crop go into `proxima_safra`.",
    )
    estagio_verao: EstagioVerao | None = Field(
        None,
        description=(
            "Stage of the current rotation's summer crop (estimated harvest = data_referencia + typical days of the stage; estimate, "
            "to be validated with Embrapa). Soybean: vegetativo, floracao (R1–R2), formacao_vagens (R3–R4), enchimento_graos (R5–R6), maturacao "
            "(R7–R8), colhida. Summer corn: vegetativo, pendoamento (VT–R1), grao_leitoso (R2–R3), grao_farinaceo (R4–R5), maturacao (R6), "
            "colhida. A stage of another crop returns 422. See GET /v1/opcoes."
        ),
    )
    colheita_prevista: str | None = Field(
        None, pattern=r"^\d{2}/\d{2}$", description="Expected summer harvest (dd/mm). If present, it takes precedence over `estagio_verao`."
    )
    data_referencia: date | None = Field(
        None, description="Today's date for the farmer (ISO, YYYY-MM-DD; default: today). Makes the stage calculation deterministic."
    )
    semeadura_safrinha: Semeadura | None = Field(
        None,
        description=(
            "Second-window sowing date (dd/mm). Optional: without it, it is the first date (15/01, 01/02, 15/02, 01/03, 15/03) from the estimated "
            "harvest on. If sent together with a stage/harvest, this one applies, but it cannot be earlier than the harvest (422). Without stage, harvest and "
            "sowing date: assumption (catalog harvest and 01/02), with a warning."
        ),
    )
    pesos: Pesos | None = Field(None, description="Criteria weights (0 to 10).")
    rotacoes: list[RotacaoSelecionada] | None = Field(
        None,
        min_length=1,
        description=(
            "Rotations to evaluate. If present, the engine evaluates and ranks only these (each pair goes into `agora` or `proxima_safra` by its summer crop); "
            "if absent, it evaluates every catalog combination. "
            "Non-empty list without duplicates. A combination eliminated by the rules comes back in 'eliminadas' with the reason (not an error)."
        ),
    )
    ajustes: Ajustes | None = None
    analise_solo: AnaliseSolo | None = Field(
        None, description="The farmer's soil analysis: replaces SoilGrids in the diagnosis and in the water-balance capacity."
    )
    restricoes: Restricoes | None = Field(
        None, description="Excluded crops, machines the farmer has and crops without a local buyer."
    )
    irrigacao: Irrigacao | None = Field(None, description="Available irrigation (changes the water criterion, the risk and the margin).")
    n_alternativas: int = Field(3, ge=1, le=6, description="How many alternatives to return.")
    incluir_diagnostico: bool = Field(True, description="Includes the full diagnosis in the response.")

    @model_validator(mode="after")
    def _calendario(self) -> "RecomendacaoIn":
        """Stage compatible with the current summer crop; a provided sowing date cannot be earlier than the harvest (422)."""
        calendario.resolver(
            calendario.verao_de(self.rotacao_atual), self.estagio_verao, self.colheita_prevista, self.data_referencia,
            self.semeadura_safrinha,
        )
        return self

    @model_validator(mode="after")
    def _sem_duplicatas(self) -> "RecomendacaoIn":
        if self.rotacoes:
            pares = [(r.verao, r.segunda) for r in self.rotacoes]
            if len(set(pares)) != len(pares):
                raise ValueError("'rotacoes' has duplicated combinations")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "area": {"talhao_id": "72638"},
                    "rotacao_atual": "soja__milho_safrinha",
                    "estagio_verao": "enchimento_graos",
                    "data_referencia": "2026-12-01",
                },
                {
                    "area": {"talhao_id": "72638"},
                    "rotacao_atual": "milho_verao__aveia",
                    "estagio_verao": "grao_leitoso",
                    "data_referencia": "2026-12-01",
                    "rotacoes": [
                        {"verao": "milho_verao", "segunda": "aveia_nabo"},
                        {"verao": "milho_verao", "segunda": "trigo"},
                        {"verao": "soja", "segunda": "milho_safrinha"},
                    ],
                },
                {
                    "area": {"talhao_id": "72638"},
                    "rotacao_atual": "soja__milho_safrinha",
                    "colheita_prevista": "20/01",
                    "semeadura_safrinha": "01/02",
                    "n_alternativas": 3,
                },
                {
                    "area": {"geometry": POLIGONO_EXEMPLO},
                    "rotacao_atual": "soja__milho_safrinha",
                    "estagio_verao": "floracao",
                    "pesos": {"renda": 8, "solo": 3, "agua": 3, "pragas": 5, "risco": 4},
                    "ajustes": {"precos": {"soja": 125.0, "milho": 58.0, "trigo": 82.0}, "linha_custo": "cot"},
                },
                {
                    "area": {"talhao_id": "72638"},
                    "rotacao_atual": "soja__milho_safrinha",
                    "estagio_verao": "maturacao",
                    "ajustes": {"produtividade": {"soja": 65.0, "milho": 110.0, "trigo": 50.0}},
                    "analise_solo": {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "cad_mm_cm": 1.4},
                    "restricoes": {"culturas_excluidas": ["trigo"], "maquinas": {"plataforma_milho": True, "semeadora_consorcio": False}},
                    "irrigacao": {"disponivel": True},
                },
            ]
        }
    )


# --------------------------------------------------------------------------
# Output (permissive: extra fields from the service are passed through)
# --------------------------------------------------------------------------
class _Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class Centroide(_Saida):
    lat: float
    lon: float


class Municipio(_Saida):
    cod_ibge: str | int | None = None
    nome: str | None = None


class AreaOut(_Saida):
    origem: str | None = None
    talhao_id: str | None = None
    area_ha: float | None = None
    centroide: Centroide | None = None
    municipio: Municipio | None = None
    geometry: dict[str, Any] | None = None


class RotacaoDetectada(_Saida):
    rotacao: str | None = None
    fonte: str | None = None
    dias_solo_descoberto: int | float | None = None


class GeadaPorSemeadura(_Saida):
    semeadura: str
    prob: float | None = None
    anos_com_evento: int | None = None
    n_anos: int | None = None


class ClimaOut(_Saida):
    fonte: str | None = None
    celula: dict[str, Any] | str | None = None
    semeadura_safrinha: str | None = None
    riscos: dict[str, Any] | None = None
    geada_por_semeadura: list[GeadaPorSemeadura] = []
    diagnostico: dict[str, Any] | None = None


class DiagnosticoOut(_Saida):
    area: AreaOut
    relevo: dict[str, Any] | None = None
    solo: dict[str, Any] | None = None
    historico: list[dict[str, Any]] = []
    rotacao_detectada: RotacaoDetectada | None = None
    clima: ClimaOut | None = None
    produtividade: dict[str, Any] | None = None
    avisos: list[str] = []


class ItemMargem(_Saida):
    cultura: str
    rendimento_sc_ha: float | None = None
    preco: float | None = None
    custo: float | None = None
    margem_r_ha: float | None = None
    fonte: str | None = None


class Margem(_Saida):
    total_r_ha: float | None = None
    incremental_r_ha: float | None = None
    escala_S_r_ha: float | None = None
    itens: list[ItemMargem] = []
    ano_ruim_r_ha: float | None = None


class Card(_Saida):
    por_que: str | None = None
    evidencias: list[Any] = []
    beneficios: list[Any] = []
    lacunas: list[Any] = []
    riscos: list[Any] = []
    avisos: list[Any] = []
    mercado: dict[str, Any] | None = Field(None, description="Market viability in Western Paraná: nivel, texto, estimativa.")


class CulturaRef(_Saida):
    id: str
    nome: str


class ItemRanking(_Saida):
    posicao: int | None = None
    id: str = Field(..., description="Stable id '<verao>__<segunda>' (e.g. soja__milho_safrinha).")
    id_legado: str | None = Field(None, description="Old slug (soybean in summer only): milho_safrinha = soja__milho_safrinha.")
    verao: CulturaRef | None = None
    segunda: CulturaRef | None = None
    rotacao: str
    nota: float | None = None
    atual: bool = False
    criterios: dict[str, float | None] = {}
    contribuicoes: dict[str, float | None] = {}
    margem: Margem | None = None
    card: Card | None = None
    irrigacao: dict[str, Any] | None = Field(None, description="Present only if the candidate is irrigated: lamina_media_mm_ano and custo_r_ha.")
    ganho_vs_atual: dict[str, Any] | None = Field(
        None,
        description=(
            "How it improves (or worsens) production against the current rotation, always with `origem`: `soja_seguinte_sc` (central), `soja_seguinte_sc_faixa` [min, max] and `soja_seguinte_rs` (BRL/ha, catalog "
            "bonus × DERAL price) with `fonte` (estimate, to be validated with an agronomist/Embrapa), `renda_2a_safra` and `margem_total` (BRL/ha; data), `solo` "
            "(days of bare soil and cover; negative days = improvement), `agua` and `risco_climatico` (criterion difference; data). "
            "Null on the current rotation itself or if the current rotation was eliminated."
        ),
    )


class ItemAtual(ItemRanking):
    """Current rotation. If eliminated by a hard rule: null posicao/nota, eliminada=true and motivos."""

    id: str | None = None
    rotacao: str | None = None
    eliminada: bool = False
    avaliada: bool | None = Field(None, description="false if the current rotation is not in 'rotacoes' (it was not evaluated).")
    motivos: list[str] = []


class Eliminada(_Saida):
    id: str
    id_legado: str | None = None
    verao: CulturaRef | None = None
    segunda: CulturaRef | None = None
    rotacao: str | None = None
    motivos: list[str] = []


class Metodologia(_Saida):
    formula: str | None = None
    criterios: dict[str, Any] = {}
    versao: str | None = None
    ajustes_aplicados: list[str] = []


class Bloco(_Saida):
    """Ranking of a set of combinations; `posicao` restarts at 1 in each block."""

    ranking: list[ItemRanking] = []
    alternativas: list[dict[str, Any]] = Field([], description="Best of the block, excluding the current rotation (up to `n_alternativas`).")
    eliminadas: list[Eliminada] = []


class CulturaAtual(_Saida):
    id: str
    nome: str


class DataOrigem(_Saida):
    data: str = Field(..., description="dd/mm")
    origem: str


class RecomendacaoOut(_Saida):
    entrada: dict[str, Any] = {}
    cultura_atual: CulturaAtual | None = Field(None, description="Summer crop of the current rotation.")
    estagio_verao: dict[str, Any] | None = Field(None, description="Provided stage, with typical days until harvest and the source (estimate).")
    colheita_estimada: DataOrigem | None = Field(None, description="dd/mm; origem: estagio | informada | premissa.")
    semeadura_2a: DataOrigem | None = Field(
        None, description="Second-window sowing date used (origem: derivada | informada | premissa); null if the harvest is too late."
    )
    dias_ate_colheita: int | None = Field(None, description="Null when the harvest is the catalog assumption.")
    diagnostico: DiagnosticoOut | None = None
    agora: Bloco | None = Field(None, description="Main block: combinations with the SAME summer crop as the current rotation (what goes in after the harvest).")
    proxima_safra: Bloco | None = Field(
        None, description="Combinations with ANOTHER summer crop (next-season decision), compared with the current rotation; same second-window sowing date."
    )
    ranking: list[ItemRanking] = Field([], description="Alias of `agora.ranking` (compatibility).")
    atual: ItemAtual | None = None
    alternativas: list[dict[str, Any]] = Field([], description="Alias of `agora.alternativas` (compatibility).")
    eliminadas: list[Eliminada] = Field([], description="Union of the eliminated rotations of `agora` and `proxima_safra` (compatibility).")
    avisos: list[str] = []
    metodologia: Metodologia | None = None


class HealthOut(BaseModel):
    status: Literal["ok", "degradado"]
    dados_carregados: bool
    versao: str
    detalhe: str | None = None


class ErroOut(BaseModel):
    erro: str
    mensagem: str | None = None
