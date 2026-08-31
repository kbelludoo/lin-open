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
