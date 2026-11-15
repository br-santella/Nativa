"""Rotas HTTP. Endpoints `def` (síncronos) rodam no threadpool do FastAPI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from field_shift.motor import servico

from . import __version__
from .schemas import (
    ClimaOut,
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


@health_router.get("/health", response_model=HealthOut, summary="Estado do serviço")
def health(request: Request) -> HealthOut:
    ok = bool(getattr(request.app.state, "dados_ok", False))
    return HealthOut(
        status="ok" if ok else "degradado",
        dados_carregados=ok,
        versao=__version__,
        detalhe=getattr(request.app.state, "dados_erro", None),
    )


@router.get("/opcoes", tags=["metadados"], summary="Opções, pesos padrão e metadados do motor")
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
    return servico.diagnosticar(corpo.area.para_servico(), semeadura_safrinha=corpo.semeadura_safrinha)


@router.post(
    "/recomendacao",
    response_model=RecomendacaoOut,
    responses=ERROS,
    tags=["motor"],
    summary="Ranking de rotações de culturas para a área",
)
def recomendacao(corpo: RecomendacaoIn) -> dict[str, Any]:
    pesos = corpo.pesos.model_dump(exclude_none=True) if corpo.pesos else None
    ajustes = corpo.ajustes.model_dump(exclude_none=True) if corpo.ajustes else None
    return servico.recomendar(
        corpo.area.para_servico(),
        semeadura_safrinha=corpo.semeadura_safrinha,
        pesos=pesos or None,
        rotacao_atual=corpo.rotacao_atual,
        ajustes=ajustes or None,
        n_alternativas=corpo.n_alternativas,
        incluir_diagnostico=corpo.incluir_diagnostico,
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
