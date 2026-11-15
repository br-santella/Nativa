"""Schemas Pydantic (entrada e saída) da API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from field_shift import calendario

Semeadura = Literal["15/01", "01/02", "15/02", "01/03", "15/03"]
# Enums fechados do catálogo (espelham field_shift.app.engine; um teste confere). Rotação = par (verão, 2ª janela).
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
# Slugs antigos da API (só soja no verão): milho_safrinha = soja__milho_safrinha.
SLUGS_LEGADOS = ("milho_safrinha", "milho_braquiaria", "trigo", "aveia", "milheto_crotalaria", "pousio", "soja_safrinha")
IDS_ROTACAO = tuple(f"{v}__{s}" for v in CulturaVerao.__args__ for s in CulturaSegunda.__args__)
RotacaoSlug = Literal[IDS_ROTACAO + SLUGS_LEGADOS]  # id novo "<verao>__<segunda>" ou slug antigo
# Estágios da cultura de verão (espelham field_shift.calendario.ESTAGIOS; um teste confere). O estágio precisa combinar com o verão da rotação atual.
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
# Problemas da área informados pelo produtor (espelha catalog/vocabulario.yaml `problemas_area`; um teste confere).
ProblemaArea = Literal["nematoide", "mofo_branco", "cigarrinha", "compactacao"]
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
# Entrada
# --------------------------------------------------------------------------
class Area(BaseModel):
    """Área de análise. Informe EXATAMENTE UMA das formas: `geometry`, `lat`+`lon` ou `talhao_id`."""

    geometry: dict[str, Any] | None = Field(
        None,
        description="GeoJSON Polygon, MultiPolygon ou Feature em EPSG:4326 (lon, lat). Máx. 5000 ha.",
    )
    lat: float | None = Field(None, ge=-90, le=90, description="Latitude (vira um quadrado de ~100 ha).")
    lon: float | None = Field(None, ge=-180, le=180, description="Longitude (vira um quadrado de ~100 ha).")
    talhao_id: str | None = Field(None, description="Id de um talhão demo (ver GET /v1/talhoes/demo).")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"talhao_id": "72638"}]},
    )

    @model_validator(mode="after")
    def _uma_forma(self) -> "Area":
        ponto = self.lat is not None or self.lon is not None
        if ponto and (self.lat is None or self.lon is None):
            raise ValueError("para ponto, informe 'lat' e 'lon' juntos")
        formas = sum([self.geometry is not None, ponto, self.talhao_id is not None])
        if formas != 1:
            raise ValueError("informe exatamente uma forma de área: 'geometry', 'lat'+'lon' ou 'talhao_id'")
        return self

    def para_servico(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class Ajustes(BaseModel):
    """Preços e custos próprios do produtor (sobrescrevem os valores de referência)."""

    precos: dict[Literal["soja", "milho", "trigo", "feijao", "sorgo"], Annotated[float, Field(ge=0)]] | None = Field(
        None, description="Preço em R$/saca (60 kg). 'milho' vale para o milho verão e o safrinha."
    )
    custos: dict[CulturaCusto, Annotated[float, Field(ge=0)]] | None = Field(
        None,
        description=(
            "Custo por cultura em R$/ha ('milho' é alias de 'milho_2safra'; 'milho_verao' de 'milho_1safra'; 'feijao' de "
            "'feijao_2safra')."
        ),
    )
    linha_custo: Literal["coe", "cot", "ct"] | None = Field(
        None, description="'coe' (operacional efetivo), 'cot' (operacional total) ou 'ct' (custo total)."
    )

    produtividade: dict[CulturaProdutividade, Annotated[float, Field(gt=0, le=500)]] | None = Field(
        None,
        description=(
            "Produtividade própria em sc/ha (soja, milho = 2ª safra, milho_verao = 1ª safra, trigo, feijao, sorgo); 'milho' é alias "
            "de 'milho_2safra'. Substitui o rendimento da PAM do município na margem; o cenário de ano ruim escala "
            "proporcionalmente (próprio × p20/média da PAM). A soja informada também muda a escala S da renda."
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
    """Análise de solo do produtor. Substitui o SoilGrids no diagnóstico e na CAD do balanço hídrico.
    Informe argila_pct e areia_pct (juntos), cad_mm_cm, ou ao menos um campo de fertilidade.

    Fertilidade (opcional, qualquer subconjunto; unidades do laudo): se NÃO informada, não entra na análise (sem estimativa nem valor
    padrão) e o card diz que não foi considerada. Se informada: custo de calagem (saturação por bases, precisa de V% e CTC) e de adubação
    P/K na margem, penalidade no critério solo para cultura sensível em solo ácido/pobre e bônus para cobertura recicladora.
    """

    argila_pct: float | None = Field(None, ge=0, le=100, description="Argila (%).")
    areia_pct: float | None = Field(None, ge=0, le=100, description="Areia (%). Areia + argila ≤ 100.")
    materia_organica_pct: float | None = Field(None, ge=0, le=100, description="Matéria orgânica (%). Alternativa a carbono_organico_g_kg.")
    carbono_organico_g_kg: float | None = Field(None, ge=0, le=580, description="Carbono orgânico (g/kg). Alternativa a materia_organica_pct.")
    ph: float | None = Field(None, ge=3, le=9, description="pH em água (3 a 9).")
    cad_mm_cm: float | None = Field(
        None, ge=0.3, le=3, description="Capacidade de água disponível (mm de água por cm de solo, 0,3 a 3). Se vier, é usada direto na CAD."
    )
    profundidade_cm: float | None = Field(
        None, ge=1, le=200, description="Profundidade da amostra (cm; padrão 20, ou seja, 0–20 cm). A amostra é tomada como representativa do perfil."
    )
    p_mg_dm3: float | None = Field(None, ge=0, le=500, description="Fósforo (Mehlich-1), mg/dm³. Fertilidade (opcional).")
    k_cmolc_dm3: float | None = Field(None, ge=0, le=10, description="Potássio, cmolc/dm³. Fertilidade (opcional).")
    ca_cmolc_dm3: float | None = Field(None, ge=0, le=40, description="Cálcio, cmolc/dm³. Fertilidade (opcional).")
    mg_cmolc_dm3: float | None = Field(None, ge=0, le=20, description="Magnésio, cmolc/dm³. Fertilidade (opcional).")
    al_cmolc_dm3: float | None = Field(None, ge=0, le=15, description="Alumínio trocável, cmolc/dm³. Fertilidade (opcional).")
    v_pct: float | None = Field(
        None, ge=0, le=100, description="Saturação por bases V% (0–100). Fertilidade (opcional). Com CTC, calcula a calagem; sem V%, é derivada se vierem Ca, Mg, K e CTC."
    )
    ctc_cmolc_dm3: float | None = Field(None, ge=0, le=60, description="CTC a pH 7, cmolc/dm³. Fertilidade (opcional).")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"argila_pct": 65, "areia_pct": 10, "materia_organica_pct": 3.5, "ph": 5.4, "cad_mm_cm": 1.4},
                {"argila_pct": 45, "areia_pct": 30, "carbono_organico_g_kg": 18},
                {"p_mg_dm3": 4, "k_cmolc_dm3": 0.12, "al_cmolc_dm3": 1.2, "v_pct": 38, "ctc_cmolc_dm3": 9},
            ]
        },
    )

    @model_validator(mode="after")
    def _minimo(self) -> "AnaliseSolo":
        if (self.argila_pct is None) != (self.areia_pct is None):
            raise ValueError("informe 'argila_pct' e 'areia_pct' juntos")
        fert = ("p_mg_dm3", "k_cmolc_dm3", "ca_cmolc_dm3", "mg_cmolc_dm3", "al_cmolc_dm3", "v_pct", "ctc_cmolc_dm3")
        if self.argila_pct is None and self.cad_mm_cm is None and all(getattr(self, k) is None for k in fert):
            raise ValueError("informe 'argila_pct' e 'areia_pct', ou 'cad_mm_cm', ou algum campo de fertilidade")
        if self.argila_pct is not None and self.argila_pct + self.areia_pct > 100:
            raise ValueError("argila_pct + areia_pct não pode passar de 100")
        if self.materia_organica_pct is not None and self.carbono_organico_g_kg is not None:
            raise ValueError("informe 'materia_organica_pct' OU 'carbono_organico_g_kg', não os dois")
        return self


class Maquinas(BaseModel):
    """Máquinas que o produtor tem. Omitido = tem. `false` não elimina a rotação: gera aviso e custo extra de terceirização."""

    plataforma_milho: bool | None = Field(
        None, description="Plataforma de colheita de milho (exigida por milho verão, milho safrinha e milho+braquiária; um custo por colheita)."
    )
    semeadora_consorcio: bool | None = Field(None, description="Semeadora de consórcio/caixa extra (exigida por milho+braquiária).")

    model_config = ConfigDict(extra="forbid")


class Restricoes(BaseModel):
    """Restrições de execução e de mercado do produtor."""

    culturas_excluidas: list[RotacaoSlug] | None = Field(
        None,
        description=(
            "Rotações que o produtor não quer/pode fazer (id '<verao>__<segunda>' ou slug antigo, que vale para soja no verão); "
            "vão para 'eliminadas' (motivo: excluída pelo produtor)."
        ),
    )
    maquinas: Maquinas | None = None
    sem_comprador: list[SemComprador] | None = Field(
        None,
        description=(
            "Culturas de venda sem comprador local. 'milho' elimina as rotações com milho (verão ou safrinha); 'trigo', 'sorgo' e "
            "'feijao' eliminam as que vendem essa cultura; 'aveia_grao' é aceito mas não tem efeito (a aveia é tratada como "
            "cobertura, sem venda de grão)."
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
    """Irrigação disponível na área. Irriga milho, milho+braquiária, trigo, sorgo e feijão da 2ª janela (não cobertura, pousio nem o verão)."""

    disponivel: bool = Field(..., description="Há irrigação na área?")
    custo_r_mm_ha: Annotated[float, Field(ge=0, le=100)] | None = Field(
        None, description="Custo por mm aplicado por ha (R$; padrão 4,0, estimativa a validar)."
    )
    lamina_max_mm_dia: Annotated[float, Field(gt=0, le=30)] | None = Field(
        None, description="Lâmina máxima por dia (mm; padrão 6)."
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"disponivel": True, "custo_r_mm_ha": 4.5, "lamina_max_mm_dia": 6}]},
    )


class Pesos(BaseModel):
    """Importância de cada critério, de 0 a 10. Omitidos usam o padrão (renda 5, demais 3)."""

    renda: Peso | None = None
    solo: Peso | None = None
    agua: Peso | None = None
    pragas: Peso | None = None
    risco: Peso | None = None

    model_config = ConfigDict(extra="forbid")


class RotacaoSelecionada(BaseModel):
    """Uma rotação pedida: cultura de verão + cultura da 2ª janela (enums fechados; ver GET /v1/opcoes)."""

    verao: CulturaVerao = Field(..., description="Cultura de verão (1ª safra).")
    segunda: CulturaSegunda = Field(..., description="Cultura da 2ª janela (safrinha, inverno ou cobertura).")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"verao": "soja", "segunda": "milho_safrinha"}]})


class DiagnosticoIn(BaseModel):
    area: Area
    semeadura_safrinha: Semeadura = Field("01/02", description="Data de semeadura da safrinha (dd/mm).")
    analise_solo: AnaliseSolo | None = Field(None, description="Análise de solo do produtor (substitui o SoilGrids no bloco solo).")

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
    semeadura_safrinha: Semeadura = Field("01/02", description="Data de semeadura da safrinha (dd/mm); usada no histórico por fase do ENSO.")

    model_config = ConfigDict(json_schema_extra={"examples": [{"area": {"talhao_id": "72638"}, "semeadura_safrinha": "01/02"}]})


class _EntradaMotor(BaseModel):
    """Campos comuns das entradas do motor."""

    area: Area
    rotacao_atual: RotacaoSlug = Field(
        ...,
        description="OBRIGATÓRIA. Rotação que o produtor usa hoje (id '<verao>__<segunda>' ou slug antigo = soja no verão). "
        "A cultura de verão dela define o bloco `agora`; as combinações com outro verão vão em `proxima_safra`.",
    )
    estagio_verao: EstagioVerao | None = Field(
        None,
        description=(
            "Estágio da cultura de verão da rotação atual (a colheita estimada = data_referencia + dias típicos do estágio; estimativa, "
            "validar com Embrapa). Soja: vegetativo, floracao (R1–R2), formacao_vagens (R3–R4), enchimento_graos (R5–R6), maturacao "
            "(R7–R8), colhida. Milho verão: vegetativo, pendoamento (VT–R1), grao_leitoso (R2–R3), grao_farinaceo (R4–R5), maturacao (R6), "
            "colhida. Estágio de outra cultura dá 422. Ver GET /v1/opcoes."
        ),
    )
    colheita_prevista: str | None = Field(
        None, pattern=r"^\d{2}/\d{2}$", description="Colheita prevista do verão (dd/mm). Se vier, tem precedência sobre `estagio_verao`."
    )
    data_referencia: date | None = Field(
        None, description="Data de hoje para o produtor (ISO, AAAA-MM-DD; padrão: hoje). Torna a conta do estágio determinística."
    )
    semeadura_safrinha: Semeadura | None = Field(
        None,
        description=(
            "Semeadura da 2ª janela (dd/mm). Opcional: sem ela, é a primeira data (15/01, 01/02, 15/02, 01/03, 15/03) a partir da colheita "
            "estimada. Se vier junto com estágio/colheita, vale esta, mas não pode ser anterior à colheita (422). Sem estágio, colheita e "
            "semeadura: premissa (colheita do catálogo e 01/02), com aviso."
        ),
    )
    pesos: Pesos | None = Field(None, description="Pesos dos critérios (0 a 10).")
    rotacoes: list[RotacaoSelecionada] | None = Field(
        None,
        min_length=1,
        description=(
            "Rotações a avaliar. Se vier, o motor avalia e ranqueia só essas (cada par cai em `agora` ou `proxima_safra` pelo verão); "
            "se não vier, avalia todas as combinações do catálogo. "
            "Lista não vazia e sem duplicatas. Combinação eliminada pelas regras volta em 'eliminadas' com motivo (não é erro)."
        ),
    )
    ajustes: Ajustes | None = None
    analise_solo: AnaliseSolo | None = Field(
        None, description="Análise de solo do produtor: substitui o SoilGrids no diagnóstico e na CAD do balanço hídrico."
    )
    restricoes: Restricoes | None = Field(
        None, description="Culturas excluídas, máquinas que o produtor tem e culturas sem comprador local."
    )
    irrigacao: Irrigacao | None = Field(None, description="Irrigação disponível (muda o critério água, o risco e a margem).")
    problemas_area: list[ProblemaArea] | None = Field(
        None,
        description=(
            "Problemas da área (opcional; lista fechada: nematoide, mofo_branco, cigarrinha, compactacao). Ajustam os critérios pragas e solo "
            "por cultura (estimativa de catálogo, validar com agrônomo/Embrapa): mofo-branco pesa em feijão, soja e nabo; nematoide favorece "
            "crotalária/milheto e braquiária e pesa em feijão e soja; cigarrinha pesa no milho (mais no milho sobre milho); compactação favorece "
            "nabo e braquiária. Se não vier, nada muda e o card diz que não foi considerado. Valor fora da lista dá 422."
        ),
        examples=[["mofo_branco", "nematoide"]],
    )
    @model_validator(mode="after")
    def _calendario(self) -> "_EntradaMotor":
        """Estágio compatível com o verão da atual; semeadura informada não pode ser anterior à colheita (422)."""
        calendario.resolver(
            calendario.verao_de(self.rotacao_atual), self.estagio_verao, self.colheita_prevista, self.data_referencia,
            self.semeadura_safrinha,
        )
        return self

    @model_validator(mode="after")
    def _sem_duplicatas(self) -> "_EntradaMotor":
        if self.rotacoes:
            pares = [(r.verao, r.segunda) for r in self.rotacoes]
            if len(set(pares)) != len(pares):
                raise ValueError("'rotacoes' tem combinações duplicadas")
        return self


class RecomendacaoIn(_EntradaMotor):
    n_alternativas: int = Field(3, ge=1, le=6, description="Quantas alternativas devolver.")
    incluir_diagnostico: bool = Field(True, description="Inclui o diagnóstico completo na resposta.")

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
# Saída (permissiva: campos extras do serviço passam adiante)
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
    fertilidade: dict[str, Any] | None = Field(
        None, description="Só se o produtor informou fertilidade em `analise_solo`: valores, classes (P, K, V%, Al), origem da V%, severidade de acidez e itens não informados."
    )
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
    mercado: dict[str, Any] | None = Field(None, description="Viabilidade de mercado no Oeste do PR: nivel, texto, estimativa.")


class CulturaRef(_Saida):
    id: str
    nome: str


class ItemRanking(_Saida):
    posicao: int | None = None
    id: str = Field(..., description="Id estável '<verao>__<segunda>' (ex.: soja__milho_safrinha).")
    id_legado: str | None = Field(None, description="Slug antigo (só soja no verão): milho_safrinha = soja__milho_safrinha.")
    verao: CulturaRef | None = None
    segunda: CulturaRef | None = None
    rotacao: str
    nota: float | None = None
    atual: bool = False
    criterios: dict[str, float | None] = {}
    contribuicoes: dict[str, float | None] = {}
    margem: Margem | None = None
    card: Card | None = None
    irrigacao: dict[str, Any] | None = Field(None, description="Presente só se a candidata é irrigada: lamina_media_mm_ano e custo_r_ha.")
    ganho_vs_atual: dict[str, Any] | None = Field(
        None,
        description=(
            "Como melhora (ou piora) a produção contra a rotação atual, sempre com `origem`: `soja_seguinte_sc` (central), `soja_seguinte_sc_faixa` [min, max] e `soja_seguinte_rs` (R$/ha, bônus do "
            "catálogo × preço DERAL) com `fonte` (estimativa, validar com agrônomo/Embrapa), `renda_2a_safra` e `margem_total` (R$/ha; dado), `solo` "
            "(dias de solo descoberto e cobertura; negativo em dias = melhora), `agua` e `risco_climatico` (diferença de critério; dado). "
            "Nulo na própria atual ou se a atual foi eliminada."
        ),
    )


class ItemAtual(ItemRanking):
    """Rotação atual. Se eliminada por regra dura: posicao/nota nulos, eliminada=true e motivos."""

    id: str | None = None
    rotacao: str | None = None
    eliminada: bool = False
    avaliada: bool | None = Field(None, description="false se a atual não está em 'rotacoes' (não foi avaliada).")
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
    """Ranking de um conjunto de combinações; `posicao` recomeça em 1 em cada bloco."""

    ranking: list[ItemRanking] = []
    alternativas: list[dict[str, Any]] = Field([], description="Melhores do bloco, sem a atual (até `n_alternativas`).")
    eliminadas: list[Eliminada] = []


class CulturaAtual(_Saida):
    id: str
    nome: str


class DataOrigem(_Saida):
    data: str = Field(..., description="dd/mm")
    origem: str


class RecomendacaoOut(_Saida):
    entrada: dict[str, Any] = {}
    cultura_atual: CulturaAtual | None = Field(None, description="Cultura de verão da rotação atual.")
    estagio_verao: dict[str, Any] | None = Field(None, description="Estágio informado, com dias típicos até a colheita e a fonte (estimativa).")
    colheita_estimada: DataOrigem | None = Field(None, description="dd/mm; origem: estagio | informada | premissa.")
    semeadura_2a: DataOrigem | None = Field(
        None, description="Semeadura da 2ª janela usada (origem: derivada | informada | premissa); nulo se a colheita é tarde demais."
    )
    dias_ate_colheita: int | None = Field(None, description="Nulo quando a colheita é a premissa do catálogo.")
    diagnostico: DiagnosticoOut | None = None
    agora: Bloco | None = Field(None, description="Bloco principal: combinações com o MESMO verão da atual (o que entra depois da colheita).")
    proxima_safra: Bloco | None = Field(
        None, description="Combinações com OUTRO verão (decisão da próxima safra), comparadas à atual; mesma semeadura da 2ª janela."
    )
    ranking: list[ItemRanking] = Field([], description="Alias de `agora.ranking` (compatibilidade).")
    atual: ItemAtual | None = None
    alternativas: list[dict[str, Any]] = Field([], description="Alias de `agora.alternativas` (compatibilidade).")
    eliminadas: list[Eliminada] = Field([], description="União das eliminadas de `agora` e `proxima_safra` (compatibilidade).")
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
