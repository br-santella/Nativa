"""Rotas HTTP. Endpoints `def` (síncronos) rodam no threadpool do FastAPI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from field_shift.motor import servico

from . import __version__
from .schemas import (
    Area,
    ClimaOut,
    ContextoIn,
    DiagnosticoIn,
    DiagnosticoOut,
    ErroOut,
    HealthOut,
    RecomendacaoIn,
    RecomendacaoOut,
    Semeadura,
)

ERROS = {
    400: {"model": ErroOut, "description": "Entrada inválida segundo o motor (`entrada_invalida`)."},
    422: {"model": ErroOut, "description": "Fora do Oeste do PR (`fora_da_regiao`) ou erro de validação do corpo."},
    500: {"model": ErroOut, "description": "Erro interno (`interno`)."},
}

health_router = APIRouter(tags=["saúde"])
router = APIRouter(prefix="/v1")


def _dump(m: Any) -> dict[str, Any] | None:
    return m.model_dump(exclude_none=True) if m is not None else None


@health_router.get("/health", response_model=HealthOut, summary="Estado do serviço")
def health(request: Request) -> HealthOut:
    ok = bool(getattr(request.app.state, "dados_ok", False))
    return HealthOut(
        status="ok" if ok else "degradado",
        dados_carregados=ok,
        versao=__version__,
        detalhe=getattr(request.app.state, "dados_erro", None),
    )


@router.get(
    "/opcoes",
    tags=["metadados"],
    summary="Culturas de verão e da 2ª janela, combinações, pesos padrão e metadados do motor",
)
def opcoes() -> dict[str, Any]:
    return servico.opcoes()


@router.get("/talhoes/demo", tags=["metadados"], summary="Talhões de demonstração")
def talhoes_demo() -> Any:
    return servico.opcoes().get("talhoes_demo", [])


@router.post(
    "/diagnostico",
    response_model=DiagnosticoOut,
    responses=ERROS,
    tags=["motor"],
    summary="Diagnóstico da área (relevo, solo, histórico, clima, produtividade)",
)
def diagnostico(corpo: DiagnosticoIn) -> dict[str, Any]:
    extra = {}
    if corpo.analise_solo is not None:
        extra["analise_solo"] = corpo.analise_solo.model_dump(exclude_none=True)
    return servico.diagnosticar(corpo.area.para_servico(), semeadura_safrinha=corpo.semeadura_safrinha, **extra)


@router.post(
    "/recomendacao",
    response_model=RecomendacaoOut,
    responses=ERROS,
    tags=["motor"],
    summary="O que entra depois da colheita do verão e como melhora a produção (`agora`), mais a próxima safra",
)
def recomendacao(corpo: RecomendacaoIn) -> dict[str, Any]:
    pesos = corpo.pesos.model_dump(exclude_none=True) if corpo.pesos else None
    ajustes = corpo.ajustes.model_dump(exclude_none=True) if corpo.ajustes else None
    return servico.recomendar(
        corpo.area.para_servico(),
        semeadura_safrinha=corpo.semeadura_safrinha,
        pesos=pesos or None,
        rotacao_atual=corpo.rotacao_atual,
        estagio_verao=corpo.estagio_verao,
        colheita_prevista=corpo.colheita_prevista,
        data_referencia=corpo.data_referencia,
        rotacoes=[r.model_dump() for r in corpo.rotacoes] if corpo.rotacoes else None,
        ajustes=ajustes or None,
        n_alternativas=corpo.n_alternativas,
        incluir_diagnostico=corpo.incluir_diagnostico,
        analise_solo=_dump(corpo.analise_solo),
        restricoes=_dump(corpo.restricoes),
        irrigacao=_dump(corpo.irrigacao),
        problemas_area=corpo.problemas_area or None,
    )



@router.get(
    "/clima",
    response_model=ClimaOut,
    responses=ERROS,
    tags=["motor"],
    summary="Atalho: só o bloco de clima para um ponto",
)
def clima(
    lat: float = Query(..., ge=-90, le=90, examples=[-24.95]),
    lon: float = Query(..., ge=-180, le=180, examples=[-53.45]),
    semeadura_safrinha: Semeadura = "01/02",
) -> dict[str, Any]:
    diag = servico.diagnosticar({"lat": lat, "lon": lon}, semeadura_safrinha=semeadura_safrinha)
    return diag["clima"]


def _contexto_da_area(area: dict[str, Any], semeadura: str) -> dict[str, Any]:
    from field_shift import contexto

    a = servico._resolver_area(area)  # mesmas validações e erros (400/422) da recomendação
    return contexto.montar(a["lat"], a["lon"], semeadura)


@router.post(
    "/contexto",
    tags=["contexto"],
    summary="Situação atual (informativa): ENSO, umidade do solo SMAP, MJO, pragas em surto",
    responses=ERROS,
)
def contexto_post(corpo: ContextoIn) -> dict[str, Any]:
    """Consulta fontes oficiais (NOAA, NASA SMAP, IDR-PR/ADAPAR) sobre eventos em curso. Não prevê nada e não altera
    ranking nem nota. Cada fonte falha isoladamente: `{"disponivel": false, "motivo": ...}`."""
    return _contexto_da_area(corpo.area.para_servico(), corpo.semeadura_safrinha)


@router.get(
    "/contexto",
    tags=["contexto"],
    summary="Situação atual (informativa) por talhao_id ou ponto lat/lon",
    responses=ERROS,
)
def contexto_get(
    talhao_id: str | None = Query(None, examples=["72638"]),
    lat: float | None = Query(None, ge=-90, le=90, examples=[-24.95]),
    lon: float | None = Query(None, ge=-180, le=180, examples=[-53.45]),
    semeadura_safrinha: Semeadura = "01/02",
) -> dict[str, Any]:
    """Mesmo contexto do POST, para talhão demo ou ponto. Para polígono use `POST /v1/contexto`."""
    try:
        area = Area(talhao_id=talhao_id, lat=lat, lon=lon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _contexto_da_area(area.para_servico(), semeadura_safrinha)
