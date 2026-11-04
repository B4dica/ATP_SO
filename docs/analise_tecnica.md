# Análise Técnica — Controle de Concorrência em Sistemas Operacionais

Este documento fundamenta, com base em autores clássicos de Sistemas Operacionais, as falhas da versão **"ANTES"** e as soluções aplicadas na versão **"DEPOIS"** do projeto ATP_SO.

> **Nota:** A versão ANTES é implementada puramente em memória (dicionários + `threading.Lock` ausente nas regiões críticas).  
> A versão DEPOIS utiliza **banco de dados SQLite real** com queries SQL para demonstrar atomicidade, prevenção de deadlock e isolamento de recursos.

---

## 1. Referências Teóricas

- **Abraham Silberschatz, Peter Baer Galvin, Greg Gagne** — *Operating System Concepts* ("Silberschatz"). Conceitos de seção crítica, exclusão mútua, condições de corrida, deadlock (condições necessárias, prevenção, detecção, recuperação), transações de banco de dados e escalonamento/inanição.
- **Andrew S. Tanenbaum** — *Modern Operating Systems* ("Tanenbaum"). Processos e threads, seções críticas, exclusão mútua por software/hardware, prevenção de deadlock por ordenação de recursos, envelhecimento (aging) e pools de recursos.

---

## 2. Versão "ANTES" — Falhas e Onde Ocorrem

### 2.1 Condição de Corrida (Race Condition) — Check-Then-Act / Lost Update

**Localização:** `antes/estoque.py`, método `reservar()`.

O método executa três etapas não atômicas em memória:
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

## 3. Versão "DEPOIS" — Soluções com Banco de Dados SQL

A versão DEPOIS reimplementa os mesmos cenários usando **SQLite real** com queries SQL, demonstrando que o controle de concorrência pode ser delegado ao gerenciador de transações do banco de dados.

### 3.1 Atomicidade e Exclusão Mútua via SQL

**Localização:** `depois/estoque.py`, método `reservar()`.

Em vez de ler e gravar separadamente em memória, a versão DEPOIS executa uma **única instrução SQL atômica** dentro de `BEGIN IMMEDIATE`:

```sql
BEGIN IMMEDIATE;
UPDATE produtos
   SET estoque = estoque - ?
 WHERE id = ?
   AND estoque >= ?;
-- se cursor.rowcount == 1: sucesso
-- se cursor.rowcount == 0: estoque insuficiente
COMMIT;
```

**Por que funciona:**
- `BEGIN IMMEDIATE` obtém um lock de gravação no banco imediatamente, serializando escritores.
- O `UPDATE` condicional verifica `estoque >= ?` e decrementa na mesma instrução, eliminando a janela de Check-Then-Act.
- Se duas threads concorrerem, o SQLite as serializa; apenas uma consegue fazer o `UPDATE` enquanto o estoque for suficiente.

**Referência:** Silberschatz et al. - Transações e isolamento; Tanenbaum - seções críticas mínimas.

---

### 3.2 Prevenção de Deadlock: Ordem Global, Try_lock com Timeout e Rollback

**Localização:** `depois/financeiro.py`, função `executar_compra_segura()`.

Uma compra completa ocorre dentro de **uma única transação** `BEGIN IMMEDIATE`, adquirindo recursos na ordem global obrigatória:

```sql
BEGIN IMMEDIATE;                                          -- try_lock (5s via busy_timeout)
UPDATE produtos SET estoque = estoque - ? ...;            -- 1. ESTOQUE
INSERT INTO pedidos  ...;                                 -- 2. PEDIDO
INSERT INTO pagamentos ...;                               -- 3. FINANCEIRO
COMMIT;                                                   -- libera todos
```

**Mecanismos de defesa:**
1. **Ordem global:** ESTOQUE → PEDIDO → FINANCEIRO. Todas as transações seguem a mesma sequência, então não há espera circular (grafo acíclico).
2. **try_lock com timeout:** `BEGIN IMMEDIATE` + `PRAGMA busy_timeout=5000`. Se outra transação de escrita estiver ativa, o SQLite aguarda até 5 segundos; se não conseguir, levanta `OperationalError`.
3. **Rollback automático:** qualquer exceção dentro do context manager dispara `ROLLBACK`, liberando locks parciais.

**Resultado observado:** zero deadlocks, zero travamentos permanentes, mesmo com 10 threads concorrentes.

**Referência:** Silberschatz et al. - prevenção de deadlock por ordenação de recursos; Tanenbaum - timeout e rollback como recuperação.

---

### 3.3 Isolamento de Recursos e Escalonamento Justo (Aging / Connection Pooling)

**Localização:** `depois/relatorio.py`, `GerenciadorRelatoriosDepois`.

1. **Pool de leitura isolado:** relatórios usam uma instância separada de `BancoDadosDepois` (mesmo arquivo `.db`, conexão dedicada). Com o modo WAL (*Write-Ahead Logging*) do SQLite, leituras concorrentes não bloqueiam escritas de compras.
2. **Transação de leitura (`BEGIN`, não `IMMEDIATE`):** relatórios não adquirem lock de escrita, portanto não competem com transações de compra.
3. **Envelhecimento (aging):** requisições de relatório de baixa prioridade que aguardam além do limite (3 rodadas) são promovidas automaticamente à fila de alta prioridade, evitando starvation.

**Resultado observado:** relatórios de baixa prioridade executam com tempo médio de espera próximo de zero, mesmo sob carga de compras.

**Referência:** Silberschatz et al. - envelhecimento contra starvation; Tanenbaum - particionamento de recursos.

---

## 4. Comparativo de Resultados

| Cenário | Versão ANTES (memória) | Versão DEPOIS (SQLite) |
|---------|------------------------|------------------------|
| Estoque 5 unidades, 20 threads | 20 vendas (overselling!), estoque inconsistente | 5 vendas (exato), estoque consistente (0) |
| Deadlock estoque↔financeiro | Travamento permanente (True) | Nenhum travamento (ordem global + BEGIN IMMEDIATE + timeout) |
| Relatórios sob carga de compras | Risco de inanição, pool compartilhado | Execução garantida (pool de leitura isolado + aging) |

---

## 5. Queries SQL-chave da Versão DEPOIS

| Propósito | Query |
|-----------|-------|
| Iniciar transação exclusiva (try_lock) | `BEGIN IMMEDIATE;` |
| Reserva atômica de estoque | `UPDATE produtos SET estoque = estoque - ? WHERE id = ? AND estoque >= ?;` |
| Registrar pedido | `INSERT INTO pedidos (id, produto_id, quantidade, status) VALUES (?, ?, ?, 'confirmado');` |
| Registrar pagamento | `INSERT INTO pagamentos (pedido_id, valor, status) VALUES (?, ?, 'aprovado');` |
| Confirmar e liberar locks | `COMMIT;` |
| Desfazer em falha | `ROLLBACK;` (automático pelo context manager) |
| Leitura isolada (relatório) | `BEGIN; SELECT ... FROM produtos; COMMIT;` |

---

## 6. Conclusão

A refatoração demonstra que os problemas de concorrência em sistemas operacionais são resolvidos por projeto: **atualização atômica via SQL**, **ordem disciplinada de recursos**, **try_lock com timeout (`BEGIN IMMEDIATE` + `busy_timeout`)**, **rollback automático** e **isolamento de pools com envelhecimento** transformam um sistema propenso a falhas em um sistema previsível e seguro sob alta carga.

---
*Projeto ATP_SO — Sistemas Operacionais | Fundamentação: Silberschatz et al., Tanenbaum.*
