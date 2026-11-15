"""Service layer of the Field Shift engine (used by the API)."""
from field_shift.motor.servico import (ROTACOES, EntradaInvalida, ErroConsultaExterna, ForaDaRegiao,
                                       aquecer, diagnosticar, opcoes, recomendar)

__all__ = ["ROTACOES", "EntradaInvalida", "ErroConsultaExterna", "ForaDaRegiao",
           "aquecer", "diagnosticar", "opcoes", "recomendar"]