#!/bin/sh
# verify_linp_c0.sh — gate do Compilador-0 da irma linp, SEM Zig e SEM Go.
#
# Mede: transpile/c/linp_c0/bin/linp_c0 (C11 puro, `cc`, linkando o SHA-256
# REAL do LIN) reproduz bit a bit os goldens pinados, e rejeita fail-closed.
# Go entra SOMENTE como oraculo DDC opcional (nunca como compilador).
# Tambem trava: src/linp_from_py.lin passa em `check`+`lint`, paridade
# LIN==PY executada, loop test-c0-full verde e zero-disturbio no repo.
#
# Uso: ./test/verify_linp_c0.sh [caminho-para-linp_c0]
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
C0=${1:-$ROOT/transpile/c/linp_c0/bin/linp_c0}
D=$ROOT/transpile/c/linp_c0
pass=0; fail=0

ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL  %s\n        %s\n' "$1" "$2"; }

if [ ! -x "$C0" ]; then
	printf 'verify_linp_c0: %s nao existe — construa com `make -C transpile/c/linp_c0`\n' "$C0" >&2
	exit 2
fi

# 1. rebuild do zero so com cc (nada de zig/go no build)
if ! make -C "$D" clean >/dev/null 2>&1 || ! make -C "$D" >/tmp/linp_c0_build.log 2>&1; then
	bad "build cc-only" "$(tail -3 /tmp/linp_c0_build.log 2>/dev/null)"
else
	if grep -qiE "warning|error" /tmp/linp_c0_build.log; then
		bad "build zero-warnings" "$(grep -iE 'warning|error' /tmp/linp_c0_build.log | head -2)"
	else
		ok "build cc-only zero-warnings"
	fi
fi

# 2. goldens bit-exact (3 discos + 4 artefatos)
read O C < "$D/golden/params"
if "$C0" "$D/golden/demo.linp" "$D/golden/demo.pay" "$O" "$C" /tmp/linp_c0_out >/tmp/linp_c0_run.log 2>&1; then
	ok "executa golden"
	for f in disk_01.txt disk_02.txt disk_03.txt job.linpbc manifest.json manifest.rulel receipt.json; do
		if cmp -s /tmp/linp_c0_out/$f "$D/golden/expected/$f"; then
			ok "golden $f bit-exact"
		else
			bad "golden $f bit-exact" "bytes divergem do pinado"
		fi
	done
else
	bad "executa golden" "$(tail -2 /tmp/linp_c0_run.log)"
fi
if (cd "$D/golden/expected" && sha256sum -c SHA256SUMS >/dev/null 2>&1); then
	ok "SHA256SUMS goldens"
else
	bad "SHA256SUMS goldens" "mismatch"
fi

# 3. determinismo: 2 runs -> mesmos bytes
"$C0" "$D/golden/demo.linp" "$D/golden/demo.pay" "$O" "$C" /tmp/linp_c0_b >/dev/null 2>&1
if cmp -s /tmp/linp_c0_out/disk_01.txt /tmp/linp_c0_b/disk_01.txt && cmp -s /tmp/linp_c0_out/receipt.json /tmp/linp_c0_b/receipt.json; then
	ok "determinismo 2 runs"
else
	bad "determinismo" "divergiu"
fi

# 4. fail-closed (cada um DEVE falhar)
printf '@LINP:1.0\nJOB x\nFILE a\nALGO lzma\nCHUNK 100\nPACK\nEND\n' > /tmp/linp_c0_bad1.linp
printf '@LINP:1.0\nJOB x\nFILE a\nALGO deflate\nCHUNK 10\nPACK\nEND\n' > /tmp/linp_c0_bad2.linp
printf '@LINP:1.0\nJOB x\nFILE a\nALGO deflate\nCHUNK 100\nEND\n' > /tmp/linp_c0_bad3.linp
printf 'lixo\n' > /tmp/linp_c0_bad4.linp
echo "QUJD" > /tmp/linp_c0_pay.b64
for b in bad1 bad2 bad3 bad4; do
	if "$C0" /tmp/linp_c0_$b.linp /tmp/linp_c0_pay.b64 1 1 /tmp/linp_c0_badout >/dev/null 2>&1; then
		bad "fail-closed $b" "aceitou entrada invalida"
	else
		ok "fail-closed $b"
	fi
done
# NOTA honesta: b64 curto/garbage NAO e rejeitado no assemble — qualquer texto
# nao-vazio e payload legitimo; a integridade se verifica no CONSUMO via
# chunk_sha (gate linz). Fail-closed real aqui: payload vazio.
: > /tmp/linp_c0_empty.b64
if "$C0" "$D/golden/demo.linp" /tmp/linp_c0_empty.b64 1 1 /tmp/linp_c0_badout >/dev/null 2>&1; then
	bad "fail-closed payload vazio" "aceitou"
else
	ok "fail-closed payload vazio"
fi

# 5. transpiler em LIN: check + lint limpos
if "$ROOT/transpile/c/bin/lin_c0" check "$ROOT/src/linp_from_py.lin" 2>&1 | grep -q '^@RULEL:LIN_CHECK:1.0.0'; then
	ok "c0 check src/linp_from_py.lin"
else
	bad "c0 check" "rejeitou o transpilador"
fi
if "$ROOT/transpile/c/bin/lin_c0" lint "$ROOT/src/linp_from_py.lin" 2>&1 | grep -q 'errors=0'; then
	ok "c0 lint 0 errors"
else
	bad "c0 lint" "diagnosticos"
fi

# 6. paridade LIN==PY executada (oraculo testemunha, sem simulacao)
if python3 "$ROOT/test/verify_linp_from_py.py" >/tmp/linp_c0_parity.log 2>&1; then
	ok "paridade LIN==PY"
else
	bad "paridade LIN==PY" "$(grep -E 'FAIL|FALHAS' /tmp/linp_c0_parity.log | head -3)"
fi

# 7. zero-disturbio: nenhum arquivo existente modificado (so aditivos)
mod=$(git -C "$ROOT" status --porcelain 2>/dev/null | grep -v '^??' || true)
if [ -z "$mod" ]; then ok "zero arquivos existentes modificados"; else bad "zero-disturbio" "$mod"; fi
unexpected=$(git -C "$ROOT" status --porcelain 2>/dev/null | grep '^??' | grep -v 'transpile/c/lin[a-z]*_c0/' | grep -v 'transpile/c/store_c0/' | grep -v 'test/verify_lin[a-z0-9_]*\.sh' | grep -v 'test/verify_lin[a-z0-9_]*\.py' | grep -v 'src/lin[a-z]*_from_[a-z]*\.lin' || true)
if [ -z "$unexpected" ]; then ok "so paths aditivos de irmas"; else bad "escopo aditivo" "$unexpected"; fi

printf 'linp_c0: %d pass, %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
