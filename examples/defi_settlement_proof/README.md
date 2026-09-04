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

---

## 4. Auditoria v2 (`audit_v2/`) — correções epistêmicas e endurecimento

A auditoria v2 re-examina cada claim acima com metodologia adversarial. **Claims
corrigidos** (detalhes e provas em `audit_v2/audit_report_v2.json`):

| Claim v1 | Status | Evidência v2 |
|---|---|---|
| "Árvore Merkle real verificável com SHA-256 padrão" | **INCORRETO no v1** — o hash era um mixer próprio de **32 bits** (`hash_pair`), não SHA-256 | Colisão por aniversário em ~44 mil avaliações; **segunda pré-imagem forjada em 12,1 s** (6599M sondas, C -O3) e o verificador legado **aceita a liquidação fraudulenta**. A camada de auditoria v2 usa SHA-256 com domínio separado (`lin:settle:v2:leaf/node/chain`) e é verificada bit-exact por hashlib (Python) e `lin_sha256.c` (C) |
| "Detecção de adulteração 100%" | **ENGANOSO no v1** — media apenas que `x ≠ y` quando se muda o valor mantendo a folha original | Matriz adversarial v2 (1.027 vetores: tamper, folha aleatória, prova de outra posição, path_bits inválido, raiz estrangeira, replay entre blocos): 100% rejeitados. Contra adversário ativo, o hash legado tem detecção ~0% (F2) |
| "Verificação em tempo constante" | **IMPRECISO** — é O(log N) (profundidade 2 no demo) | Estatística com 15 rodadas + warmup: p50 = 1,68 µs/prova (hashlib); auditor C11: 1.136 ns/prova |
| "Paridade 100% bit-exact com Uniswap V2" | **VÁLIDO apenas no domínio seguro** (todos os intermediários cabem em i64) — agora declarado e imposto fail-closed | Vetores de fronteira: `reserve_in=2^62` → wrap para positivo → **pagamento em excesso** vs. matemática exata (indetectável por guarda in-range); B2/B3 → wrap negativo |
| **NOVO — Vulnerabilidade F1 (severidade alta)** | — | No front-end C0, `|` tem precedência **maior** que `<=`; as guardas `?(den <= 0 | num <= 0)` da imagem congelada compilam como `(den <= (0|num)) <= 0` — **invertidas**: `settle_swap(1000, 0, 200000, 1970)` paga **200000 contra reserva ZERO**. Correção: `settlement_engine_fixed.lin` (parênteses explícitos nas 4 guardas), imagem `774ae8311b70df…`, fail-closed comprovado (G1/G2/B2/B3 → -1/0), saídas idênticas à congelada nas 200 txs do domínio seguro |
| Zero-heap | Sustentado e agora **provado em runtime** | `test_no_heap.c` (linker `--wrap` em malloc/calloc/realloc/free/memalign/strdup): 0 operações de heap em load + 10.000 execs + verify; ASan+UBSan limpos |
| Loader fail-closed | Sustentado e agora **provado exaustivamente** | `test_image_hardening.c`: **24.784/24.784 mutações de 1 bit rejeitadas**, 3.098/3.098 truncamentos, 64/64 bytes extras |
| Compilação canônica | Sustentado | Recompilação bit-exact (`a5095750…`, 3.098 bytes); cauda embutida == hash de domínio `d41fbfe8…` |

### Custo de auditar vs. reexecutar (honesto)
- Verificar prova (hashlib, p50): **1,68 µs**/tx · (lin_sha256 C11, p50): **1,14 µs**/tx
- Reexecutar na VM in-process C11 (p50): 1,54 µs/tx → verificação é ~1,4× mais barata
  **e** independe da VM/TCB (o auditor não roda código do operador)
- Reexecutar via processo (padrão "subir nó e replays"): 1.141 µs/tx → ~700× o custo da prova

### Reproduzir
```bash
sh examples/defi_settlement_proof/audit_v2/run_audit.sh
```
Executa: build → suíte v2 (8 estágios) → camada ASan/UBSan. Exit 0 só se tudo passar.

### 4.1 "Verificação em tempo constante": como ter de verdade (estudo empírico)

O claim original ("~2,3 µs em tempo constante") era uma medição única sem metodologia.
O estudo `audit_v2/constant_time_study.py` mede com warmup + 21 rodadas + best/p50/p95 +
regressão linear (resultados em `audit_v2/constant_time_study.json`):

**O que cresce e o que não cresce (medido):**

| Arquitetura | Custo/verificação | Evidência |
|---|---|---|
| Árvore única de N folhas | **O(log N)** — confirmado empiricamente: inclinação 0,745 µs/nível ≈ 1 SHA-256/nível (baseline 0,627 µs), **R² = 0,994** | 1,69 µs (N=4) → 7,78 µs (N=1024) |
| Blocos encadeados com bloco FIXO (arquitetura do repo, B=4) | **O(1) em N** — variação de 6,5% entre 40 e 40.000 txs (ruído de CPU) | 1,63–1,72 µs/prova sempre |
| Árvore única + RSA accumulator (Strong RSA) | **O(1) em N** — verificação ~477–484 µs plano (R² com log N = 0,09 ⇒ sem relação), prova de 144 B constante | prover cresce 4→1.225 ms (tradeoff honesto) |

**Como ter "tempo constante", três caminhos honestos:**

1. **Já temos, se o claim for escrito corretamente:** com tamanho de bloco B fixo como
   constante do protocolo (demo: 4), verificar 1 tx é O(log B) = O(1) no total do lote.
   Claim correto: *"O(log B), constante em N; ~1,6 µs/prova (best de 21 rodadas)"*.
2. **Prova de inclusão O(1) em árvore única:** acumulador criptográfico (RSA/Strong RSA —
   demo inclusa, 144 B e ~480 µs planos; produção: modulus ≥ 3072 bits — ou KZG/Verkle,
   48 B + 1 pairing, requer biblioteca de curvas pareamento-eficientes e setup).
   Prova MEMBERSHIP (mesmo modelo de confiança do Merkle), não a computação.
   Crossover de tamanho: acumulador fica menor que o caminho Merkle a partir de bloco
   de ~16–24 folhas.
3. **Provar a COMPUTAÇÃO em O(1):** exige SNARK (Groth16/PLONK: prova ~128–500 B,
   verificação ~ms constante) ou STARK (transparente, mas prova O(log²N)) — ambos
   requerem aritmetizar a LinVM em circuito (roadmap real: meses, com bibliotecas de
   corpo finito; fora do escopo stdlib deste repositório).

**Metodologia de medição (a lição do "2,3 µs"):** clock monotônico ns; warmup; ≥21
rodadas independentes; reportar best/p50/p95 (nunca número único); consumir o resultado
(contra DCE); modelo preditivo (µs ≈ profundidade × µs(SHA-256 64B)); regressão vs
log2(N) com R² para confirmar a classe de complexidade — não declará-la.

```bash
python3 examples/defi_settlement_proof/audit_v2/constant_time_study.py
```

---

## 5. Auditoria v3 — motor u256, dataset Mainnet e GPU (correção de overclaims)

Uma revisão externa do relatório "100% paridade Mainnet / 100% detecção de fraude /
441k swaps/s em GPU" encontrou os problemas abaixo. Cada linha diz o que era falso,
o que é verdadeiro e como reproduzir.

| Alegação anterior | Status | O que o código sustenta agora |
|---|---|---|
| "100% de paridade com a Ethereum Mainnet (2.000 swaps)" | **TAUTOLÓGICO** — os ingestores `test/pilot_harness/ingest_real_mainnet_*.py` descartavam silenciosamente (`if (num//den) != expected_out: continue`) todo swap que não batia com `getAmountOut`. O dataset foi selecionado pela fórmula que depois foi "validada" contra ele. | `tools/ingest_mainnet_unfiltered.py` grava **todos** os `Swap` de uma janela contínua de blocos e classifica: `EXACT_INPUT`, `EXACT_OUTPUT` (getAmountIn, +1 wei), `OVERPAID_INPUT` (roteador/fee-on-transfer), `BOTH_DIRECTIONS`, `K_VIOLATION`, `UNCLASSIFIED`, além de contar receipts indisponíveis. O número honesto é essa distribuição. `mainnet_real_swaps_2000.json` fica marcado como **pré-filtrado** pela suíte. |
| "Comparação tripla Nó ↔ EVM ↔ LinVM" | **DUPLA** — o "oráculo EVM" era `num // den` em Python big-int; nenhum bytecode Solidity é executado. | A suíte declara: Lin (LinVM real via `lin_bc1_run`) ↔ referência big-int ↔ `amount_out` do log. `lin==onchain` só é esperado em `EXACT_INPUT`. |
| "9/9 fraudes rejeitadas — 100% de detecção" | **CALIBRADO** — o delta do ataque em `reserve_out` foi aumentado (10³ → 10¹⁴) até a divisão inteira acusar diferença. Isso é evidência de que a função não é constante, não de detecção. | `test_honest_parity_and_sensitivity.py` FASE 2 mede por busca binária o **menor delta detectável** por campo. Em 25 swaps reais: ±1 wei é invisível em `amount_in` 14/25, `reserve_in` 15/25, `reserve_out` 23/25. Teorema: adulteração de `reserve_out` ≥ `den/(997·amount_in)` é **sempre** detectada; abaixo disso **não há garantia** — e nenhuma reimplementação bit-exata da EVM pode fazer melhor. |
| "Verificado formalmente pelo compilador Lin (0 rejected)" | **IMPRECISO** — `lin verify` é gate de gramática/manifesto, não prova de corretude aritmética. | A evidência de corretude é a paridade contra big-int em todos os vetores + guardas `-1/-2` (FASE 1/3). Não há prova de equivalência com o `.sol`. |
| "441.053 swaps/s em GPU" vs 1,62M no commit anterior | **NÃO EXPLICADO / NÃO REPRODUZÍVEL** — `swaps_2000_raw.bin` não estava versionado; lote de 2k é dominado por latência fixa de lançamento/PCIe. O host imprimia `"PARIDADE BIT-EXACT 100%"` como texto fixo mesmo com falhas. | Host corrigido (imprime concordam/divergem, exit≠0 em divergência, aviso de que o número de um lote pequeno não é pico). O `.bin` é gerado deterministicamente do JSON (`--bin`). `u256_kernel_cpu_ref.c` compila o **mesmo** `.cl` como C11 e reproduz o resultado sem GPU: 2.000/2.000 concordam; lote com 100 `expected` adulterados → 100 divergências, exit 1. |
| `src/lin_uniswap_v2_library.lin` como "biblioteca Uniswap" | **TOY int64** — estoura em qualquer reserva de 18 decimais. | Cabeçalho marcado `TOY_INT64_PROTOTYPE_NOT_FOR_MAINNET_VALUES`; motor canônico é `u256_settlement_engine.lin`. |
| `.mojo` "SIMD de alto rendimento" | **NUNCA EXECUTADO** — sem toolchain. | Não incluído neste repositório. |

### O que é sólido
- `u256_settlement_engine.lin`: `getAmountOut` em 256 bits, 16 limbs × 16 bits, sem `/` (divisão por shift-subtract), fail-closed `-1` (entrada zero) / `-2` (overflow do numerador ou de `amount_in·997` / `reserve_in·1000`). Bit-exato com big-int em todos os swaps testados (1.000 execuções da LinVM para 200 swaps).
- Proveniência do dataset legado: `tx_hash` + `log_index` + bloco, verificáveis num explorador — apenas a **seleção** era enviesada, não os valores.

### Reproduzir (sem GPU)
```bash
make -C transpile/c bin/lin_c0 bin/lin_bc1_run
python3 test/pilot_harness/test_honest_parity_and_sensitivity.py --limit 200 --sens-sample 25 --bin /tmp/swaps.bin
cc -O2 -std=c11 -o /tmp/u256_cpu_ref examples/defi_settlement_proof/u256_kernel_cpu_ref.c && /tmp/u256_cpu_ref /tmp/swaps.bin
# dataset sem filtro (requer JSON-RPC Mainnet acessível):
python3 tools/ingest_mainnet_unfiltered.py --blocks 200 --out test/pilot_harness/mainnet_unfiltered.json
python3 test/pilot_harness/test_honest_parity_and_sensitivity.py --json test/pilot_harness/mainnet_unfiltered.json
```
Com GPU (ROCm/OpenCL): `u256_opencl_host /tmp/swaps.bin`. Cite throughput apenas comparando lotes de tamanhos distintos (ex.: 2k, 10k, 100k).
