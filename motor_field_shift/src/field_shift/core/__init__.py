"""Camada de serviço do motor Field Shift (usada pela API)."""
from field_shift.core.service import (ROTATIONS, InvalidInput, ExternalQueryError, OutOfRegion,
                                       warm_up, diagnose, options, recommend)

__all__ = ["ROTACOES", "EntradaInvalida", "ErroConsultaExterna", "ForaDaRegiao",
           "aquecer", "diagnosticar", "opcoes", "recomendar"]