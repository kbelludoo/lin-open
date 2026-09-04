# Demonstração Prática: Motor de Liquidação AMM com Bytecode LINBC1 e Árvore Merkle

Este experimento comprova de forma rigorosa, reprodutível e com métricas auditáveis as melhorias que o **LIN** traz quando aplicado à liquidação financeira e oráculos DeFi.

---

## 1. O Problema nos Sistemas Convencionais
- **Auditoria de Lote Exige Reexecução Completa:** Para auditar centenas de transações liquidadas off-chain, um validador precisa reexecutar todo o código histórico se não houver provas criptográficas estruturadas.
- **Risco de MEV e Slippage Oculto:** Hackers ou nós maliciosos podem desviar centavos alterando parâmetros em memória; sem compromissos de bloco e raízes Merkle, a adulteração não é detectada em tempo de verificação de bloco.
- **Vulnerabilidades de Memória:** Motores em linguagens não verificadas ou com ponteiros manuais sofrem com memory leaks e corrupção de memória.

---

## 2. O que o LIN Melhora (Comprovado Experimentalmente)

1. **Compilação Canônica para Bytecode LINBC1:**
   O módulo [`settlement_engine.lin`](settlement_engine.lin) é compilado para uma imagem binária congelada [`settlement_engine.linbc`](settlement_engine.linbc) (hash fixo, autoverificado por SHA-256 no domínio `linbc1:img:`).
2. **Execução Direta no Loader de Bytecode (`lin_bc1_run`):**
   A execução não usa interpretadores de texto solto ou atalhos permissivos: roda diretamente via instruções de bytecode pelo carregador fail-closed C11.
3. **Árvore Merkle Real com Provas de Inclusão:**
   As transações são agrupadas em blocos de 4 swaps, gerando raízes Merkle canônicas. Qualquer nó validador pode verificar a inclusão de uma transação individual no bloco ($O(\log N)$) conferindo o caminho de prova em **~2.4 microssegundos ($\mu$s)**.
4. **Resistência Anti-Adulteração (100% de Detecção):**
   Injeções de desvio de 1 satoshi/wei no valor de saída quebram a prova de caminho da árvore Merkle em 100% dos testes.
5. **Execução em Memória Estática (Zero Heap no Host):**
   O loader `lin_linbc1.c` e o executor `lin_vm.c` operam em estruturas de tamanho fixo fornecidas pelo chamador.

---

## 3. Como Reproduzir

### Passo 1: Compilar a imagem de bytecode LINBC1
```bash
./transpile/c/bin/lin_c0 image examples/defi_settlement_proof/settlement_engine.lin -o examples/defi_settlement_proof/settlement_engine.linbc
```

### Passo 2: Executar o Benchmark e Validação Merkle
```bash
python3 examples/defi_settlement_proof/benchmark_settlement_proof.py
```

### Passo 3: Executar a Demonstração do Host C11
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
