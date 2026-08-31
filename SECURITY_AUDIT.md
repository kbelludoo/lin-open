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

| Item | Ação | Prioridade |
|---|---|---|
| Receipt Merkle | Manter como a prova principal e publicá-lo (CI já faz). | ✅ já OK |
| Paridade GPU | Não alegar "prova". Reclassificar como **teste de conformidade/determinismo** (comparação de duas implementações), não como criptografia. | Alta |
| `[PASS]` hardcoded | Reescrever como **asserções computadas reais** (comparar resultado de fato). | Alta |
| Certificado auto-ref | Remover `compiler_sha256=/proc/self/exe` da "prova"; usar só hashes de fonte+dados. | Alta |
| Corpus deletado | Restaurar `gpu_parallel_map_kernels.lin` ou repontar o runner. | Média |
| Prova real | Se o objetivo for prova de execução à prova de adversário, usar **TEE/attestation** (ex.: enclave com medida de execução) ou **ZK**, não OpenCL. | Estratégico |

Conclusão honesta: o que hoje se chama de "verificação" é em grande parte **determinismo +
auto-consistência**, não **prova criptográfica à prova de falsificação**. Reclassificar a
comunicação para "execução determinística com receipt auditable" e corrigir os itens acima é
o caminho certo.
