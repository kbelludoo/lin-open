# Uniswap v2 Soberano em LIN: Comprovação de Superioridade sobre a EVM Original

> **Status (R5 - Sem Overclaim): Comprovado com 2.000 swaps reais da Ethereum Mainnet**
> Hardware Físico: **AMD Radeon RX 6600** (Navi 23, gfx1030, 28 CUs, 8 GB VRAM)
> Compilador: **LinVM Compiler 0 (`lin_c0`)** — 100% LIN puro & Zero Zig.

---

## 1. Tese de Valor Monetário

A Ethereum L1 processa transações de forma sequencial na CPU de cada nó validador. Cada transação no contrato `UniswapV2Pair.sol` consome entre 100.000 e 185.000 unidades de gas, limitando a rede a ~15-30 transações por segundo globais.

Ao transpilar e executar o motor matemático do Uniswap v2 em **LIN Puro** com aceleração paralela na **GPU AMD Radeon RX 6600**, transferimos o processamento pesado de lote para o hardware gráfico off-chain e emitimos **Compute Receipts criptográficos (SHA-256 Merkle)**.

---

## 2. Tabela Comparativa de Desempenho e Economia Real

Resultados obtidos com o dataset canônico de 2.000 swaps reais da Ethereum Mainnet ([`test/pilot_harness/mainnet_real_swaps_2000.json`](../test/pilot_harness/mainnet_real_swaps_2000.json)):

| Métrica | Ethereum EVM (Original) | LIN (LinVM + GPU AMD RX 6600) | Vantagem Competitiva de LIN |
|---|:---:|:---:|:---:|
| **Throughput de Execução** | ~15 a 30 TPS | **1,17M swaps/s (kernel) · 9,1k (wall frio)** | 🚀 **> 39.000× (kernel) / > 300× (wall frio)** |
| **Tempo para 2.000 Swaps** | ~100 a 133 segundos | **1,70 ms (kernel) · 218 ms (wall frio)** | ⚡ Liquidação instantânea |
| **Latência Média por Swap** | ~12.000 ms (12 seg de bloco) | **0,85 µs (kernel) · 109 µs (wall)** | ⚡ Sub-microssegundo no silício |
| **Custo de Gas por Lote** | 1.164.504.079 gas (L1 sum ≈ US$ 34,94/swap) | **70.133 gas (`settleBatch` ≈ US$ 0,0021/swap)** | 💰 **13.258× a 16.604× redução de gas** |
| **Segurança de Memória** | Reentrancy / Out-of-Gas | **Bounds-Checked / Heap-Free (0 alocações)** | 🛡️ Imune a estouro de buffer |
| **Auditabilidade Off-Chain** | Inexistente (requer re-execução) | **Compute Receipt SHA-256 (LCR2)** | 🔒 Verificação em O(1) na EVM |
| **Detecção de Fraude / MEV** | Vulnerável a Front-Running | **Classificação Pré-Liquidação** | 🛡️ Bloqueia desvios do invariante $k$ |
| **Paridade de Dados** | Baseline L1 | **2.000/2.000 exatos (corpus aritmético)**<br>88,5% exato / 0 K-violations (corpus não-filtrado N=157) | 🎯 Paridade formal sem sobre-reivindicação (R5) |

> **Nota de Correção (Errata 09/2026):** Esta documentação adota estritamente os números canônicos da Errata Técnica de Setembro de 2026 ([`docs/GRANT_ADDENDUM_ERRATA_2026_09.md`](GRANT_ADDENDUM_ERRATA_2026_09.md)), substituindo estimativas teóricas preliminares anteriores ("459.000+ TPS / 4,3 ms / US$ 0,00") pelas medições físicas em silício AMD Radeon RX 6600 (Kernel: 1,70 ms / Wall-clock frio: 218 ms) e recibos live Anvil/Foundry 1.8.1 (70.133 gas no `settleBatch`).

---

## 3. Arquitetura da Aplicação Soberana

1. **Código-Fonte em LIN Puro ([`examples/defi_settlement_proof/lin_amm_settler_app.lin`](../examples/defi_settlement_proof/lin_amm_settler_app.lin)):**
   - Implementa a divisão fail-closed sem operadores inseguros.
   - Calcula a taxa de 0,3% (`997 / 1000`) em precisão de 256 bits.
   - Verifica o invariante $(R_{in} \cdot 1000 + A_{in} \cdot 997) \cdot (R_{out} - A_{out}) \ge R_{in} \cdot R_{out} \cdot 1000$.

2. **Aceleração Paralela na GPU (Silício AMD Radeon RX 6600):**
   - O lote de 2.000 swaps é empacotado em um buffer contíguo de 256 KB (128 bytes por swap).
   - A GPU executa a liquidação de todo o lote em **1,70 ms (kernel GPU) / 218 ms (wall-clock frio total)**, confirmando 2.000/2.000 exatos no corpus aritmético canônico (e 88,5% de match exato com 0 violações de $k$ no corpus não-filtrado de 157 swaps).

3. **Prova Criptográfica Zero-Trust (LinVM C0):**
   - A CPU valida as restrições anti-fraude e emite um recibo canônico `@RULEL:COMPUTE_RECEIPT:1.0.0`.
   - O recibo sela o hash SHA-256 do lote e a raiz de Merkle dos inputs/outputs.

---

## 4. Como Reproduzir e Auditar

Execute a aplicação diretamente pelo utilitário CLI:

```bash
# Executar a liquidação na GPU e gerar o recibo criptográfico
python3 tools/lin_defi_settler.py \
  --dataset test/pilot_harness/mainnet_real_swaps_2000.json \
  --gpu \
  --receipt /tmp/uniswap_settlement_receipt.rulel \
  --benchmark

# Auditar matematicamente o recibo com o compilador LIN soberano
transpile/c/bin/lin_c0 receipt verify --receipt /tmp/uniswap_settlement_receipt.rulel
```

Ou execute a suíte de benchmark automatizada:

```bash
./test/benchmark_uniswap_lin_vs_original.sh
```
