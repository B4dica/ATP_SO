"""
dashboard/simulacao.py
============================================================
Executa as simulações do ATP_SO (versões ANTES e DEPOIS) e devolve dados
estruturados para o dashboard Streamlit.

Princípios:
  * Os módulos originais (antes/, depois/, comum/) NÃO são alterados.
  * Usa os próprios simuladores (ServidorAntes / ServidorDepois) e apenas
    "espia" a execução com monkeypatch temporário para medir tempos e eventos.
  * O DEPOIS roda em um banco SQLite temporário com estoque conhecido, sem
    tocar em depois/ecommerce.db (que já está com estoque 0 no repositório).

Formato dos segmentos de linha do tempo (usados nos gráficos de Gantt):
    {"linha": str, "inicio": float, "fim": float, "tipo": str, "detalhe": str}
    tipo: "executando" | "esperando" | "bloqueado" | "sucesso" | "recusada" | "timeout"
    inicio/fim em segundos desde o começo do cenário.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from antes import financeiro as _fin_antes  # noqa: E402
from antes.servidor import ServidorAntes  # noqa: E402
from depois import servidor as _srv_depois  # noqa: E402
from depois.banco import BancoDadosDepois  # noqa: E402
from depois.estoque import EstoqueDepois  # noqa: E402
from depois.relatorio import GerenciadorRelatoriosDepois  # noqa: E402
from depois.servidor import ServidorDepois  # noqa: E402

# Os patches e o redirecionamento de stdout são globais ao processo; o Streamlit
# atende várias sessões, então serializamos as execuções.
_LOCK_EXECUCAO = threading.Lock()

_RECURSO_OPOSTO = {"ESTOQUE": "FINANCEIRO", "FINANCEIRO": "ESTOQUE"}


def _seg(linha, inicio, fim, tipo, detalhe=""):
    return {"linha": linha, "inicio": inicio, "fim": fim, "tipo": tipo, "detalhe": detalhe}


def _derivar_corrida(r: dict) -> dict:
    """Acrescenta métricas de consistência ao resultado do cenário 1."""
    r = dict(r)
    teorico = r["estoque_inicial"] - r["vendas"]
    r["estoque_teorico"] = teorico
    r["atualizacoes_perdidas"] = max(0, r["estoque_final"] - teorico)
    r["overselling"] = r["vendas"] > r["vendas_esperadas"]
    r["estoque_negativo"] = r["estoque_final"] < 0
    r["consistente"] = (
        not r["overselling"]
        and r["estoque_final"] >= 0
        and r["estoque_final"] == teorico
    )
    return r


# ----------------------------------------------------------------------
# ANTES
# ----------------------------------------------------------------------
def _medir_deadlock_antes(srv: ServidorAntes) -> dict:
    eventos: list[tuple[float, str]] = []
    t0 = time.perf_counter()

    def _print_registrado(*args, **kwargs):
        eventos.append((time.perf_counter() - t0, " ".join(str(a) for a in args)))
        print(*args, **kwargs)

    # antes/financeiro.py chama print() ao adquirir cada lock; interceptamos
    # só esse módulo para saber QUANDO cada processo obteve cada recurso.
    with mock.patch.object(_fin_antes, "print", _print_registrado, create=True):
        travado = srv.simular_deadlock()
    duracao = time.perf_counter() - t0

    padrao = re.compile(r"\[Processo ([AB])\] Bloqueou (\w+)")
    adquiridos: dict[str, list[tuple[float, str]]] = {"A": [], "B": []}
    for t, texto in eventos:
        m = padrao.search(texto)
        if m:
            adquiridos[m.group(1)].append((t, m.group(2)))

    segmentos = []
    ciclo = {}
    for proc in ("A", "B"):
        lista = adquiridos[proc]
        if not lista:
            continue
        t1, r1 = lista[0]
        r2 = _RECURSO_OPOSTO[r1]
        linha = f"Processo {proc}"
        ciclo[proc] = {"segura": r1, "espera": r2}
        if len(lista) > 1:  # conseguiu o segundo recurso: não travou
            t2 = lista[1][0]
            segmentos.append(_seg(linha, t1, t2, "esperando", f"segura {r1}, aguarda {r2}"))
            segmentos.append(_seg(linha, t2, min(duracao, t2 + 0.02), "executando", f"segura {r1} e {r2}"))
        else:
            segmentos.append(
                _seg(linha, t1, duracao, "bloqueado", f"segura {r1} e aguarda {r2} para sempre")
            )
    return {
        "travado": bool(travado),
        "duracao": duracao,
        "segmentos": segmentos,
        "ciclo": ciclo,
    }


def _medir_starvation_antes(srv: ServidorAntes) -> dict:
    registros: list[tuple[str, float, float, float | None]] = []
    original = srv.relatorios.executar_relatorio
    t0 = time.perf_counter()

    def medido(nome, prioridade="baixa"):
        ini = time.perf_counter() - t0
        espera = original(nome, prioridade=prioridade)
        fim = time.perf_counter() - t0
        registros.append((nome, ini, fim, espera))
        return espera

    srv.relatorios.executar_relatorio = medido
    media_reportada = srv.simular_starvation()

    segmentos, esperas = [], {}
    for nome, ini, fim, espera in sorted(registros):
        if espera is None:  # timeout do semáforo
            esperas[nome] = fim - ini
            segmentos.append(_seg(f"Relatório {nome}", ini, fim, "timeout", "não obteve conexão"))
            continue
        esperas[nome] = espera
        segmentos.append(_seg(f"Relatório {nome}", ini, ini + espera, "esperando", "aguardando conexão do pool"))
        segmentos.append(_seg(f"Relatório {nome}", ini + espera, fim, "executando", "lendo dados"))
    media = sum(esperas.values()) / len(esperas) if esperas else 0.0
    return {
        "media_espera": media,
        "media_reportada": media_reportada,
        "esperas": esperas,
        "segmentos": segmentos,
    }


def executar_antes(n_threads: int = 20, estoque_inicial: int = 5) -> dict:
    """Roda os 3 cenários da versão ANTES e devolve métricas + linhas do tempo."""
    with _LOCK_EXECUCAO:
        t_inicio = time.perf_counter()
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            srv = ServidorAntes()
            srv.estoque.produtos["PROD-001"] = estoque_inicial
            corrida = _derivar_corrida(srv.simular_corrida_estoque("PROD-001", n_threads))
            deadlock = _medir_deadlock_antes(srv)
            starvation = _medir_starvation_antes(srv)
        return {
            "corrida": corrida,
            "deadlock": deadlock,
            "starvation": starvation,
            "log": saida.getvalue(),
            "duracao_total": time.perf_counter() - t_inicio,
        }


# ----------------------------------------------------------------------
# DEPOIS
# ----------------------------------------------------------------------
def _medir_compras_depois(srv: ServidorDepois, n_compras: int) -> dict:
    registros: list[tuple[float, float, dict]] = []
    original = _srv_depois.executar_compra_segura
    t0 = time.perf_counter()

    def medido(bd, produto_id, quantidade, preco, timeout_s=5.0):
        ini = time.perf_counter() - t0
        res = original(bd, produto_id, quantidade, preco, timeout_s=timeout_s)
        registros.append((ini, time.perf_counter() - t0, res))
        return res

    with mock.patch.object(_srv_depois, "executar_compra_segura", medido):
        resultados = srv.simular_compra_segura("PROD-002", 1, 50.0, n_compras)
    duracao = time.perf_counter() - t0

    segmentos = []
    for i, (ini, fim, res) in enumerate(sorted(registros, key=lambda x: x[0]), start=1):
        if res["sucesso"]:
            tipo, detalhe = "sucesso", "compra confirmada (COMMIT)"
        elif "Estoque insuficiente" in res["mensagem"]:
            tipo, detalhe = "recusada", "estoque insuficiente (sem overselling)"
        else:
            tipo, detalhe = "timeout", "timeout/lock indisponível (ROLLBACK)"
        segmentos.append(_seg(f"Compra {i:02d}", ini, fim, tipo, detalhe))

    # Integridade: cada compra confirmada deve ter 1 pedido e 1 pagamento.
    bd = srv.bd_compras
    pedidos = bd.executar(
        "SELECT COUNT(*) FROM pedidos WHERE id NOT LIKE 'PED-TEST-%'"
    ).fetchone()[0]
    pagamentos = bd.executar(
        "SELECT COUNT(*) FROM pagamentos WHERE pedido_id NOT LIKE 'PED-TEST-%'"
    ).fetchone()[0]
    return {
        **resultados,
        "n_compras": n_compras,
        "estoque_final": srv.estoque.quantidade("PROD-002"),
        "pedidos": pedidos,
        "pagamentos": pagamentos,
        "duracao": duracao,
        "segmentos": segmentos,
    }


def _medir_relatorios_depois(srv: ServidorDepois) -> dict:
    registros: list[tuple[str, float, float, float | None]] = []
    original = srv.relatorios.executar_relatorio
    t0 = time.perf_counter()

    def medido(nome, prioridade="baixa"):
        ini = time.perf_counter() - t0
        leitura = original(nome, prioridade=prioridade)
        registros.append((nome, ini, time.perf_counter() - t0, leitura))
        return leitura

    srv.relatorios.executar_relatorio = medido
    media_reportada = srv.simular_relatorios()

    segmentos, esperas = [], {}
    for nome, ini, fim, leitura in sorted(registros):
        leitura = leitura or 0.0
        # executar_relatorio() só mede a leitura (depois da fila). A espera real
        # até começar é o tempo total da chamada menos essa leitura.
        fila = max(0.0, (fim - ini) - leitura)
        esperas[nome] = fila
        segmentos.append(_seg(f"Relatório {nome}", ini, ini + fila, "esperando", "fila justa com aging"))
        segmentos.append(_seg(f"Relatório {nome}", ini + fila, fim, "executando", "leitura no pool isolado"))
    media = sum(esperas.values()) / len(esperas) if esperas else 0.0
    return {
        "media_espera": media,
        "media_reportada": media_reportada,
        "esperas": esperas,
        "segmentos": segmentos,
    }


def executar_depois(
    n_threads: int = 20,
    estoque_inicial: int = 5,
    n_compras: int = 10,
    estoque_compras: int = 6,
) -> dict:
    """Roda os 3 cenários da versão DEPOIS num banco SQLite temporário."""
    with _LOCK_EXECUCAO, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t_inicio = time.perf_counter()
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            bd_compras = BancoDadosDepois(caminho_db=os.path.join(tmp, "demo.db"))
            bd_relatorios = BancoDadosDepois(caminho_db=bd_compras.caminho_db)
            bd_compras.executar(
                "UPDATE produtos SET estoque = ? WHERE id = 'PROD-001'", (estoque_inicial,)
            )
            bd_compras.executar(
                "UPDATE produtos SET estoque = ? WHERE id = 'PROD-002'", (estoque_compras,)
            )

            # Mesma montagem de ServidorDepois.__init__, mas apontando para o
            # banco temporário (o __init__ original sempre usa depois/ecommerce.db).
            srv = ServidorDepois.__new__(ServidorDepois)
            srv.bd_compras = bd_compras
            srv.bd_relatorios = bd_relatorios
            srv.estoque = EstoqueDepois(bd_compras)
            srv.relatorios = GerenciadorRelatoriosDepois(bd_relatorios)

            corrida = _derivar_corrida(srv.simular_corrida_estoque("PROD-001", n_threads))
            compras = _medir_compras_depois(srv, n_compras)
            relatorios = _medir_relatorios_depois(srv)
        return {
            "corrida": corrida,
            "compras": compras,
            "relatorios": relatorios,
            "log": saida.getvalue(),
            "duracao_total": time.perf_counter() - t_inicio,
        }


def executar_tudo(
    n_threads: int = 20,
    estoque_inicial: int = 5,
    n_compras: int = 10,
    estoque_compras: int = 6,
) -> dict:
    return {
        "parametros": {
            "n_threads": n_threads,
            "estoque_inicial": estoque_inicial,
            "n_compras": n_compras,
            "estoque_compras": estoque_compras,
        },
        "antes": executar_antes(n_threads, estoque_inicial),
        "depois": executar_depois(n_threads, estoque_inicial, n_compras, estoque_compras),
    }


if __name__ == "__main__":  # teste rápido pelo terminal: python dashboard/simulacao.py
    import json

    resultado = executar_tudo()
    for versao in ("antes", "depois"):
        resultado[versao].pop("log", None)
        for bloco in resultado[versao].values():
            if isinstance(bloco, dict):
                bloco.pop("segmentos", None)
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
