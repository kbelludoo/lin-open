#!/bin/sh
# verify_grant_artifacts.sh — cheap, no-Zig gate that the grant package is
# present, compiles, and produces the observable proof output.
#
# This is NOT a claim of production readiness. It catches obvious packaging
# regressions and is deliberately runnable in CI or locally with cc + Python.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
C0=$ROOT/transpile/c/bin/lin_c0
XC=$ROOT/transpile/c/bin/lin_c_receipt
PY=$ROOT/lin_verify.py

pass=0
fail=0

expect_file() {
  label=$1; path=$2
  if [ -f "$path" ]; then pass=$((pass + 1)); printf '  ok    %s (%s)\n' "$label" "$path"; \
  else fail=$((fail + 1)); printf '  FAIL  %s: missing %s\n' "$label" "$path"; fi
}

expect_run() {
  label=$1; shift
  if "$@" >/dev/null 2>&1; then pass=$((pass + 1)); printf '  ok    %s\n' "$label"; \
  else fail=$((fail + 1)); printf '  FAIL  %s\n' "$label"; fi
}

printf 'verify_grant_artifacts — grant package self-check (no Zig)\n'

expect_file "proposta"            "$ROOT/GRANT_PROPOSAL.md"
expect_file "spec formal"         "$ROOT/FORMAL_SPECIFICATION.md"
expect_file "rationalist status"  "$ROOT/docs/RATIONALIST_PROOF_STATUS.md"
expect_file "licence"             "$ROOT/LICENSE"
expect_file "licence rulel"       "$ROOT/LICENSE.rulel"
expect_file "cli verifier"        "$PY"
expect_file "external proof"      "$ROOT/test/prove_all_claims_external.py"
expect_file "fuzz harness"        "$ROOT/test/fuzz_differential.py"
expect_file "benchmark harness"   "$ROOT/test/benchmark_audit_cost.py"
expect_file "c0 host binary"      "$C0"
expect_file "c receipt binary"    "$XC"

if [ ! -x "$C0" ]; then
  printf '  build ... make -C transpile/c all\n'
  make -C "$ROOT/transpile/c" all >/dev/null || { printf 'FAIL: C build failed\n' >&2; exit 2; }
fi

expect_run "receipt verifier"          python3 "$PY" receipt "$ROOT/benchmarks/fixtures/receipt_sqr9.json"
expect_run "provenance"                python3 "$PY" provenance
expect_run "selfhost gates"            python3 "$PY" selfhost
expect_run "quick proof (100 vectors)" python3 "$ROOT/test/prove_all_claims_external.py" --iterations 100
expect_run "quick fuzz (10 vectors)"   python3 "$ROOT/test/fuzz_differential.py" --iterations 10
expect_run "quick benchmark (10)"      python3 "$ROOT/test/benchmark_audit_cost.py" --iterations 10

printf '\n'
if [ "$fail" -ne 0 ]; then
  printf 'VERIFY-GRANT: FAIL (%d failed, %d ok)\n' "$fail" "$pass"
  exit 1
fi
printf 'VERIFY-GRANT: PASS (%d checks, no Zig)\n' "$pass"
