"""
Módulo: depois/estoque.py
============================================================
VERSÃO "DEPOIS" - Estoque com atomicidade e exclusão mútua granular
============================================================

Solução aplicada:
  * Exclusão mútua granular: um lock distinto por produto, de modo que a
    região crítica seja o menor possível (apenas o produto alvo).
  * Operação atômica: leitura (check) e gravação (act) ocorrem dentro do
    mesmo lock, eliminando a janela de vulnerabilidade do Check-Then-Act.
  * Região crítica curta: minimiza o tempo dentro do lock, reduzindo
    contenção e aumentando o throughput sob alta carga.

Referência clássica:
  Tanenbaum - Exclusão mútua e seções críticas; locks granulares reduzem
  a granularidade da contenção sem comprometer a correção.
  Silberschatz et al. - Região crítica: apenas um processo por vez na seção
  crítica; solução de software/hardware para exclusão mútua.
"""

import threading


class EstoqueDepois:
    """
    Estoque seguro para concorrência.

    Cada produto tem seu próprio lock (dicionário _locks protegido por um
    meta-lock). Isso evita que uma operação em "PROD-001" bloqueie
    operações em "PROD-002" (concorrência real, não serialização total).
    """

    def __init__(self):
        self.produtos = {
            "PROD-001": 5,
            "PROD-002": 10,
        }
        self._locks_por_produto: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()  # protege a criação de novos locks

    def _obter_lock(self, produto_id: str) -> threading.Lock:
        """Retorna (criando se necessário) o lock granular do produto."""
        with self._meta_lock:
            if produto_id not in self._locks_por_produto:
                self._locks_por_produto[produto_id] = threading.Lock()
            return self._locks_por_produto[produto_id]

    def obter_lock_produto(self, produto_id: str) -> threading.Lock:
        """
        Expõe o lock do produto para uso externo (ex: transação composta
        estoque + financeiro que precisa adquirir o lock do estoque antes
        do financeiro, respeitando a ordem global).
        """
        return self._obter_lock(produto_id)

    def reservar(self, produto_id: str, quantidade: int) -> bool:
        """
        Reserva de forma atômica.

        >>> SEGURO <<<
        O lock é adquirido ANTES da leitura e liberado APÓS a gravação.
        Nenhuma outra thread pode observar estado intermediário.
        """
        lock = self._obter_lock(produto_id)
        with lock:  # regiao crítica mínima: apenas este produto
            return self._reservar_sem_lock(produto_id, quantidade)

    def _reservar_sem_lock(self, produto_id: str, quantidade: int) -> bool:
        """
        Pressupõe que o caller já detém o lock do produto.
        Usado por transações compostas que já adquiriram o lock externamente.
        """
        atual = self.produtos.get(produto_id, 0)
        if atual >= quantidade:
            self.produtos[produto_id] = atual - quantidade
            return True
        return False

    def quantidade(self, produto_id: str) -> int:
        lock = self._obter_lock(produto_id)
        with lock:
            return self.produtos.get(produto_id, 0)
