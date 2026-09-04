# Demonstração Prática: Motor de Liquidação AMM com Bytecode LINBC1 e Árvore Merkle SHA-256 Real (Caminho 1)

Este experimento demonstra a implementação do **Caminho 1**: uma arquitetura em duas camadas onde a execução financeira determinística ocorre no bytecode da **LinVM**, e a agregação criptográfica em **Árvore Merkle SHA-256 real de 256 bits (FIPS 180-4)** é operada pelo Host C11 e verificadores independentes.

---

## 1. Arquitetura em Duas Camadas

```text
[ Ordens de Swap ]
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  CAMADA 1: EXECUÇÃO DETERMINÍSTICA LINVM               │
│  - Módulo: settlement_engine.linbc (3.098 bytes)       │
│  - Digest: sha256:d41fbfe856155828... (linbc1:img:)    │
│  - Regra: Uniswap V2 x*y=k + Slippage Guard (Fail-Close)│
└────────────────────────────────────────────────────────┘
        │
        │ Saída canônica: (image_sha256, tx_id, amount_in, out_val, steps, status)
        ▼
┌────────────────────────────────────────────────────────┐
│  CAMADA 2: COMPROMISSO CRIPTOGRÁFICO SHA-256 (HOST C11) │
│  - Serialização binária canônica de 72 bytes           │
│  - Folha = SHA-256(registro_72_bytes)                  │
│  - Nós = SHA-256(left_32_bytes || right_32_bytes)      │
│  - Raiz do Bloco: 256 bits com resistência FIPS 180-4  │
└────────────────────────────────────────────────────────┘
        │
        ▼
[ Prova de Inclusão Merkle O(log N) em ~2.8 µs ]
```

---

## 2. Propriedades Comprovadas e Medidas no Benchmark

1. **Separação Limpa de Responsabilidades:**
   - A LinVM não precisa emular o FIPS 180-4 em bytecode: ela executa a regra matemática em bytecode compilado com 100% de pureza e limites rígidos de execução.
   - O host C11 (via [`lin_sha256.c`](../../transpile/c/lin_c/lin_sha256.c)) constrói as folhas e os ramos combinando blocos de 32 bytes de forma canônica.

2. **Registro de Folha Canônico de 72 Bytes:**
   O hash da folha cobre de forma imutável:
   - `0..31`: Digest de 32 bytes da imagem de bytecode executada (`linbc1:img:`).
   - `32..39`: `tx_id` (uint64 little-endian).
   - `40..47`: `amount_in` (uint64 little-endian).
   - `48..55`: `out_val` (int64 little-endian).
   - `56..63`: `steps` (uint64 little-endian).
   - `64..71`: `status` (int64 little-endian: 1 = aprovado, -1 = rejeição por slippage).

3. **Custo e Desempenho Medidos (200 Swaps / 50 Blocos de 4):**
   - **Execução na LinVM (Bytecode LINBC1):** ~161 ms total (~0.81 ms por swap).
   - **Construção das Árvores Merkle SHA-256 (256-bit):** ~0.90 ms total (~4.5 µs por transação).
   - **Auditoria Independente de Inclusão:** ~0.56 ms total (~2.8 µs por swap auditado).
   - **Detecção de Adulteração:** 50/50 mutações detectadas instantaneamente pela divergência da raiz SHA-256.

---

## 3. Como Reproduzir

### Passo 1: Compilar e rodar a demonstração em C11 com SHA-256 real
```bash
gcc -O2 -Wall -Wextra -std=c11 \
  -Itranspile/c/lin_c \
  -o /tmp/merkle_sha256_host \
  examples/defi_settlement_proof/merkle_sha256_host.c \
  transpile/c/lin_c/lin_linbc1.c \
  transpile/c/lin_c/lin_vm.c \
  transpile/c/lin_c/lin_sha256.c \
  transpile/c/lin_c/lin_common.c \
  transpile/c/lin_c/lin_token.c \
  transpile/c/lin_c/lin_ast.c \
  transpile/c/lin_c/lin_parse.c \
  transpile/c/lin_c/lin_str.c

/tmp/merkle_sha256_host
```

### Passo 2: Executar o benchmark automatizado
```bash
python3 examples/defi_settlement_proof/benchmark_settlement_proof.py
```
