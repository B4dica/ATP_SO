"""
Módulo: antes/servidor.py
============================================================
VERSÃO "ANTES" - Simulador de servidor de e-commerce com falhas
============================================================

Orquestra os três cenários de falha de concorrência:
  1. Race Condition no estoque.
  2. Deadlock por espera circular entre estoque e financeiro.
  3. Starvation de relatórios por esgotamento de conexões compartilhadas.
"""

import threading
import time
import random

from .estoque import EstoqueAntes
from .financeiro import FinanceiroAntes, executar_processo_a, executar_processo_b
from .relatorio import GerenciadorRelatoriosAntes


class ServidorAntes:
    def __init__(self):
        self.estoque = EstoqueAntes()
        self.financeiro = FinanceiroAntes()
        self.relatorios = GerenciadorRelatoriosAntes(total_conexoes=3)

    # ----------------------------------------------------------------
    # Cenário 1: Race Condition / Lost Update
    # ----------------------------------------------------------------
    def simular_corrida_estoque(self, produto_id: str = "PROD-001",
                                n_threads: int = 20) -> dict:
        print("\n" + "=" * 60)
        print(f"Cenário 1: Race Condition no Estoque ({n_threads} threads concorrentes)")
        print("=" * 60)
        estoque_inicial = self.estoque.quantidade(produto_id)
        print(f"Estoque inicial de {produto_id}: {estoque_inicial}")

        sucessos = [0]
        lock_sucesso = threading.Lock()

        def reserva():
            if self.estoque.reservar(produto_id, 1):
                with lock_sucesso:
                    sucessos[0] += 1

        threads = [threading.Thread(target=reserva, daemon=True) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        estoque_final = self.estoque.quantidade(produto_id)
        vendas_esperadas = min(n_threads, estoque_inicial)

        print(f"Vendas registradas: {sucessos[0]} (esperado: {vendas_esperadas})")
        print(f"Estoque final: {estoque_final}")
        if estoque_final < 0:
            print("ERRO CRÍTICO: Estoque NEGATIVO detectado!")
        elif sucessos[0] > vendas_esperadas:
            print("ERRO CRÍTICO: Overselling - vendas excederam o estoque inicial!")

        return {
            "estoque_inicial": estoque_inicial,
            "vendas": sucessos[0],
            "estoque_final": estoque_final,
            "vendas_esperadas": vendas_esperadas,
        }

    # ----------------------------------------------------------------
    # Cenário 2: Deadlock por espera circular
    # ----------------------------------------------------------------
    def simular_deadlock(self) -> bool:
        print("\n" + "=" * 60)
        print("Cenário 2: Deadlock por Espera Circular (Estoque <-> Financeiro)")
        print("=" * 60)
        print("Processo A: ESTOQUE -> FINANCEIRO")
        print("Processo B: FINANCEIRO -> ESTOQUE  (ordem invertida!)")

        t_a = threading.Thread(target=executar_processo_a,
                               args=(self.estoque, self.financeiro, "PROD-001", 1, 100.0),
                               daemon=True)
        t_b = threading.Thread(target=executar_processo_b,
                               args=(self.estoque, self.financeiro, "PROD-001", 1, 100.0),
                               daemon=True)
        t_a.start()
        t_b.start()
        t_a.join(timeout=3)
        t_b.join(timeout=3)

        travado = t_a.is_alive() or t_b.is_alive()
        if travado:
            print("DEADLOCK DETECTADO: threads ainda vivas após 3s (travamento permanente).")
        else:
            print("Sem deadlock nesta execução (resultado não-determinístico).")
        return travado

    # ----------------------------------------------------------------
    # Cenário 3: Starvation de relatórios
    # ----------------------------------------------------------------
    def simular_starvation(self) -> float:
        print("\n" + "=" * 60)
        print("Cenário 3: Inanição (Starvation) de Relatórios de Baixa Prioridade")
        print("=" * 60)

        def compra(i: int):
            self.estoque.reservar("PROD-002", 1)

        threads = []
        # Muitas compras curtas consomem as conexões do pool compartilhado
        for i in range(12):
            t = threading.Thread(target=compra, args=(i,), daemon=True)
            threads.append(t)
            t.start()

        esperas = []

        def relatorio(i: int):
            espera = self.relatorios.executar_relatorio(f"R{i}", prioridade="baixa")
            if espera is not None:
                esperas.append(espera)

        # Relatórios lançados enquanto compras seguram as conexões
        for i in range(5):
            t = threading.Thread(target=relatorio, args=(i,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        media = self.relatorios.media_tempo_espera()
        print(f"Tempo médio de espera dos relatórios: {media:.3f}s")
        print("Relatórios de baixa prioridade podem esperar indefinidamente (starvation).")
        return media

    def executar_todos(self):
        print(">>> VERSÃO ANTES - Iniciando simulações de falhas de concorrência <<<")
        r1 = self.simular_corrida_estoque()
        r2 = self.simular_deadlock()
        r3 = self.simular_starvation()
        print("\n>>> Resumo da versão ANTES <<<")
        print(f"  - Corrida de estoque: vendas={r1['vendas']}, esperado={r1['vendas_esperadas']}, "
              f"estoque_final={r1['estoque_final']}")
        print(f"  - Deadlock detectado: {r2}")
        print(f"  - Starvation (media espera relatorios): {r3:.3f}s")
        return {"corrida": r1, "deadlock": r2, "starvation": r3}
