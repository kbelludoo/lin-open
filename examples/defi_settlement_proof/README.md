# Demonstração Prática: Motor de Liquidação AMM com Bytecode LINBC1 e Árvore de Compromissos Merkle

Este experimento demonstra de forma reprodutível, transparente e com delimitação técnica estrita (conforme regra de higiene epistêmica R5) a execução de um motor de liquidação financeira off-chain compilado para bytecode LINBC1.

---

## 1. Escopo e Propriedades Rigorosamente Comprovadas

A auditoria independente confirmou as seguintes propriedades empíricas no commit `48bcc8b`:

1. **Pureza e Compilação Canônica LINBC1:**
   - O módulo [`settlement_engine.lin`](settlement_engine.lin) atinge elegibilidade de 4/4 funções no C0 (`coverage total=4 eligible=4 rejected=0`).
   - A divisão inteira necessária para a curva AMM $x \cdot y = k$ foi implementada em LIN puro via shifts e subtrações binárias $O(\log N)$, eliminando qualquer rejeição de pureza (`VM_REJ_INT_DIVISION`).
   - A compilação em checkout limpo é byte a byte idêntica, produzindo uma imagem de 3.098 bytes com os seguintes digests documentados:
     - **Hash SHA-256 do arquivo `.linbc` em disco:** `a5095750c28526c056f9e06163752109b4e1f1faf9537cc74bf0084037f91227`
     - **Digest interno de auto-integridade do loader (domínio `linbc1:img:`):** `d41fbfe856155828301e0d91248980b25e9b6cf2f9390676f510b46761e55a6f`

2. **Execução Direta do Bytecode via Loader C11:**
   - A execução dos 200 swaps do benchmark ocorre exclusivamente através do executável `lin_bc1_run` (sem utilizar interpretadores de código-fonte solto).
   - O consenso roundtrip (`lin_c0 roundtrip`) entre o código-fonte e o bytecode é confirmado (`CONSENSUS`).

3. **Árvore de Compromissos Merkle (4 Folhas por Bloco):**
   - Implementação de árvore binária de 2 níveis para blocos de 4 transações com caminhos de inclusão compostos por nós irmãos e bits de direção.
   - O benchmark verificou com sucesso 200/200 caminhos de prova de inclusão.
   - Foram testadas 50 mutações de 1 unidade no valor de liquidação: 50/50 foram detectadas e rejeitadas pela verificação da raiz Merkle.

4. **Perfil de Memória no Host C11:**
   - O host de demonstração [`main_settlement_host.c`](main_settlement_host.c) carrega a imagem em buffer fixo e inicializa o loader em estruturas pré-alocadas na stack.
   - A inspeção de símbolos dinâmicos via `nm -u` confirma a ausência de chamadas diretas a `malloc`, `calloc`, `realloc` e `free`.

---

## 2. Limitações Técnicas e Ressalvas Explícitas (R5)

Para total honestidade e conformidade epistêmica:

- **Primitiva de Hashing da Árvore:** A função `!hash_pair` no módulo LIN opera em inteiros truncados a 32 bits usando rotações e constantes inteiras. Trata-se de uma **árvore de compromissos de 32 bits**, e **não** de uma árvore Merkle SHA-256 criptograficamente forte resistente a ataques de colisão em larga escala.
- **Detecção de Adulteração:** A detecção foi de 100% sobre as **50 instâncias avaliadas no teste**. Isso comprova a sensibilidade aos casos testados, mas não constitui prova formal de colisão zero para qualquer entrada arbitrária no espaço de 32 bits.
- **Complexidade de Auditoria:** A verificação de um caminho em uma árvore de 4 folhas é $O(\log 4) = O(1)$, mas a verificação de um lote inteiro de $N$ recibos tem custo total linear $O(N)$.
- **Garantias de Memória:** A ausência de imports diretos de alocadores heap no binário demonstra que o código principal não faz uso de alocação dinâmica direta; não substitui uma prova formal de ausência total de falhas de memória em todos os ramos possíveis do host.

---

## 3. Como Reproduzir

### Passo 1: Verificar pureza do código LIN
```bash
./transpile/c/bin/lin_c0 info examples/defi_settlement_proof/settlement_engine.lin
```

### Passo 2: Emitir a imagem binária congelada
```bash
./transpile/c/bin/lin_c0 image examples/defi_settlement_proof/settlement_engine.lin -o examples/defi_settlement_proof/settlement_engine.linbc
```

### Passo 3: Executar o benchmark com a imagem LINBC1
```bash
python3 examples/defi_settlement_proof/benchmark_settlement_proof.py
```

### Passo 4: Executar o Host C11 sobre a imagem
```bash
gcc -O2 -Wall -Wextra -std=c11 \
  -Itranspile/c/lin_c \
  -o /tmp/settlement_host \
  examples/defi_settlement_proof/main_settlement_host.c \
  transpile/c/lin_c/lin_linbc1.c \
  transpile/c/lin_c/lin_vm.c \
  transpile/c/lin_c/lin_sha256.c \
  transpile/c/lin_c/lin_common.c \
  transpile/c/lin_c/lin_token.c \
  transpile/c/lin_c/lin_ast.c \
  transpile/c/lin_c/lin_parse.c \
  transpile/c/lin_c/lin_str.c

/tmp/settlement_host
```
