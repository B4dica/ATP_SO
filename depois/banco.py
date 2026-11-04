"""
Módulo: depois/banco.py
============================================================
VERSÃO "DEPOIS" - Camada de banco de dados (SQLite) com controle de concorrência

Este módulo implementa a camada de persistência usada exclusivamente pela
versão DEPOIS. Ele demonstra:

  * Transações seguras com BEGIN IMMEDIATE (exclusão mútua no banco).
  * SELECT ... FOR UPDATE (bloqueio de linha para leitura + escrita).
  * Pools isolados: uma conexão/pool para compras (escrita) e outra para
    relatórios (leitura), evitando que leituras pesadas bloqueiem vendas.
  * busy_timeout como "try_lock com tempo limite" (5 segundos).
  * Rollback automático em caso de exceção (context manager).
"""

import sqlite3
import threading
import os
from contextlib import contextmanager


class BancoDadosDepois:
    """
    Wrapper sobre SQLite que expõe transações controladas para a versão DEPOIS.

    Cada thread obtém sua própria conexão (thread-local). O arquivo SQLite é
    compartilhado, então todas as threads veem os mesmos dados.

    Parâmetros:
        caminho_db: caminho para o arquivo .db (None => arquivo ao lado deste módulo).
    """

    def __init__(self, caminho_db=None):
        if caminho_db is None:
            base = os.path.dirname(os.path.abspath(__file__))
            caminho_db = os.path.join(base, "ecommerce.db")
        self.caminho_db = caminho_db
        self._local = threading.local()
        self._inicializar_esquema()

    def _conexao(self):
        """Retorna a conexão SQLite da thread atual, criando se necessário."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            # timeout=30: tempo máximo de espera por lock do banco (segundos)
            # busy_timeout=5000: try_lock de 5s por operação (PRAGMA)
            conn = sqlite3.connect(self.caminho_db, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")  # 5 segundos de try_lock
            self._local.conn = conn
        return self._local.conn

    def _inicializar_esquema(self):
        conn = self._conexao()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS produtos (
                id TEXT PRIMARY KEY,
                nome TEXT,
                preco REAL,
                estoque INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                produto_id TEXT,
                quantidade INTEGER,
                status TEXT
            );
            CREATE TABLE IF NOT EXISTS pagamentos (
                pedido_id TEXT PRIMARY KEY,
                valor REAL,
                status TEXT
            );
            """
        )
        # Semente inicial (apenas se tabela vazia)
        conn.execute(
            "INSERT OR IGNORE INTO produtos (id, nome, preco, estoque) VALUES (?, ?, ?, ?)",
            ("PROD-001", "Produto A", 100.0, 5),
        )
        conn.execute(
            "INSERT OR IGNORE INTO produtos (id, nome, preco, estoque) VALUES (?, ?, ?, ?)",
            ("PROD-002", "Produto B", 50.0, 10),
        )
        conn.commit()

    @contextmanager
    def transacao(self, modo="immediato"):
        """
        Gerenciador de contexto para transações SQLite.

        modo='immediato' -> BEGIN IMMEDIATE: obtém lock de gravação imediatamente,
            serializando escritores. Se outra transação já tiver o lock, o SQLite
            espera até busy_timeout (5s) e, falhando, levanta OperationalError.
            Isso funciona como try_lock com timeout.

        modo='normal'    -> BEGIN DEFERRED: usado para leituras isoladas
            (relatórios), não bloqueando escritores desnecessariamente.

        Em exceção: faz ROLLBACK automático (libera locks parciais).
        Em sucesso:    -> COMMIT.
        """
        conn = self._conexao()
        if modo == "immediato":
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute("BEGIN")
        try:
            yield conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def executar(self, sql: str, parametros=()):
        conn = self._conexao()
        cur = conn.execute(sql, parametros)
        conn.commit()
        return cur
