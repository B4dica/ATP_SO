"""
Módulo: antes/estoque.py
============================================================
VERSÃO "ANTES" - Estoque SEM controle de concorrência adequado
============================================================

Cenário demonstrado:
  * Condição de Corrida (Race Condition) tipo Check-Then-Act.
  * Lost Update (atualização perdida).
  * Estoque negativo / overselling (venda de itens inexistentes).

Falha teórica localizada:
  O método reservar() NÃO É ATÔMICO. Executa:
    1. READ  -> ler quantidade atual
    2. CHECK -> verificar se estoque >= quantidade solicitada
    3. ACT   -> gravar nova quantidade

  Entre o READ (1) e o ACT (3), outra thread pode alterar o estoque.
  Como não há lock/região crítica protegendo esse intervalo, duas threads
  podem ler o mesmo valor, ambas passarem no CHECK e gravarem um resultado
  baseado em leitura obsoleta (stale read). Resultado: vendemos mais do que
  temos e o estoque pode ficar negativo.

Referência clássica:
  Silberschatz, Galvin, Gagne - Operating System Concepts (cap. Sincronização
  e Condição de Corrida).
  Tanenbaum - Modern Operating Systems (cap. Processos e Threads, seções sobre
  seções críticas e exclusão mútua).
"""

import threading
import time


class EstoqueAntes:
    """
    Estoque rudimentar. Nenhuma exclusão mútua protege a leitura+escrita
    conjunta de um produto.
    """

    def __init__(self):
        self.produtos = {
            "PROD-001": 5,   # estoque intencionalmente baixo para forçar corrida
            "PROD-002": 10,
        }
        self._contador_vendas = 0

    # ------------------------------------------------------------------
    # FALHA: região crítica não protegida (início)
    # ------------------------------------------------------------------
    def reservar(self, produto_id: str, quantidade: int) -> bool:
        """
        Reserva quantidade do produto.

        >>> FALHA TEÓRICA <<<
        Esta operação não é atômica. Várias threads podem:
          - ler o mesmo estoque (atual = 5);
          - todas passar no if (atual >= 1);
          - todas gravar atual - 1 = 4.
        Resultado: 20 vendas com estoque inicial 5 => estoque final incorreto,
        possivelmente negativo se a lógica permitir decremento sem rechecagem.
        """
        atual = self.produtos.get(produto_id, 0)          # READ (não protegido)

        # Janela de vulnerabilidade: outra thread pode alterar self.produtos aqui.
        time.sleep(0.001)  # simula latência de E/S e amplia a janela de race condition

        if atual >= quantidade:                             # CHECK (baseado em dado obsoleto)
            self.produtos[produto_id] = atual - quantidade   # ACT/WRITE (Lost Update possível)
            self._contador_vendas += 1
            return True
        # >>> FALHA TEÓRICA <<< (fim da região crítica desprotegida)

        return False

    def quantidade(self, produto_id: str) -> int:
        return self.produtos.get(produto_id, 0)

    def total_vendas(self) -> int:
        return self._contador_vendas
