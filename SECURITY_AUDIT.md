# Auditoria de segurança do LIN — "é possível burlar a verificação CPU/GPU?"

Autor: arena.ai · Data: 2026-08-31 · Tipo: red-team / white-hat no próprio código.

**Resposta curta: SIM, a "verificação" criptográfica de paridade CPU/GPU do LIN é
forjável.** Este documento demonstra, com código executável, por que as afirmações de
"prova de execução verificável" **não se sustentam** sob escrutínio adversário, e o que
seria preciso para torná-las honestas e, aí sim, vendáveis.

---

## 1. O PoC que comprovou a falsificação (executei de verdade)

Criei um runtime OpenCL **falso** (`redteam/fake_ocl.c`) que:

- Reporta uma plataforma `AMD Accelerated Parallel Processing` e um device
  `FAKE-GPU-AMD-RX-6600(gfx1030)` **sem existir GPU nenhuma**.
- No `clEnqueueNDRangeKernel`, **fabrica** o resultado como `out[i] = in[i]*2 + 1`
  (a semântica exata do kernel do LIN), sem executar cálculo algum.

Um harness (`redteam/spoof_main.zig`) que reproduz a lógica de paridade do runner produziu:

```
Plataforma reportada: AMD Accelerated Parallel Processing
Dispositivo reportado: FAKE-GPU-AMD-RX-6600(gfx1030)
R_cpu=1050624  R_gpu=1050624  -> BIT_EXACT [PASS]
```

**O verificador imprimiu `BIT_EXACT [PASS]` sem existir GPU nenhuma.** Conclusão: a
"prova de paridade" confia cegamente no runtime OpenCL reportar fielmente a execução. Um
runtime malicioso (ou um driver comprometido) fabrica o resultado e o LIN aceita.

### Por que isso acontece
- A paridade compara `resultado_do_OpenCL` vs `resultado_da_VM_CPU`. O OpenCL é uma **caixa
  preta**: o LIN não tem como provar que o número veio de execução real no silício. É
  **confiança de processo**, não **prova criptográfica**.
- `clGetDeviceIDs`/`clCreateContext`/`clBuildProgram` retornam `CL_SUCCESS`; basta o runtime
  devolver os números esperados → PASS.

### Como reproduzir
```bash
gcc -c -I./stubs redteam/fake_ocl.c -o redteam/fake_ocl.o
zig build-exe redteam/spoof_main.zig -O ReleaseFast -I./stubs --library c \
    -femit-bin=redteam/spoof_main redteam/fake_ocl.o
./redteam/spoof_main
```

---

## 2. Os `[PASS]` hardcoded (suíte compat)

As subgates `001A`–`001D` da suíte `test_lin_selfhost_compat_001.zig` imprimem
`[PASS]` **sem nenhuma computação**:

```zig
try stdout.print("[001A] Parser Compatibility: ... [PASS]\n", .{});
passed_subgates += 1;   // apenas um contador incrementado
```

Não há parser, type-system, IR nem runtime sendo exercitados — é um `print`. Essas linhas
dão `PASS_FULL_LEGACY_COMPATIBILITY` sem provar nada. (As subgates 001E+ ao menos rodam o
kernel real; as 001A–001D são teatro.)

---

## 3. O certificado auto-referencial

`@LIN:SEMANTIC_CERTIFICATE` calcula `compiler_sha256 = hash(/proc/self/exe)` — ou seja, a
"prova" hasheia **o próprio binário**. Isso não é uma prova independente: qualquer
recompilação gera um binário novo e um certificado novo que "passa". Não é verificável por
terceiros.

---

## 4. O runner real está quebrado (corpus deletado)

`gpu-verify` no binário real falha antes da paridade:
```
gpu-verify: cannot open file test/corpus/gpu_parallel_map_kernels.lin
```
O código ainda aponta para o corpus removido na limpeza de 2026-08-31. Ou seja, na prática
o caminho GPU não roda nem com GPU real de verdade hoje.

---

## 5. O que isso significa para "vender"

Se o produto é vendido como **"prova de execução verificável / compute receipts"**, o
cliente (ou um auditor) pode rodar um red-team como este e **refutar a alegação**. Isso
derruba a credibilidade e abre risco legal (publicidade enganosa / promessa não entregue).

**O que É genuíno hoje:** o **`receipt create` é determinístico e independente do binário** —
`sha256(source + input + output + steps + sp)` → Merkle `b96fecee…`. Esse é um **verdadeiro
commitment** e é auditável por terceiros (basta recomputar a partir de source/input/output).

**O que NÃO é genuíno:** a "prova de paridade GPU", o certificado self-hosted auto-referencial
e os `[PASS]` hardcoded.

---

## 6. Plano honesto para tornar verificável (e vendável)

| Item | Ação | Status |
|---|---|---|
| Receipt Merkle | Manter como a prova principal e publicá-lo (CI já faz). | ✅ feito |
| Paridade GPU | Não alegar "prova". Reclassificar como **teste de conformidade/determinismo** (comparação de duas implementações), não como criptografia. | ✅ feito (README + docs) |
| `[PASS]` hardcoded | Reescrever como **asserções computadas reais** (comparar resultado de fato). | ✅ feito (17/17 subgates) |
| Certificado auto-ref | Remover `compiler_sha256=/proc/self/exe` da "prova"; usar só hashes de fonte+dados. | ✅ feito (`compiler_sha256` = hash do source `compiler/lin.zig`) |
| Corpus deletado | Restaurar `gpu_parallel_map_kernels.lin` ou repontar o runner. | ✅ feito (`examples/map_kernels.lin` + fallback de device; `gpu-verify` PASS 21/21) |
| Prova real | Se o objetivo for prova de execução à prova de adversário, usar **TEE/attestation** (ex.: enclave com medida de execução) ou **ZK**, não OpenCL. | Estratégico (fora do escopo) |

Conclusão honesta: o que hoje se chama de "verificação" é em grande parte **determinismo +
auto-consistência**, não **prova criptográfica à prova de falsificação**. As correções desta
revisão reclassificam a comunicação para "execução determinística com receipt auditable",
removem os `[PASS]` falsos, tiram o hash do próprio binário da "prova", e reparam o caminho
GPU. O ponto estratégico remanescente (prova à prova de adversário via TEE/ZK) permanece
aberto para quem quiser vender "prova" de verdade.

---

## 7. Auditoria dos comandos de atestação — "criptografia real vs. mock" (2026-08-31)

Segunda passada de red-team, agora sobre os sub-comandos `lin *-verify`. A pergunta
foi a mesma da seção 1: **o que este binário computa de verdade e o que ele apenas
imprime?** Cada linha abaixo foi verificada lendo o código e executando o binário
compilado (`zig build -Dgpu=false -O ReleaseFast`), não por inspeção visual.

### 7.1 O que é criptografia real (manter)

| Caminho | Evidência executada |
|---|---|
| `receipt create` / `receipt verify` | Árvore Merkle SHA-256 sobre (fonte, entrada, saída, passos, pilha). Determinística: `sha256:b96fecee…` reproduzido em toda execução. Verificado por `make test-cpu`. |
| `bundle-pack` / `bundle-verify` | `BundleVerifier.verify` recomputa o Git blob OID da fonte embutida, o hash semântico MIR e o hash de lowering de cada kernel, reexecuta o oráculo de CPU sobre 262.144 entradas, reconstrói as árvores Merkle de 8 folhas e a raiz do ledger, e **verifica a assinatura Ed25519** sobre a mensagem canônica (`sig.verify(canonical_msg, pubkey)`). Qualquer divergência é erro. |
| `attest-issue` / `ledger-issue` / `*-verify` correspondentes | Ed25519 real + Merkle real. **Ressalva:** a chave de autoridade é derivada de uma semente fixa no repositório, então a assinatura autentica o formato, não uma autoridade externa. |
| `integrity` / `hypo --all` | Hashes reais das 20 fontes; `confirmed=20, refuted=0`. |
| Suíte `test_lin_selfhost_compat_001.zig` | As 17 subgates são asserções computadas (parser, wrapping, determinismo de IR, execução na LinVM, paridade CPU/GPU/oracle). Não são `print`s. |

### 7.2 O que era teatro (agora bloqueado)

Executado antes da correção, com `bundle_attestation.rulel` contendo **texto
qualquer**:

```
$ lin cleanroom-verify        # bundle de lixo
  [4/4] MERKLE ROOT & DIGITAL SEAL ... [PASS] (Cryptographic verification successful)
CLEANROOM REPRODUCTION CERTIFIED
$ cat cleanroom_receipt.rulel
  verified_ed25519_seal=true
  cleanroom_reproduction="BIT_EXACT_REPRODUCED"
  zero_trust_passed=true
```

Nenhuma linha de verificação foi executada: o comando abria o arquivo e escrevia o
recibo. `notary-verify` imprimia `[SIGNATURE VALID]` para as chaves-fantasma
`1111…`/`2222…`/`3333…` sem jamais decodificar uma assinatura. `polyglot-verify`
comparava seis "implementações" cujo `calculated_audit_digest` era a **mesma
constante**, garantindo 6/6 por construção — e citava verificadores Rust/Go/Python/C
e o diretório `test/conformance_vectors` que não existem no repositório.

Levantamento completo (todos com `exit=0` e recibo gravado antes da correção):
`cleanroom-verify`, `notary-verify`/`transparency-verify`, `verify-all`/`audit`,
`polyglot-verify`/`test-vectors`/`conformance-verify`, `cross-verify`/`multi-verify`,
`n-version-verify`/`common-mode-verify`, `federation-verify`, `global-ledger-verify`,
`temporal-ledger-verify`, `roster-transition-verify`, `pkg-distribute`/`pkg-verify`/
`enterprise-verify`, `consistency-verify`/`e2e-trust-verify`/`verify-003r`,
`protocol-evolution-verify`/`longterm-verify`/`verify-004`,
`federation-governance-verify`/`fed-verify`/`verify-fed-001`, `mir-ssa-verify`,
`nanopass-benchmark`.

Dois detalhes agravantes encontrados na leitura:

- `n-version-verify` anunciava três verificadores independentes, mas o Verifier A e
  o Verifier B chamam **exatamente o mesmo** `BundleVerifier.verify` sobre duas
  cópias dos mesmos bytes; o Verifier C conferia constantes fixas de um único bundle
  e validava a assinatura apenas por comprimento (`sig.len != 128`).
- `verify-all` imprimia dez campos de evidência `VERIFIED` a partir de zero
  computação, e o "corpus adversarial REJECTED (3/3)" não submetia bundle nenhum.

### 7.3 Correção aplicada

1. **`compiler/lin_attestation_guard.zig`** — tabela única e auditável dos comandos
   sem evidência. Cada entrada lista, em texto, as afirmações que o comando faria
   sem computar e o que seria preciso implementar. O despacho da CLI consulta a
   tabela antes de executar: sem `--allow-simulated`, o comando **não roda**, não
   escreve arquivo e termina com `error.NotImplemented` (exit 3). Com a flag, roda
   anunciando em stderr que a saída **não é evidência** e registra a execução em
   `simulated_attestations.log`.
2. **`cleanroom-verify` reescrito para verificar de verdade** — chama
   `BundleVerifier.verify` (blob OID, Merkle de kernels, raiz do ledger, oráculo de
   CPU e selo Ed25519). Falha ⇒ nada é gravado e o exit é não-zero. O recibo passou
   a carregar apenas valores computados (`recomputed_git_blob_oid`,
   `recomputed_ledger_merkle_root`, `ed25519_signed_message`, …) e declara
   explicitamente o que **não** faz: `gpu_parity_checked=false`,
   `independent_implementation=false`, `isolation_boundary_enforced=false`.
3. **`notary-verify` com quórum Ed25519 real** — lê um roster
   (`@RULEL:LIN_WITNESS_ROSTER:1.0.0`), recalcula o digest do *signed tree head* a
   partir dos campos do arquivo, verifica cada co-assinatura com
   `Ed25519.verify`, recusa quórum não-majoritário, testemunha duplicada e
   assinatura inválida. As provas de consistência/inclusão do log passaram a ser
   declaradas `false` / "não avaliadas" em vez de `[PASS]`. O comando novo
   `lin notary-sign` gera um roster com chaves e assinaturas reais (rotulado como
   fixture de auto-teste, não como raiz de confiança).
4. **`bundle-verify`** passou a emitir o recibo com os valores do `Report` retornado
   pela verificação, e não com literais.
5. **Testes** — `test/attestation_honesty.sh` (19 asserções: recusa dos 35 nomes de
   comando, ausência de artefatos, caminho simulado, fail-closed do cleanroom,
   quórum real, tamper, corpus adversarial 7/7 e round-trip do receipt) mais 5
   testes unitários em `lin_attestation_guard.zig`. Rodados por
   `make attestation-gate`, acoplado a `make test`/`make test-cpu` e ao CI.

### 7.4 O que continua em aberto

- **N-Version real (C × Zig):** `transpile/c/` tem um parser/VM independente em C,
  mas nada ainda o executa como segundo verificador do mesmo bytecode. `cross-verify`
  e `n-version-verify` seguem bloqueados até isso existir.
- **LIN Parity de 5 linguagens:** inexistente. `polyglot-verify` continua bloqueado
  e nenhuma promessa de paridade multi-linguagem deve ser feita.
- **Prova de execução à prova de adversário:** o PoC da seção 1 segue válido —
  paridade OpenCL é conformidade, não prova. TEE/ZK continuam sendo o único caminho.

---

## 8. N-Version real: Zig × C (2026-08-31)

O item 2 do plano de correção pedia que a suíte C de `transpile/c/` fosse integrada
à verificação cruzada — "o mesmo bytecode executado pela VM Zig e pela VM C deve
gerar a mesma raiz Merkle". Está feito e é executável.

### O que foi construído

| Peça | Onde | Estado |
|---|---|---|
| SHA-256 próprio em C (sem OpenSSL) | `transpile/c/lin_c/lin_sha256.{h,c}` | validado contra vetores **publicados** (FIPS 180-4 + NIST CAVP 1 MiB): 5/5 |
| Emissor de recibo do lado C | `transpile/c/tool/lin_c_receipt.c` | parse → AST eval → lower → LinVM C → raiz Merkle |
| Comando de verificação cruzada | `lin crosscheck-c` (em `compiler/lin.zig`) | executa o mesmo corpus nas duas implementações e compara as raízes |
| Alvo de build | `make xver` (raiz) e `make -C transpile/c xver` | exit 0 |

### Canonicalização (especificação única, implementada duas vezes)

```
bytecode_image = por instrução: 1 byte (ordinal do opcode) + operando i64 little-endian
leaf_source = SHA256("lin:xver:source:" || expr)
leaf_env    = SHA256("lin:xver:env:"    || env_spec)
leaf_code   = SHA256("lin:xver:code:"   || bytecode_image)
leaf_exec   = SHA256("lin:xver:exec:"   || result ":" steps ":" sp_at_ret)
root        = node(node(leaf_source, leaf_env), node(leaf_code, leaf_exec))
```

### Resultado executado

```
$ make xver
N-VERSION CONSENSUS: 34 vectors | agreements 34 | divergences 0
Independent implementations compared: 2 (Zig, C11)
```

Corpus = 29 vetores do oráculo compartilhado (23 avaliados + 6 que ambos os lados
rejeitam, com o mesmo nome de erro) + 5 vetores de fronteira INT64
(`9223372036854775807+1` → `INT64_MIN`, `-9223372036854775807-2` → `INT64_MAX`,
`9223372036854775807*2` → `-2`, `(0-9223372036854775807)-1` → `INT64_MIN`,
`x*x*x*x` → 10000). São exatamente os casos em que um port de aritmética com
wrapping diverge — e não divergiu.

O recibo fixa a segunda implementação por hash: `engine_b_sha256="sha256:238fe8a7…"`.
"Concordaram" é auditável porque se sabe *qual* binário concordou.

### Por que isso é evidência e não teatro

- As duas implementações são fontes separadas (`compiler/lin.zig` vs.
  `transpile/c/lin_c/*.c`), escritas contra a mesma especificação, e a comparação é
  feita sobre **dados observáveis** (bytecode emitido, resultado, passos, pilha).
- **Injeção de falha:** `test/attestation_honesty.sh` troca a segunda implementação
  por um script que mente (`result=999`, raiz falsa). O comando reporta
  `DIVERGENCE DETECTED`, **não escreve recibo** e sai não-zero.
- **Fail-closed:** sem a segunda implementação compilada, `crosscheck-c` devolve
  `error.NotImplemented` (exit 3) em vez de relatar um cross-check que não rodou.

### O que isto **não** cobre

- É N-Version do **pipeline de expressões** (o slice que o port C implementa). Não
  cobre funções com corpo, `if/while/for`, arrays nem o caminho GPU — o port C ainda
  não tem esses slices (ver "Próximos slices" em `transpile/c/README.md`).
- `n-version-verify` (nível de *bundle*) continua bloqueado pelo guard: ele precisa
  passar a usar esta segunda implementação e deixar de fixar as constantes de um
  único bundle.

---

## 9. LIN Gate — verificador de integridade no CI (2026-08-31)

Item 3 do relatório: "LIN CI Integrity Checker: o *LIN Gate* que bloqueia um PR
gerado por IA cujo *receipt Merkle root* difere do esperado". Implementado e
executado, sem simulação.

### O que faz

`lin gate-check` (ou `make gate`):

1. percorre o escopo rastreado — `compiler/`, `transpile/c/lin_c/`,
   `transpile/c/tool/`, `transpile/c/test/` — e calcula o **SHA-256 real** de cada
   arquivo em disco (stream, 16 KiB por vez);
2. ordena os caminhos lexicograficamente e constrói uma **árvore de Merkle real**
   com a canonicalização `LIN_GATE_MANIFEST_v1`:
   - `folha_i = SHA256("lin:gate:leaf:" || caminho || ":" || bytes || ":" || hex(sha256))`
   - `no(l,r) = SHA256("lin:gate:node:" || l || r)` (nó sem par é promovido)
   - `raiz = redução sobre as folhas ordenadas`
3. compara a raiz recomputada com a raiz atestada em `lin_gate_manifest.rulel`
   (31 arquivos, 6 níveis) e lista cada divergência por arquivo;
4. decide: **GATE OPEN** (exit 0), **GATE BLOCKED** (exit 1) ou "não avaliável"
   — manifesto ausente/malformado/escopo vazio (exit 3, nunca 0).

`lin gate-attest` regrava o manifesto com a raiz recalculada. É o ato humano de
re-atestação: quem revisa a mudança assina o novo raiz e o commita junto com ela.

### Resultado executado

```
$ make gate
  scope ........... compiler,transpile/c/lin_c,transpile/c/tool,transpile/c/test
  tracked files ... 31
  merkle levels ... 6
  git HEAD ........ 8c6bf25
  recomputed root . sha256:948850d1abcad93752d49bccb0d97b20738640fd8d318a73dbf314cb26b2f0e0
  merkle root (attested) ... sha256:948850d1abcad93752d49bccb0d97b20738640fd8d318a73dbf314cb26b2f0e0
  merkle root (recomputed) . sha256:948850d1abcad93752d49bccb0d97b20738640fd8d318a73dbf314cb26b2f0e0
GATE OPEN — Merkle root matches the attested manifest (31 files).
```

Injeções de falha executadas contra o repositório real (todas bloqueadas):

| Injeção | Saída | Exit |
| :--- | :--- | :--- |
| `printf '\n// tampered\n' >> compiler/lin_gpu_execution_oracle.zig` | `MODIFIED` + raiz diferente | **1** |
| `echo 'const probe = 1;' > compiler/zz_gate_probe.zig` | `ADDED` | **1** |
| `mv transpile/c/lin_c/lin_sha256.h /tmp/` | `DELETED` | **1** |
| `gate-check --manifest /tmp/nope.rulel` (inexistente) | "não avaliável" | **3** |
| escopo vazio (cwd fora do repositório) | `GATE BLOCKED — no tracked files` | **3** |

O gate também pegou a si mesmo durante o desenvolvimento: editar `compiler/lin.zig`
e recompilar invalidou o manifesto até a re-atestação — comportamento esperado, já
que o compilador é parte do artefato atestado.

Os mesmos cinco caminhos são assertados em `test/attestation_honesty.sh` (seção 7,
8 asserções, dentro de um *sandbox* temporário para não sujar o repositório), mais
uma asserção de que o manifesto commitado confere com a árvore na raiz do repo.
Total: **35 asserções**.

### Por que isso é um produto e não teatro

- O verificador é o próprio binário construído a partir do checkout do PR — não há
  raiz "esperada" embutida em código; ela está no manifesto, em texto, auditável.
- Nenhum caminho de sucesso imprime `PASS` sem ter calculado: se o manifesto falta,
  se o escopo está vazio ou se qualquer digest diverge, o exit é ≠ 0 e nada é escrito.
- A raiz é determinística (atestada duas vezes no teste → mesmo valor), então um
  terceiro pode reproduzi-la em qualquer máquina com `make gate-attest`.

### Assinatura da atestação (Ed25519 real)

O manifesto pode — e deve, em produção — ser assinado. Três comandos:

```
lin gate-keygen --key k.seed --roster lin_gate_roster.rulel --key-id m1 --quorum 1
lin gate-attest --key k.seed --key-id m1        # assina o corpo do manifesto
lin gate-check  --roster lin_gate_roster.rulel  # exige quórum de assinaturas válidas
```

- `gate-keygen` gera uma semente **aleatória** (`std.crypto.random`), escreve a
  chave privada com **modo 0600** e publica apenas a chave pública no roster. Não
  há derivação determinística de chave (diferente do `notary-sign` de autoteste):
  ninguém consegue regenerar a chave a partir de um prefixo.
- A assinatura cobre **exatamente os bytes do corpo** do manifesto (sujeito +
  registros por arquivo + veredito); o bloco `.g{}` fica, por construção, fora da
  região assinada. `body_sha256` é recalculado e comparado antes de qualquer
  verificação Ed25519.
- Com `--roster`, o gate exige `>= quorum` assinaturas válidas de chaves listadas
  no roster. Sem `--roster`, ele declara explicitamente
  `signature NOT VERIFIED (no --roster supplied)` — nunca insinua que verificou.

Caminhos negativos executados (todos bloqueados):

| Ataque | Resultado | Exit |
| :--- | :--- | :--- |
| trocar um dígito hex de um digest no corpo | `MODIFIED` + `REJECTED — body_sha256 does not match the manifest body` | **1** |
| trocar um dígito hex **da assinatura** | `REJECTED — Ed25519 verification failed` | **1** |
| assinar com chave fora do roster | `REJECTED — signer is not in the roster` | **1** |
| `--quorum 2` com 1 assinatura válida | `1 valid … 2 required` | **1** |
| manifesto sem assinatura + `--roster` | `UNSIGNED` | **1** |
| roster inexistente / sem chaves | não avaliável | **3** |

Os oito casos são assertados em `test/attestation_honesty.sh` (seção 8), dentro de
um sandbox temporário — a suíte agora tem **43 asserções**.

### O que isto **não** cobre

- **Distribuição do roster.** O gate só é tão forte quanto a confiança no roster.
  Nenhum roster está commitado neste repositório: sem ele, `make gate` verifica a
  raiz Merkle e **diz** que não verificou assinatura. Publicar um roster exige
  decidir quem são os signatários e distribuir as chaves públicas fora de banda.
- **Revogação / rotação.** Não há CRL nem epoch de chave; remover uma chave do
  roster é hoje o único mecanismo de revogação.
- **Conteúdo semântico.** O gate garante que o toolchain é o atestado; não prova que
  ele é correto. A correção vem das suítes (N-Version, honestidade, `integrity`).
- **Fora do escopo.** `src/**` (corpus `.lin`), `stubs/**`, os testes auto-hospedados
  na raiz e os artefatos de build não entram na raiz — só o compilador e a segunda
  implementação independente.
- **CI não executado aqui.** O sandbox não tem GitHub Actions; o YAML
  `.github/workflows/lin_gate.yml` foi escrito, mas o push de arquivos de workflow é
  recusado pelo token desta sessão (permissão `workflows`). O gate em si foi
  verificado localmente, comando por comando.
