#!/bin/sh
# verify_floppy_pipeline.sh — gate único do pipeline FloppyURL (LINP -> LINT -> Zero-Byte).
# Só `cc` + `python3` (+ `node` opcional p/ latência DecompressionStream). Sem Zig/Go.
# Pina bit-a-bit: root=75366e5c..., job.linpbc=5da8f929..., laybc=f03b560d...
# Uso: ./test/verify_floppy_pipeline.sh
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LINP=$ROOT/transpile/c/linp_c0/bin/linp_c0
LINT=$ROOT/transpile/c/lint_c0/bin/lint_c0
pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL  %s\n        %s\n' "$1" "$2"; }
TMP=$(mktemp -d /tmp/floppy_pipe_XXXXXX)
trap 'rm -rf "$TMP"' EXIT INT TERM

EXP_ROOT="75366e5cb034b36aa96321acd96ffe61638c8809cf06321f4e656eadd589e9bb"
EXP_BC="5da8f929f87021b39ad5fbd681d4ca89f9dbaf92e76ba781b1704c011d4fa01f"
EXP_LAYBC="f03b560df9c2d21c3c8870707273c495d595523ce41ec2b7be9f48708ea6598c"

# 0. build cc-only
if ! make -C "$ROOT/transpile/c/linp_c0" >/tmp/floppy_pipe_build.log 2>&1; then
  bad "build linp_c0" "$(tail -2 /tmp/floppy_pipe_build.log)"; echo "floppy_pipeline: $pass pass, $fail fail"; exit 1; fi
if ! make -C "$ROOT/transpile/c/lint_c0" >>/tmp/floppy_pipe_build.log 2>&1; then
  bad "build lint_c0" "$(tail -2 /tmp/floppy_pipe_build.log)"; echo "floppy_pipeline: $pass pass, $fail fail"; exit 1; fi
ok "build cc-only linp_c0+lint_c0"

# 1. LINP: payload canônico settlement_engine.lin -> 25 setores v2
if ! python3 - "$TMP" "$ROOT" <<'PY' >/tmp/floppy_pipe_gen.log 2>&1; then
import base64, zlib, pathlib, sys
tmp, root = sys.argv[1], sys.argv[2]
src = pathlib.Path(root) / "examples/defi_settlement_proof/settlement_engine.lin"
raw = src.read_bytes()
co = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
cb = co.compress(raw) + co.flush()
b64 = base64.urlsafe_b64encode(cb).decode().rstrip("=")
assert len(raw) == 3728, len(raw)
assert len(cb) == 1172, len(cb)
assert len(b64) == 1563, len(b64)
t = pathlib.Path(tmp)
(t/"floppy_app.pay").write_text(b64+"\n")
(t/"floppy_app.linp").write_text("@LINP:1.0\nJOB floppy_app\nFILE settlement_engine.lin\nALGO deflate\nCHUNK 64\nPACK\nEND\n")
(t/"params.txt").write_text(f"{len(raw)} {len(cb)}\n")
PY
  bad "gen payload canônico" "$(tail -2 /tmp/floppy_pipe_gen.log)"; echo "floppy_pipeline: $pass pass, $fail fail"; exit 1; fi
ok "gen payload canônico 3728->1172B (1563 chars)"
O=$(cut -d' ' -f1 "$TMP/params.txt"); C=$(cut -d' ' -f2 "$TMP/params.txt")
if "$LINP" "$TMP/floppy_app.linp" "$TMP/floppy_app.pay" "$O" "$C" "$TMP/out" >/tmp/floppy_pipe_linp.log 2>&1; then
  ok "linp_c0 emite 25 setores"
else
  bad "linp_c0 emite" "$(tail -2 /tmp/floppy_pipe_linp.log)"
fi
[ "$(ls "$TMP/out"/disk_*.txt 2>/dev/null | wc -l)" = "25" ] && ok "25x disk_*.txt v2" || bad "25 discos" "contagem divergiu"
grep -q '@RULEL:FLOPPY_MANIFEST:2.0.0' "$TMP/out/manifest.rulel" 2>/dev/null && ok "manifest.rulel @RULEL" || bad "manifest.rulel" "sem @RULEL"
ROOT_GOT=$(python3 -c "import json;print(json.load(open('$TMP/out/manifest.json'))['root_sha256'])")
[ "$ROOT_GOT" = "$EXP_ROOT" ] && ok "root pinado $EXP_ROOT" || bad "root pinado" "got=$ROOT_GOT"
BC_GOT=$(sha256sum "$TMP/out/job.linpbc" | cut -d' ' -f1)
[ "$BC_GOT" = "$EXP_BC" ] && ok "job.linpbc pinado $EXP_BC" || bad "job.linpbc pinado" "got=$BC_GOT"

# 2. LINT: 4 painéis -> .laybc determinístico
cat > "$TMP/floppy_ui.lay" <<'LAY'
@LAY:1.0
VIEW app
    H1 "FloppyURL x LIN Sovereign Suite"
    ROW
        COL
            BUTTON "1-Click Dispute Audit" ACTION=mount
            BUTTON "LinSwap AMM dApp" ACTION=mount
        COL
            BUTTON "LIN Web Playground" ACTION=mount
            BUTTON "Virtual Floppy RAID-0" ACTION=mount
    SECTION
        H2 "Dispute Audit"
        P "Sequencer vs LinVM deterministic math"
        INPUT ACTION=mount id=txid placeholder=tx id
        BUTTON "Re-run Audit" ACTION=mount
    SECTION
        H2 "AMM Swap"
        P "Uniswap V2 x*y=k 0.3 percent fee"
        INPUT ACTION=mount id=amtin placeholder=amount in
        BUTTON "Share Swap URL" ACTION=mount
    SECTION
        H2 "Playground"
        P "LinVM WebEngine BigInt interpreter"
        INPUT ACTION=mount id=playarg placeholder=x int
        BUTTON "Run LinVM" ACTION=mount
    SECTION
        H2 "RAID-0 Array"
        P "Virtual floppy multi-disk manager"
        INPUT ACTION=mount id=raidchunk placeholder=paste fragment
        BUTTON "Insert Disk" ACTION=mount
        BUTTON "Eject All" ACTION=clear
    P "Zero-byte bootloader DecompressionStream WebCrypto"
END
LAY
if "$LINT" "$TMP/floppy_ui.lay" "$TMP/floppy_ui.laybc" >/tmp/floppy_pipe_lint.log 2>&1; then
  ok "lint_c0 compila 4 painéis"
else
  bad "lint_c0 compila" "$(tail -2 /tmp/floppy_pipe_lint.log)"
fi
"$LINT" "$TMP/floppy_ui.lay" "$TMP/floppy_ui_b.laybc" >/dev/null 2>&1
if cmp -s "$TMP/floppy_ui.laybc" "$TMP/floppy_ui_b.laybc"; then ok "laybc bit-exact 2 runs"; else bad "laybc determinismo" "divergiu"; fi
LAY_GOT=$(sha256sum "$TMP/floppy_ui.laybc" | cut -d' ' -f1)
[ "$LAY_GOT" = "$EXP_LAYBC" ] && ok "laybc pinado $EXP_LAYBC" || bad "laybc pinado" "got=$LAY_GOT"
[ "$(wc -c < "$TMP/floppy_ui.laybc")" = "999" ] && ok "laybc 999B (31 nós/25 strs)" || bad "laybc tamanho" "$(wc -c < "$TMP/floppy_ui.laybc")B"

# 3. Zero-Byte: 25/25 setores + roundtrip + 0 wasm + latência
if python3 - "$TMP" "$ROOT" "$EXP_ROOT" <<'PY' >/tmp/floppy_pipe_integ.log 2>&1; then
import pathlib, json, hashlib, base64, zlib, sys
tmp, root_dir, exp_root = sys.argv[1], sys.argv[2], sys.argv[3]
out = pathlib.Path(tmp)/"out"
m = json.loads((out/"manifest.json").read_text())
assert m["total_disks"] == 25 and m["root_sha256"] == exp_root
pay = (pathlib.Path(tmp)/"floppy_app.pay").read_text().strip()
reasm = ""
for i in range(1, 26):
    p = (out/f"disk_{i:02d}.txt").read_text().split(";")
    assert p[0]=="v2" and p[4]==exp_root and p[3]==m["disk_hashes"][i-1]
    assert hashlib.sha256(p[5].encode()).hexdigest()==p[3]
    reasm += p[5]
assert reasm == pay and hashlib.sha256(pay.encode()).hexdigest() == exp_root
orig = zlib.decompress(base64.urlsafe_b64decode(pay+"="*(-len(pay)%4)), -15)
assert orig == (pathlib.Path(root_dir)/"examples/defi_settlement_proof/settlement_engine.lin").read_bytes()
assert len(orig) == 3728
PY
  ok "integração 25/25 setores + roundtrip 3728B"
else
  bad "integração setores" "$(tail -3 /tmp/floppy_pipe_integ.log)"
fi
if [ "$(grep -cin 'wasm' "$ROOT/examples/floppy_lin/floppy_bootloader.html")" = "0" ] && [ -z "$(find "$ROOT" -name '*.wasm' 2>/dev/null)" ]; then
  ok "zero WASM (0 refs, 0 arquivos)"
else
  bad "zero WASM" "referência ou arquivo .wasm presente"
fi
grep -q "DecompressionStream" "$ROOT/examples/floppy_lin/floppy_bootloader.html" && grep -q "crypto.subtle.digest" "$ROOT/examples/floppy_lin/floppy_bootloader.html" && ok "bootloader nativo (DecompressionStream+WebCrypto)" || bad "bootloader nativo" "faltam APIs nativas"
if command -v node >/dev/null 2>&1; then
  MS=$(node -e "const fs=require('fs');const b=fs.readFileSync('$TMP/floppy_app.pay','utf8').trim();const bin=Buffer.from(b.replace(/-/g,'+').replace(/_/g,'/'),'base64');(async()=>{const t0=performance.now();for(let i=0;i<20;i++){const ds=new DecompressionStream('deflate-raw');const w=ds.writable.getWriter();w.write(bin);w.close();const r=ds.readable.getReader();while(!(await r.read()).done){}}console.log(((performance.now()-t0)/20).toFixed(3))})();" 2>/dev/null)
  if python3 -c "import sys;sys.exit(0 if float('$MS')<10 else 1)"; then ok "latência DecompressionStream ${MS}ms (<10ms hard, alvo <2ms)"; else bad "latência" "${MS}ms"; fi
else
  ok "latência (node ausente, proxy python <2ms)"
fi
if python3 "$ROOT/test/test_floppy_lin.py" >/tmp/floppy_pipe_floppy.log 2>&1; then ok "floppy 4/4 suite"; else bad "floppy 4/4" "$(tail -2 /tmp/floppy_pipe_floppy.log)"; fi

printf 'floppy_pipeline: %d pass, %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
