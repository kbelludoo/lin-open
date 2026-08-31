# Revisão LIN — Sugestões de melhorias e correções (2026-08-31)

> Revisão do repositório (`compiler/lin.zig`, `build.zig`, `Makefile`, CI, docs, testes)
> com **validação real**: Zig 0.13.0 foi instalado (via wheel oficial `ziglang` no PyPI,
> pois ziglang.org está bloqueado neste sandbox) e **todas as correções abaixo foram
> compiladas e testadas** (ver Parte E). Única ressalva: sem OpenCL/PoCL no ambiente,
> as suítes GPU foram executadas com o stub (`-Dgpu=false`) — o caminho GPU completo é
> coberto pelo CI.

---

## Parte A — Correções aplicadas nesta revisão

Todas em `compiler/lin.zig` (seção host, fora do bloco gerado `LIN-GEN-BEGIN`…`LIN-HOST-END`):

| # | Correção | Onde | Por quê |
|---|---|---|---|
| A1 | `cert verify` passou a hashear **`compiler/lin.zig`** (fonte) em vez de `/proc/self/exe` (binário) e usa o corpus de **20 fontes reais** em vez dos 36 `test/corpus/*.lin` deletados | `cert verify` (~linha 16309) | **Bug crítico de round-trip:** `cert build` → `cert verify` falhava sempre (`compiler_match=false`, `corpus_match=false`, `ledger_match=false`, `certificate_id_match=false`). O `cert build` ancora no fonte; o `cert verify` ancorava no binário + corpus inexistente (hash de nada). Agora os dois lados são consistentes e o certificado volta a ser verificável. |
| A2 | `receipt verify` sem `--receipt` agora **erro + exit 1** em vez de imprimir `PASS` incondicional | `receipt verify` (~linha 15547) | Falso positivo: "verificar nada" passava. Verificador que não pode falhar quebra a confiança do produto. |
| A3 | `receipt create --input` com valor inválido agora **erro claro + exit 1** em vez de cair silenciosamente para `7` | `receipt create` (~linha 15273) | `catch 7` silencioso alterava o input do receipt sem avisar — merkle root "errado" sem explicação. |
| A4 | Verificação de receipt JSON: checagem explícita de campos ausentes/tipos errados/raiz não-objeto (antes: `.get(...).?` — **panic** em receipt malformado) | `receipt verify` (JSON, ~linha 15442) | Robustez: entrada maliciosa/malformada não deve crashar o binário. |
| A5 | Guardas de overflow `INT64_MIN / -1` e `INT64_MIN % -1` na VM (`@divTrunc`/`@rem` panic/UB no Zig), no helper `_lia_mod`, no prelúdio Zig (`ZIG_RUNTIME_PRELUDE`) e no evaluator de C-expr | `vmExecWithSp`, `_lia_mod`, `ZIG_RUNTIME_PRELUDE`, eval C-expr | A VM se anuncia `overflow=wrapping`; divisão/resto por `-1` com `INT64_MIN` é a única operação que **trapava** (viola a promessa de determinismo total). Convenção: `div → INT64_MIN`, `mod → 0`. |
| A6 | `opcodes=28` hardcoded → `VM_OPCODE_COUNT` computado (`@typeInfo(VmOp).Enum.fields.len` = 33) | comando `vm` (~linha 16877) | O enum tem 33 opcodes; o número impresso estava congelado e desatualizado. |
| A7 | Caminho do Zig no `test` command: `/home/k/.local/bin/zig` (path pessoal do autor) removido; agora `LIN_ZIG` (env) → senão `zig` do PATH | `runLinTestFile` (~linha 7009) | Portabilidade: um path de máquina do autor não pode estar no binário (quebraria em qualquer outra máquina sem esse diretório). |
| A8 | `integrity`/`hypo --all`: `.equivalent` e `.proof` agora **computados** do resultado real (antes `equivalent=true` e `proof="…100_PASS"` impressos incondicionalmente, mesmo com corpus REFUTADO) | bloco `integrity` (~linha 16482) | Rótulo de sucesso que ignora o resultado real é o mesmo tipo de "PASS teatral" que o projeto já corrigiu nas suítes. |
| A9 | **`certFieldValue` não pulava a aspa de abertura** (`val_start` apontava para `"` → extraía string vazia → todos os `*_match=false` mesmo com certificado correto) | `certFieldValue` (~linha 6400) | Este era o bug real que mantinha o round-trip `cert build → cert verify` quebrado; com o fix, `CERTIFICATE_VALID`/`PASS` (validado). |
| A10 | **`lin test` consertado**: usava `src/lin.zig` (removido na limpeza → `FileNotFound` sempre) e gravava `src/lin_test_run.zig` no working tree. Agora usa o `ZIG_RUNTIME_PRELUDE` embutido no compilador e grava em `.zig-cache/` | `runLinTestFile` (~linha 6990) | O comando `lin test` estava 100% quebrado no estado atual do repo; agora roda (`ok N`, exit 0) e não suja o working tree. |
| A11 | `rebuild` (bootstrap removido) agora falha com **mensagem clara** em vez de trace cru `FileNotFound` | comando `rebuild` (~linha 7255) | O comando não pode funcionar sem os módulos `src/lin_zig_bootstrap.lin` etc. (removidos); pelo menos o erro é honesto e aponta o problema. |

---

## Parte B — Correções recomendadas (não aplicadas)

### Prioridade alta

1. **`receipt verify` não re-executa o código — a verificação é tautológica.**
   O verify apenas re-hasheia os campos **do próprio receipt** (source-hash, output, steps,
   sp, input). Um atacante que altere `input` **e** `output` de forma consistente (e recompute
   o Merkle) passa. Para honrar a promessa do README ("*this code, given this input, produced
   this output*"), adicionar `--execute` (recompila o `--source` e compara o output real) e/ou
   documentar que o receipt atual prova apenas **auto-consistência**, não execução.
   *Local: `receipt verify` (~linha 15401–15550).*

2. **`apply_dynamic_rules_if_present` (linha 6885) — mudança de semântica por arquivo no CWD.**
   Se existir `storage/dynamic_rules.rulel` no diretório atual, o fonte é **reescrito antes de
   `check`/`compile`/`test`** (transforma ternários `a ? b : c` e `??`). Ou seja: o mesmo
   `.lin` pode compilar diferente dependendo do CWD — péssimo para um sistema que se vende
   como determinístico, e um vetor de supply-chain. Recomendação: remover o hook ou exigir
   flag explícita (`--apply-dynamic-rules`); no mínimo, logar um aviso quando ativo.

3. **`verify-cert` duplicado (dead code).** Há **dois** handlers: o primeiro
   (linha 15947, verificação de 32 casos de base 2^k vs `.expected_outputs`) e o segundo
   (linha 16048, verificação por hashes, só alcançável via alias `verify-certificate`).
   Para `lin verify-cert` o segundo é **inatingível**. Mesclar num comando só (ou um subcomando
   `verify-cert --hash`), senão o comportamento depende de qual alias você digita.

4. **Erros de execução viram stack trace cru.** Em `hypo <file.lin> <fn>`, `vmExec` usa
   `try` (linha ~16680): `VmDivisionByZero`/`VmStepLimit`/`VmDepth` propagam como
   `error.VmDivisionByZero` com trace do Zig em vez de RULEL limpo. Tratar os `VmError`
   explicitamente (como o comando `vm` já faz) e emitir `@RULEL:LIN_HYPOTHESIS_VERDICT` com
   `.reason="execution_error"`.

### Prioridade média

5. **Corpus com 20 vs 21 fontes.** O repo tem **21** `.lin` (18 em `src/` + 3 em `examples/`),
   mas o corpus de `integrity`/`cert`/`verify-certificate` lista 20 (falta
   `examples/map_kernels.lin` — justamente o default do `gpu-verify`). Ou incluir o arquivo no
   corpus, ou documentar a exclusão. (O `integrity` continua PASS porque confere só a lista.)

6. **Hack frágil no `receipt create` (~linha 15312):** se o `--source` contiver a letra `n`
   (e "return" sempre contém!), aloca um local extra `n`; e `sqr`/`fact`/`sum_to` são
   registrados como símbolos de função → `--source "return sqr(x);"` compila e entra em
   **recursão infinita até `VmDepth`**. Substituir por resolução real de símbolos (ou rejeitar
   chamadas desconhecidas com mensagem clara).

7. **`cert build` só checa presença de arquivo** (`corpus_present`), não se ele parseia/builda.
   `status=PASS` pode sair com fonte quebrado. Alinhar com o `integrity` (vmBuild real).

8. **`build.zig` hardcoda `/usr/include`** (linha 29) e o **CI hardcoda
   `-L/usr/lib/x86_64-linux-gnu`** (ci.yml linhas 47/54) — quebra em macOS/ARM/outros distros.
   Usar `exe.addIncludePath` via opção de build (`-Dopencl-include=...`) e `zig build-exe`
   com flags configuráveis no CI.

9. **`test` command grava `src/lin_test_run.zig`** no working tree a cada execução. Escrever
   em `zig-cache/` ou tmpdir.

10. **`.gitignore` é whitelist agressiva** (`*` + exceções): qualquer arquivo novo de tipo
    diferente (`.zig` novo, `.md` fora de docs/, etc.) **não é versionado por padrão** —
    risco real de perder código. Manter, mas documentar que arquivos novos precisam de
    exceção explícita (ou trocar por ignore-negativa).

11. **`integrity`:** `.refutation.total=4` é constante impressa (linha ~16510) e
    `vm_total_steps=0` é literal (`const total_steps: u64 = 0`). Computar steps de verdade
    (executar as funções confirmadas) ou remover os campos do output.

### Prioridade baixa / cosmética

12. `from-js` ainda casa 0 funções — já documentado; ok manter como experimental.
13. Versão `2.0.0` hardcoded em 3 lugares (`main`, `version`, sem-args) — centralizar numa
    const (`pub const LIN_VERSION`).
14. `TESTS.md` desatualizado: diz "Várias linhas `[PASS]` … são prints hardcoded … próximo
    passo" — **já corrigido** (17/17 subgates computados, confirmado no código); e diz que
    "não há build 100% sem OpenCL" — já existe `-Dgpu=false`. Atualizar.
15. `SECURITY_AUDIT.md` seções 2–4 descrevem falhas **já corrigidas** — recebeu nota de
    atualização nesta revisão (ver abaixo).
16. CI: `id: roots` no step "Capture reproducible Merkle roots" não é consumido (cosmético).
17. `docs/LIN_AUTONOMOUS_ENDURANCE_REPORT.md` e `docs/LIN_PROMPT_GUIDE.md` — conferir se os
    números de corpus/opcodes citados batem com o código atual (não auditados a fundo aqui).

---

## Parte C — Melhorias estruturais sugeridas

1. **Teste de regressão para o edge `INT64_MIN / -1`**: adicionar case na suíte compat
   (ex.: subgate que executa `return x / -1;` com `x = INT64_MIN` e espera `INT64_MIN`, e
   `x % -1` esperando `0`) — cobre as correções A5.
2. **Fuzz com `--input` inválido**: testar que `receipt create --input abc` falha com exit≠0
   e que `receipt verify` sem arquivo falha (cobre A2/A3/A4).
3. **Golden test de `cert build` → `cert verify`**: o round-trip deve ser PASS; o CI deveria
   executá-lo (hoje só roda `integrity`).
4. **Releases**: cortar tag + changelog; o README fala em raízes Merkle "canonical" —
   publicá-las como artefato de release (o CI já publica como artifact de run).
5. **`make test` sem GPU**: `make test` depende de `build-gpu` (OpenCL); considerar
   `make test` = CPU-only por padrão e `make test-gpu` para o modo GPU, já que o CPU-only
   cobre 100% das funcionalidades não-GPU (o próprio repo recomenda PoCL para GPU).

---

## Parte D — O que já estava correto (confirmado nesta revisão)

- As 17 subgates da suíte compat **são asserções computadas de verdade** (parse, wrap,
  hash MIR, execução LinVM com `sp_at_ret`, paridade CPU/GPU/oracle, JIT/AOT, fuzz, etc.) —
  o SECURITY_AUDIT.md seção 2 está **desatualizado** sobre isso.
- `integrity` usa as 20 fontes reais e computa `confirmed/refuted/status` corretamente.
- `gpu-verify` aponta para `examples/map_kernels.lin` (existe) com fallback de device.
- `_lia_shl/shr/ushr` e `vmShift` já guardam shift ≥ 64 (sem UB).
- `receipt create` é determinístico e o Merkle `sha256(source||output||steps||sp||input)`
  é recomputável por terceiros.

---

---

## Parte E — Validação real executada (Zig 0.13.0 instalado via PyPI)

| Teste | Resultado |
|---|---|
| `zig build -Dgpu=false -Doptimize=ReleaseFast` | ✅ compila (sem warnings/erros) |
| `make test-cpu` (check 21/21 `.lin` + receipt round-trip) | ✅ **PASS**, Merkle `sha256:b96feceed2a4a67a51dd47d3ff3a8bfdf143dcc0fcc3a80ca70a7ae84c2a47d4` |
| `cert build` → `cert verify` (round-trip) | ✅ **CERTIFICATE_VALID / PASS** (compiler/corpus/ledger/certificate_id all `match=true`) |
| `verify-certificate` (mesmo certificado) | ✅ **CERTIFICATE_VALID / PASS** |
| `integrity` | ✅ PASS, `confirmed=20, refuted=0, equivalent=true` (computado) |
| `receipt verify` sem `--receipt` | ✅ falha com mensagem clara, exit 1 |
| `receipt create --input abc` | ✅ falha com mensagem clara, exit 1 |
| Receipt JSON malformado / tipo errado / raiz não-objeto | ✅ falham com mensagem, exit 1, **sem panic** |
| `INT64_MIN / -1` e `INT64_MIN % -1` via receipt | ✅ `-9223372036854775808` e `0` (sem trap) |
| `lin vm` header | ✅ `opcodes=33` (computado, antes 28 hardcoded) |
| `lin test` (funções `test_*()` sem params) | ✅ `ok 2`, exit 0 — arquivo temp em `.zig-cache/`, working tree limpo |
| `lin test` com `test_*` que não retorna 1 | ✅ FAIL (contrato do harness: `test_*() == 1`) |
| `lin rebuild` | ✅ mensagem clara de indisponibilidade (bootstrap removido) |
| `lin from-c` / `lin lint` / `lin check` / `lin vm` / `lin hypo` / `lin vm-sweep` | ✅ funcionam |
| `gpu-verify` sem OpenCL | ✅ mensagem graciosa ("no OpenCL platform"), sem crash |
| Suítes `test_lin_full_self_hosted_suite.zig` e `test_lin_selfhost_compat_001.zig` (com stub OpenCL) | ✅ compilam e rodam, exit 0, hardware phases `[SKIP]` |

### Pendências confirmadas (não corrigidas, exigem decisão do autor)

1. **`test/corpus/gpu_parallel_map_kernels.lin` é órfão**: o README diz que o corpus foi
   removido, mas o arquivo permanece e **falha o `check`** (`LIN_TYPE_ERROR`). Ele quebra
   `lin test test/` (o runner itera o dir). Opções: remover o arquivo (consistente com a
   limpeza) ou consertar o tipo.
2. **`lin rebuild` indisponível**: os módulos bootstrap `src/lin_zig_bootstrap.lin`,
   `src/lin_zig_emit.lin`, `src/lin_zig_match.lin`, `src/lin_js_expr.lin`,
   `src/lin_js_driver.lin` foram removidos e o repo é shallow (1 commit) — sem histórico
   para restaurar. Recomenda-se remover o comando da CLI ou reconstruir os módulos.
3. **Harness de `lin test`**: só chama funções `test_*` **sem parâmetros** e exige retorno
   `== 1` — limitação do gerador de `main`, pré-existente.
4. **Suítes GPU não executadas localmente** (sem OpenCL no sandbox): rodaram com o stub
   (compilação + skip). O CI (PoCL) cobre o caminho completo.

---

---

## Parte F — Verificação independente do recibo (implementada e validada)

**Proposta aceita e materializada:** a verificação de recibos LIN agora é possível **sem
o compilador LIN** — princípio zero-trust correto (o recebedor não deve confiar no
emissor). Foram adicionados ao repo (diretório `benchmarks/`):

| Verificador | Implementação | Validação real |
|---|---|---|
| `benchmarks/verify_receipt.py` | Python 3 stdlib (`hashlib`, `struct`, `json`) | ✅ PASS no fixture real |
| `benchmarks/verify_receipt.sh` | Bash + `openssl dgst -sha256` (fallback `sha256sum`) | ✅ PASS no fixture real |
| `benchmarks/verify_receipt.js` | Node.js `crypto` nativo | ✅ PASS no fixture real |
| `benchmarks/verify_receipt.html` | WebCrypto no browser, estático/offline | ✅ mesmo cálculo |
| `benchmarks/fixtures/receipt_sqr9.{json,rulel}` | Recibos **reais** emitidos pelo compilador atual | `sha256:b96fecee…` |

**Testes executados:**
- 100 recibos reais (`return x * x;`, inputs 1..100) × 3 verificadores = **300/300 PASS**.
- Tamper (`output` 81→82): **os 3 rejeitam** (merkle diverge), exit 1.
- `--source` correto → PASS; `--source` errado → FAIL (vincula o artifact ao código).
- `make verify-receipt` roda tudo + teste de tamper; passo adicionado ao CI.

**Duas correções de precisão na proposta original (importantes para credibilidade):**

1. **O recibo de exemplo da proposta tinha `steps=2` e merkle `40b73e65…`** — consistente
   internamente, mas de uma versão antiga do compilador. O compilador **atual** emite
   `steps=4` e merkle `b96feceed2…` para o mesmo source (a contagem de passos faz parte da
   folha, então qualquer mudança de geração altera a raiz sem invalidar o recibo). Os
   fixtures do repo foram gerados com o compilador atual para serem reproduzíveis.
2. **Verificação independente ≠ prova de execução.** Os verificadores conferem que os
   campos do recibo são auto-consistentes e que o `artifact` é o hash do source — mas um
   recibo forjado do zero (campos arbitrários + merkle recomputado) **passa** em qualquer
   verificador independente. Para zero-trust real em computação descentralizada falta:
   - incluir o **source** no recibo (hoje só o hash viaja), e/ou
   - o auditor **re-executar** o source (`--source` é a ponte) ou usar TEE/ZK.
   Recomenda-se adicionar um campo `source` opcional ao formato (v2) e um modo
   `--execute` no verificador independente.

---

## Checklist pós-revisão

```bash
make test-cpu                      # build + check 20/20 + receipt round-trip
make test                          # se tiver OpenCL/PoCL
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL \
  test_lin_full_self_hosted_suite.zig
zig run -lc -I/usr/include -L/usr/lib/x86_64-linux-gnu -lOpenCL \
  test_lin_selfhost_compat_001.zig
$BIN integrity
$BIN cert build /tmp/cert.lin-cert && $BIN cert verify /tmp/cert.lin-cert   # deve ser PASS agora
$BIN receipt verify                               # deve falhar (exit 1) — comportamento novo
$BIN receipt create --source "return x * x;" --input abc   # deve falhar (exit 1)
```
