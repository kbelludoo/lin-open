#!/usr/bin/env python3
# lin0_selflex.py — transplantador de corpus do lexer LIN auto-aplicável (B2).
#
# O que faz: pega o módulo do lexer escrito em LIN
# (`src/linvm0_compiler/lin_lexer_selfhost.lin`) e troca o corpus embutido
# (`src: [256]int = [...]`, `n = <N>`) pelos primeiros min(len,256) bytes de um
# arquivo `.lin` QUALQUER — por default o próprio módulo do lexer. O módulo
# gerado é compilado e executado pela LinVM (`lin_c0 vm` / `lin_c0 run`), sem
# Zig, e tem que reproduzir os tokens que o ORÁCULO INDEPENDENTE
# (`reference_tokenize.py`, transcrição de `vmTokenize` do Stage0) computa sobre
# os mesmos bytes — oráculo que este script também usa para preencher
# `lex_scan_expected`/`lex_count_expected`, de modo que `lex_gate()` continue
# sendo a asserção interna do módulo.
#
# Por que isto é um passo de self-hosting e não um enfeite: o front-end LIN lê o
# texto fonte do próprio front-end. O limite é a ISA de hoje (VM_MAX_ARR_LEN =
# 256 células por array), declarado no cabeçalho gerado — não é escolha do
# script. Nada aqui toca o compilador C11 nem o Zig: quem valida é a LinVM.
#
# Uso:
#   python3 test/lin0_selflex.py src/linvm0_compiler/lin_lexer_selfhost.lin \
#       --out /tmp/selflex.lin
# Saída (uma linha por chave, para o gate comparar com grep):
#   target=... bytes=... sha256=... tokens=... checksum=... out=...
import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src", "linvm0_compiler"))
import reference_tokenize as oracle  # oráculo independente (não toca o compilador)

CAP = 256          # VM_MAX_ARR_LEN — limite da ISA atual, não deste script
TEMPLATE_DEFAULT = os.path.join(ROOT, "src", "linvm0_compiler", "lin_lexer_selfhost.lin")


def transplant(template_text, data, cap=CAP):
    """Retorna (fonte_do_modulo_gerado, n_bytes) ou levanta ValueError."""
    n = min(len(data), cap)
    body = list(data[:n]) + [0] * (cap - min(len(data), cap))
    if len(body) != cap:
        raise ValueError("corpus não coube no arranjo de %d células" % cap)
    # chunk por ELEMENTO (16 por linha, como no template). Cortar a 800
    # caracteres quebrava números no meio e mudava o arranjo.
    vals = [str(b) for b in body]
    lit = ",\n    ".join(", ".join(vals[i:i + 16]) for i in range(0, len(vals), 16))

    out, subs = template_text, 0
    out, k = re.subn(r"src: \[%d\]int\s*=\s*\[[^\]]*\]" % cap,
                     "src: [%d]int = [%s]" % (cap, lit), out, flags=re.S)
    subs += k
    if subs != 2:  # lex_scan_embedded + lex_count_embedded
        raise ValueError("esperava 2 literais de corpus no template, achei %d" % subs)

    out, k = re.subn(r"\n  n = \d+;", "\n  n = %d;" % n, out)
    if k != 2:
        raise ValueError("esperava 2 linhas `n = <N>;`, achei %d" % k)
    toks = oracle.tokenize(bytes(data[:n]).decode("latin-1"))
    sum_ = oracle.checksum(toks)
    out, k = re.subn(r"(!lex_scan_expected\(\) -> int \{\n  \^)-?\d+(;)",
                     r"\g<1>%d\g<2>" % sum_, out)
    if k != 1:
        raise ValueError("não localizei lex_scan_expected")
    out, k = re.subn(r"(!lex_count_expected\(\) -> int \{\n  \^)-?\d+(;)",
                     r"\g<1>%d\g<2>" % len(toks), out)
    if k != 1:
        raise ValueError("não localizei lex_count_expected")
    return out, n, len(toks), sum_, toks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="arquivo .lin cujo texto será lexado pelo lexer LIN")
    ap.add_argument("--module", default=TEMPLATE_DEFAULT, help="template do lexer LIN")
    ap.add_argument("--out", required=True, help="arquivo .lin gerado")
    ap.add_argument("--cap", type=int, default=CAP)
    ap.add_argument("--dump-tokens", action="store_true")
    a = ap.parse_args()

    data = open(a.target, "rb").read()
    tpl = open(a.module, encoding="utf-8").read()
    src, n, ntok, csum, toks = transplant(tpl, data, a.cap)

    rel = os.path.relpath(a.target, ROOT)
    banner = (
        "// GERADO POR test/lin0_selflex.py — NÃO EDITE.\n"
        "// corpus = %d primeiros bytes de %s (sha256 %s), cap %d = VM_MAX_ARR_LEN da ISA.\n"
        "// esperado: lex_scan_embedded=%d  lex_count_embedded=%d  (oráculo reference_tokenize.py)\n"
        % (n, rel, hashlib.sha256(data).hexdigest()[:16], a.cap, csum, ntok)
    )
    # injeta o banner como comentário após o cabeçalho @LIN/@LINVM0_LEXER
    lines = src.split("\n")
    at = 0
    while at < len(lines) and lines[at].startswith("@"):
        at += 1
    lines.insert(at, banner)
    src = "\n".join(lines)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(src)

    print("target=%s" % rel)
    print("bytes=%d" % n)
    print("target_sha256=%s" % hashlib.sha256(data).hexdigest())
    print("tokens=%d" % ntok)
    print("checksum=%d" % csum)
    print("out=%s" % a.out)
    if a.dump_tokens:
        for kind, text in toks:
            print("  token kind=%d text=%r" % (kind, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
