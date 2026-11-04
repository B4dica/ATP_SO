"""
Módulo: antes/relatorio.py
============================================================
VERSÃO "ANTES" - Relatórios sofrem Inanição (Starvation) e Gargalo de I/O
============================================================

Cenário demonstrado:
  * Starvation: threads de relatório (baixa prioridade) nunca obtêm uma
    fatia de tempo porque o pool de conexões é esgotado por transações de
    compra (alta frequência, curta duração).
  * Gargalo de I/O: todas as operações compartilham o mesmo semáforo de
    conexões; relatórios pesados bloqueiam o mesmo recurso usado por vendas.

Falha teórica localizada:
  Um único semáforo/pool é compartilhado por compras e relatórios.
  Compras curtas e frequentes consomem as conexões; relatórios de baixa
  prioridade enfrentam espera ilimitada ou timeouts repetidos.

Referência clássica:
  Silberschatz et al. - Inanição (starvation) e escalonamento não justo.
  Tanenbaum - Escalonamento e envelhecimento (aging) como defesa contra
  inanição de processos de baixa prioridade.
"""

import threading
import time
import random


class GerenciadorRelatoriosAntes:
    """
    Relatórios e compras disputam o MESMO semáforo de conexões.
    Não há isolamento de recursos nem política de envelhecimento.
    """

    def __init__(self, total_conexoes: int = 3):
        self.semaforo_conexoes = threading.Semaphore(total_conexoes)
        self.tempos_espera = []

    def executar_relatorio(self, nome_relatorio: str,
                           prioridade: str = "baixa") -> float | None:
        """
        Tenta obter uma conexão do pool compartilhado com espera ilimitada
        (timeout fixo de 10s). Se compras segurarem as conexões, o relatório
        pode nunca ser executado -> starvation.
        """
        inicio = time.time()
        adquiriu = self.semaforo_conexoes.acquire(timeout=10)
        espera = time.time() - inicio
        self.tempos_espera.append(espera)

        if not adquiriu:
            print(f"[RELATÓRIO {nome_relatorio}] Falha ao obter conexão (timeout).")
            return None

        try:
            print(f"[RELATÓRIO {nome_relatorio}] Executando (prioridade {prioridade})...")
            time.sleep(random.uniform(0.2, 0.6))  # I/O pesado de leitura
        finally:
            self.semaforo_conexoes.release()

        return espera

    def media_tempo_espera(self) -> float:
        if not self.tempos_espera:
            return 0.0
        return sum(self.tempos_espera) / len(self.tempos_espera)
