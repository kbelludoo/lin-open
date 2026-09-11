#!/usr/bin/env bash
# ==============================================================================
# test/test_redteam_fixes_external.sh — External Tool Validation for Red Team Fixes
# Uses standard Linux utilities (bash, ulimit, python3) and external compilers
# to strictly verify that LRT-01, LRT-02, and LRT-03 vulnerabilities are dead.
# Zero dependency on internal self-approving logic.
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_RECEIPT="${ROOT_DIR}/transpile/c/bin/lin_c_receipt"
BIN_C0="${ROOT_DIR}/transpile/c/bin/lin_c0"
TMP_DIR="/tmp/lin_redteam_test_$$"
mkdir -p "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "================================================================================"
echo "=== LIN://BREAK RED TEAM FIXES: EXTERNAL VALIDATION TEST HARNESS             ==="
echo "================================================================================"

PASSED_COUNT=0
FAILED_COUNT=0

check() {
    local desc="$1"
    shift
    if "$@"; then
        echo "  [PASS] ${desc}"
        PASSED_COUNT=$((PASSED_COUNT + 1))
    else
        echo "  [FAIL] ${desc}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
}

# ------------------------------------------------------------------------------
# 1. LRT-02: Paren bomb attack under standard and restricted ulimit stack
# ------------------------------------------------------------------------------
echo "-- 1. LRT-02: Paren Bomb Protection (25k, 50k, 60k parentheses) --"

# Generate 25,000 parentheses
python3 -c "print('(' * 25000 + '1' + ')' * 25000)" > "${TMP_DIR}/bomb25k.txt"

# Test 1.1: Standard stack must reject cleanly with code 2 (not 139 / SIGSEGV)
set +e
"${BIN_RECEIPT}" --expr "$(cat "${TMP_DIR}/bomb25k.txt")" --env x=1 > "${TMP_DIR}/out25k.log" 2>&1
RC=$?
set -e
check "25k parens fails-closed with exit code 2 (not SIGSEGV 139)" test "${RC}" -eq 2
check "25k parens error is error.ParseTooDeep" grep -q "error.ParseTooDeep" "${TMP_DIR}/out25k.log"

# Test 1.2: Restricted stack (ulimit -s 1024 = 1 MiB stack)
set +e
bash -c "ulimit -s 1024; '${BIN_RECEIPT}' --expr \"\$(cat '${TMP_DIR}/bomb25k.txt')\" --env x=1" > "${TMP_DIR}/out_ulimit.log" 2>&1
RC_ULIMIT=$?
set -e
check "25k parens under ulimit -s 1024 fails-closed with code 2 (zero SIGSEGV)" test "${RC_ULIMIT}" -eq 2

# Test 1.3: 60,000 parentheses bomb (exact test from Red Team report)
python3 -c "print('(' * 60000 + '42' + ')' * 60000)" > "${TMP_DIR}/bomb60k.txt"
set +e
"${BIN_RECEIPT}" --expr "$(cat "${TMP_DIR}/bomb60k.txt")" --env x=1 > "${TMP_DIR}/out60k.log" 2>&1
RC_60K=$?
set -e
check "60k paren bomb fails-closed with exit code 2 (zero SIGSEGV)" test "${RC_60K}" -eq 2
check "60k paren bomb error is error.ParseTooDeep" grep -q "error.ParseTooDeep" "${TMP_DIR}/out60k.log"

# Test 1.4: 100,000 unary minus bomb (exact test from Red Team report)
python3 -c "print('-' * 100000 + '1')" > "${TMP_DIR}/bomb_unary100k.txt"
set +e
bash -c "ulimit -s 1024; '${BIN_RECEIPT}' --expr \"\$(cat '${TMP_DIR}/bomb_unary100k.txt')\" --env x=1" > "${TMP_DIR}/out_unary100k.log" 2>&1
RC_UNARY100K=$?
set -e
check "100k unary minus bomb fails-closed with exit code 2 under ulimit -s 1024 (zero SIGSEGV)" test "${RC_UNARY100K}" -eq 2
check "100k unary minus error is error.ParseTooDeep" grep -q "error.ParseTooDeep" "${TMP_DIR}/out_unary100k.log"

# Test 1.5: Exact 64/65 boundary for parens and unaries
python3 -c "print('(' * 64 + '1' + ')' * 64)" > "${TMP_DIR}/paren64.txt"
python3 -c "print('(' * 65 + '1' + ')' * 65)" > "${TMP_DIR}/paren65.txt"
python3 -c "print('-' * 64 + '1')" > "${TMP_DIR}/unary64.txt"
python3 -c "print('-' * 65 + '1')" > "${TMP_DIR}/unary65.txt"

set +e
"${BIN_RECEIPT}" --expr "$(cat "${TMP_DIR}/paren64.txt")" --env x=1 > "${TMP_DIR}/out_p64.log" 2>&1
RC_P64=$?
"${BIN_RECEIPT}" --expr "$(cat "${TMP_DIR}/paren65.txt")" --env x=1 > "${TMP_DIR}/out_p65.log" 2>&1
RC_P65=$?
"${BIN_RECEIPT}" --expr "$(cat "${TMP_DIR}/unary64.txt")" --env x=1 > "${TMP_DIR}/out_u64.log" 2>&1
RC_U64=$?
"${BIN_RECEIPT}" --expr "$(cat "${TMP_DIR}/unary65.txt")" --env x=1 > "${TMP_DIR}/out_u65.log" 2>&1
RC_U65=$?
set -e

check "64 parens boundary evaluates cleanly (exit 0, status=EVALUATED)" test "${RC_P64}" -eq 0
check "65 parens boundary rejected with error.ParseTooDeep (exit 2)" test "${RC_P65}" -eq 2
check "64 unaries boundary evaluates cleanly (exit 0, status=EVALUATED)" test "${RC_U64}" -eq 0
check "65 unaries boundary rejected with error.ParseTooDeep (exit 2)" test "${RC_U65}" -eq 2

# ------------------------------------------------------------------------------
# 2. LRT-03: VM Execution under Restricted Native Stack (ulimit -s 1024, 128 KiB thread, array isolation)
# ------------------------------------------------------------------------------
echo "-- 2. LRT-03: VM Execution under Restricted Native Stack & Array Isolation --"

# Test 2.1: Execute lin_c0 VM suite under ulimit -s 1024
set +e
bash -c "ulimit -s 1024; '${BIN_C0}' vm compiler/lin.zig" > "${TMP_DIR}/c0_ulimit.log" 2>&1
RC_C0=$?
set -e
check "lin_c0 VM runs all compiler functions cleanly under ulimit -s 1024 (exit 0)" test "${RC_C0}" -eq 0

# Test 2.2: Context & frame tests (array isolation 111 vs 999, 128 KiB pthread recursion without SIGSEGV)
BIN_CTX="${ROOT_DIR}/transpile/c/bin/test_context"
set +e
"${BIN_CTX}" > "${TMP_DIR}/ctx_test.log" 2>&1
RC_CTX=$?
set -e
check "bin/test_context passes all checks including 128 KiB thread and array isolation" test "${RC_CTX}" -eq 0
check "bin/test_context proves array isolation and zero SIGSEGV" grep -q "22 passed, 0 failed" "${TMP_DIR}/ctx_test.log"

# ------------------------------------------------------------------------------
# 3. LRT-01: Receipt Output Fraud Detection via Independent Cleanroom Oracle
# ------------------------------------------------------------------------------
echo "-- 3. LRT-01: Active Replay Oracle Detects Output Fraud (9x9 = 999999) --"

# Legitimate receipt: f(9) = 81
python3 "${ROOT_DIR}/tools/verify_compute_receipt.py" \
    --receipt "${ROOT_DIR}/benchmarks/fixtures/receipt_sqr9.json" \
    --source "return x * x;" > "${TMP_DIR}/oracle_good.log" 2>&1
check "Genuine receipt f(9)=81 approved by independent oracle" grep -q "PASS: FULL_CONSENSUS" "${TMP_DIR}/oracle_good.log"

# Forged receipt: claim 9x9 = 999999 with forged self-consistent Merkle root
SRC="return x * x;"
SRC_HASH=$(python3 -c "import hashlib; print(hashlib.sha256(b'return x * x;').hexdigest())")
FORGED_LEAF=$(python3 -c "
import hashlib, struct
leaf = hashlib.sha256(b'return x * x;').digest() + struct.pack('<qQQq', 999999, 4, 1, 9)
print('sha256:' + hashlib.sha256(leaf).hexdigest())
")

cat <<EOF > "${TMP_DIR}/forged_sqr.json"
{
  "schema": "LIN_COMPUTE_RECEIPT_1.0",
  "artifact": "sha256:${SRC_HASH}",
  "input": "9",
  "output": "999999",
  "steps": 4,
  "sp_at_ret": 1,
  "merkle_root": "${FORGED_LEAF}"
}
EOF

set +e
python3 "${ROOT_DIR}/tools/verify_compute_receipt.py" \
    --receipt "${TMP_DIR}/forged_sqr.json" \
    --source "return x * x;" > "${TMP_DIR}/oracle_fraud.log" 2>&1
RC_FRAUD=$?
set -e
check "Forged receipt (9x9=999999) rejected with non-zero exit code" test "${RC_FRAUD}" -ne 0
check "Forged receipt rejected with OUTPUT_FRAUD_DETECTED" grep -q "OUTPUT_FRAUD_DETECTED" "${TMP_DIR}/oracle_fraud.log"

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
echo "--------------------------------------------------------------------------------"
echo "RED TEAM FIXES VERIFICATION: ${PASSED_COUNT} passed, ${FAILED_COUNT} failed"
echo "================================================================================"

if [ "${FAILED_COUNT}" -gt 0 ]; then
    exit 1
fi
exit 0
