#!/usr/bin/env python3
# reference_tokenize.py — oraculo INDEPENDENTE de referencia para o lexer LIN
# auto-aplicavel (src/linvm0_compiler/lin_lexer_selfhost.lin).
#
# E uma transcricao fiel de `vmTokenize` (compiler/lin.zig:5678) e do fold
# i64-wrap usado pelo modulo LIN. Ele NAO toca o compilador LIN: serve para
# cross-checkar o checksum que o lexer LIN produz (R4: um digest, um significado;
# R3: dogfooding com oraculo independente).
#
# Uso:
#   python3 src/linvm0_compiler/reference_tokenize.py
# Reporta o checksum e a contagem de tokens para a fonte de teste embutida no
# modulo .lin. Se `lex_gate()` (via `lin vm`) devolve 1, os dois concordam.
M64 = (1 << 64) - 1

def wrap(x):
    x &= M64
    return x - (1 << 64) if x >= (1 << 63) else x

# Fonte de teste — deve casar 1:1 com o array `src` embutido em
# lin_lexer_selfhost.lin (lex_scan_embedded / lex_count_embedded).
SRC = "!proc(a: int) -> int {\n  b = a & 4294967295;\n  ^b;\n}\n"


def is_ident_start(c):
    return ('a' <= c <= 'z') or ('A' <= c <= 'Z') or c == '_' or c == '$'


def is_ident_part(c):
    return is_ident_start(c) or ('0' <= c <= '9')


def tokenize(src):
    toks = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in (' ', '\t', '\r', '\n'):
            i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '"':
            start = i
            i += 1
            while i < n and src[i] != '"':
                if src[i] == '\\' and i + 1 < n:
                    i += 1
                i += 1
            if i < n:
                i += 1
            toks.append((4, src[start:i]))
            continue
        if '0' <= c <= '9':
            start = i
            while i < n and '0' <= src[i] <= '9':
                i += 1
            toks.append((2, src[start:i]))
            continue
        if is_ident_start(c):
            start = i
            while i < n and is_ident_part(src[i]):
                i += 1
            toks.append((1, src[start:i]))
            continue
        if i + 1 < n:
            two = src[i:i + 2]
            if two in ('==', '!=', '<=', '>=', '&&', '||', '->'):
                toks.append((3, two))
                i += 2
                continue
        toks.append((3, src[i:i + 1]))
        i += 1
    return toks


def checksum(toks):
    # fold identico ao modulo LIN:
    #   h = ((h*31)+kind) ; th=((th+byte)*31)... ; h=((h*31)+len); h=((h*31)+th)
    h = 0
    for kind, text in toks:
        h = wrap(h * 31 + kind)
        th = 0
        for ch in text:
            th = wrap((th + ord(ch)) * 31)
        h = wrap(h * 31 + len(text))
        h = wrap(h * 31 + th)
    return h


def main():
    toks = tokenize(SRC)
    print(f"source_len={len(SRC)}")
    print(f"num_tokens={len(toks)}")
    print(f"checksum={checksum(toks)}")
    for kind, text in toks:
        print(f"  kind={kind} text={text!r}")


if __name__ == "__main__":
    main()
