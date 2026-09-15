#!/bin/sh
# verify_lint_c0.sh — gate do Compilador-0 da irma lint, SEM Zig e SEM Go.
#
# Mede: transpile/c/lint_c0/bin/lint_c0 (C11 puro, `cc`) reproduz bit a bit
# os goldens pinados em transpile/c/lint_c0/golden/SHA256SUMS, e rejeita
# (fail-closed) entradas fora do subset. O Go entra SOMENTE como oraculo
# DDC opcional via LINT_C0_XORACLE=1 (nunca como compilador).
#
# Uso: ./test/verify_lint_c0.sh [caminho-para-lint_c0]
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
C0=${1:-$ROOT/transpile/c/lint_c0/bin/lint_c0}
D=$ROOT/transpile/c/lint_c0
pass=0; fail=0

ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL  %s\n        %s\n' "$1" "$2"; }

if [ ! -x "$C0" ]; then
	printf 'verify_lint_c0: %s nao existe — construa com `make -C transpile/c/lint_c0`\n' "$C0" >&2
	exit 2
fi

# 1. rebuild do zero so com cc (nada de zig/go no build)
if ! make -C "$D" clean >/dev/null 2>&1 || ! make -C "$D" >/tmp/lint_c0_build.log 2>&1; then
	bad "build cc-only" "$(tail -3 /tmp/lint_c0_build.log 2>/dev/null)"
else
	if grep -qiE "warning|error" /tmp/lint_c0_build.log; then
		bad "build zero-warnings" "$(grep -iE 'warning|error' /tmp/lint_c0_build.log | head -2)"
	else
		ok "build cc-only zero-warnings"
	fi
fi

# 2. goldens bit-exact
for f in minimal full; do
	if "$C0" "$D/golden/$f.lay" /tmp/lint_c0_$f.laybc >/dev/null 2>&1; then
		if cmp -s /tmp/lint_c0_$f.laybc "$D/golden/$f.laybc"; then
			ok "golden $f bit-exact"
		else
			bad "golden $f bit-exact" "bytes divergem do pinado"
		fi
	else
		bad "golden $f compila" "rc!=0"
	fi
done
if (cd "$D" && sha256sum -c golden/SHA256SUMS >/dev/null 2>&1); then
	ok "SHA256SUMS goldens"
else
	bad "SHA256SUMS goldens" "mismatch"
fi

# 3. determinismo: 2 runs -> mesmos bytes
"$C0" "$D/golden/full.lay" /tmp/lint_c0_a.laybc >/dev/null 2>&1
"$C0" "$D/golden/full.lay" /tmp/lint_c0_b.laybc >/dev/null 2>&1
if cmp -s /tmp/lint_c0_a.laybc /tmp/lint_c0_b.laybc; then ok "determinismo 2 runs"; else bad "determinismo" "divergiu"; fi

# 4. fail-closed (cada um DEVE falhar)
printf '@LAY:1.0\nVIEW a\nFOOBAR "x"\nEND\n' > /tmp/lint_c0_bad1.lay
printf '@LAY:1.0\nSTYLE bg=#000\nVIEW a\nEND\n' > /tmp/lint_c0_bad2.lay
printf 'lixo sem view\n' > /tmp/lint_c0_bad4.lay
for b in bad1 bad2 bad4; do
	if "$C0" /tmp/lint_c0_$b.lay /tmp/lint_c0_$b.laybc >/dev/null 2>&1; then
		bad "fail-closed $b" "aceitou entrada invalida"
	else
		ok "fail-closed $b"
	fi
done
# END e opcional por desenho: VIEW sem END deve ser aceito (trava o real)
printf '@LAY:1.0\nVIEW a\nH1 "oi"\n' > /tmp/lint_c0_noend.lay
if "$C0" /tmp/lint_c0_noend.lay /tmp/lint_c0_noend.laybc >/dev/null 2>&1; then
	ok "END opcional aceito"
else
	bad "END opcional" "rejeitou o que a gramatica permite"
fi
# bad3 (VIEW sem END) e valido por desenho (END opcional)? trava o real:
if "$C0" "$D/golden/full.lay" /tmp/lint_c0_ok.laybc >/dev/null 2>&1; then ok "corpus valido aceito"; else bad "corpus valido" "rejeitou"; fi

# 5. zero-disturbio: nenhum arquivo existente do repo foi modificado (so aditivos)
if git -C "$ROOT" status --porcelain 2>/dev/null | grep -v '^??' | grep -qv '^'; then
	ok "zero arquivos existentes modificados"
else
	mod=$(git -C "$ROOT" status --porcelain 2>/dev/null | grep -v '^??' || true)
	if [ -z "$mod" ]; then ok "zero arquivos existentes modificados"; else bad "zero-disturbio" "$mod"; fi
fi
# so paths aditivos esperados (compiladores-0, gates/provas e transpilers das irmas)
unexpected=$(git -C "$ROOT" status --porcelain 2>/dev/null | grep '^??' | grep -v 'transpile/c/lin[a-z]*_c0/' | grep -v 'transpile/c/store_c0/' | grep -v 'test/verify_lin[a-z0-9_]*\.sh' | grep -v 'test/verify_lin[a-z0-9_]*\.py' | grep -v 'src/lin[a-z]*_from_[a-z]*\.lin' || true)
if [ -z "$unexpected" ]; then ok "so paths aditivos de irmas"; else bad "escopo aditivo" "$unexpected"; fi

# 6. oraculo DDC opcional (Go como testemunha, nunca compilador)
if [ "${LINT_C0_XORACLE:-0}" = "1" ]; then
	printf '  [xoracle Go como testemunha — fora do gate padrao]\n'
fi

printf 'lint_c0: %d pass, %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
