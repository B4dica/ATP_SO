"""
Módulo: comum/banco_dados.py
Wrapper simples sobre SQLite para simular transações de banco de dados.

Objetivo pedagógico: mostrar como transações (BEGIN IMMEDIATE / COMMIT /
ROLLBACK) substituem a exclusão mútua manual em região crítica de memória.

Nota: SQLite em modo WAL ou com transações imediatas oferece isolamento
suficiente para este exercício de Sistemas Operacionais.
"""

import sqlite3
import threading
from typing import Optional


class BancoDados:
    """
    Conexão SQLite thread-safe (check_same_thread=False) com controle de
    transações explícitas.

    Cada thread deve usar suas próprias transações; o SQLite bloqueia o
    banco de gravação durante BEGIN IMMEDIATE, serializando escritores.
    """

    def __init__(self, caminho: str = ":memory:"):
        self.caminho = caminho
        self._local = threading.local()

    def _conexao(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.caminho, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
            self._criar_tabelas(conn)
        return self._local.conn

    def _criar_tabelas(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS produtos (
                id TEXT PRIMARY KEY,
                nome TEXT,
                preco REAL,
                estoque INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                produto_id TEXT,
                quantidade INTEGER,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pagamentos (
                pedido_id TEXT PRIMARY KEY,
                valor REAL,
                status TEXT
            )
            """
        )
        conn.commit()

    def executar(self, sql: str, parametros: tuple = ()):
        conn = self._conexao()
        cur = conn.execute(sql, parametros)
        conn.commit()
        return cur

    def transacao(self):
        """
        Retorna um gerenciador de contexto que abre BEGIN IMMEDIATE e faz
        COMMIT no sucesso ou ROLLBACK na exceção.

        Uso:
            with bd.transacao() as cur:
                cur.execute("SELECT estoque FROM produtos WHERE id=?", (pid,))
                ...
        """
        return _Transacao(self)


class _Transacao:
    def __init__(self, bd: BancoDados):
        self.bd = bd
        self.cur: Optional[sqlite3.Cursor] = None

    def __enter__(self):
        conn = self.bd._conexao()
        # BEGIN IMMEDIATE: obtém lock de escrita imediatamente, serializando
        # escritores e evitando deadlocks de atualização perdida no SQLite.
        conn.execute("BEGIN IMMEDIATE")
        self.cur = conn.cursor()
        return self.cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        conn = self.bd._conexao()
        if exc_type is not None:
            conn.rollback()
        else:
            conn.commit()
        self.cur = None
        return False
