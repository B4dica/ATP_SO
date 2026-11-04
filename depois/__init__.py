"""
Pacote: depois
Sistema de e-commerce refatorado com banco de dados SQLite e controle de concorrência robusto.
"""

from .config import TIMEOUT_LOCK_SEGUNDOS
from .banco import BancoDadosDepois
from .estoque import EstoqueDepois
from .financeiro import executar_compra_segura
from .relatorio import GerenciadorRelatoriosDepois, EnvelhecimentoPrioridade
from .servidor import ServidorDepois

__all__ = [
    "TIMEOUT_LOCK_SEGUNDOS",
    "BancoDadosDepois",
    "EstoqueDepois",
    "executar_compra_segura",
    "GerenciadorRelatoriosDepois",
    "EnvelhecimentoPrioridade",
    "ServidorDepois",
]
