#!/usr/bin/env bash
# test/test_receipt_soundness.sh — Adversarial receipt soundness & anti-fraud verification suite.
# Asserts that:
#   1. Genuine compute receipts generate reproducible and valid SHA-256 Merkle roots.
#   2. Full execution replay with source code verifies bit-exact outputs.
#   3. Forged outputs (output fraud) are detected and rejected.
#   4. Tampered Merkle roots, artifact hashes, inputs, steps, and stack depths are rejected.
#   5. Both C11 host (lin_c0) and independent Python oracle agree on verdicts.

set -u

C0_BIN="${C0_BIN:-transpile/c/bin/lin_c0}"
ZIG_BIN="${BIN:-zig-out/bin/lin_native}"
PYTHON="${PYTHON:-python3}"
ORACLE="tools/verify_compute_receipt.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

[ -x "$C0_BIN" ] || { echo "test_receipt_soundness: cannot execute $C0_BIN"; exit 1; }
[ -f "$ORACLE" ] || { echo "test_receipt_soundness: cannot find $ORACLE"; exit 1; }

fails=0
checks=0

ok()   { checks=$((checks + 1)); printf '  ok   %s\n' "$1"; }
bad()  { checks=$((checks + 1)); fails=$((fails + 1)); printf '  FAIL %s\n' "$1"; }

echo "================================================================================"
echo "=== LIN COMPUTE RECEIPT SOUNDNESS & ANTI-FRAUD TEST HARNESS                  ==="
echo "================================================================================"

# ── 1. Genuine Receipt Round-Trip (lin_c0 + independent oracle) ───────────────
echo "-- 1. Genuine compute receipt round-trip --"
SRC="return x * x;"
"$C0_BIN" receipt create --source "$SRC" --input 9 > "$WORK/genuine.rulel" 2>/dev/null
if [ $? -eq 0 ] && [ -s "$WORK/genuine.rulel" ]; then
    ok "genuine receipt created via lin_c0"
else
    bad "failed to create genuine receipt"
fi

"$C0_BIN" receipt verify --receipt "$WORK/genuine.rulel" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ok "genuine receipt verified structurally by lin_c0"
else
    bad "genuine receipt failed structural verification by lin_c0"
fi

"$PYTHON" "$ORACLE" --receipt "$WORK/genuine.rulel" --source "$SRC" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ok "genuine receipt verified with full execution replay (f(9)=81) by Python oracle"
else
    bad "genuine receipt failed replay verification by Python oracle"
fi

# ── 2. Attack: Output Fraud (Fake output value with forged self-hash) ──────────
echo "-- 2. Adversarial: Output fraud (forged output with self-sealed leaf) --"
"$PYTHON" -c "
import hashlib, struct
art = hashlib.sha256(b'$SRC').digest()
leaf = art + struct.pack('<qQQq', 99999999, 2, 1, 9)
root = hashlib.sha256(leaf).hexdigest()
open('$WORK/forged_output.rulel', 'w').write(f'''@RULEL:RECEIPT:1.0.0
.a=\"sha256:{art.hex()}\"
.i=9
.o=99999999
.s=2
.p=1
.m=\"sha256:{root}\"
''')
"

"$PYTHON" "$ORACLE" --receipt "$WORK/forged_output.rulel" --source "$SRC" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "output fraud rejected by independent execution replay"
else
    bad "output fraud was accepted by independent execution replay!"
fi

# ── 3. Attack: Tampered Merkle Root ───────────────────────────────────────────
echo "-- 3. Adversarial: Tampered Merkle root --"
sed 's/\.m="sha256:[0-9a-f]*/\.m="sha256:0000000000000000000000000000000000000000000000000000000000000000/' \
    "$WORK/genuine.rulel" > "$WORK/tampered_root.rulel"

"$C0_BIN" receipt verify --receipt "$WORK/tampered_root.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered Merkle root rejected by lin_c0"
else
    bad "tampered Merkle root accepted by lin_c0!"
fi

"$PYTHON" "$ORACLE" --receipt "$WORK/tampered_root.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered Merkle root rejected by Python oracle"
else
    bad "tampered Merkle root accepted by Python oracle!"
fi

# ── 4. Attack: Tampered Input Field ───────────────────────────────────────────
echo "-- 4. Adversarial: Tampered input field --"
sed 's/\.i=9/\.i=10/' "$WORK/genuine.rulel" > "$WORK/tampered_input.rulel"

"$C0_BIN" receipt verify --receipt "$WORK/tampered_input.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered input rejected by lin_c0"
else
    bad "tampered input accepted by lin_c0!"
fi

"$PYTHON" "$ORACLE" --receipt "$WORK/tampered_input.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered input rejected by Python oracle"
else
    bad "tampered input accepted by Python oracle!"
fi

# ── 5. Attack: Tampered Steps Field ───────────────────────────────────────────
echo "-- 5. Adversarial: Tampered steps count --"
sed 's/\.s=[0-9]*/\.s=999/' "$WORK/genuine.rulel" > "$WORK/tampered_steps.rulel"

"$C0_BIN" receipt verify --receipt "$WORK/tampered_steps.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered steps count rejected by lin_c0"
else
    bad "tampered steps count accepted by lin_c0!"
fi

"$PYTHON" "$ORACLE" --receipt "$WORK/tampered_steps.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered steps count rejected by Python oracle"
else
    bad "tampered steps count accepted by Python oracle!"
fi

# ── 6. Attack: Tampered Stack Depth (sp) ──────────────────────────────────────
echo "-- 6. Adversarial: Tampered stack depth (sp) --"
sed 's/\.p=[0-9]*/\.p=999/' "$WORK/genuine.rulel" > "$WORK/tampered_sp.rulel"

"$C0_BIN" receipt verify --receipt "$WORK/tampered_sp.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered stack depth rejected by lin_c0"
else
    bad "tampered stack depth accepted by lin_c0!"
fi

"$PYTHON" "$ORACLE" --receipt "$WORK/tampered_sp.rulel" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "tampered stack depth rejected by Python oracle"
else
    bad "tampered stack depth accepted by Python oracle!"
fi

# ── 7. Attack: Source Mismatch ────────────────────────────────────────────────
echo "-- 7. Adversarial: Source mismatch with artifact digest --"
"$PYTHON" "$ORACLE" --receipt "$WORK/genuine.rulel" --source "return x + 1;" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    ok "differing source code rejected by oracle (digest mismatch)"
else
    bad "differing source code was accepted by oracle!"
fi

# ── 8. JSON Format Verification ───────────────────────────────────────────────
echo "-- 8. JSON receipt format verification --"
"$C0_BIN" receipt create --source "$SRC" --input 9 --format json > "$WORK/genuine.json" 2>/dev/null
if [ $? -eq 0 ] && [ -s "$WORK/genuine.json" ]; then
    ok "JSON compute receipt created via lin_c0"
else
    bad "failed to create JSON receipt"
fi

"$C0_BIN" receipt verify --receipt "$WORK/genuine.json" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ok "JSON receipt verified structurally by lin_c0"
else
    bad "JSON receipt failed structural verification by lin_c0"
fi

"$PYTHON" "$ORACLE" --receipt "$WORK/genuine.json" --source "$SRC" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ok "JSON receipt verified with full execution replay by Python oracle"
else
    bad "JSON receipt failed replay verification by Python oracle"
fi

echo "--------------------------------------------------------------------------------"
if [ "$fails" -eq 0 ]; then
    echo "RECEIPT SOUNDNESS GATE: PASS ($checks checks, 0 failures)"
    exit 0
else
    echo "RECEIPT SOUNDNESS GATE: FAIL ($fails of $checks checks failed)"
    exit 1
fi
