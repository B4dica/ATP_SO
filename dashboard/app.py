"""
dashboard/app.py
============================================================
Dashboard Streamlit do ATP_SO: mostra, lado a lado, as três falhas de
concorrência da versão ANTES e como a versão DEPOIS as resolve.

Como rodar (a partir da raiz do projeto):
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import simulacao  # noqa: E402  (também adiciona a raiz do projeto ao sys.path)
from antes.estoque import EstoqueAntes  # noqa: E402
from antes.financeiro import executar_processo_a, executar_processo_b  # noqa: E402
from antes.relatorio import GerenciadorRelatoriosAntes  # noqa: E402
from depois.estoque import EstoqueDepois  # noqa: E402
from depois.financeiro import executar_compra_segura  # noqa: E402
from depois.relatorio import GerenciadorRelatoriosDepois  # noqa: E402

st.set_page_config(page_title="ATP_SO · Antes × Depois", page_icon="🧵", layout="wide")

# ----------------------------------------------------------------------
# Paleta (validada com o validador do skill dataviz, claro e escuro).
# ANTES = série 1 (azul), DEPOIS = série 2 (laranja). O vermelho "crítico"
# é reservado para estados de erro (deadlock/timeout), sempre com rótulo.
# ----------------------------------------------------------------------
PALETAS = {
    "light": dict(
        antes="#2a78d6", depois="#eb6834", texto="#0b0b0b", texto2="#52514e",
        mudo="#898781", grade="#e1e0d9", base="#c3c2b7", critico="#d03b3b",
        superficie="#fcfcfb",
    ),
    "dark": dict(
        antes="#3987e5", depois="#d95926", texto="#f0efec", texto2="#c3c2b7",
        mudo="#898781", grade="#2c2c2a", base="#383835", critico="#d03b3b",
        superficie="#1a1a19",
    ),
}


def _paleta() -> dict:
    try:
        modo = "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # versões antigas do Streamlit
        modo = "light"
    return PALETAS[modo]


P = _paleta()


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def _n(valor: float, casas: int = 1) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    return f"{valor:.{casas}f}".replace(".", ",")


def _badge(nome: str, cor: str) -> str:
    return (
        f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;'
        f'background:{cor};margin-right:8px;vertical-align:middle"></span>'
        f'<span style="font-size:1.15rem;font-weight:700;vertical-align:middle">{nome}</span>'
    )


def _fonte(obj) -> str:
    """Código-fonte real do objeto, sem a docstring (para caber no painel)."""
    src = textwrap.dedent(inspect.getsource(obj))
    try:
        func = ast.parse(src).body[0]
        primeiro = func.body[0]
        if (
            isinstance(primeiro, ast.Expr)
            and isinstance(primeiro.value, ast.Constant)
            and isinstance(primeiro.value.value, str)
        ):
            linhas = src.splitlines()
            del linhas[primeiro.lineno - 1 : primeiro.end_lineno]
            return "\n".join(linhas)
    except Exception:
        pass
    return src


def _painel_codigo(titulo, objs_antes, objs_depois, ideia_antes, ideia_depois):
    with st.expander(f"🔍 O que mudou no código · {titulo}"):
        c1, c2 = st.columns(2)
        for col, nome, cor, objs, ideia in (
            (c1, "ANTES", P["antes"], objs_antes, ideia_antes),
            (c2, "DEPOIS", P["depois"], objs_depois, ideia_depois),
        ):
            with col:
                st.markdown(_badge(nome, cor), unsafe_allow_html=True)
                st.markdown(ideia)
                st.code("\n\n".join(_fonte(o) for o in objs), language="python")


def _layout(fig, altura, titulo_y=None, titulo_x=None):
    fig.update_layout(
        height=altura,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=P["texto2"], size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=P["texto"])),
        hoverlabel=dict(font_size=13),
    )
    fig.update_xaxes(
        gridcolor=P["grade"], linecolor=P["base"], zerolinecolor=P["base"],
        title_text=titulo_x, title_font=dict(color=P["texto2"]), title_standoff=12,
        tickfont=dict(color=P["texto2"]), automargin=True,
    )
    fig.update_yaxes(
        gridcolor=P["grade"], linecolor=P["base"], zerolinecolor=P["base"],
        title_text=titulo_y, title_font=dict(color=P["texto2"]), title_standoff=12,
        tickfont=dict(color=P["texto2"]), automargin=True,
    )
    return fig


def _barras_agrupadas(categorias, valores_antes, valores_depois, titulo_y, fmt, altura=360):
    fig = go.Figure()
    for nome, cor, valores in (
        ("ANTES", P["antes"], valores_antes),
        ("DEPOIS", P["depois"], valores_depois),
    ):
        fig.add_trace(
            go.Bar(
                name=nome,
                x=categorias,
                y=valores,
                marker=dict(color=cor, line=dict(width=0)),
                text=[fmt(v) for v in valores],
                textposition="outside",
                textfont=dict(color=P["texto"]),
                cliponaxis=False,
                hovertemplate="%{x}<br><b>%{text}</b><extra>" + nome + "</extra>",
            )
        )
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    return _layout(fig, altura, titulo_y=titulo_y)


# Estados da linha do tempo: (nome na legenda, cor, hachura?)
def _estilo_estado(tipo: str, cor_versao: str):
    return {
        "executando": ("Executando", cor_versao, False),
        "sucesso": ("Compra confirmada", cor_versao, False),
        "esperando": ("Esperando", P["mudo"], True),
        "recusada": ("Recusada (sem estoque)", P["mudo"], False),
        "bloqueado": ("Bloqueado (deadlock)", P["critico"], False),
        "timeout": ("Timeout / rollback", P["critico"], False),
    }[tipo]


def _gantt(segmentos, cor_versao, unidade="s", rotulos=False, altura=None):
    """Linha do tempo: uma linha por thread/processo, uma barra por estado."""
    mult = 1000.0 if unidade == "ms" else 1.0
    linhas = list(dict.fromkeys(s["linha"] for s in segmentos))
    fig = go.Figure()
    ja_na_legenda = set()
    for s in segmentos:
        nome, cor, hachura = _estilo_estado(s["tipo"], cor_versao)
        dur = (s["fim"] - s["inicio"]) * mult
        marker = dict(color=cor, line=dict(width=0))
        if hachura:
            marker["pattern"] = dict(shape="/", fgcolor=P["superficie"], solidity=0.35)
        fig.add_trace(
            go.Bar(
                y=[s["linha"]],
                x=[dur],
                base=[s["inicio"] * mult],
                orientation="h",
                name=nome,
                legendgroup=nome,
                showlegend=nome not in ja_na_legenda,
                marker=marker,
                text=[s["detalhe"]] if rotulos else None,
                textposition="inside",
                insidetextanchor="start",
                textfont=dict(color="#ffffff"),
                customdata=[[s["detalhe"], f"{_n(dur, 2)} {unidade}"]],
                hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>duração: %{customdata[1]}<extra></extra>",
            )
        )
        ja_na_legenda.add(nome)
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_yaxes(autorange="reversed", categoryorder="array", categoryarray=linhas)
    altura = altura or min(520, 130 + 30 * len(linhas))
    return _layout(fig, altura, titulo_x=f"tempo desde o início do cenário ({unidade})")


def _dot_ciclo(ciclo: dict) -> str:
    """Grafo de alocação de recursos da versão ANTES (o ciclo é o deadlock)."""
    estilo_no = (
        f'fontname="Helvetica", fontsize=12, fontcolor="{P["texto"]}", color="{P["mudo"]}", '
        f'style="filled", fillcolor="{P["superficie"]}"'
    )
    linhas = [
        "digraph G {",
        "rankdir=LR; bgcolor=transparent; nodesep=0.6; ranksep=0.9;",
        f"node [{estilo_no}];",
        f'edge [fontname="Helvetica", fontsize=11, fontcolor="{P["texto"]}", color="{P["mudo"]}"];',
        'ESTOQUE [shape=box, label="ESTOQUE"];',
        'FINANCEIRO [shape=box, label="FINANCEIRO"];',
    ]
    for proc, info in ciclo.items():
        linhas.append(f'P{proc} [shape=ellipse, label="Processo {proc}"];')
        linhas.append(f'{info["segura"]} -> P{proc} [label=" segura"];')
        linhas.append(
            f'P{proc} -> {info["espera"]} [label=" aguarda", style=dashed, penwidth=2, color="{P["critico"]}"];'
        )
    linhas.append("}")
    return "\n".join(linhas)


def _dot_ordem() -> str:
    """Ordem global de recursos da versão DEPOIS."""
    estilo_no = (
        f'shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, '
        f'fontcolor="{P["texto"]}", color="{P["depois"]}", fillcolor="{P["superficie"]}"'
    )
    return "\n".join(
        [
            "digraph G {",
            "rankdir=LR; bgcolor=transparent; nodesep=0.4; ranksep=0.5;",
            f"node [{estilo_no}];",
            f'edge [color="{P["depois"]}", penwidth=2];',
            'T [label="Compra\\nBEGIN IMMEDIATE"];',
            'E [label="1 · ESTOQUE"];',
            'D [label="2 · PEDIDO"];',
            'F [label="3 · FINANCEIRO"];',
            'C [label="COMMIT\\n(libera tudo)"];',
            "T -> E -> D -> F -> C;",
            "}",
        ]
    )


# ----------------------------------------------------------------------
# Cabeçalho e controles
# ----------------------------------------------------------------------
st.markdown("# ATP_SO · Antes × Depois")
st.markdown(
    "Sistema de e-commerce sob alta carga: **as mesmas três falhas de concorrência**, "
    "primeiro como estavam e depois da refatoração com conceitos de Sistemas Operacionais. "
    "Os números abaixo são medidos agora, rodando o código real do projeto."
)

with st.expander("⚙️ Parâmetros da simulação"):
    pc1, pc2 = st.columns(2)
    n_threads = pc1.slider("Threads disputando o estoque (cenário 1)", 5, 50, 20)
    estoque_ini = pc1.slider("Estoque inicial do PROD-001 (cenário 1)", 1, 20, 5)
    n_compras = pc2.slider("Compras simultâneas no DEPOIS (cenário 2)", 2, 30, 10)
    estoque_compras = pc2.slider("Estoque do PROD-002 no cenário 2 do DEPOIS", 1, 30, 6)

if st.button("▶ Executar simulação", type="primary"):
    with st.spinner("Executando ANTES e DEPOIS… (o deadlock leva cerca de 6 s para ser confirmado)"):
        st.session_state["resultado"] = simulacao.executar_tudo(
            n_threads, estoque_ini, n_compras, estoque_compras
        )

R = st.session_state.get("resultado")
if R is None:
    st.info("Clique em **▶ Executar simulação** para rodar as duas versões e ver o comparativo.")
    st.stop()

par = R["parametros"]
A, D = R["antes"], R["depois"]
st.caption(
    f"Resultado gerado com {par['n_threads']} threads, estoque inicial {par['estoque_inicial']}, "
    f"{par['n_compras']} compras simultâneas (estoque {par['estoque_compras']}). "
    f"ANTES levou {_n(A['duracao_total'])} s; DEPOIS levou {_n(D['duracao_total'], 2)} s."
)

# ----------------------------------------------------------------------
# Resumo
# ----------------------------------------------------------------------
corrida_a, corrida_d = A["corrida"], D["corrida"]
dead_a = A["deadlock"]
comp_d = D["compras"]
star_a, star_d = A["starvation"], D["relatorios"]
espera_max_a = max(star_a["esperas"].values(), default=0.0) * 1000
espera_max_d = max(star_d["esperas"].values(), default=0.0) * 1000
n_travadas = sum(1 for s in dead_a["segmentos"] if s["tipo"] == "bloqueado")

veredito_corrida_a = (
    f"❌ Overselling: {corrida_a['vendas']} vendas com {corrida_a['estoque_inicial']} em estoque"
    if corrida_a["overselling"]
    else "✅ Sem overselling nesta execução"
)
veredito_corrida_d = (
    f"✅ {corrida_d['vendas']} vendas para {corrida_d['estoque_inicial']} em estoque, saldo {corrida_d['estoque_final']}"
    if corrida_d["consistente"]
    else f"❌ Inconsistente: {corrida_d['vendas']} vendas, saldo {corrida_d['estoque_final']}"
)
veredito_dead_a = (
    f"❌ Deadlock: {n_travadas} processos presos após {_n(dead_a['duracao'], 0)} s"
    if dead_a["travado"]
    else "✅ Sem deadlock nesta execução (o resultado pode variar)"
)
veredito_dead_d = (
    f"✅ {comp_d['sucesso'] + comp_d['falha_estoque']} compras concluídas, nenhuma travou"
    if comp_d["timeout"] == 0
    else f"⚠️ {comp_d['timeout']} compras com timeout (rollback)"
)
veredito_star_a = (
    f"⚠️ Espera máxima de {_n(espera_max_a, 0)} ms para começar"
    if espera_max_a > 50
    else f"✅ Espera máxima de {_n(espera_max_a, 1)} ms"
)
veredito_star_d = f"✅ Espera máxima de {_n(espera_max_d, 2)} ms para começar"

with st.container(border=True):
    h0, h1, h2 = st.columns([1.1, 1.4, 1.4])
    h0.markdown("**Cenário**")
    h1.markdown(_badge("ANTES", P["antes"]), unsafe_allow_html=True)
    h2.markdown(_badge("DEPOIS", P["depois"]), unsafe_allow_html=True)
    for nome, va, vd in (
        ("1 · Condição de corrida", veredito_corrida_a, veredito_corrida_d),
        ("2 · Deadlock", veredito_dead_a, veredito_dead_d),
        ("3 · Inanição (starvation)", veredito_star_a, veredito_star_d),
    ):
        c0, c1, c2 = st.columns([1.1, 1.4, 1.4])
        c0.markdown(f"**{nome}**")
        c1.markdown(va)
        c2.markdown(vd)

tab1, tab2, tab3 = st.tabs(
    ["1 · Condição de corrida", "2 · Deadlock", "3 · Inanição (starvation)"]
)

# ----------------------------------------------------------------------
# Cenário 1: condição de corrida
# ----------------------------------------------------------------------
with tab1:
    st.markdown(
        f"{par['n_threads']} threads tentam reservar 1 unidade cada, com "
        f"**{par['estoque_inicial']}** em estoque. No total só poderiam ser vendidas "
        f"**{corrida_a['vendas_esperadas']}**."
    )
    c1, c2 = st.columns(2)
    for col, nome, cor, r, veredito in (
        (c1, "ANTES", P["antes"], corrida_a, veredito_corrida_a),
        (c2, "DEPOIS", P["depois"], corrida_d, veredito_corrida_d),
    ):
        with col:
            st.markdown(_badge(nome, cor), unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Vendas registradas", r["vendas"])
            m2.metric("Estoque final registrado", r["estoque_final"])
            m3.metric(
                "Atualizações perdidas",
                r["atualizacoes_perdidas"],
                help="Escritas sobrescritas por outra thread: diferença entre o estoque registrado "
                "e (estoque inicial − vendas).",
            )
            st.markdown(veredito)

    categorias = ["Estoque inicial", "Vendas registradas", "Estoque final registrado", "Estoque que deveria ficar"]
    fig = _barras_agrupadas(
        categorias,
        [corrida_a["estoque_inicial"], corrida_a["vendas"], corrida_a["estoque_final"], corrida_a["estoque_teorico"]],
        [corrida_d["estoque_inicial"], corrida_d["vendas"], corrida_d["estoque_final"], corrida_d["estoque_teorico"]],
        titulo_y="unidades",
        fmt=lambda v: str(int(v)),
    )
    st.plotly_chart(fig, theme=None, key="g_corrida")
    st.caption(
        "No ANTES, o estoque registrado fica diferente de (inicial − vendas): várias threads leram o "
        "mesmo valor e uma sobrescreveu a escrita da outra (lost update). No DEPOIS os dois coincidem."
    )
    _painel_codigo(
        "condição de corrida",
        [EstoqueAntes.reservar],
        [EstoqueDepois.reservar],
        "**READ → CHECK → WRITE** sem exclusão mútua (check-then-act). Qualquer thread pode "
        "alterar o estoque entre a leitura e a escrita.",
        "**UPDATE … WHERE estoque >= ?** dentro de `BEGIN IMMEDIATE`: verificar e gravar viram "
        "uma única operação atômica.",
    )

# ----------------------------------------------------------------------
# Cenário 2: deadlock
# ----------------------------------------------------------------------
with tab2:
    st.markdown(
        "No ANTES, dois processos pegam os mesmos recursos em **ordem inversa**. "
        f"No DEPOIS, {par['n_compras']} compras simultâneas seguem uma **ordem global** única."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(_badge("ANTES", P["antes"]), unsafe_allow_html=True)
        m1, m2 = st.columns(2)
        m1.metric("Processos travados", f"{n_travadas} de {len(dead_a['segmentos'])}")
        m2.metric("Tempo observado", f"{_n(dead_a['duracao'])} s")
        st.markdown(veredito_dead_a)
        if dead_a["ciclo"]:
            st.graphviz_chart(_dot_ciclo(dead_a["ciclo"]))
            st.caption("Ciclo de espera: cada processo segura um recurso que o outro precisa.")
        st.plotly_chart(
            _gantt(dead_a["segmentos"], P["antes"], "s", rotulos=True, altura=230),
            theme=None,
            key="g_deadlock_antes",
        )
    with c2:
        st.markdown(_badge("DEPOIS", P["depois"]), unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Confirmadas", comp_d["sucesso"])
        m2.metric("Recusadas (sem estoque)", comp_d["falha_estoque"])
        m3.metric("Timeouts", comp_d["timeout"])
        integro = (
            comp_d["pedidos"] == comp_d["sucesso"]
            and comp_d["pagamentos"] == comp_d["sucesso"]
            and comp_d["estoque_final"] == par["estoque_compras"] - comp_d["sucesso"]
        )
        st.markdown(
            f"{veredito_dead_d}  \n"
            f"{'✅' if integro else '❌'} Pedidos gravados: {comp_d['pedidos']} · "
            f"pagamentos: {comp_d['pagamentos']} · estoque final: {comp_d['estoque_final']}"
        )
        st.graphviz_chart(_dot_ordem())
        st.caption("Todas as compras adquirem os recursos na mesma ordem: não há espera circular.")
        st.plotly_chart(
            _gantt(comp_d["segmentos"], P["depois"], "ms"),
            theme=None,
            key="g_compras_depois",
        )
    _painel_codigo(
        "deadlock",
        [executar_processo_a, executar_processo_b],
        [executar_compra_segura],
        "Processo A pega **ESTOQUE → FINANCEIRO** e o B pega **FINANCEIRO → ESTOQUE**, com "
        "`acquire()` sem timeout: espera circular permanente.",
        "Ordem global **ESTOQUE → PEDIDO → FINANCEIRO** numa única transação `BEGIN IMMEDIATE`, "
        "com timeout de 5 s e ROLLBACK automático.",
    )

# ----------------------------------------------------------------------
# Cenário 3: inanição
# ----------------------------------------------------------------------
with tab3:
    st.markdown(
        "5 relatórios de baixa prioridade pedem acesso aos dados. Aqui medimos **quanto cada um "
        "espera até começar a executar**."
    )
    c1, c2 = st.columns(2)
    for col, nome, cor, r, veredito in (
        (c1, "ANTES", P["antes"], star_a, veredito_star_a),
        (c2, "DEPOIS", P["depois"], star_d, veredito_star_d),
    ):
        with col:
            st.markdown(_badge(nome, cor), unsafe_allow_html=True)
            m1, m2 = st.columns(2)
            m1.metric("Espera média", f"{_n(r['media_espera'] * 1000, 2)} ms")
            m2.metric("Espera máxima", f"{_n(max(r['esperas'].values(), default=0) * 1000, 2)} ms")
            st.markdown(veredito)

    nomes = sorted(star_a["esperas"])
    fig = _barras_agrupadas(
        nomes,
        [star_a["esperas"][n] * 1000 for n in nomes],
        [star_d["esperas"].get(n, 0.0) * 1000 for n in nomes],
        titulo_y="espera até começar (ms)",
        fmt=lambda v: _n(v, 1),
    )
    st.plotly_chart(fig, theme=None, key="g_relatorios")
    st.caption(
        "No ANTES os relatórios dividem um pool único de 3 conexões, sem prioridade nem aging, e os "
        "últimos ficam na fila. No DEPOIS usam um pool de leitura isolado (WAL) com fila justa. "
        "No DEPOIS a espera é medida desde a chamada até a leitura começar: o "
        "`media_tempo_espera()` original só mede a leitura em si."
    )
    with st.expander("📈 Linha do tempo dos relatórios"):
        t1, t2 = st.columns(2)
        with t1:
            st.markdown(_badge("ANTES", P["antes"]), unsafe_allow_html=True)
            st.plotly_chart(_gantt(star_a["segmentos"], P["antes"], "s"), theme=None, key="g_rel_antes")
        with t2:
            st.markdown(_badge("DEPOIS", P["depois"]), unsafe_allow_html=True)
            st.plotly_chart(_gantt(star_d["segmentos"], P["depois"], "ms"), theme=None, key="g_rel_depois")
    _painel_codigo(
        "inanição",
        [GerenciadorRelatoriosAntes.executar_relatorio],
        [GerenciadorRelatoriosDepois.executar_relatorio],
        "Um **semáforo único** de conexões compartilhado, sem prioridade nem envelhecimento.",
        "**Pool de leitura isolado** (SQLite em WAL) e fila com **aging**: quem espera muito é promovido.",
    )

with st.expander("🖥️ Saída original dos scripts (log do terminal)"):
    l1, l2 = st.columns(2)
    l1.markdown(_badge("ANTES", P["antes"]), unsafe_allow_html=True)
    l1.code(A["log"], language=None)
    l2.markdown(_badge("DEPOIS", P["depois"]), unsafe_allow_html=True)
    l2.code(D["log"], language=None)
