"""
Pacote: depois
Sistema de e-commerce refatorado com controle de concorrência robusto.
"""

from .config import (
    TIMEOUT_LOCK_SEGUNDOS,
    POOL_COMPRAS,
    POOL_RELATORIOS,
    ORDEM_RECURSOS,
    LIMITE_AGING,
)
from .estoque import EstoqueDepois
from .financeiro import FinanceiroDepois, executar_compra_segura
from .relatorio import (
    PoolConexoes,
    EnvelhecimentoPrioridade,
    GerenciadorRelatoriosDepois,
)
from .servidor import ServidorDepois

__all__ = [
    "TIMEOUT_LOCK_SEGUNDOS",
    "POOL_COMPRAS",
    "POOL_RELATORIOS",
    "ORDEM_RECURSOS",
    "LIMITE_AGING",
    "EstoqueDepois",
    "FinanceiroDepois",
    "executar_compra_segura",
    "PoolConexoes",
    "EnvelhecimentoPrioridade",
    "GerenciadorRelatoriosDepois",
    "ServidorDepois",
]
