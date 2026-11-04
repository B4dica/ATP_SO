"""
Módulo: antes/financeiro.py
============================================================
VERSÃO "ANTES" - Módulo financeiro com locks adquiridos em ordem arbitrária
============================================================

Cenário demonstrado:
  * Deadlock por Espera Circular (Circular Wait).

Falha teórica localizada:
  Dois processos adquirem dois recursos (ESTOQUE e FINANCEIRO) em ordens
  opostas:
    Processo A: trava ESTOQUE, depois tenta travar FINANCEIRO.
    Processo B: trava FINANCEIRO, depois tenta travar ESTOQUE.

  Se A segura ESTOQUE e espera FINANCEIRO, enquanto B segura FINANCEIRO e
  espera ESTOQUE, nenhum avança -> travamento permanente (Liveness violada).

Referência clássica:
  Silberschatz et al. - Condições necessárias para deadlock (exclusão mútua,
  espera parcial, não-preempção, espera circular).
  Tanenbaum - Prevenção de deadlock via ordenação de recursos.
"""

import threading
import time

from .estoque import EstoqueAntes


class FinanceiroAntes:
    """
    Módulo financeiro com seu próprio lock. O deadlock surge quando este lock
    e o lock do estoque são adquiridos em ordens opostas por threads distintas.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.caixa = 0.0

    def debitar(self, valor: float) -> bool:
        with self.lock:
            self.caixa += valor
            return True

    def get_caixa(self) -> float:
        with self.lock:
            return self.caixa


# ------------------------------------------------------------------
# Helpers que simulam os dois processos com ordem de lock INVERTIDA
# ------------------------------------------------------------------
def _garantir_lock_estoque(estoque: EstoqueAntes) -> threading.Lock:
    """
    Garante que o objeto EstoqueAntes possua um lock associado.
    (Na versão ANTES o EstoqueAntes não expõe lock público; simulamos um
    lock externo para ilustrar o deadlock entre dois módulos.)
    """
    lock = getattr(estoque, "_lock_externo", None)
    if lock is None:
        lock = threading.Lock()
        estoque._lock_externo = lock
    return lock


def executar_processo_a(estoque: EstoqueAntes, financeiro: FinanceiroAntes,
                        produto_id: str, quantidade: int, preco: float):
    """
    Processo A: adquire ESTOQUE primeiro, depois FINANCEIRO.
    """
    lock_estoque = _garantir_lock_estoque(estoque)
    lock_estoque.acquire()
    print("[Processo A] Bloqueou ESTOQUE")
    time.sleep(0.05)  # amplia janela para deadlock

    try:
        financeiro.lock.acquire()  # tenta FINANCEIRO -> pode bloquear para sempre
        print("[Processo A] Bloqueou FINANCEIRO")
        financeiro.debitar(preco * quantidade)
        estoque.reservar(produto_id, quantidade)
        financeiro.lock.release()
    finally:
        lock_estoque.release()


def executar_processo_b(estoque: EstoqueAntes, financeiro: FinanceiroAntes,
                        produto_id: str, quantidade: int, preco: float):
    """
    Processo B: adquire FINANCEIRO primeiro, depois ESTOQUE.
    Ordem INVERTIDA em relação ao Processo A => Espera Circular.
    """
    financeiro.lock.acquire()
    print("[Processo B] Bloqueou FINANCEIRO")
    time.sleep(0.05)

    try:
        lock_estoque = _garantir_lock_estoque(estoque)
        lock_estoque.acquire()  # tenta ESTOQUE -> deadlock com Processo A
        print("[Processo B] Bloqueou ESTOQUE")
        estoque.reservar(produto_id, quantidade)
        financeiro.debitar(preco * quantidade)
        lock_estoque.release()
    finally:
        financeiro.lock.release()
