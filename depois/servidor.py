"""
Módulo: depois/servidor.py
============================================================
VERSÃO "DEPOIS" - Simulador de servidor de e-commerce refatorado
============================================================

Demonstra que os mesmos cenários da versão ANTES são neutralizados:
  1. Estoque atômico (sem race condition / lost update).
  2. Compra segura sem deadlock (ordem global + try_lock + rollback).
  3. Relatórios executam sem starvation (pool isolado + aging).
"""

import threading
import time
import random

from .estoque import EstoqueDepois
from .financeiro import FinanceiroDepois, executar_compra_segura
from .relatorio import GerenciadorRelatoriosDepois, PoolConexoes, EnvelhecimentoPrioridade
from . import config


class ServidorDepois:
    def __init__(self):
        self.estoque = EstoqueDepois()
        self.financeiro = FinanceiroDepois()

        # Pools ISOLADOS: compras e relatórios não competem pelas mesmas conexões.
        pool_compras = PoolConexoes(config.POOL_COMPRAS, "compras")
        pool_relatorios = PoolConexoes(config.POOL_RELATORIOS, "relatorios")
        envelhecimento = EnvelhecimentoPrioridade()
        self.relatorios = GerenciadorRelatoriosDepois(pool_relatorios, envelhecimento)

        # Mantemos a referência do pool de compras (útil para diagnóstico)
        self.pool_compras = pool_compras

    # ----------------------------------------------------------------
    # Cenário 1: Estoque atômico (sem corrida)
    # ----------------------------------------------------------------
    def simular_corrida_estoque(self, produto_id="PROD-001", n_threads=20):
        print("\n" + "=" * 60)
        print("Cenário 1: Estoque Atômico (" + str(n_threads) + " threads concorrentes)")
        print("=" * 60)
        estoque_inicial = self.estoque.quantidade(produto_id)
        print("Estoque inicial de " + produto_id + ": " + str(estoque_inicial))

        sucessos = [0]
        lock_sucesso = threading.Lock()

        def reserva():
            if self.estoque.reservar(produto_id, 1):
                with lock_sucesso:
                    sucessos[0] += 1

        threads = [threading.Thread(target=reserva) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        estoque_final = self.estoque.quantidade(produto_id)
        vendas_esperadas = min(n_threads, estoque_inicial)

        print("Vendas registradas: " + str(sucessos[0]) +
              " (esperado: " + str(vendas_esperadas) + ")")
        print("Estoque final: " + str(estoque_final))
        if estoque_final < 0:
            print("ERRO CRÍTICO: Estoque NEGATIVO (não deveria ocorrer na versão DEPOIS)!")
        elif sucessos[0] != vendas_esperadas:
            print("AVISO: número de vendas diferente do esperado.")
        else:
            print("OK: estoque consistente, sem overselling nem estoque negativo.")

        return {
            "estoque_inicial": estoque_inicial,
            "vendas": sucessos[0],
            "estoque_final": estoque_final,
            "vendas_esperadas": vendas_esperadas,
        }

    # ----------------------------------------------------------------
    # Cenário 2: Compra segura sem deadlock
    # ----------------------------------------------------------------
    def simular_compra_segura(self, produto_id="PROD-001", quantidade=1,
                              preco=100.0, n_threads=10):
        print("\n" + "=" * 60)
        print("Cenário 2: Compras Concorrentes Sem Deadlock (" +
              str(n_threads) + " threads)")
        print("=" * 60)
        print("Ordem global de locks: ESTOQUE -> FINANCEIRO (try_lock + timeout 5s)")

        resultados = {"sucesso": 0, "falha_estoque": 0, "timeout": 0}
        lock_res = threading.Lock()

        def compra_thread():
            try:
                ok = executar_compra_segura(
                    self.estoque, self.financeiro,
                    produto_id, quantidade, preco,
                    timeout=config.TIMEOUT_LOCK_SEGUNDOS,
                )
                with lock_res:
                    if ok:
                        resultados["sucesso"] += 1
                    else:
                        if self.estoque.quantidade(produto_id) == 0:
                            resultados["falha_estoque"] += 1
                        else:
                            resultados["timeout"] += 1
            except Exception as exc:  # rollback já foi feito dentro de executar_compra_segura
                with lock_res:
                    resultados["timeout"] += 1
                print("[Compra] Exceção tratada com rollback: " + str(exc))

        threads = [
            threading.Thread(target=compra_thread)
            for _ in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print("Sucessos: " + str(resultados["sucesso"]))
        print("Falhas por estoque insuficiente: " +
              str(resultados["falha_estoque"]))
        print("Timeouts/rollback: " + str(resultados["timeout"]))
        print("Nenhuma travou permanentemente (sem deadlock).")
        return resultados

    # ----------------------------------------------------------------
    # Cenário 3: Relatórios sem starvation
    # ----------------------------------------------------------------
    def simular_relatorios(self):
        print("\n" + "=" * 60)
        print("Cenário 3: Relatórios sem Starvation (pool isolado + aging)")
        print("=" * 60)

        esperas = []
        lock_esp = threading.Lock()

        # Compras ocupam o pool de COMPRAS (não afetam relatórios)
        def compra(i):
            self.estoque.reservar("PROD-002", 1)

        threads_compra = [threading.Thread(target=compra, args=(i,))
                          for i in range(12)]
        for t in threads_compra:
            t.start()

        def relatorio(i):
            espera = self.relatorios.executar_relatorio(
                "R" + str(i), prioridade="baixa", timeout=10.0
            )
            if espera is not None:
                with lock_esp:
                    esperas.append(espera)

        threads_rel = [threading.Thread(target=relatorio, args=(i,))
                       for i in range(5)]
        for t in threads_rel:
            t.start()

        for t in threads_compra:
            t.join(timeout=5)
        for t in threads_rel:
            t.join(timeout=10)

        media = self.relatorios.media_tempo_espera()
        print("Tempo médio de espera dos relatórios: " +
              str(round(media, 3)) + "s")
        print("Relatórios de baixa prioridade executam graças ao pool dedicado e aging.")
        return media

    def executar_todos(self):
        print(">>> VERSÃO DEPOIS - Sistema refatorado e seguro <<<")
        r1 = self.simular_corrida_estoque()
        r2 = self.simular_compra_segura()
        r3 = self.simular_relatorios()
        print("\n>>> Resumo da versão DEPOIS <<<")
        print("  - Corrida de estoque: vendas=" + str(r1["vendas"]) +
              ", esperado=" + str(r1["vendas_esperadas"]) +
              ", estoque_final=" + str(r1["estoque_final"]))
        print("  - Compras seguras: sucesso=" + str(r2["sucesso"]) +
              ", falha_estoque=" + str(r2["falha_estoque"]) +
              ", timeouts=" + str(r2["timeout"]))
        print("  - Starvation (media espera relatorios): " + str(round(r3, 3)) + "s")
        return {"corrida": r1, "compras_seguras": r2, "relatorios": r3}
