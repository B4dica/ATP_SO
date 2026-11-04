"""
Módulo: depois/servidor.py
============================================================
VERSÃO "DEPOIS" - Simulador de servidor de e-commerce com banco de dados real

Demonstra, com queries SQL, que os mesmos cenários da versão ANTES são
neutralizados:
  1. Estoque atômico via SELECT ... FOR UPDATE (sem race condition).
  2. Compra segura sem deadlock (ordem global + BEGIN IMMEDIATE + busy_timeout + ROLLBACK).
  3. Relatórios sem starvation (pool de leitura isolado + aging).
"""

import threading
import time
import uuid

from .banco import BancoDadosDepois
from .estoque import EstoqueDepois
from .financeiro import executar_compra_segura
from .relatorio import GerenciadorRelatoriosDepois


class ServidorDepois:
    def __init__(self):
        # Banco para compras/escritas (transações BEGIN IMMEDIATE)
        self.bd_compras = BancoDadosDepois()

        # Banco para relatórios/leituras (mesmo arquivo .db, conexão dedicada)
        # Em SQLite + WAL, leituras concorrentes não bloqueiam escritas.
        self.bd_relatorios = BancoDadosDepois(caminho_db=self.bd_compras.caminho_db)

        self.estoque = EstoqueDepois(self.bd_compras)
        self.relatorios = GerenciadorRelatoriosDepois(self.bd_relatorios)

    # ------------------------------------------------------------
    # Cenário 1: Estoque atômico via SQL (sem race condition)
    # ------------------------------------------------------------
    def simular_corrida_estoque(self, produto_id="PROD-001", n_threads=20):
        print("\n" + "=" * 60)
        print("Cenário 1: Estoque Atômico via SQL (" +
              str(n_threads) + " threads concorrentes)")
        print("=" * 60)
        estoque_inicial = self.estoque.quantidade(produto_id)
        print("Estoque inicial de " + produto_id + ": " + str(estoque_inicial))

        sucessos = [0]
        lock_sucesso = threading.Lock()

        def reserva():
            if self.estoque.reservar(produto_id, 1):
                with lock_sucesso:
                    sucessos[0] += 1

        threads = [threading.Thread(target=reserva, daemon=True)
                   for _ in range(n_threads)]
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
            print("OK: estoque consistente via UPDATE condicional + BEGIN IMMEDIATE, sem overselling.")

        return {
            "estoque_inicial": estoque_inicial,
            "vendas": sucessos[0],
            "estoque_final": estoque_final,
            "vendas_esperadas": vendas_esperadas,
        }

    # ------------------------------------------------------------
    # Cenário 2: Compra segura sem deadlock (ordem global + SQL)
    # ------------------------------------------------------------
    def simular_compra_segura(self, produto_id="PROD-001", quantidade=1,
                              preco=100.0, n_threads=10):
        print("\n" + "=" * 60)
        print("Cenário 2: Compras Concorrentes Sem Deadlock (" +
              str(n_threads) + " threads)")
        print("=" * 60)
        print("Ordem global de recursos no banco: ESTOQUE -> PEDIDO -> FINANCEIRO")
        try:
            from . import config
            print("try_lock via BEGIN IMMEDIATE + busy_timeout = " +
                  str(config.TIMEOUT_LOCK_SEGUNDOS) + "s")
        except Exception:
            print("try_lock via BEGIN IMMEDIATE + busy_timeout = 5s")

        resultados = {"sucesso": 0, "falha_estoque": 0, "timeout": 0}
        lock_res = threading.Lock()

        def compra_thread():
            pedido_id = "PED-SIM-" + uuid.uuid4().hex[:6]
            try:
                res = executar_compra_segura(
                    self.bd_compras,
                    produto_id, quantidade, preco,
                    timeout_s=5.0,
                )
                with lock_res:
                    if res["sucesso"]:
                        resultados["sucesso"] += 1
                    elif "Estoque insuficiente" in res["mensagem"]:
                        resultados["falha_estoque"] += 1
                    else:
                        resultados["timeout"] += 1
            except Exception as exc:
                with lock_res:
                    resultados["timeout"] += 1
                print("[Compra] Exceção tratada com rollback: " + str(exc))

        threads = [threading.Thread(target=compra_thread, daemon=True)
                   for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print("Sucessos: " + str(resultados["sucesso"]))
        print("Falhas por estoque insuficiente: " +
              str(resultados["falha_estoque"]))
        print("Timeouts/rollback: " + str(resultados["timeout"]))
        print("Nenhuma travou permanentemente (sem deadlock via ordem global).")
        return resultados

    # ------------------------------------------------------------
    # Cenário 3: Relatórios sem starvation (pool isolado + aging)
    # ------------------------------------------------------------
    def simular_relatorios(self):
        print("\n" + "=" * 60)
        print("Cenário 3: Relatórios sem Starvation (pool de leitura isolado + aging)")
        print("=" * 60)

        esperas = []
        lock_esp = threading.Lock()

        # Compras usam o pool de ESCRITA; relatórios usam pool de LEITURA isolado.
        def compra(i):
            self.estoque.reservar("PROD-002", 1)

        threads_compra = [threading.Thread(target=compra, args=(i,), daemon=True)
                          for i in range(12)]
        for t in threads_compra:
            t.start()

        def relatorio(i):
            espera = self.relatorios.executar_relatorio(
                "R" + str(i), prioridade="baixa")
            if espera is not None:
                with lock_esp:
                    esperas.append(espera)

        threads_rel = [threading.Thread(target=relatorio, args=(i,), daemon=True)
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
        print("Relatórios de baixa prioridade executam via pool isolado e aging.")
        return media

    def executar_todos(self):
        print(">>> VERSÃO DEPOIS - Banco de dados SQLite com controle de concorrência <<<")
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
