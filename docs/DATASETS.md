# Registro Canônico de Datasets — Lin-Open

Este documento consolida a totalidade dos datasets on-chain presentes neste repositório.
Em conformidade com a regra **R5 (`LABEL_TOY_VS_EXPERIMENTAL_VS_REAL_WORLD_NO_OVERCLAIM`)**, cada conjunto de dados declara explicitamente sua política de amostragem, intervalo de blocos, taxa de filtragem e status de verificação.

---

## 1. Tabela Unificada de Datasets On-Chain

| Dataset | Registros | Pools Cobertos | Intervalo de Blocos | Política de Filtragem | Comando de Reprodução | Status de Verificação LinVM / GPU |
| :--- | :---: | :--- | :---: | :--- | :--- | :--- |
| **`mainnet_unfiltered.json`** | **157** | USDC/WETH, USDT/WETH, UNI/WETH | 25.900.848 .. 25.901.047 (200 blocos contínuos) | **SEM FILTRO (100% dos logs gravados):**<br>• 139 EXACT_INPUT (88,54%)<br>• 18 OVERPAID_INPUT (11,46%)<br>• 0 K_VIOLATION | `python3 tools/ingest_mainnet_unfiltered.py --blocks 200 --out test/pilot_harness/mainnet_unfiltered.json` | **139/139 (100%)** LinVM paridade exata.<br>**18/18** divergência de roteador explicada.<br>**139/139** aprovados na GPU (`u256_opencl_host`). |
| **`mainnet_swaps_unbiased_audit.json`** | **50** | USDC, USDT, DAI, WBTC | 25.900.411 .. 25.901.011 (600 blocos) | **SEM FILTRO:**<br>• 31 EXACT_INPUT (62%)<br>• 19 COMPLEX/OVERPAID (38%) | `python3 tools/ingest_real_mainnet_dataset.py --count 15 --blocks 600` | **31/31 (100%)** LinVM e GPU. |
| **`mainnet_real_swaps_2000.json`** | **2.000** | USDC (896), USDT (714), UNI (251), DAI (108), WBTC (31) | 25.891.842 .. 25.900.827 (~30 horas contínuas) | **PRÉ-FILTRADO (Legado):** descarta qualquer swap onde `(num//den) != expected_out`. Tautológico para paridade de rede, mas válido como corpus aritmético. | `python3 test/pilot_harness/ingest_real_mainnet_2000.py` | **2.000/2.000 (100%)** em LinVM (`test_live_ethereum_2000_benchmark.py`) e GPU (`u256_opencl_host`). |
| **`mainnet_real_swaps_multi_pools_500.json`** | **192** | USDC (80), USDT (80), DAI (19), WBTC (13) | 25.899.540 .. 25.900.631 (~1.000 blocos) | **PRÉ-FILTRADO (Legado):** apenas swaps canônicos matching getAmountOut. | `python3 test/pilot_harness/ingest_real_mainnet_multi_pools.py` | **192/192 (100%)** LinVM (`test_live_ethereum_multi_pools_192.py`). |
| **`mainnet_real_swaps_100.json`** | **50** | USDC/WETH exclusivamente | 25.891.861 .. 25.892.400 (539 blocos) | **PRÉ-FILTRADO (Legado):** amostra preliminar de fumaça. | `python3 test/pilot_harness/ingest_real_mainnet_swaps.py` | **50/50 (100%)** LinVM (`test_live_ethereum_batch_50.py`). |
| **`test/ethereum_tx/fixtures/*.json`** | **4** | Fixtures Canônicos M1 (Types 0, 1, 2, 3) | N/A (Fixtures de Wire Format EIP-2718) | **CONFORMIDADE CRIPTOGRÁFICA M1:**<br>• Legacy (Tipo 0)<br>• EIP-2930 (Tipo 1)<br>• EIP-1559 (Tipo 2)<br>• EIP-4844 (Tipo 3) | `python3 tools/lin_audit_tx.py corpus verify --dir test/ethereum_tx/fixtures/` | **4/4 (100%)** Keccak-256 e RLP canônico aprovados. |

---

## 2. Metodologia de Classificação

O classificador canônico ([tools/ingest_mainnet_unfiltered.py](file:///home/k/Downloads/lin-master/tools/ingest_mainnet_unfiltered.py)) processa os eventos `Swap` e `Sync` sem descartes e aplica a seguinte hierarquia de decisão:

1. **`K_VIOLATION`**: Violação do invariante $k$ do pool ($(R_{in} \cdot 1000 - A_{in} \cdot 3) \cdot R_{out} > R_{in}^{\text{post}} \cdot R_{out}^{\text{post}} \cdot 1000$). Indica falha crítica ou contrato anômalo.
2. **`EXACT_INPUT`**: Paridade bit-a-bit estrita com a fórmula $y = \lfloor \frac{A_{in} \cdot 997 \cdot R_{out}}{R_{in} \cdot 1000 + A_{in} \cdot 997} \rfloor$.
3. **`EXACT_OUTPUT`**: Satisfaz $A_{in} = \lfloor \frac{R_{in} \cdot y \cdot 1000}{(R_{out} - y) \cdot 997} \rfloor + 1$ (swaps onde o usuário fixou o retorno e o contrato arredondou a entrada em $+1 \text{ wei}$).
4. **`OVERPAID_INPUT`**: O invariante $k$ se sustenta, mas $y < \text{getAmountOut}$. Típico de agregadores (1inch, Uniswap Router), transações com slippage fixo em contratos inteligentes, ou tokens com taxa (*fee-on-transfer*).

---

## 3. Diretrizes para Avaliadores e Pesquisadores

- **Para avaliar paridade matemática do motor LinVM:** Qualquer um dos datasets é válido, pois os campos `amount_in`, `reserve_in`, `reserve_out` e `expected_out` são extraídos de logs on-chain autênticos.
- **Para avaliar distribuição e comportamento da Mainnet:** Utilize estritamente **`mainnet_unfiltered.json`**, pois ele não contém o filtro artificial `continue`.
- **Reprodução determinística:** Todos os arquivos `.bin` de 128 bytes consumidos pelo host OpenCL (`u256_opencl_host`) ou pelo runner de referência CPU (`u256_kernel_cpu_ref.c`) podem ser regenerados diretamente a partir dos arquivos `.json` com o parâmetro `--bin`.
