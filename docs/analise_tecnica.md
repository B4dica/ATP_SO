# Análise Técnica — Controle de Concorrência em Sistemas Operacionais

Este documento fundamenta, com base em autores clássicos de Sistemas Operacionais, as falhas da versão **"ANTES"** e as soluções aplicadas na versão **"DEPOIS"** do projeto ATP_SO.

---

## 1. Referências Teóricas

- **Abraham Silberschatz, Peter Baer Galvin, Greg Gagne** — *Operating System Concepts* ("Silberschatz"). Conceitos de seção crítica, exclusão mútua, condições de corrida, deadlock (condições necessárias, prevenção, detecção, recuperação) e escalonamento/inanição.
- **Andrew S. Tanenbaum** — *Modern Operating Systems* ("Tanenbaum"). Processos e threads, seções críticas, exclusão mútua por software/hardware, locks granulares, prevenção de deadlock por ordenação de recursos, envelhecimento (aging) e pools de recursos.

---

## 2. Versão "ANTES" — Falhas e Onde Ocorrem

### 2.1 Condição de Corrida (Race Condition) — Check-Then-Act / Lost Update

**Localização:** `antes/estoque.py`, método `reservar()`.

O método executa três etapas não atômicas:
1. **READ** — lê a quantidade atual do produto.
2. **CHECK** — verifica se `estoque >= quantidade solicitada`.
3. **ACT/WRITE** — grava `estoque - quantidade` com base na leitura anterior.

Entre o passo 1 e o passo 3 não há qualquer exclusão mútua. Duas (ou mais) threads podem ler o mesmo valor de estoque, todas passarem na verificação e gravarem um resultado baseado em leitura obsoleta (*stale read*).

**Consequências observadas na simulação:**
- **Overselling:** com estoque inicial de 5 unidades, 20 threads concorrentes registraram 20 vendas.
- **Estoque negativo:** possível quando a janela de vulnerabilidade permite decremento abaixo de zero.
- **Lost Update:** a gravação de uma thread sobrescreve a de outra, fazendo reservas desaparecerem silenciosamente.

**Fundamentação:** Silberschatz define *condição de corrida* como o cenário onde múltiplos processos acessam e manipulam dados concorrentemente, e o resultado final depende da ordem relativa da execução. Tanenbaum destaca que a seção crítica deve ser protegida para que apenas um processo por vez esteja nela.

---

### 2.2 Deadlock por Espera Circular (Circular Wait)

**Localização:** `antes/financeiro.py`, processos `executar_processo_a` e `executar_processo_b`.

Dois recursos são disputados: **ESTOQUE** e **FINANCEIRO**.
- Processo A: trava ESTOQUE, depois tenta travar FINANCEIRO.
- Processo B: trava FINANCEIRO, depois tenta travar ESTOQUE.

Quando A segura ESTOQUE e aguarda FINANCEIRO, enquanto B segura FINANCEIRO e aguarda ESTOQUE, surge um **ciclo de espera**. Nenhum dos dois avança -> travamento permanente.

**Condições necessárias para deadlock (Silberschatz):** todas as quatro estão presentes:
1. Exclusão mútua (recursos não compartilháveis).
2. Espera parcial (processo segurando um recurso aguarda por outro).
3. Não-preempção (recursos não podem ser tirados à força).
4. **Espera circular** (ciclo de processos aguardando recursos).

**Consequência observada:** as threads travam permanentemente (liveness violada). O sistema não prograda e o processo só termina por intervenção externa.

**Fundamentação:** Tanenbaum ensina que a espera circular pode ser eliminada impondo uma ordem total sobre a aquisição de recursos, de modo que o grafo de dependências seja sempre acíclico.

---

### 2.3 Inanição (Starvation) e Gargalo de I/O

**Localização:** `antes/relatorio.py`, `GerenciadorRelatoriosAntes`.

Relatórios de baixa prioridade e transações de compra disputam o **mesmo semáforo de conexões** (pool único com 3 conexões). Como compras são curtas e frequentes, elas consomem as conexões repetidamente. Relatórios de baixa prioridade enfrentam espera ilimitada — podem nunca obter uma fatia de tempo adequada.

**Consequência:** inanição de processos de baixa prioridade e gargalo de I/O, já que o mesmo recurso é usado por classes de trabalho com requisitos diferentes.

**Fundamentação:** Silberschatz define *starvation* como a situação em que um processo aguarda indefinidamente por um recurso. Tanenbaum propõe o *envelhecimento* (aging) — aumentar gradualmente a prioridade de processos que aguardam muito tempo — como defesa contra inanição.

---

## 3. Versão "DEPOIS" — Soluções Aplicadas

### 3.1 Atomicidade e Exclusão Mútua Granular

**Localização:** `depois/estoque.py`.

Cada produto tem seu próprio `threading.Lock` (*lock granular*). A operação `reservar()` adquire o lock **antes** da leitura e o libera **após** a gravação. Dessa forma:
- Leitura e gravação ocorrem dentro da mesma região crítica — a operação é **atômica**.
- A região crítica é o menor possível (apenas o produto alvo), minimizando contenção e maximizando throughput sob alta carga.

**Proteção:** elimina a janela de vulnerabilidade do Check-Then-Act. Não há overselling nem estoque negativo.

**Fundamentação:** Tanenbaum recomenda que a seção crítica seja o menor possível. Locks granulares permitem concorrência real (operações em produtos distintos não se bloqueiam mutuamente), ao contrário de um lock global único que serializaria tudo.

---

### 3.2 Prevenção de Deadlock: Ordem Global, Try_lock com Timeout e Rollback

**Localização:** `depois/financeiro.py`, função `executar_compra_segura()`.

Três mecanismos atuam em conjunto:

1. **Ordem global de aquisição:** toda transação que precise de mais de um recurso deve adquiri-los na sequência fixa `ESTOQUE → FINANCEIRO → PEDIDO` (definida em `depois/config.py`). Como todos os processos seguem a mesma ordem, não há espera circular -> o grafo de dependências é acíclico.

2. **try_lock com timeout:** em vez de `acquire()` bloqueante (espera ilimitada), usa-se `acquire(timeout=5.0)`. Se o segundo recurso não estiver disponível em 5 segundos, a tentativa falha.

3. **Rollback automático:** se o lock de FINANCEIRO não for obtido, o lock de ESTOQUE já adquirido é liberado antes de abortar a transação (`finally`). Nenhum recurso fica parcialmente bloqueado.

**Por que não há deadlock:** a ordem total elimina a espera circular; o timeout impede bloqueio indefinido; o rollback garante liberação de recursos parciais.

**Fundamentação:** Silberschatz apresenta a ordenação de recursos como método de prevenção de deadlock. Tanenbaum discute timeouts e rollback como mecanismos de recuperação quando a prevenção falha.

---

### 3.3 Isolamento de Recursos e Escalonamento Justo (Aging / Connection Pooling)

**Localização:** `depois/relatorio.py` e `depois/config.py`.

1. **Pools de conexões isolados:** transações de compra usam `POOL_COMPRAS` (10 conexões) e relatórios usam `POOL_RELATORIOS` (5 conexões). As duas classes de trabalho não competem pelas mesmas conexões.

2. **Envelhecimento (aging):** a fila de relatórios promove automaticamente requisitos de baixa prioridade para alta prioridade após aguardar `LIMITE_AGING` rodadas (configurável, padrão 3). Isso garante que nenhum relatório fique esperando indefinidamente.

3. **Escalonamento justo:** FIFO dentro de cada nível de prioridade; a fila alta é atendida antes da baixa, mas o aging impede que a baixa seja esquecida.

**Consequência observada:** relatórios de baixa prioridade executam mesmo sob carga de compras; tempo médio de espera mantido baixo.

**Fundamentação:** Silberschatz recomenda envelhecimento para evitar starvation em escalonamento por prioridade. Tanenbaum defende o particionamento de recursos para isolar classes de trabalho com requisitos distintos.

---

## 4. Comparativo de Resultados

| Cenário | Versão ANTES | Versão DEPOIS |
|---------|-------------|---------------|
| Estoque com 5 unidades, 20 threads | 20 vendas (overselling!), estoque inconsistente | 5 vendas (exato), estoque consistente |
| Deadlock estoque↔financeiro | Travamento permanente (True) | Nenhum travamento (ordem global + timeout) |
| Relatórios sob carga de compras | Risco de inanição, pool compartilhado | Execução garantida (pool isolado + aging) |

---

## 5. Conclusão

A refatoração demonstra que os problemas de concorrência em sistemas operacionais não são resolvidos por acaso, mas por projeto: **exclusão mútua adequada**, **ordem disciplinada de recursos**, **timeouts com rollback** e **isolamento de pools com escalonamento justo** transformam um sistema propenso a falhas em um sistema previsível e seguro sob alta carga.

---
*Projeto ATP_SO — Sistemas Operacionais | Fundamentação: Silberschatz et al., Tanenbaum.*
