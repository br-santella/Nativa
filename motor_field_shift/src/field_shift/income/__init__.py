"""Rotation income: margin = municipal yield (IBGE PAM) × price (SEAB/DERAL) − cost (CONAB)."""
from field_shift.income.income import (CASH_CROPS, INCOME_SCALE_MIN, compute_margins, load_reference, cost_source, price_source,
                                     yields)

__all__ = ["CULTURAS_VENDA", "RENDA_ESCALA_MIN", "calcular_margens", "carregar_referencia", "fonte_custo", "fonte_preco", "rendimentos"]
