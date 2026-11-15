"""Camada de serviço do motor Field Shift (usada pela API)."""
from field_shift.motor.plano import plano_plurianual
from field_shift.motor.servico import (ROTACOES, EntradaInvalida, ErroConsultaExterna, ForaDaRegiao,
                                       aquecer, diagnosticar, opcoes, recomendar)

__all__ = ["ROTACOES", "EntradaInvalida", "ErroConsultaExterna", "ForaDaRegiao",
           "aquecer", "diagnosticar", "opcoes", "plano_plurianual", "recomendar"]
