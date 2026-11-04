"""
Módulo: depois/config.py
============================================================
VERSÃO "DEPOIS" - Configurações centralizadas
============================================================

Parâmetros de tuning da solução refatorada:
  * TIMEOUT_LOCK_SEGUNDOS: tempo máximo para try_lock antes de acionar rollback.
  * POOL_COMPRAS / POOL_RELATORIOS: isolamento de pools de conexões.
  * ORDEM_RECURSOS: sequência estrita e obrigatória de aquisição de locks.
"""

TIMEOUT_LOCK_SEGUNDOS = 5.0

POOL_COMPRAS = 10      # conexões dedicadas a transações de compra (escrita)
POOL_RELATORIOS = 5    # conexões dedicadas a leituras/relatórios (leitura)

# Ordem global obrigatória para aquisição de múltiplos recursos.
# Qualquer transação que precise de mais de um lock deve respeitar:
# ESTOQUE -> FINANCEIRO -> PEDIDO
ORDEM_RECURSOS = ["ESTOQUE", "FINANCEIRO", "PEDIDO"]

# Limite de aging: uma requisição de baixa prioridade que aguardar N rodadas
# na fila é promovida automaticamente para alta prioridade.
LIMITE_AGING = 3
