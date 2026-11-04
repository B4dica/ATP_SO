"""
Módulo: comum/modelos.py
Entidades de domínio compartilhadas entre as versões ANTES e DEPOIS.

Domínio: e-commerce de venda de produtos com controle de concorrência.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Produto:
    id: str
    nome: str
    preco: float
    estoque: int


@dataclass
class Pedido:
    id: str
    produto_id: str
    quantidade: int
    status: str = "pendente"  # pendente | confirmado | cancelado | falha_estoque


@dataclass
class Pagamento:
    pedido_id: str
    valor: float
    status: str = "pendente"  # pendente | aprovado | recusado


@dataclass
class ResultadoTransacao:
    sucesso: bool
    pedido_id: str
    mensagem: str
    estoque_restante: Optional[int] = None
