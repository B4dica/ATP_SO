# =========================================================
# ANEXO III: CÓDIGO INICIAL (COM FALHAS DE CONCORRÊNCIA)
# =========================================================

import time
import threading
import sqlite3  # ou outro driver de DB

# Simulação de conexão e cursor (substitua pela sua conexão real)
conn = sqlite3.connect('exemplo.db', check_same_thread=False)
cursor = conn.cursor()

# FALHA 1: Condição de Corrida (Check-Then-Act) no Estoque
def processar_compra_vulneravel(produto_id, usuario_id):
    # Linha 1: Leitura do estoque (Sem trava/Sem transação atômica)
    cursor.execute("SELECT estoque FROM produtos WHERE id = ?", (produto_id,))
    estoque = cursor.fetchone()['estoque']  # <-- FALHA AQUI: PID_01 e PID_02 leem '1' ao mesmo tempo

    if estoque > 0:
        # Simula atraso/processamento entre a checagem e a escrita
        time.sleep(0.002)

        # Linha 2: Subtração sobreposta (Lost Update)
        cursor.execute("UPDATE produtos SET estoque = estoque - 1 WHERE id = ?", (produto_id,))
        conn.commit()
        # <-- RESULTADO: Saldo fica -1 no banco de dados!
        return "Compra aprovada"
    else:
        return "Sem estoque"


# FALHA 2: Deadlock por Inversão na Ordem dos Locks
lock_inventario = threading.Lock()
lock_financeiro = threading.Lock()

# Processo A (ex: Venda - PID_15)
def processo_venda_vulneravel():
    lock_inventario.acquire()  # Pega Inventário primeiro
    time.sleep(0.001)
    lock_financeiro.acquire()  # Aguarda Financeiro indefinidamente <-- DEADLOCK!
    # ... processa venda ...
    lock_financeiro.release()
    lock_inventario.release()

# Processo B (ex: Auditoria/Financeiro - PID_16)
def processo_auditoria_vulneravel():
    lock_financeiro.acquire()  # Pega Financeiro primeiro (ORDEM INVERTIDA)
    time.sleep(0.001)
    lock_inventario.acquire()  # Aguarda Inventário indefinidamente <-- DEADLOCK!
    # ... processa auditoria ...
    lock_inventario.release()
    lock_financeiro.release()

# FALHA 3: Escalonamento Estático sem Aging (Starvation de Relatórios)
# Simulação simples de fila de tarefas sem envelhecimento
import queue

fila_tarefas = queue.Queue()

def enfileirar_tarefa(nome, prioridade):
    # prioridade: número menor = maior prioridade
    fila_tarefas.put((prioridade, nome))

def processar_fila():
    while not fila_tarefas.empty():
        prioridade, nome = fila_tarefas.get()
        print(f"Processando {nome} (prioridade {prioridade})")
        time.sleep(0.01)  # simula trabalho
        # Nenhum mecanismo de aging: tarefas de baixa prioridade podem esperar indefinidamente