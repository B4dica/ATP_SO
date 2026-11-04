# =========================================================
# ANEXO IV: CÓDIGO REFATORADO (COM MUTEX, TIMEOUT E ORDENAÇÃO)
# =========================================================

import threading
import time

# Dicionário de travas granulares por produto (Exclusão Mútua Granular)
locks_produtos = {}
mapa_lock_global = threading.Lock()

def obter_lock_produto(produto_id):
    with mapa_lock_global:
        if produto_id not in locks_produtos:
            locks_produtos[produto_id] = threading.Lock()
        return locks_produtos[produto_id]

# ---------------------------------------------------------
# CORREÇÃO 1: Integridade do Estoque (Atomicidade no Banco e Mutex)
# ---------------------------------------------------------
def processar_compra_corrigida(produto_id, usuario_id):
    lock_item = obter_lock_produto(produto_id)

    # Exclusão mútua na aplicação para o mesmo item
    with lock_item:
        # Instrução SQL Atômica: garante decremento apenas se saldo >= 1
        query = """
            UPDATE produtos
            SET estoque = estoque - 1
            WHERE id = %s AND estoque >= 1
        """
        cursor.execute(query, (produto_id,))

        # Se nenhuma linha foi afetada, o estoque já era 0
        if cursor.rowcount == 0:
            return "Falha: Item sem estoque disponível", 400

        db.commit()
        return "Sucesso: Compra realizada", 200


# ---------------------------------------------------------
# CORREÇÃO 2: Prevenção de Deadlock e Liveness (Timeout de 5s)
# ---------------------------------------------------------
# Regra Estrita: SEMPRE adquirir Lock_Inventario ANTES de Lock_Financeiro
lock_inventario = threading.Lock()
lock_financeiro = threading.Lock()

def executar_transacao_segura():
    # 1. Quebra da Espera Circular: Ordem fixa e hierárquica
    # Tenta adquirir Lock_Inventario com timeout de 5 segundos (Regra 2)
    inventario_adquirido = lock_inventario.acquire(timeout=5.0)
    if not inventario_adquirido:
        return "Erro 504: Timeout ao aguardar inventário", 504

    try:
        # Tenta adquirir Lock_Financeiro com timeout
        financeiro_adquirido = lock_financeiro.acquire(timeout=5.0)
        if not financeiro_adquirido:
            return "Erro 504: Timeout na validação financeira (> 5s)", 504

        try:
            # Processamento seguro da transação
            return "Processado com sucesso", 200
        finally:
            lock_financeiro.release()
    finally:
        lock_inventario.release()


# ---------------------------------------------------------
# CORREÇÃO 3: Escalonamento e Fairness (Aging para Relatórios)
# ---------------------------------------------------------
import queue

class Tarefa:
    def __init__(self, prioridade, nome):
        self.prioridade = prioridade  # Menor número = Maior prioridade
        self.nome = nome
        self.tempo_espera = 0

# Fila do Escalonador com Aging
def aplicar_aging(fila_tarefas):
    for tarefa in fila_tarefas:
        # Incrementa prioridade de tarefas que esperam há muito tempo
        tarefa.tempo_espera += 1
        if tarefa.tempo_espera > 10:  # A cada 10 min
            tarefa.prioridade = max(0, tarefa.prioridade - 1) # Promove a tarefa