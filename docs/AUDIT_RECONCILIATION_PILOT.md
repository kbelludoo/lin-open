# Auditoria — Motor de Conciliação DeFi + Suíte Adversarial (2026-09-03)

> Postura: cética. Verificamos as claims do commit `a7254d6` executando de fato
> a LinVM (`lin_bc1_run`) e conferindo os dados on-chain contra o Etherscan.
> Resultado: a evidência **real** é forte; havia 4 lacunas de integridade que
> foram corrigidas no harness e 2 limitações honestas que permanecem declaradas.

---

## 1. O que é GENUÍNO (e forte para o grant)

### 1.1 Paridade bit-exact contra 4 swaps reais da Mainnet
`test/pilot_harness/test_live_ethereum_settlement.py` alimenta a imagem
`u256_settlement_engine.linbc` (256-bit multiword) com reservas reais e confere
contra o evento `Swap` on-chain:

| Bloco | Tx (real) | amount_in | On-chain out | LinVM out | Paridade |
|---|---|---|---|---|---|
| 25900671 | 0x6868136a… | 5.098e21 | 84960706468242430 | 84960706468242430 | ✅ bit-exact |
| 25900672 | 0x85463ec7… | 9.637e16 | 10868296257934984776561196 | 10868296257934984776561196 | ✅ bit-exact |
| 25900674 | 0xd9a2dfd8… | 9.932e24 | 99846118750068289 | 99846118750068289 | ✅ bit-exact |
| 25900675 | 0xacb5314b… | 4.626e21 | 403521125 | 403521125 | ✅ bit-exact |

**Dado verificado independentemente:** a tx `0x6868136a…` existe no Etherscan,
bloco 25900671, swap Uniswap V2 `5,098.477 ZIG → 0.08496 ETH`; os valores
batem exatamente com `amount_in` e `expected_out_real`. Os 4 hashes de bloco
foram conferidos no Etherscan (ver `test_reconciliation_adversarial_7.py`).

Isto é a evidência mais forte do repositório até agora: **aritmética de 256 bits
do LIN reproduz saída de swap real da Mainnet bit a bit**, com reservas
verificáveis e output confirmado on-chain.

### 1.2 Classificador de conciliação fail-closed (5 regras na LinVM)
`reconciler_engine.lin` (imagem 1113 bytes, 2 funções) classifica com sentinelas
`-1..-6` e passa na baseline (0 falsos positivos). A imagem carrega fail-closed
no `lin_bc1_run` (`img_sha256 = b2df876a80fd…`).

---

## 2. Lacunas de integridade ENCONTRADAS e CORRIGIDAS (harness)

| # | Lacuna | Severidade | Correção |
|---|---|---|---|
| 1 | Registro LCR4 ancorava **hash de bloco fake** (`0x89abcdef…` placeholder) | Alta | Hashes reais por bloco (conferidos no Etherscan) |
| 2 | Registro ancorava **sha256 do arquivo cru** (`989f157b…`), não o digest canônico que o loader verifica (`b2df876a…`) | Alta | Passou a ler `img_sha256` de `lin_bc1_run --verify` |
| 3 | Ataques 1 (replay) e 2 (omissão) eram **asserções Python vacuas** (`seen.add(h); assert h in seen`), não passavam pela VM e eram contadas como "detectados pela LinVM" | Alta | Rotulados como **camada de admissão (host)**; asserts reescritos para detecção real de duplicata/omissão; veredito agora distingue 5/5 LinVM + 2/2 host |
| 4 | Truncamento i64 (`& 0xFFFFFFFFFFFFFFFF`) de saídas reais > 2^64 (tx 2 ≈ 1.09e25) sem declaração | Média | Declarado no docstring e em comentário do `run_lin_classify` |

Veredito após correção: `5/5 FRAUDES DETECTADAS NA LINVM + 2/2 REGRAS DE ADMISSÃO (HOST) = 7/7`.

---

## 3. Limitações honestas que PERMANECEM (declaradas, não escondidas)

1. **Classificador é escalar i64.** `classify_reconciliation` compara os 64 bits
   baixos dos valores; o registro LCR4 preserva 256 bits. Para conciliar
   montantes > 2^64 em precisão total, o classificador deveria ser promovido a
   multiword u256 (como o motor de settlement). *Recomendado como próximo passo.*
2. **`compute_delta` é exportado mas não é exercitado** pelos testes.
3. **"~1,6 µs"** de verificação de prova é um print fixo nesse teste; o número
   medido está em `benchmarks/audit_cost_benchmark.py` (~5,3 µs Python /
   ~1,6 µs host C). Apontar para o benchmark, não hardcodar.
4. **LCR4** declara 248 bytes mas usa 240 (8 de reserva) — documentar ou preencher.
5. Limiar de escala de decimais: o kernel usa `_lia_shr(val,30)` (fator ~10^9,
   direção conservadora); o rótulo "10^12" (6 vs 18 decimais) é o caso coberto,
   não o limiar exato. Ok, mas documentado para não confundir.

---

## 4. Conclusão

- **Manter e destacar no grant:** a paridade 4/4 contra Mainnet real (bit-exact,
  verificável no Etherscan). É exatamente o tipo de evidência reproduzível que o
  ESP/NLnet pedem.
- **Não afirmar** "7/7 detectados pela LinVM" sem o qualificador: são 5 na VM +
  2 na camada de admissão (host). A versão corrigida do harness já diz isso.
- A imagem da regra de conciliação e o registro LCR4 agora ancoram digest
  canônico + hashes de bloco reais, fechando a cadeia de proveniência.
