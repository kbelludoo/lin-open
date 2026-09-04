# Estratégia de Funding (Grants) — LIN

> Objetivo: monetizar o LIN via capital não-dilutivo (grants) antes de qualquer
> preço comercial. Este documento define os alvos, a ordem de ataque e o que
> depende do mantenedor vs. o que já está feito. Posicionamento honesto: LIN é
> **computação determinística + receipts Merkle reproduzíveis externamente** —
> NÃO é um ZKVM e NÃO deve competir com RISC Zero/SP1/Jolt. O encaixe nos
> programas abaixo é "developer tooling + formal verification + provable
> execution", não "novo sistema de prova ZK".

---

## 1. Alvos priorizados (pesquisa em 2026-09-03)

### 🥇 1. Ethereum Foundation — Ecosystem Support Program (ESP)
- **O quê:** grants de $5k–$50k (infraestrutura pode passar de $200k), sem prazo
  fixo (rolling), pagos on-chain em ETH/USDC.
- **Encaixe:** o programa financia explicitamente *dev tooling*, *formal
  verification*, *zero-knowledge cryptography* e *security/audits*. No Q1/2026 a
  EF financiou "formal verification of a RISC-V zkVM" e "GPU acceleration for
  R1CS witness generation" — LIN se posiciona no mesmo balde: **verificação
  formal de uma VM determinística + receipts de execução reproduzíveis**.
- **Requisitos:** saída open-source, não-comercial, benefício ao ecossistema;
  empresas com fins lucrativos podem aplicar, mas o trabalho financiado tem que
  ser público. Sem token. Licença permissiva (MIT) é preferida.
- **Processo:** inquiry → convite para aplicação formal → decisão em 2–6 semanas.
  Requer identidade (KYC) e gestão de milestone.
- **Links:** [esp.ethereum.foundation/applicants](https://esp.ethereum.foundation/applicants) · [wishlist](https://esp.ethereum.foundation/wishlist)

### 🥈 2. NLnet — NGI Zero Commons Fund
- **O quê:** €5k–€50k, rolling (chamadas fecham no dia 1 dos meses pares),
  foco em "fix the internet": software livre, padrões abertos, **verifiable
  computing**, *software engineering / protocols / cryptography / algorithms /
  proofs*.
- **Encaixe:** o fundo já financiou projetos no mesmo quadrante — ex. "Domino:
  Security Proofs that Scale" e "Provability Fabric" (proveniência + verificação
  formal + trilhas de auditoria). O receipt determinístico do LIN é
  literalmente "provability/auditability infrastructure".
- **Requisitos:** FOSS, licença reconhecida, entregáveis abertos.
- **Links:** [nlnet.nl/NGI0](https://nlnet.nl/NGI0/) · [call Commons Fund](https://nlnet.nl/commonsfund/)

### 🥉 3. Ethereum Foundation — Trillion Dollar Security (1TS)
- **O quê:** grants para segurança do ecossistema (ex. WEBCAT: front-ends
  verificáveis via signed manifests + transparency logs).
- **Encaixe:** o LIN pode se posicionar como "integridade verificável de
  artefato/execução" (adjacente ao WEBCAT: code assurance). É um stretch, mas a
  categoria "verifiable software delivery" está em alta.
- **Links:** [blog.ethereum.org 1TS](https://blog.ethereum.org/2026/08/05/1ts-grant)

### Retroativos (depois de tração)
- **Optimism RetroPGF** e **Gitcoin Grants** — exigem uso público/tração; não
  são a porta de entrada agora, mas são o segundo ciclo depois do ESP/NLnet.

### Não recomendados (por ora)
- Grants de ecossistemas específicos (Aztec/Noir, Starknet, Mina, RISC Zero) —
  exigem amarrar o LIN à stack deles; competitivo e dispersa foco. Deixar para
  depois se houver um integração vertical clara.

---

## 2. Ordem de ataque recomendada

| Passo | Ação | Quem | Estado |
|---|---|---|---|
| 1 | Fechar evidência técnica (100k fuzz, benchmark, spec frozen, LICENSE) | feito | ✅ esta sessão |
| 2 | Tornar o repo **público** + CI rodando | mantenedor | ⏳ pendente |
| 3 | 1 auditor externo pequeno (review do claim set) | mantenedor | ⏳ pendente |
| 4 | Submeter **ESP inquiry** (1 página) + **NLnet** em paralelo | mantenedor | 🔜 |
| 5 | Aplicação formal ESP (budget/milestones — base: GRANT_PROPOSAL.md) | mantenedor | 🔜 |
| 6 | Publicar benchmark + fuzz como artigo técnico (prova social) | mantenedor | 🔜 |

Aplicar para ESP e NLnet **em paralelo** é viável e legítimo (são fundos
distintos; só não usar o mesmo grant para pagar o mesmo trabalho duas vezes).

---

## 3. O que já está pronto nesta sessão (evidência medida)

- **400.003 vetores diferenciais, 0 divergências** (QOI 100k + Uniswap 100.003 +
  SipHash/xxHash 200k), exit 0 — `test/prove_all_claims_external.py --iterations 100000`.
- **uint256 single-shot**: 1.000/1.000 vs oráculo BigInt (vetor 18 decimais →
  `1662497915624478906`).
- **Benchmark de custo de auditoria**: verificar um recibo (Merkle LCR2) ≈
  **5,3 µs** vs re-executar o bloco na VM ≈ **26,4 ms** → **~4.986× mais barato
  auditar por receipt** — `benchmarks/audit_cost_benchmark.py`.
- **Spec congelada (candidata)**: `docs/SPEC_FREEZE_1_0.rulel` pina os digests.
- **LICENSE MIT** reconhecível (arquivo `LICENSE`).
- Manifesto de evidência: `docs/GRANT_EVIDENCE_2026_09.rulel`.

## 4. O que só o mantenedor consegue fazer (fora do sandbox)

1. **Tornar o repo público** (hoje `private` — o checklist do grant afirmava
   "public ✅" incorretamente).
2. **Habilitar CI** (o workflow existe; falta permissão de `workflows` no GitHub
   App / fazer o primeiro push de workflow num repo que você controla).
3. **Contratar 1 auditor externo** (o único gap técnico não automatizável).
4. **Criar a identidade/onboarding** do ESP (KYC, endereço ETH para receber).
5. **Bless do congelamento** da spec (renomear `FROZEN_CANDIDATE` → `frozen`).

## 5. Riscos que a proposta NÃO deve esconder

- Não alegar "economia de gás de 99%" nem "mais rápido que LLVM" (sem benchmark
  que suporte; o repo já marca isso como NOT-PROVEN — manter).
- Posicionar como determinismo/tamper-evidence, não como ZK. A pergunta nº 1 de
  qualquer reviewer será "por que não usar RISC Zero/SP1?" — a resposta honesta
  é "não somos um sistema de prova ZK; somos receipts Merkle + re-execução
  determinística fail-closed, mais baratos de verificar e auditáveis por
  qualquer um em Python/hashlib".
- Single-maintainer: mitigar declarando o orçamento de auditor + escopo pequeno
  e honesto (é o que o GRANT_PROPOSAL.md já faz).
