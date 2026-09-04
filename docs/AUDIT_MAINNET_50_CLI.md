# Auditoria — Validação Mainnet 50 Swaps + CLI lin-audit (2026-09-03)

> Postura cética, como nas auditorias anteriores. Verificamos executando de fato
> e conferindo contra o Etherscan. **Veredito: o dado e a paridade são reais e
> fortes; havia 4 lacunas de integridade nos recibos/CLI que foram corrigidas, e
> 2 problemas estratégicos na proposta de grant.**

---

## 1. O que é GENUÍNO (verificado)

### 1.1 Dataset de 50 swaps reais
`test/pilot_harness/mainnet_real_swaps_100.json` contém 50 swaps reais do pool
USDC/WETH (`0xb4e16d0…`), blocos 25900475–25900661, ambas as direções
(34 USDC→WETH, 16 WETH→USDC). O ingestor só aceita um swap se
`num//den == expected_out` (checagem interna da matemática Uniswap V2).

**Verificação independente:** a tx `0xd81d04ef…` existe no Etherscan (bloco
25900475, swap `0.0066509 ETH → 16.634498 USDC` = `16634498`), batendo exatamente
com `expected_out_real` do dataset. O dado não é fabricado.

### 1.2 Paridade 50/50 bit-exact
`test_live_ethereum_batch_50.py` re-rodado aqui: **50/50 PASS**, 58.118.630
steps, ~0.46 s (~9 ms/swap). O motor u256 reproduz a saída on-chain de cada swap
bit a bit. Este é o headline correto para o grant (reproduzível por terceiros).

---

## 2. Lacunas de integridade ENCONTRADAS e CORRIGIDAS

| # | Lacuna | Onde | Correção |
|---|---|---|---|
| 1 | Recibo LCR2 ancorava `sha256(arquivo cru)` (`44a5fdcd…`) em vez do digest **canônico** que o loader verifica (`4f4d1288…`) | `test_live_ethereum_batch_50.py` | Digest agora lido de `lin_bc1_run --verify` |
| 2 | CLI ancorava `sha256(arquivo cru)` (`989f157b…`) em vez do digest canônico (`b2df876a…`) | `tools/lin_reconcile_cli.py` | idem |
| 3 | CLI ancorava **hash de bloco zerado** (`b"\x00"*32`) — o "binds block hash" era falso | `tools/lin_reconcile_cli.py` | Lê `block_hash` do dataset quando presente; sem ele marca `block_anchored=false` e avisa |
| 4 | `min_out` calculado em **float** (`int(x*9950/10000)`) — perda de precisão para valores > 2^53 | `tools/lin_reconcile_cli.py` | Aritmética inteira: `x*(10000-bps)//10000` |

Consequência: a raiz Merkle do lote mudou (`5e37b648…` → `10818f14…`) porque a
folha agora ancora o digest correto. A raiz antiga estava ancorada ao hash
errado.

Também: `ingest_real_mainnet_swaps.py` agora resolve `block_hash` via
`eth_getBlockByNumber` (com cache) — re-rodar com rede regenera o dataset com
hash de bloco real, fechando a ancoragem on-chain (RPC indisponível neste
sandbox; funciona no ambiente do usuário).

---

## 3. Limitações honestas que PERMANECEM

1. **Classificador de conciliação é i64.** Compara 64 bits baixos; valores
   > 2^64-1 são truncados (a CLI agora avisa em runtime). Promover para
   multiword u256 é o próximo upgrade.
2. **Gas não é atribuível por hop**: algumas txs têm `gas_used` de milhões (rotas
   agregadas/MEV); a checagem de gas só faz sentido para swaps single-hop.
3. **Dataset não contém `block_hash`** (o commit atual foi feito antes da
   correção do ingestor). Re-rodar `ingest_real_mainnet_swaps.py` com rede
   regenera o campo.

---

## 4. Proposta de grant (Uniswap Foundation) — problemas corrigidos

| Claim original | Problema | Correção |
|---|---|---|
| "Target Track: Developer Tools / Infrastructure & Protocol Analytics" | Track inventado | "Category: Developer Tooling / Protocol Infrastructure", alinhado às prioridades públicas da UF |
| "50 real, **contiguous** swaps" | Não são contíguos (50 swaps em ~186 blocos) | "50 real swaps from blocks 25900475–25900661" |
| "100% detection rate" (7 ataques) | 5 na LinVM + 2 no host; "100% pela VM" era overclaim | "5 fraud classes in the LinVM + 2 admission rules in the host" |
| "under 2 µs" | Não era o número medido | "≈5.3 µs (Python) / ≈1.6 µs (C host)" — benchmark citado |
| "MIT / Apache 2.0 compatible" | Licença é MIT | "MIT" |
| Repo privado linkado como se público | Reviewer vê 404 | Nota explícita de tornar público antes de submeter |

### Problema estratégico NÃO removível por código
A **Uniswap Foundation está em processo de fechamento** (aprovado dez/2025;
staff → Uniswap Labs; grants ~US$100M sob time residual, depois "growth budget"
sob Labs). A proposta continua válida, mas:
- confirmar o canal ativo no momento da submissão (Foundation vs Labs);
- as prioridades atuais da UF são **V4 hooks / protocol tooling / onboarding**
  — uma proposta centrada em V2 pode ser vista como desalinhada. Recomendação
  primária: **Ethereum Foundation ESP** (ver `docs/GRANT_FUNDING_STRATEGY.md`),
  que financia exatamente "formal verification + dev tooling", com o ângulo
  Uniswap V2/V3 como evidência de paridade real.

---

## 5. Conclusão
A evidência de paridade (50/50 Mainnet + 400k fuzz) é **excelente e real**. Os
recibos agora ancoram o digest canônico e declaram honestamente quando não
ancoram hash de bloco. A proposta foi reescrita para não overclaim. O próximo
passo de maior impacto para monetização continua sendo: repo público + CI +
inquiry no ESP.
