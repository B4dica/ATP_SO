# ATP_SO - Sistema de E-commerce com Controle de Concorrência

Este projeto implementa, em **duas etapas**, um servidor de e-commerce e processamento concorrente sob alta carga:

1. **Versão "ANTES"** — sistema rudimentar com falhas clássicas de concorrência (race condition, deadlock por espera circular, inanição/starvation).
2. **Versão "DEPOIS"** — refatoração robusta aplicando conceitos de Sistemas Operacionais (atomicidade, ordem global de recursos, try_lock com timeout, rollback, pools isolados e envelhecimento/aging).

---

## Estrutura do Projeto

```
ATP_SO/
├── antes/                # Versão original com falhas de concorrência
│   ├── __init__.py
│   ├── estoque.py        # Race Condition / Check-Then-Act / Lost Update
│   ├── financeiro.py     # Deadlock por Espera Circular
│   ├── relatorio.py      # Starvation / Gargalo de I/O
│   ├── servidor.py       # Simulador dos 3 cenários
│   └── main.py           # Ponto de entrada
├── depois/               # Versão refatorada e segura
│   ├── __init__.py
│   ├── config.py         # Parâmetros de tuning (timeout, pools, ordem)
│   ├── estoque.py        # Atomicidade + exclusão mútua granular
│   ├── financeiro.py     # Ordem global + try_lock + timeout + rollback
│   ├── relatorio.py      # Pool isolado + aging (envelhecimento)
│   ├── servidor.py       # Simulador dos 3 cenários corrigidos
│   └── main.py           # Ponto de entrada
├── comum/                # Compartilhado por ambas as versões
│   ├── __init__.py
│   ├── modelos.py        # Entidades de domínio (Produto, Pedido, Pagamento)
│   └── banco_dados.py    # Wrapper SQLite com transações (BEGIN IMMEDIATE)
├── docs/
│   └── analise_tecnica.md# Fundamentação teórica (Tanenbaum & Silberschatz)
├── README.md
└── requirements.txt      # Apenas stdlib Python
```

---

## Como Executar

Requisitos: Python 3.x (não há dependências externas).

```bash
# Versão ANTES (com falhas)
python -m antes.main

# Versão DEPOIS (refatorada e segura)
python -m depois.main
```

Os scripts são autossuficientes: imprimem os resultados de cada cenário e um resumo comparativo final.

---

## O que cada versão demonstra

### Versão ANTES

| Cenário | Falha | Onde ocorre | Sintoma |
|---------|-------|-------------|---------|
| Race Condition | Check-Then-At não atômico | `antes/estoque.py::reservar()` | Overselling (vendas > estoque), estoque negativo |
| Deadlock | Espera circular | `antes/financeiro.py` (Processo A vs B) | Travamento permanente (liveness violada) |
| Starvation | Pool de conexões compartilhado | `antes/relatorio.py` | Relatórios de baixa prioridade não obtêm tempo de CPU/E/S |

### Versão DEPOIS

| Cenário | Solução | Onde ocorre |
|---------|---------|-------------|
| Race Condition | Lock granular por produto; região crítica mínima | `depois/estoque.py::reservar()` |
| Deadlock | Ordem global ESTOQUE→FINANCEIRO; try_lock com timeout de 5s; rollback | `depois/financeiro.py::executar_compra_segura()` |
| Starvation | Pool dedicado para relatórios; fila com aging (promoção de prioridade) | `depois/relatorio.py` |

---

## Documentação Técnica

Veja `docs/analise_tecnica.md` para a explicação fundamentada em autores clássicos (Tanenbaum e Silberschatz).

## Licença

Projeto acadêmico para disciplina de Sistemas Operacionais.
