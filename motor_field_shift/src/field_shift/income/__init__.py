"""Renda da rotação: margem = rendimento municipal (IBGE PAM) × preço (SEAB/DERAL) − custo (CONAB)."""
from field_shift.income.income import (CASH_CROPS, INCOME_SCALE_MIN, compute_margins, load_reference, cost_source, price_source,
                                     yields)

__all__ = ["CULTURAS_VENDA", "RENDA_ESCALA_MIN", "calcular_margens", "carregar_referencia", "fonte_custo", "fonte_preco", "rendimentos"]
