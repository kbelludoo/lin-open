# LIN — Relatório de testes (executado em ambiente limpo)

Executado em 2026-08-31 sobre o clone limpo do repositório, com Zig 0.13.0 e
**PoCL 6.0** (runtime OpenCL de CPU — a "placa" disponível neste ambiente; não há GPU).

## Como rodar nesta placa (PoCL, sem GPU)

```bash
sudo apt-get install -y ocl-icd-opencl-dev pocl-opencl-icd clinfo
zig build-exe compiler/lin.zig -O ReleaseFast -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL --library c -femit-bin=bin/lin_native
make test
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL test_lin_full_self_hosted_suite.zig
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL test_lin_selfhost_compat_001.zig
```

## Resultados reais

| Teste | Resultado |
|---|---|
| `make test` (build + check + receipt) | ✅ exit 0 |
| `lin check` em **20/20** `.lin` | ✅ 20 OK, 0 falhas |
| `lin integrity` | ✅ **PASS**, confirmed=20, refuted=0 |
| `receipt create → verify` (RULEL + JSON) | ✅ PASS, Merkle determinístico `b96fecee…` |
| `lin from-c` (C escalar → LIN) | ✅ transpila |
| `lin lint` | ✅ sem erros |
| **full self-hosted suite** | ✅ `PASS_FULL_SELF_HOSTED_LIN`, bit-exact, Merkle `62b7d202…` |
| **compat suite** | ✅ `PASS_FULL_LEGACY_COMPATIBILITY`, 17/17 subgates, 1000/1000 fuzz, 0 mismatches |
| `make attestation-gate` | ✅ **PASS** — 5 testes unitários do guard + 43 asserções de honestidade |
| `make gate` (LIN Gate, Merkle do toolchain) | ✅ **GATE OPEN** — 31 arquivos, 6 níveis, raiz = atestada |
| `make xver` (N-Version Zig × C) | ✅ **34/34 vectors, 0 divergences** — mesmas raízes Merkle nas duas implementações |
| `make -C transpile/c test` / `test-edges` / `test-sha256` | ✅ 29/29, 17/17, 5/5 (vetores FIPS/NIST publicados) |

### Attestation honesty gate (destaques)

Executado com o build CPU-only (`zig build -Dgpu=false -O ReleaseFast`):

```
  ok   35 gated command names refused with exit 3
  ok   no receipt or report file written by any refused command
  ok   simulated run announces itself on stderr
  ok   simulated run recorded in simulated_attestations.log
  ok   garbage bundle refused (exit 1)          # cleanroom-verify fail-closed
  ok   no cleanroom receipt written for an unverifiable bundle
  ok   no roster -> NotImplemented (exit 3)
  ok   4/4 co-signatures verified with Ed25519
  ok   tampered state root -> quorum refused
  ok   2-of-4 valid signatures cannot satisfy a 3-of-4 quorum
  ok   adversarial corpus rejected every mutation   # 7/7
  ok   Merkle root is deterministic across runs (sha256:b96fecee…)
  ok   C11 second implementation built (transpile/c/bin/lin_c_receipt)
  ok   crosscheck-c reached consensus (exit 0)
  ok   34 vectors agreed across two implementations, 0 divergences
  ok   receipt records independent_implementations=2
  ok   receipt pins the C binary by SHA-256
  ok   a lying second implementation is detected (divergence, no receipt)
  ok   missing second implementation -> NotImplemented (exit 3)
  ok   gate without a manifest is not evaluable (exit 3)
  ok   gate-attest writes a manifest with the recomputed root
  ok   gate opens on an attested tree
  ok   gate Merkle root is deterministic across runs
  ok   a modified compiler file blocks the gate (exit 1)
  ok   a new unattested file blocks the gate (exit 1)
  ok   deleting an attested file blocks the gate (exit 1)
  ok   committed manifest matches the tracked toolchain at the repo root
  ok   gate-keygen writes the private seed with mode 0600
  ok   gate-attest --key signs the manifest body with Ed25519
  ok   gate-check verifies the Ed25519 attestation against the roster
  ok   an attestation signed by a non-roster key is rejected
  ok   a tampered signature fails Ed25519 verification
  ok   quorum 2 with a single valid signature blocks the gate
  ok   an unsigned attestation fails closed when a roster is required
  ok   without a roster the gate discloses that it skipped signature verification
```

### N-Version Zig × C (`make xver`)

```
$ make xver
N-VERSION CONSENSUS: 34 vectors | agreements 34 | divergences 0
Independent implementations compared: 2 (Zig, C11)
RESULT: CONSENSUS — receipt written to xver_receipt.rulel
```

Corpus: os 29 vetores do oráculo compartilhado (23 avaliados + 6 rejeitados por
ambos os lados, com o mesmo nome de erro) mais 5 vetores de fronteira INT64.
Canonicalização `LIN_XVER_CANONICAL_v1` (4 folhas: fonte, ambiente, bytecode
emitido, execução). O recibo fixa o binário C por SHA-256 (`engine_b_sha256`).

### LIN Gate (`make gate`) — verificador de integridade do CI

```
$ make gate
  scope ........... compiler,transpile/c/lin_c,transpile/c/tool,transpile/c/test
  tracked files ... 31
  merkle levels ... 6
  recomputed root . sha256:948850d1abcad93752d49bccb0d97b20738640fd8d318a73dbf314cb26b2f0e0
  merkle root (attested) ... sha256:948850d1…
  merkle root (recomputed) . sha256:948850d1…
GATE OPEN — Merkle root matches the attested manifest (31 files).
```

Códigos de saída: **0** = gate aberto, **1** = bloqueado (mudança não atestada ou
assinatura não verificada), **3** = não avaliável (manifesto/roster ausente ou
malformado, escopo vazio).

A atestação pode ser assinada com Ed25519 real: `lin gate-keygen` gera a chave
(semente aleatória, arquivo 0600) e o roster público; `gate-attest --key` assina o
corpo do manifesto; `gate-check --roster` exige quórum M-de-N. Sem `--roster` a
saída declara `signature NOT VERIFIED` — nunca sugere que verificou. Os caminhos de
bloqueio (MODIFIED / ADDED / DELETED) são testados dentro de um sandbox temporário
pela suíte de honestidade; o manifesto commitado é conferido contra a árvore real
na raiz do repositório. Re-atestação humana: `make gate-attest`.

Rodar isoladamente: `make attestation-gate` (ou `./test/attestation_honesty.sh
zig-out/bin/lin_native`). O alvo também é chamado por `make test` e `make test-cpu`
e pelo workflow de CI.

### Full self-hosted suite (destaques)
- `Silicon Parity: R_cpu == R_gpu == R_oracle` → **Bit-Exact: true**
- Merkle root: `sha256:62b7d202…` (idêntico ao certificado do README original)
- Fases 1–7 todas `PASS`, exit 0

### Compat suite (destaques)
- 17/17 subgates, mask `0x1FFFF`, closure valid
- Fuzz 1000/1000, mismatches 0
- exit 0

## Correções aplicadas nesta revisão

1. **Descoberta de dispositivo robusta** (2 suítes): preferia `CL_DEVICE_TYPE_GPU` e
   acessava `platforms[0]`/`devices[0]` sem checar — crashava sem GPU. Agora faz fallback para
   qualquer dispositivo OpenCL (ex.: PoCL CPU) e sai com graça se não houver nenhum.
2. **Flag de build de kernel**: `-cl-std=CL2.0` forçado → `null` (default do dispositivo).
   Permite compilar o kernel em runtimes OpenCL C 1.2 como o PoCL.
3. **`integrity`/`hypo --all`**: apontava para 36 arquivos `test/corpus/*.lin` deletados na
   limpeza de 2026-08-31 (todos `REFUTED`). Agora auto-verifica as 20 fontes reais do repo →
   `PASS`. Mesma correção aplicada a `verify-cert` e `cert`.

## Limitações honestas que permanecem

- `make build` ainda faz **link duro com OpenCL** (precisa de `ocl-icd-opencl-dev` + um ICD,
  ou ROCm). Não há build 100% sem OpenCL ainda — refatoração recomendada.
- Várias linhas `[PASS]` das suítes GPU são **prints hardcoded**, não asserções computadas.
  Reescrever como asserções reais é o próximo passo de credibilidade.
- `from-js` ainda casa 0 funções em formas com arrow/expressão.
- A execução aqui foi em **CPU via PoCL** (paridade computada, bit-exact). Não foi validado
  em hardware AMD GPU físico (não existe neste ambiente).

## Atualização: OpenCL opcional (compile-time) + CI

- Novo `build.zig` (Zig 0.13) com opção `-Dgpu`.
- **`make build-cpu` / `zig build -Dgpu=false`**: compila o mesmo código contra um stub
  OpenCL local (`stubs/CL/`) — não exige headers/ICD/GPU. Comandos GPU falham graciosamente.
- **`make test-cpu`**: build CPU-only + check 20/20 `.lin` + receipt round-trip → ✅ exit 0.
- **CI** (`.github/workflows/ci.yml`): pin Zig 0.13, instala OpenCL+PoCL, roda build GPU e
  CPU, as 2 suítes, integrity, e publica os Merkle roots no resumo do run e como artefato.

## Atualização: "todas as correções" do security audit

- **17/17 subgates da suíte compat agora são asserções computadas reais** (não prints):
  001A parser, 001B wrap-around, 001C MIR determinístico, 001D LinVM exec real,
  001E CPU parity, 001F GPU parity, 001G JIT re-eval, 001H AOT determinismo,
  001I rejeição de erro, 001J version, 001K parse de fontes, 001L dual-run determinismo,
  001M redução, 001N fuzz 1000, 001O corpus parse, 001P self-host build, 001Q kernel real.
  Todas PASS, exit 0.
- **Certificado auto-referencial corrigido**: `compiler_sha256` agora é hash do *source*
  `compiler/lin.zig` (reproduzível/verificável), não mais `/proc/self/exe`.
- **`gpu-verify` reparado**: default `examples/map_kernels.lin` (kernels unários reais),
  fallback de device para CPU, roda → PASS 21/21 bit-exact.
- **Paridade GPU reclassificada** como teste de conformidade (não prova criptográfica) —
  ver SECURITY_AUDIT.md.
