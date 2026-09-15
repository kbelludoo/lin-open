#!/bin/sh
# verify_settlement_store.sh — gate CORE<->STORE<->GATE: LinVM settlement
# durável em store_c0 + recibo unificado LINP+STORE + crash-kill mid-batch.
# Só `cc` + `python3`. Sem Zig/Go.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
HOST_SRC=$ROOT/examples/defi_settlement_proof/settlement_store_host.c
IMG=$ROOT/examples/defi_settlement_proof/settlement_engine.linbc
HOST_BIN=/tmp/settle_store_host_gate
pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL  %s\n        %s\n' "$1" "$2"; }
TMP=$(mktemp -d /tmp/settle_store_XXXXXX)
trap 'rm -rf "$TMP" "$HOST_BIN"' EXIT INT TERM

EXP_CODE="75366e5cb034b36aa96321acd96ffe61638c8809cf06321f4e656eadd589e9bb"
EXP_IMG="4fd10f6846cb16751a7e5754df9c799f1bbbea1f1eac6791a3574328a4311dd4"

# 1. build cc-only zero-warnings
LINC=$ROOT/transpile/c/lin_c
if cc -O2 -std=c11 -Wall -Wextra -I$LINC -I$ROOT/transpile/c/store_c0 \
    -o "$HOST_BIN" "$HOST_SRC" $ROOT/transpile/c/store_c0/store_c0.c \
    $LINC/lin_sha256.c $LINC/lin_common.c $LINC/lin_token.c $LINC/lin_ast.c \
    $LINC/lin_parse.c $LINC/lin_vm.c $LINC/lin_str.c $LINC/lin_linbc1.c \
    $LINC/lin_abi.c $LINC/lin_region.c 2>/tmp/settle_build.log; then
  if grep -qiE "warning|error" /tmp/settle_build.log; then
    bad "build zero-warnings" "$(grep -iE 'warning|error' /tmp/settle_build.log | head -2)"
  else
    ok "build cc-only zero-warnings"
  fi
else
  bad "build cc-only" "$(tail -3 /tmp/settle_build.log)"
fi

# 2. full batch -> unified receipt
if "$HOST_BIN" "$IMG" "$TMP/store" "$TMP/receipt.json" >/tmp/settle_run.log 2>&1; then
  ok "batch 8 swaps commitados (fsync por swap)"
else
  bad "batch exec" "$(tail -3 /tmp/settle_run.log)"
fi
python3 - "$TMP/receipt.json" "$EXP_CODE" "$EXP_IMG" <<'PY' >/tmp/settle_receipt.log 2>&1
import json, sys
r = json.load(open(sys.argv[1]))
assert r["code_root_sha256"] == sys.argv[2], r["code_root_sha256"]
assert r["img_sha256"] == sys.argv[3], r["img_sha256"]
assert r["tx_count"] == 8 and r["applied"] == 6 and r["rejected"] == 2, r
assert r["frames"] == 24 and r["active_keys"] == 17, r
assert r["invariants"] == "CONSERVED" and r["status"] == "ATTESTED_DURABLE", r
assert len(r["state_merkle_root"]) == 64
PY
if [ $? -eq 0 ]; then ok "recibo unificado (code+img+6/2, 24 frames)"; else bad "recibo unificado" "$(tail -2 /tmp/settle_receipt.log)"; fi

# 3. N-version oracle: python reexecuta a matemática + replay do WAL, raiz bit-a-bit
if PYTHONPATH="$ROOT/transpile/c/store_c0" python3 - "$TMP" <<'PY' >/tmp/settle_oracle.log 2>&1; then
import sys, hashlib
sys.path.insert(0, sys.argv[1] + "/../transpile/c/store_c0")
sys.path.insert(0, "/home/k/Downloads/lin-master/transpile/c/store_c0")
import oracle_store
from pathlib import Path
tmp = Path(sys.argv[1])
vecs = [("alice",1000,100000,200000,1970),("bob",5000,1000000,2000000,9000),
        ("carol",1000,100000,200000,1980),("dave",0,100000,200000,1),
        ("erin",10000,1000000,2000000,19000),("frank",700,500000,800000,1000),
        ("grace",1000000,100000,200000,1),("heidi",2500,750000,1500000,4000)]
def settle(ai,ri,ro,mo):
    if ai<=0 or ri<=0 or ro<=0 or mo<=0: return -1
    if ai>1000000 or ri>9000000000000000 or ro>9000000000 or mo>9000000000: return -1
    fee, num, den = ai*997, ai*997*ro, ri*1000+ai*997
    if fee<=0 or num<=0 or den<=0: return -1
    q = num//den
    return q if q>=mo else -1
exp = [settle(*v[1:]) for v in vecs]
frames, kvs = oracle_store.parse_and_replay_wal(str(tmp/"store/store.wal"))
assert frames == 24, frames
for (u, *_), e in zip(vecs, exp):
    got = kvs.get(b"acc:"+u.encode()).decode()
    assert got == str(e), (u, got, e)
    assert (e>=0) == (got != "-1")
assert kvs[b"pool:amm"] == b"750000:1500000", kvs[b"pool:amm"]
assert b"tx:000007" in kvs and b"tx:000008" not in kvs
root = oracle_store.compute_merkle_root(kvs).hex()
import json
assert root == json.load(open(tmp/"receipt.json"))["state_merkle_root"], (root,)
PY
  ok "N-version oracle (matemática + WAL replay + raiz bit-a-bit)"
else
  bad "N-version oracle" "$(tail -3 /tmp/settle_oracle.log)"
fi

# 4. crash-kill mid-settlement: commit 5, stage 6o sem commit, _exit(137)
"$HOST_BIN" "$IMG" "$TMP/crash" "$TMP/crash_receipt.json" --crash-after 5 >/tmp/settle_crash.log 2>&1
if [ $? -eq 137 ]; then ok "crash-kill simulado (exit 137)"; else bad "crash-kill exit" "$(tail -2 /tmp/settle_crash.log)"; fi
if PYTHONPATH="$ROOT/transpile/c/store_c0" python3 - "$TMP" <<'PY' >/tmp/settle_prefix.log 2>&1; then
import sys
sys.path.insert(0, "/home/k/Downloads/lin-master/transpile/c/store_c0")
import oracle_store
from pathlib import Path
frames, kvs = oracle_store.parse_and_replay_wal(str(Path(sys.argv[1])/"crash/store.wal"))
assert frames == 15, frames
assert len([k for k in kvs if k.startswith(b"acc:")]) == 5
assert b"tx:000004" in kvs and b"tx:000005" not in kvs, sorted(k.decode() for k in kvs if k.startswith(b"tx:"))
assert b"acc:frank" not in kvs, "ghost balance de tx nao-commitada!"
assert kvs[b"pool:amm"] == b"1000000:2000000"
_ = oracle_store.compute_merkle_root(kvs)
PY
  ok "prefixo estrito pós-crash (15 frames, sem fantasmas)"
else
  bad "prefixo pós-crash" "$(tail -3 /tmp/settle_prefix.log)"
fi

# 5. checkpoint atômico presente + floppy 4/4 intacto
[ -f "$TMP/store/store.chk" ] && [ "$(wc -c < "$TMP/store/store.chk")" = "80" ] && ok "checkpoint atômico 80B" || bad "checkpoint" "ausente ou tamanho errado"
if python3 "$ROOT/test/test_floppy_lin.py" >/tmp/settle_floppy.log 2>&1; then ok "floppy 4/4 intacto"; else bad "floppy 4/4" "$(tail -2 /tmp/settle_floppy.log)"; fi

printf 'settlement_store: %d pass, %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
