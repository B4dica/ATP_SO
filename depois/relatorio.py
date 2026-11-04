"""
Módulo: depois/relatorio.py
============================================================
VERSÃO "DEPOIS" - Isolamento de recursos e escalonamento justo (Aging)

Soluções aplicadas:
  1. Pool de conexões ISOLADO para relatórios: usa uma instância separada de
     BancoDadosDepois (mesmo arquivo .db, mas conexão dedicada a leituras).
     Como usamos WAL (Write-Ahead Logging), leituras concorrentes não bloqueiam
     escritas de compras, e vice-versa.
  2. Envelhecimento (aging): requisições de relatório de baixa prioridade que
     aguardam muitas rodadas são promovidas automaticamente para alta prioridade,
     evitando starvation.
  3. Transação normal (BEGIN DEFERRED) para leituras: não adquire lock de
     escrita, portanto não concorre com transações de compra.

Referência clássica:
  Silberschatz et al. - Envelhecimento (aging) contra starvation.
  Tanenbaum - Particionamento de recursos para isolar classes de trabalho.
"""

import threading
import time
import random
from collections import deque


class EnvelhecimentoPrioridade:
    def __init__(self):
        self.fila_alta = deque()
        self.fila_baixa = deque()
        self.lock = threading.Lock()
        self.contador_espera = {}

    def enfileirar(self, id_requisicao: str, prioridade: str = "baixa"):
        with self.lock:
            if prioridade == "alta":
                self.fila_alta.append(id_requisicao)
            else:
                self.fila_baixa.append(id_requisicao)
            self.contador_espera[id_requisicao] = 0

    def proximo(self):
        with self.lock:
            promovidos = []
            for id_req in list(self.fila_baixa):
                self.contador_espera[id_req] += 1
                if self.contador_espera[id_req] >= 3:  # LIMITE_AGING
                    promovidos.append(id_req)
            for id_req in promovidos:
                self.fila_baixa.remove(id_req)
                self.fila_alta.append(id_req)
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
    Gerenciador de relatórios com pool de leitura ISOLADO e escalonamento
    justo (aging). Não compartilha conexões de escrita com compras.
    """

    def __init__(self, bd_leitura):
        self.bd_leitura = bd_leitura
        self.envelhecimento = EnvelhecimentoPrioridade()
        self.tempos_espera = []
        self._lock_resultados = threading.Lock()

    def executar_relatorio(self, nome_relatorio: str,
                           prioridade: str = "baixa") -> float | None:
        id_req = nome_relatorio
        self.envelhecimento.enfileirar(id_req, prioridade)

        # Espera na fila justa até ser a próxima da vez
        while True:
            proximo = self.envelhecimento.proximo()
            if proximo == id_req:
                break
            time.sleep(0.05)

        inicio = time.time()
        try:
            # Leitura isolada: BEGIN (não IMMEDIATE), não trava escritores
            with self.bd_leitura.transacao(modo="normal") as cur:
                cur.execute("SELECT id, nome, preco, estoque FROM produtos")
                _ = cur.fetchall()  # simula leitura de relatório
        finally:
            espera = time.time() - inicio
            with self._lock_resultados:
                self.tempos_espera.append(espera)
            self.envelhecimento.remover(id_req)

        print(f"[RELATORIO {nome_relatorio}] Executando (pool de leitura isolado, "
              f"prioridade {prioridade}, espera {espera:.3f}s)...")
        return espera

    def media_tempo_espera(self) -> float:
        with self._lock_resultados:
            if not self.tempos_espera:
                return 0.0
            return sum(self.tempos_espera) / len(self.tempos_espera)
