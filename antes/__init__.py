"""
Pacote: antes
Sistema de e-commerce com falhas clássicas de concorrência (versão original).
"""

from .estoque import EstoqueAntes
from .financeiro import FinanceiroAntes, executar_processo_a, executar_processo_b
from .relatorio import GerenciadorRelatoriosAntes
from .servidor import ServidorAntes

__all__ = [
    "EstoqueAntes",
    "FinanceiroAntes",
    "executar_processo_a",
    "executar_processo_b",
    "GerenciadorRelatoriosAntes",
    "ServidorAntes",
]
