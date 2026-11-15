"""Aplicação FastAPI do Field Shift."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from field_shift.motor import servico

from . import __version__
from .rotas import health_router, router

log = logging.getLogger("field_shift_api")

DESCRICAO = """
API do **Field Shift**: apoio à decisão de **rotação de culturas** (safrinha / entressafra) para o
**Oeste do Paraná** (50 municípios, código IBGE 4106). Dado um talhão (id demo), um polígono GeoJSON
ou um ponto lat/lon, devolve um diagnóstico da área e um ranking de rotações com nota, margem
estimada (R$/ha) e um cartão explicativo por opção.

Áreas fora do Oeste do PR retornam **422** (`fora_da_regiao`).

**Fontes de dados:** NASA POWER (clima), SoilGrids (solo), MapBiomas (uso e cobertura do solo),
NASADEM (relevo), IBGE PAM (produtividade municipal), SEAB/DERAL (custos e preços regionais) e
CONAB (preços e custos de referência).

Os números de renda e risco são **estimativas** para apoiar a conversa com o agrônomo, não
substituem o ZARC nem a recomendação técnica.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dados_ok = False
    app.state.dados_erro = None
    try:
        servico.aquecer()
        app.state.dados_ok = True
    except Exception as exc:  # a API sobe mesmo sem dados; /health mostra "degradado"
        log.exception("falha ao carregar dados no startup")
        app.state.dados_erro = f"{type(exc).__name__}: {exc}"
    yield


app = FastAPI(
    title="Field Shift API",
    description=DESCRICAO,
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(router)


@app.exception_handler(servico.ForaDaRegiao)
async def _fora_da_regiao(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"erro": "fora_da_regiao", "mensagem": str(exc)})


@app.exception_handler(servico.EntradaInvalida)
async def _entrada_invalida(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"erro": "entrada_invalida", "mensagem": str(exc)})


@app.exception_handler(servico.ErroConsultaExterna)
async def _erro_consulta_externa(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=504, content={"erro": "timeout_externo", "mensagem": str(exc)})


@app.exception_handler(Exception)
async def _interno(request: Request, exc: Exception) -> JSONResponse:
    log.error("erro inesperado em %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"erro": "interno", "mensagem": "Erro interno do servidor."},
    )
