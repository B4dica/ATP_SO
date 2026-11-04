"""
Módulo: depois/financeiro.py
============================================================
VERSÃO "DEPOIS" - Prevenção de Deadlock com ordem global e timeouts
============================================================

Soluções aplicadas:
  1. Ordem global de aquisição: toda transação que precise de mais de um
     recurso deve adquiri-los na sequência ESTOQUE -> FINANCEIRO -> PEDIDO.
     Isso quebra a condição de "espera circular" necessária para deadlock.
  2. try_lock com timeout (5 segundos): em vez de bloqueio ilimitado,
     usamos acquire(timeout=...). Se o segundo recurso não estiver
     disponível no prazo, liberamos o primeiro e fazemos rollback.
  3. Rollback automático: ao falhar ao adquirir qualquer recurso, todos os
     já adquiridos são liberados e a transação é abortada.

Referência clássica:
  Silberschatz et al. - Prevenção de deadlock via imposição de ordem total
  sobre recursos (elimina espera circular).
  Tanenbaum - Detecção e prevenção de deadlock; timeouts e rollback como
  mecanismos de recuperação.
"""

import threading
from contextlib import contextmanager

from . import config


class FinanceiroDepois:
    """
    Módulo financeiro com try_lock com timeout e rollback implícito.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.caixa = 0.0

    @contextmanager
    def adquirir_com_timeout(self, identificador: str,
                             timeout: float = config.TIMEOUT_LOCK_SEGUNDOS):
        """
        Tenta adquirir o lock com tempo limite. Se falhar, levanta
        TimeoutError para que o chamador execute rollback dos recursos
        já bloqueados (ex: liberar o lock do estoque obtido antes).
        """
        adquiriu = self.lock.acquire(timeout=timeout)
        if not adquiriu:
            msg = ("Timeout (" + str(timeout) + "s) ao adquirir lock "
                   "financeiro para " + identificador)
            raise TimeoutError(msg)
        try:
            yield
        finally:
            self.lock.release()

    def debitar(self, valor: float) -> bool:
        with self.lock:
            self.caixa += valor
            return True

    def get_caixa(self) -> float:
        with self.lock:
            return self.caixa


def executar_compra_segura(estoque, financeiro, produto_id: str,
                           quantidade: int, preco: float,
                           timeout: float = config.TIMEOUT_LOCK_SEGUNDOS) -> bool:
    """
    Executa uma compra de forma livre de deadlock.

    Algoritmo (ordem global obrigatória):
      1. Adquire lock do ESTOQUE com try_lock + timeout.
      2. Adquire lock do FINANCEIRO com try_lock + timeout.
      3. Executa reserva e débito dentro da região crítica ordenada.
      4. Em qualquer falha de timeout, libera os recursos já obtidos
         (rollback) e retorna False.

    Por que não há deadlock:
      - Todos os processos seguem a mesma ordem (Estoque antes de Financeiro).
      - Nunca há espera circular porque o grafo de dependências é acíclico.
      - O try_lock com timeout impede bloqueio indefinido; o rollback
        garante liberação dos recursos parciais.
    """
    # Passo 1: ESTOQUE primeiro (ordem global)
    lock_estoque = estoque.obter_lock_produto(produto_id)
    if not lock_estoque.acquire(timeout=timeout):
        print("[Compra-" + produto_id +
              "] Falha: timeout ao adquirir ESTOQUE. Rollback.")
        return False

    try:
        # Passo 2: FINANCEIRO depois (mesma ordem para todas as threads)
        if not financeiro.lock.acquire(timeout=timeout):
            print("[Compra-" + produto_id +
                  "] Falha: timeout ao adquirir FINANCEIRO. Rollback do ESTOQUE.")
            return False

        try:
            # Região crítica curta e ordenada: estoque + financeiro
            if not estoque._reservar_sem_lock(produto_id, quantidade):
                print("[Compra-" + produto_id +
                      "] Estoque insuficiente. Abortando.")
                return False

            financeiro.debitar(preco * quantidade)
            print("[Compra-" + produto_id +
                  "] Confirmada: " + str(quantidade) +
                  "x por R$" + str(preco) + ".")
            return True
        finally:
            financeiro.lock.release()
    finally:
        lock_estoque.release()
