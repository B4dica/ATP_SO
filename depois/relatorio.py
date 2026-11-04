"""
Módulo: depois/relatorio.py
============================================================
VERSÃO "DEPOIS" - Isolamento de recursos e escalonamento justo (Aging)
============================================================

Soluções aplicadas:
  1. Isolamento de pools de conexões: transações de COMPRA usam um pool
     dedicado e rotinas de LEITURA/RELATÓRIO usam outro pool separado.
     Compras não esgotam conexões necessárias pelos relatórios.
  2. Envelhecimento (aging): requisitos de relatório de baixa prioridade que
     aguardam muitas rodadas são promovidos automaticamente para alta
     prioridade, eliminando a inanição (starvation).
  3. Fila de escalonamento justa: FIFO dentro de cada nível de prioridade.

Referência clássica:
  Silberschatz et al. - Escalonamento por prioridade com envelhecimento
  (aging) para evitar starvation de processos de baixa prioridade.
  Tanenbaum - Particionamento de recursos e pools de conexões para isolar
  classes de trabalho com diferentes requisitos de desempenho.
"""

import threading
import time
import random
from collections import deque

from . import config


class PoolConexoes:
    """
    Pool simples de conexões controlado por semáforo.
    """

    def __init__(self, tamanho: int, nome: str):
        self.nome = nome
        self.tamanho = tamanho
        self.semaforo = threading.Semaphore(tamanho)

    def adquirir(self, timeout: float = 10.0) -> bool:
        return self.semaforo.acquire(timeout=timeout)

    def liberar(self):
        self.semaforo.release()

    def disponiveis(self) -> int:
        return getattr(self.semaforo, "_valor", self.tamanho)


class EnvelhecimentoPrioridade:
    """
    Implementa envelhecimento (aging): itens de baixa prioridade que aguardam
    além do LIMITE_AGING são promovidos à fila de alta prioridade.
    """

    def __init__(self):
        self.fila_alta = deque()
        self.fila_baixa = deque()
        self.lock = threading.Lock()
        self.contador_espera: dict = {}

    def enfileirar(self, id_requisicao: str, prioridade: str = "baixa"):
        with self.lock:
            if prioridade == "alta":
                self.fila_alta.append(id_requisicao)
            else:
                self.fila_baixa.append(id_requisicao)
            self.contador_espera[id_requisicao] = 0

    def proximo(self):
        """
        Retorna o próximo id da fila respeitando aging.
        """
        with self.lock:
            # Aging: promover itens de baixa que esperaram demais
            promovidos = []
            for id_req in list(self.fila_baixa):
                self.contador_espera[id_req] += 1
                if self.contador_espera[id_req] >= config.LIMITE_AGING:
                    promovidos.append(id_req)

            for id_req in promovidos:
                self.fila_baixa.remove(id_req)
                self.fila_alta.append(id_req)
                print("[Aging] " + id_req +
                      " promovido de baixa para ALTA prioridade.")

            if self.fila_alta:
                return self.fila_alta.popleft()
            if self.fila_baixa:
                return self.fila_baixa.popleft()
            return None

    def remover(self, id_requisicao: str):
        with self.lock:
            self.contador_espera.pop(id_requisicao, None)
            try:
                self.fila_alta.remove(id_requisicao)
            except ValueError:
                pass
            try:
                self.fila_baixa.remove(id_requisicao)
            except ValueError:
                pass


class GerenciadorRelatoriosDepois:
    """
    Gerenciador de relatórios com:
      - Pool de conexões ISOLADO (não compartilhado com compras).
      - Escalonamento justo com envelhecimento (aging).
    """

    def __init__(self, pool: PoolConexoes,
                 envelhecimento: EnvelhecimentoPrioridade):
        self.pool = pool
        self.envelhecimento = envelhecimento
        self.tempos_espera = []
        self._lock_resultados = threading.Lock()

    def executar_relatorio(self, nome_relatorio: str,
                           prioridade: str = "baixa",
                           timeout: float = 10.0):
        """
        Executa um relatório aguardando na fila justa e usando o pool
        dedicado de conexões. Starvation é evitado por aging + pool isolado.
        """
        id_req = nome_relatorio
        self.envelhecimento.enfileirar(id_req, prioridade)

        # Espera justa na fila até ser o próximo da vez
        while True:
            proximo = self.envelhecimento.proximo()
            if proximo == id_req:
                break
            time.sleep(0.05)

        inicio = time.time()
        adquiriu = self.pool.adquirir(timeout=timeout)
        espera = time.time() - inicio

        with self._lock_resultados:
            self.tempos_espera.append(espera)

        if not adquiriu:
            self.envelhecimento.remover(id_req)
            print("[RELATORIO " + nome_relatorio +
                  "] Falha ao obter conexão do pool dedicado.")
            return None

        try:
            print("[RELATORIO " + nome_relatorio + "] Executando " +
                  "(pool dedicado, prioridade " + prioridade +
                  ", espera " + str(round(espera, 3)) + "s)...")
            time.sleep(random.uniform(0.1, 0.3))  # I/O de leitura isolado
        finally:
            self.pool.liberar()
            self.envelhecimento.remover(id_req)

        return espera

    def media_tempo_espera(self) -> float:
        with self._lock_resultados:
            if not self.tempos_espera:
                return 0.0
            return sum(self.tempos_espera) / len(self.tempos_espera)
