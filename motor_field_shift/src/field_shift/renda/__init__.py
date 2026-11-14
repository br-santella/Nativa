"""Renda da rotação: margem = rendimento municipal (IBGE PAM) × preço (SEAB/DERAL) − custo (CONAB)."""
from field_shift.renda.renda import (CULTURAS_VENDA, RENDA_ESCALA_MIN, calcular_margens, carregar_referencia, fonte_custo, fonte_preco,
                                     rendimentos)

__all__ = ["CULTURAS_VENDA", "RENDA_ESCALA_MIN", "calcular_margens", "carregar_referencia", "fonte_custo", "fonte_preco", "rendimentos"]
