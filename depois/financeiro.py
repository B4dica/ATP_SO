"""
Módulo: depois/financeiro.py
============================================================
VERSÃO "DEPOIS" - Prevenção de Deadlock com ordem global, try_lock e rollback

Soluções aplicadas:
  1. Ordem global de aquisição de recursos: toda transação composta adquire
     os bloqueios na sequência ESTOQUE -> PEDIDO -> FINANCEIRO. Como toda
     compra ocorre dentro de UMA única transação BEGIN IMMEDIATE, não há
     espera circular entre transações distintas -> deadlock eliminado.
  2. try_lock com timeout: BEGIN IMMEDIATE + busy_timeout=5s.
     Se outra transação de escrita estiver ativa, o SQLite aguarda no
     máximo 5 segundos; caso contrário, levanta OperationalError.
  3. Rollback automático: qualquer exceção dentro da transação faz ROLLBACK,
     liberando todos os locks parciais.

Queries SQL demonstradas:
    BEGIN IMMEDIATE;                                     -- try_lock de escrita (5s)
    UPDATE produtos SET estoque = ... WHERE ...;         -- lock/grava ESTOQUE
    INSERT INTO pedidos ...;                             -- grava PEDIDO
    INSERT INTO pagamentos ...;                          -- grava FINANCEIRO
    COMMIT;                                              -- libera todos os locks
    -- ou ROLLBACK automático em exceção

Referência clássica:
  Silberschatz et al. - Prevenção de deadlock via ordem total de recursos.
  Tanenbaum - Timeout e rollback como mecanismos de recuperação de deadlock.
"""

import sqlite3
import uuid


def executar_compra_segura(bd, produto_id: str, quantidade: int,
                           preco: float, timeout_s: float = 5.0) -> dict:
    """
    Executa uma compra completa de forma livre de deadlock e segura contra
    condições de corrida.

    Algoritmo (ordem global obrigatória):
      1. Abre transação BEGIN IMMEDIATE (try_lock de escrita no banco, 5s).
      2. UPDATE produtos ... WHERE estoque >= quantidade  (ESTOQUE).
      3. INSERT pedidos ...                               (PEDIDO).
      4. INSERT pagamentos ...                            (FINANCEIRO).
      5. COMMIT -> libera todos os locks de uma vez.

    Se qualquer passo falhar (timeout, exceção):
      - O context manager faz ROLLBACK automaticamente.
      - Nenhum lock fica parcial.

    Retorna dicionário com: sucesso (bool), mensagem, pedido_id.
    """
    pedido_id = "PED-" + uuid.uuid4().hex[:8]

    try:
        with bd.transacao(modo="immediato") as cur:
            # --- Passo 1: ESTOQUE (primeiro recurso, ordem global) ---
            cur.execute(
                "UPDATE produtos SET estoque = estoque - ? "
                "WHERE id = ? AND estoque >= ?",
                (quantidade, produto_id, quantidade),
            )
            if cur.rowcount != 1:
                return {"sucesso": False,
                        "mensagem": "Estoque insuficiente",
                        "pedido_id": pedido_id}

            # --- Passo 2: PEDIDO ---
            cur.execute(
                "INSERT OR REPLACE INTO pedidos (id, produto_id, quantidade, status) "
                "VALUES (?, ?, ?, 'confirmado')",
                (pedido_id, produto_id, quantidade),
            )

            # --- Passo 3: FINANCEIRO (último recurso, ordem global) ---
            cur.execute(
                "INSERT OR REPLACE INTO pagamentos (pedido_id, valor, status) "
                "VALUES (?, ?, 'aprovado')",
                (pedido_id, preco * quantidade),
            )

            # Commit libera todos os locks (estoque, pedido, financeiro)
        return {"sucesso": True, "mensagem": "Compra confirmada",
                "pedido_id": pedido_id}

    except sqlite3.OperationalError as exc:
        # O context manager já fez ROLLBACK. Reportamos o timeout/lock.
        return {"sucesso": False,
                "mensagem": f"Timeout/lock indisponível ({timeout_s}s): {exc}",
                "pedido_id": pedido_id}
