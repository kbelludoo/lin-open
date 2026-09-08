#!/usr/bin/env bash
# test/verify_opencl_host_freshness.sh — gate contra binario OpenCL stale.
# Falha se:
#   1. binario ausente ou mais velho que .c/.cl
#   2. binario imprime strings legadas de marketing (prova de stale)
#   3. paridade 2000/2000 nao confere no dataset canonico
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="$ROOT/examples/defi_settlement_proof/u256_opencl_host"
SRC="$ROOT/examples/defi_settlement_proof/u256_opencl_host.c"
KCL="$ROOT/examples/defi_settlement_proof/u256_opencl_kernel.cl"
JSON="$ROOT/test/pilot_harness/mainnet_real_swaps_2000.json"
BIN="/tmp/gate_swaps.bin"

[ -f "$HOST" ] || { echo "FAIL: host binario ausente: $HOST"; exit 1; }
[ -f "$SRC" ] || { echo "FAIL: fonte ausente: $SRC"; exit 1; }
if [ "$SRC" -nt "$HOST" ] || [ "$KCL" -nt "$HOST" ]; then
  echo "FAIL: binario stale (fonte mais novo que binario). Recompile:"
  echo "  cc -O3 $SRC -lOpenCL -o $HOST"
  ls -l --time-style=full-iso "$HOST" "$SRC" "$KCL"
  exit 1
fi
echo "ok: binario mais novo que fontes"

# Gera .bin deterministicamente do JSON (128B/swap: ain,rin,rout,exp big-endian)
python3 - "$JSON" "$BIN" <<'PY'
import json,sys
jp, bp = sys.argv[1], sys.argv[2]
d = json.load(open(jp))
swaps = d if isinstance(d, list) else d.get("swaps", [])
with open(bp, "wb") as f:
    for s in swaps:
        for v in (int(s.get("amount_in",0)), int(s.get("reserve_in",0)),
                  int(s.get("reserve_out",0)),
                  int(s.get("expected_out_real", s.get("amount_out", s.get("expected_out",0))))):
            f.write(v.to_bytes(32, byteorder="big"))
print(f"bin: {len(swaps)} swaps -> {bp}")
PY

OUT="$("$HOST" "$BIN" 2>&1)"
echo "$OUT" | tail -n 12
echo "$OUT" | grep -q "Tempo do kernel" || { echo "FAIL: binario legado (sem 'Tempo do kernel'). Recompile do fonte atual."; exit 1; }
echo "$OUT" | grep -q "NAO e' pico" || { echo "FAIL: aviso de batch-size ausente (binario stale)."; exit 1; }
echo "$OUT" | grep -q "proveniencia" || { echo "FAIL: aviso de proveniencia ausente."; exit 1; }
echo "$OUT" | grep -q "PARIDADE BIT-EXACT em 2000/2000" || { echo "FAIL: paridade 2000/2000 nao confirmada."; exit 1; }
echo "PASS: opencl host fresco + honesto + paridade 2000/2000"

# Sustentado: --repeat 5 no mesmo contexto (JIT amortizado, sem drift)
OUT_R="$("$HOST" "$BIN" --repeat 5 2>&1)"
echo "$OUT_R" | grep -q "Sustentado --repeat 5" || { echo "FAIL: flag --repeat ausente (recompile)."; exit 1; }
echo "$OUT_R" | grep -q "PARIDADE BIT-EXACT em 2000/2000" || { echo "FAIL: paridade --repeat 5 falhou."; exit 1; }
echo "PASS: --repeat 5 sustentado, sem drift"

# Lote 10k (5x repeticao deterministica do corpus 2000): prova saturacao
python3 - "$JSON" /tmp/gate_swaps_10k.bin <<'PY'
import json,sys
d = json.load(open(sys.argv[1]))
big = (d * 5)[:10000]
with open(sys.argv[2], "wb") as f:
    for s in big:
        for v in (int(s.get("amount_in",0)), int(s.get("reserve_in",0)),
                  int(s.get("reserve_out",0)), int(s.get("expected_out_real",0))):
            f.write(v.to_bytes(32, byteorder="big"))
print(f"bin10k: {len(big)} swaps")
PY
OUT_10K="$("$HOST" /tmp/gate_swaps_10k.bin 2>&1)"
echo "$OUT_10K" | grep -q "PARIDADE BIT-EXACT em 10000/10000" || { echo "FAIL: paridade 10k falhou."; echo "$OUT_10K" | tail -n 12; exit 1; }
echo "$OUT_10K" | tail -n 6
echo "PASS: lote 10k paridade + throughput de saturacao medido"
