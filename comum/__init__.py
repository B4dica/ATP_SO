"""
Pacote: comum
Modelos de domínio e wrapper de banco de dados compartilhados.
"""

from .modelos import Produto, Pedido, Pagamento, ResultadoTransacao
from .banco_dados import BancoDados

__all__ = [
    "Produto",
    "Pedido",
    "Pagamento",
    "ResultadoTransacao",
    "BancoDados",
]
