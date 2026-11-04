"""
Módulo: depois/estoque.py
============================================================
VERSÃO "DEPOIS" - Estoque com atomicidade via banco de dados (SQLite)

Soluções aplicadas:
  * Atomicidade: a verificação e atualização ocorrem em uma ÚNICA instrução
    SQL (UPDATE ... WHERE estoque >= ?), dentro de uma transação
    BEGIN IMMEDIATE. Não há Check-Then-Act separado.
  * Exclusão mútua no banco: BEGIN IMMEDIATE serializa escritores, evitando
    atualizações perdidas (lost update).
  * Região crítica curta: apenas o tempo da instrução UPDATE + commit.

Queries SQL demonstradas:
    BEGIN IMMEDIATE;
    UPDATE produtos SET estoque = estoque - ? WHERE id = ? AND estoque >= ?;
    -- se cursor.rowcount == 1 -> sucesso; se 0 -> estoque insuficiente
    COMMIT;  (ou ROLLBACK automático em exceção)

Nota: o SQLite embutido no Python 3.11 não suporta SELECT ... FOR UPDATE,
então a atomicidade é alcançada com UPDATE condicional + BEGIN IMMEDIATE,
que é a abordagem equivalente e compatível.

Referência clássica:
  Silberschatz et al. - Transações e isolamento; atualização atômica via SQL.
  Tanenbaum - Seções críticas devem ser o menor possível.
"""

import sqlite3


class EstoqueDepois:
    def __init__(self, bd):
        self.bd = bd

    def reservar(self, produto_id: str, quantidade: int) -> bool:
        """
        Reserva estoque de forma atômica usando SQL.

        >>> SEGURO <<<
        O UPDATE condicional verifica e decrementa em uma única instrução,
        sob proteção de BEGIN IMMEDIATE. Duas threads concorrentes não
        conseguem ambas decrementar o mesmo estoque porque o SQLite
        serializa escritores.
        """
        try:
            with self.bd.transacao(modo="immediato") as cur:
                cur.execute(
                    "UPDATE produtos SET estoque = estoque - ? "
                    "WHERE id = ? AND estoque >= ?",
                    (quantidade, produto_id, quantidade),
                )
                # rowcount = 1 significa que a linha foi atualizada (estoque suficiente)
                # rowcount = 0 significa estoque insuficiente ou produto inexistente
                return cur.rowcount == 1
        except sqlite3.OperationalError:
            # busy_timeout esgotado: não conseguiu o lock de escrita em 5s
            return False

    def quantidade(self, produto_id: str) -> int:
        """Leitura simples de estoque (transação normal de leitura)."""
        with self.bd.transacao(modo="normal") as cur:
            cur.execute("SELECT estoque FROM produtos WHERE id = ?", (produto_id,))
            linha = cur.fetchone()
            return linha[0] if linha else 0
