#!/usr/bin/env bash
# test/attestation_honesty.sh — executable specification of the attestation guard.
#
# Asserts that:
#   1. every command listed in compiler/lin_attestation_guard.zig refuses to run
#      (exit 3) and writes no receipt unless --allow-simulated is given;
#   2. a simulated run is announced on stderr and logged to
#      simulated_attestations.log;
#   3. cleanroom-verify fails closed on a bundle that does not verify;
#   4. notary-verify verifies real Ed25519 co-signatures, refuses a roster that
#      cannot reach quorum, and rejects every mutation in its adversarial corpus;
#   5. the genuine compute-receipt Merkle round-trip still passes;
#   6. the Zig x C11 N-Version cross-check reaches consensus and rejects a
#      lying second implementation;
#   7. the LIN Gate blocks a change whose tracked-toolchain Merkle root
#      differs from the attested manifest, and opens on an attested tree.
#
# Usage: test/attestation_honesty.sh [path/to/lin_native]
set -u

BIN_ARG="${1:-zig-out/bin/lin_native}"
case "$BIN_ARG" in
  /*) BIN="$BIN_ARG" ;;
  *)  BIN="$PWD/$BIN_ARG" ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

[ -x "$BIN" ] || { echo "attestation-honesty: cannot execute $BIN"; exit 1; }

fails=0
checks=0

ok()   { checks=$((checks + 1)); printf '  ok   %s\n' "$1"; }
bad()  { checks=$((checks + 1)); fails=$((fails + 1)); printf '  FAIL %s\n' "$1"; }
group() { # group <name> — runs the following block in a fresh cwd
  rm -rf "$WORK/$1" && mkdir -p "$WORK/$1"
  cd "$WORK/$1" || exit 1
}

echo "== attestation honesty: $BIN =="
"$BIN" version >/dev/null 2>&1 || { echo "cannot run $BIN"; exit 1; }

# ── 1. gated commands fail closed and write nothing ───────────────────────────
echo "-- gated commands must refuse (exit 3) and write nothing --"
GATED="verify-all audit polyglot-verify test-vectors conformance-verify
pkg-distribute pkg-verify enterprise-verify consistency-verify e2e-trust-verify
verify-003r protocol-evolution-verify longterm-verify verify-004
federation-governance-verify fed-verify verify-fed-001 mir-ssa-verify mir-verify
transpiler-verify nanopass-benchmark nanopass-verify rewrite-benchmark
federation-verify federated-attest global-ledger-verify scale-ledger-verify
temporal-ledger-verify temporal-verify roster-transition-verify recovery-verify
cross-verify multi-verify n-version-verify common-mode-verify"

group gated
refused=0
for cmd in $GATED; do
  "$BIN" "$cmd" >/dev/null 2>&1
  got=$?
  if [ "$got" = 3 ]; then
    refused=$((refused + 1))
  else
    bad "lin $cmd: expected exit 3, got $got"
  fi
done
[ "$refused" != 0 ] && ok "$refused gated command names refused with exit 3"
written=$(ls -A | grep -vc '^simulated_attestations\.log$')
if [ "$written" = 0 ]; then
  ok "no receipt or report file written by any refused command"
else
  bad "refused commands wrote files: $(ls -A | tr '\n' ' ')"
fi

# ── 2. --allow-simulated runs, warns and logs ─────────────────────────────────
echo "-- --allow-simulated must warn and append to simulated_attestations.log --"
group simulated
printf 'garbage\n' > bundle_attestation.rulel
"$BIN" verify-all --allow-simulated >/dev/null 2>err.txt
if grep -q 'SIMULATED ATTESTATION' err.txt; then
  ok "simulated run announces itself on stderr"
else
  bad "no simulation warning on stderr"
fi
if grep -q 'cmd="verify-all" mode="SIMULATED"' simulated_attestations.log 2>/dev/null; then
  ok "simulated run recorded in simulated_attestations.log"
else
  bad "no audit-log entry for the simulated run"
fi

# ── 3. cleanroom-verify fails closed on a bundle that does not verify ─────────
echo "-- cleanroom-verify must fail closed on an unverifiable bundle --"
group cleanroom
printf 'this is not a LIN bundle\n' > bundle_attestation.rulel
"$BIN" cleanroom-verify >/dev/null 2>&1
got=$?
if [ "$got" != 0 ]; then
  ok "garbage bundle refused (exit $got)"
else
  bad "garbage bundle was accepted by cleanroom-verify"
fi
if [ ! -e cleanroom_receipt.rulel ]; then
  ok "no cleanroom receipt written for an unverifiable bundle"
else
  bad "cleanroom receipt written for an unverifiable bundle"
fi

# ── 4. notary quorum: real Ed25519 verification ───────────────────────────────
echo "-- notary-verify must verify real Ed25519 co-signatures --"
group notary

"$BIN" notary-verify >/dev/null 2>&1
if [ $? = 3 ]; then ok "no roster -> NotImplemented (exit 3)"; else bad "missing roster did not fail closed"; fi

if "$BIN" notary-sign -o roster.rulel >/dev/null 2>&1; then
  ok "notary-sign minted a roster with real keys"
else
  bad "notary-sign failed"
fi

if grep -q '1111111111111111' roster.rulel 2>/dev/null; then
  bad "roster still contains placeholder 1111... keys"
else
  ok "roster contains no placeholder 1111... keys"
fi

"$BIN" notary-verify --roster roster.rulel >out.txt 2>&1
if [ $? = 0 ]; then ok "valid roster reaches quorum (exit 0)"; else bad "valid roster rejected"; cat out.txt; fi

n_valid=$(grep -c 'SIGNATURE VALID' out.txt 2>/dev/null)
n_witness=$(grep -c 'PubKey' out.txt 2>/dev/null)
if [ "${n_valid:-0}" = "${n_witness:-1}" ] && [ "${n_valid:-0}" -ge 3 ]; then
  ok "$n_valid/$n_witness co-signatures verified with Ed25519"
else
  bad "expected all $n_witness signatures valid, got ${n_valid:-0}"
fi

if grep -q 'signature_verified=true' transparency_checkpoint_receipt.rulel 2>/dev/null; then
  ok "receipt records per-witness signature verification"
else
  bad "receipt missing signature_verified fields"
fi

# Tamper the notarised state root: every co-signature must become invalid.
sed 's/state_root="sha256:[0-9a-f]\{4\}/state_root="sha256:dead/' roster.rulel > tampered.rulel
"$BIN" notary-verify --roster tampered.rulel >tampered.txt 2>&1
if [ $? != 0 ]; then ok "tampered state root -> quorum refused"; else bad "tampered roster still passed"; fi
if grep -q 'SIGNATURE VALID' tampered.txt 2>/dev/null; then
  bad "a tampered roster produced a valid signature"
else
  ok "zero valid co-signatures after tampering the state root"
fi

# Corrupt two of four co-signatures: a 3-of-4 quorum must fail.
python3 - <<'PY'
lines = open('roster.rulel').read().split('\n')
seen, out = 0, []
for line in lines:
    if line.strip().startswith('.witness_'):
        seen += 1
        if seen >= 3:
            i = line.index('signature_hex="') + len('signature_hex="')
            line = line[:i] + ('1' if line[i] == '0' else '0') + line[i + 1:]
    out.append(line)
open('weak.rulel', 'w').write('\n'.join(out))
PY
"$BIN" notary-verify --roster weak.rulel >weak.txt 2>&1
if [ $? != 0 ]; then
  ok "2-of-4 valid signatures cannot satisfy a 3-of-4 quorum"
else
  bad "quorum satisfied with too few valid signatures"
fi

"$BIN" notary-verify --roster roster.rulel --adversarial >adv.txt 2>&1
if [ $? = 0 ]; then ok "adversarial corpus rejected every mutation"; else bad "adversarial corpus leaked a mutation"; cat adv.txt; fi
if grep -q 'accepted: 0' adv.txt 2>/dev/null; then
  ok "adversarial summary reports 0 accepted mutations"
else
  bad "adversarial summary shows accepted mutations"
fi

# ── 5. the genuine Merkle receipt still round-trips ───────────────────────────
echo "-- real compute receipt (the asset that must keep working) --"
group receipt
"$BIN" receipt create --source "return x * x;" --input 9 > receipt.rulel 2>/dev/null
"$BIN" receipt verify --receipt receipt.rulel >verify.txt 2>&1
if grep -q '^PASS' verify.txt; then
  ok "receipt create -> verify round-trip passes"
else
  bad "receipt round-trip broke"; cat verify.txt
fi
root=$(grep -o 'sha256:[0-9a-f]\{64\}' verify.txt | head -1)
if [ -n "$root" ] && "$BIN" receipt create --source "return x * x;" --input 9 2>/dev/null | grep -q "$root"; then
  ok "Merkle root is deterministic across runs ($root)"
else
  bad "Merkle root is not reproducible"
fi

# ── 6. N-Version: Zig LinVM vs the independent C11 port ───────────────────────
echo "-- N-Version cross-check (Zig LinVM vs transpile/c C11 port) --"
if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
  echo "  SKIP no C compiler available; cannot build the second implementation"
else
  group xver
  if make -C "$REPO_ROOT/transpile/c" xver >build.log 2>&1; then
    ok "C11 second implementation built (transpile/c/bin/lin_c_receipt)"
  else
    bad "could not build the C11 implementation"; tail -5 build.log
  fi

  CBIN="$REPO_ROOT/transpile/c/bin/lin_c_receipt"
  "$BIN" crosscheck-c --c-bin "$CBIN" -o "$WORK/xver/xver_receipt.rulel" >xver.txt 2>&1
  xrc=$?
  if [ "$xrc" = 0 ]; then
    ok "crosscheck-c reached consensus (exit 0)"
  else
    bad "crosscheck-c did not reach consensus (exit $xrc)"; tail -20 xver.txt
  fi
  if grep -q 'divergences 0' xver.txt; then
    vectors=$(grep -o 'CONSENSUS: [0-9]* vectors' xver.txt | grep -o '[0-9]*')
    ok "$vectors vectors agreed across two implementations, 0 divergences"
  else
    bad "divergences reported between Zig and C"
  fi
  if grep -q 'DIVERGE' xver.txt; then
    bad "a vector diverged between the two implementations"
  else
    ok "no per-vector divergence lines"
  fi
  if grep -q 'independent_implementations=2' xver_receipt.rulel 2>/dev/null; then
    ok "receipt records independent_implementations=2"
  else
    bad "receipt missing independent_implementations=2"
  fi
  if grep -q 'engine_b_sha256="sha256:[0-9a-f]\{64\}"' xver_receipt.rulel 2>/dev/null; then
    ok "receipt pins the C binary by SHA-256"
  else
    bad "receipt does not pin the C binary digest"
  fi

  # Fault injection: a "second implementation" that lies must be caught.
  cat > liar.sh <<'EOF'
#!/bin/sh
echo '@LIN:XVER:1.0 engine="C" status="EVALUATED" expr="x" env="x=10" ast_val=999 result=999 steps=1 sp_at_ret=1 insts=1 code_sha256="0000000000000000000000000000000000000000000000000000000000000000" root="sha256:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"'
EOF
  chmod +x liar.sh
  "$BIN" crosscheck-c --c-bin ./liar.sh --expr "x + 1" -o "$WORK/xver/liar_receipt.rulel" >liar.txt 2>&1
  if [ $? != 0 ] && [ ! -e liar_receipt.rulel ]; then
    ok "a lying second implementation is detected (divergence, no receipt)"
  else
    bad "a lying second implementation was accepted"
  fi

  # Missing second implementation must fail closed, not silently pass.
  "$BIN" crosscheck-c --c-bin ./does_not_exist >/dev/null 2>&1
  if [ $? = 3 ]; then
    ok "missing second implementation -> NotImplemented (exit 3)"
  else
    bad "missing second implementation did not fail closed"
  fi
fi

# --- 7. LIN GATE: CI integrity checker must block unattested changes --------
echo
echo "-- LIN Gate (CI integrity checker) --"

group gate_sandbox
mkdir -p compiler transpile/c/lin_c transpile/c/tool transpile/c/test
printf 'const a = 1;\n' > compiler/a.zig
printf 'int b(void) { return 2; }\n' > transpile/c/lin_c/b.c
printf 'int c(void) { return 3; }\n' > transpile/c/tool/c.c
printf 'int t(void) { return 4; }\n' > transpile/c/test/t.c

"$BIN" gate-check --manifest m.rulel >/dev/null 2>&1
if [ $? = 3 ]; then
  ok "gate without a manifest is not evaluable (exit 3)"
else
  bad "gate accepted a missing manifest"
fi

"$BIN" gate-attest --manifest m.rulel >/dev/null 2>&1
if [ $? = 0 ] && [ -f m.rulel ]; then
  ok "gate-attest writes a manifest with the recomputed root"
else
  bad "gate-attest did not write a manifest"
fi

"$BIN" gate-check --manifest m.rulel >open.txt 2>&1
if [ $? = 0 ] && grep -q 'GATE OPEN' open.txt; then
  ok "gate opens on an attested tree"
else
  bad "gate did not open on an attested tree"
fi

root1=$(grep -o 'merkle_root="sha256:[0-9a-f]*"' m.rulel | head -1)
"$BIN" gate-attest --manifest m.rulel >/dev/null 2>&1
root2=$(grep -o 'merkle_root="sha256:[0-9a-f]*"' m.rulel | head -1)
if [ -n "$root1" ] && [ "$root1" = "$root2" ]; then
  ok "gate Merkle root is deterministic across runs"
else
  bad "gate Merkle root is not deterministic ($root1 vs $root2)"
fi

printf '// tampered by a PR\n' >> compiler/a.zig
"$BIN" gate-check --manifest m.rulel >mod.txt 2>&1
if [ $? = 1 ] && grep -q 'MODIFIED' mod.txt; then
  ok "a modified compiler file blocks the gate (exit 1)"
else
  bad "a modified compiler file did not block the gate"
fi
printf 'const a = 1;\n' > compiler/a.zig

printf 'const injected = 0;\n' > compiler/zz_injected.zig
"$BIN" gate-check --manifest m.rulel >add.txt 2>&1
if [ $? = 1 ] && grep -q 'ADDED' add.txt; then
  ok "a new unattested file blocks the gate (exit 1)"
else
  bad "a new unattested file did not block the gate"
fi
rm -f compiler/zz_injected.zig

rm -f transpile/c/lin_c/b.c
"$BIN" gate-check --manifest m.rulel >del.txt 2>&1
if [ $? = 1 ] && grep -q 'DELETED' del.txt; then
  ok "deleting an attested file blocks the gate (exit 1)"
else
  bad "deleting an attested file did not block the gate"
fi

cd "$REPO_ROOT" || exit 1
"$BIN" gate-check >"$WORK/gate_repo.txt" 2>&1
if [ $? = 0 ] && grep -q 'GATE OPEN' "$WORK/gate_repo.txt"; then
  ok "committed manifest matches the tracked toolchain at the repo root"
else
  bad "repo manifest does not match the tree (re-attest: lin gate-attest)"
fi

echo
if [ "$fails" = 0 ]; then
  echo "attestation-honesty: PASS ($checks checks)"
  exit 0
fi
echo "attestation-honesty: FAIL ($fails of $checks checks failed)"
exit 1
