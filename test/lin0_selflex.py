#!/usr/bin/env python3
"""
lin0_selflex.py — gerador do passo B2 de auto-aplicação (sem Zig).

O que ele faz
-------------
Pega um módulo `.lin`, recorta os primeiros 256 bytes do seu TEXTO (o teto
`VM_MAX_ARR_LEN` da ISA) e emite um novo módulo `.lin` que embute esse recorte
como array local e roda sobre ele o LEXER LIN de
`src/linvm0_compiler/lin_lexer_selfhost.lin` — ou seja: o lexer escrito em LIN
tokeniza o texto do próprio front-end.

O módulo gerado expõe as mesmas funções do módulo original:

    lex_scan_embedded()   -> fold i64 (checksum) dos tokens
    lex_count_embedded()  -> número de tokens
    lex_scan_expected()   -> constante: checksum do ORÁCULO independente
    lex_count_expected()  -> constante: contagem do ORÁCULO independente
    lex_gate()            -> 1 sse embutido == oráculo (dentro da LinVM)

Honestidade (R5)
----------------
`lex_scan_expected`/`lex_count_expected` são transcritos do oráculo Python
abaixo (uma reimplementação byte a byte de `vmTokenize`,
`compiler/lin.zig:5678`, independente do compilador). O que `lex_gate()==1`
prova, portanto, é que o lexer **em LIN, executado na LinVM**, reproduz o
oráculo sobre um texto que ele não foi escrito para conter — não é uma
tautologia: o fold é recomputado em tempo de execução pela VM.

Uso
---
    python3 test/lin0_selflex.py <fonte.lin> --out <gerado.lin>
    python3 test/lin0_selflex.py <fonte.lin>            # só reporta os valores

Saída (stdout), lida por test/verify_c0_selfhost.sh:
    checksum=<i64>
    tokens=<n>
"""
import argparse
import os
import sys

M64 = (1 << 64) - 1
CAP = 256          # VM_MAX_ARR_LEN (docs/LINVM_ISA_V1.rulel §6)


def wrap(x):
    x &= M64
    return x - (1 << 64) if x >= (1 << 63) else x


def is_ident_start(c):
    return (ord('a') <= c <= ord('z')) or (ord('A') <= c <= ord('Z')) \
        or c == ord('_') or c == ord('$')


def is_ident_part(c):
    return is_ident_start(c) or (ord('0') <= c <= ord('9'))


TWO = (b'==', b'!=', b'<=', b'>=', b'&&', b'||', b'->')


def tokenize(data):
    """vmTokenize (compiler/lin.zig:5678) sobre bytes. Retorna [(kind, bytes)]."""
    toks = []
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        if c in (ord(' '), ord('\t'), ord('\r'), ord('\n')):
            i += 1
            continue
        if c == ord('/') and i + 1 < n and data[i + 1] == ord('/'):
            while i < n and data[i] != ord('\n'):
                i += 1
            continue
        if c == ord('"'):
            start = i
            i += 1
            while i < n and data[i] != ord('"'):
                if data[i] == ord('\\') and i + 1 < n:
                    i += 1
                i += 1
            if i < n:
                i += 1
            toks.append((4, data[start:i]))
            continue
        if ord('0') <= c <= ord('9'):
            start = i
            while i < n and ord('0') <= data[i] <= ord('9'):
                i += 1
            toks.append((2, data[start:i]))
            continue
        if is_ident_start(c):
            start = i
            while i < n and is_ident_part(data[i]):
                i += 1
            toks.append((1, data[start:i]))
            continue
        if i + 1 < n and data[i:i + 2] in TWO:
            toks.append((3, data[i:i + 2]))
            i += 2
            continue
        toks.append((3, data[i:i + 1]))
        i += 1
    return toks


def checksum(toks):
    """Fold i64-wrap idêntico ao do módulo LIN."""
    h = 0
    for kind, text in toks:
        h = wrap(h * 31 + kind)
        th = 0
        for b in text:
            th = wrap((th + b) * 31)
        h = wrap(h * 31 + len(text))
        h = wrap(h * 31 + th)
    return h


def oracle(path):
    """(bytes_embutidos, checksum, n_tokens) para os primeiros CAP bytes."""
    with open(path, 'rb') as f:
        data = f.read(CAP)
    toks = tokenize(data)
    return data, checksum(toks), len(toks)


def arr_literal(data):
    """Array literal de exatamente CAP células (zeros à direita), 16 por linha."""
    cells = list(data) + [0] * (CAP - len(data))
    lines = []
    for i in range(0, CAP, 16):
        lines.append("    " + ", ".join(str(c) for c in cells[i:i + 16]) + ",")
    body = "\n".join(lines).rstrip(',')
    return "  src: [%d]int = [\n%s];" % (CAP, body)


TEMPLATE = '''@LIN:L1c:0.2
@LINVM0_SELFLEX{{version=1 generated_by="test/lin0_selflex.py" source="{src}" \
bytes={n} cap={cap} oracle="vmTokenize transcription (independent of the compiler)"}}

// ============================================================================
// MODULO GERADO — nao editar a mao (regenerar: python3 test/lin0_selflex.py {src}).
//
// Auto-aplicacao B2: o lexer LIN de src/linvm0_compiler/lin_lexer_selfhost.lin
// aplicado ao TEXTO de {src} (primeiros {n} bytes — teto VM_MAX_ARR_LEN da ISA).
// Os corpos abaixo sao os do modulo original; so o array `src` e o `n` mudam,
// mais as duas constantes de golden, que vem do oraculo independente.
// ============================================================================

!lex_scan_embedded() -> int {{
{arr}
  i = 0;
  n = {n};
  h = 0;
  while (i < n) {{
    c = src[i];
    ?(c == 32 || c == 9 || c == 13 || c == 10) {{
      i = i + 1;
    }} : (c == 47 && i + 1 < n && src[i + 1] == 47) {{
      while (i < n && src[i] != 10) {{ i = i + 1; }};
    }} : (c == 34) {{
      tstart = i;
      i = i + 1;
      while (i < n && src[i] != 34) {{
        ?(src[i] == 92 && i + 1 < n) {{ i = i + 1; }};
        i = i + 1;
      }};
      ?(i < n) {{ i = i + 1; }};
      tlen = i - tstart;
      h = h * 31 + 4;
      th = 0;
      k = 0;
      while (k < tlen) {{ th = (th + src[tstart + k]) * 31; k = k + 1; }};
      h = h * 31 + tlen;
      h = h * 31 + th;
    }} : (c >= 48 && c <= 57) {{
      tstart = i;
      while (i < n && src[i] >= 48 && src[i] <= 57) {{ i = i + 1; }};
      tlen = i - tstart;
      h = h * 31 + 2;
      th = 0;
      k = 0;
      while (k < tlen) {{ th = (th + src[tstart + k]) * 31; k = k + 1; }};
      h = h * 31 + tlen;
      h = h * 31 + th;
    }} : (lex_is_ident_start(c) == 1) {{
      tstart = i;
      while (i < n && lex_is_ident_part(src[i]) == 1) {{ i = i + 1; }};
      tlen = i - tstart;
      h = h * 31 + 1;
      th = 0;
      k = 0;
      while (k < tlen) {{ th = (th + src[tstart + k]) * 31; k = k + 1; }};
      h = h * 31 + tlen;
      h = h * 31 + th;
    }} : {{
      tstart = i;
      ?(i + 1 < n && lex_is_two(src[i], src[i + 1]) == 1) {{
        i = i + 2;
      }} : {{
        i = i + 1;
      }};
      tlen = i - tstart;
      h = h * 31 + 3;
      th = 0;
      k = 0;
      while (k < tlen) {{ th = (th + src[tstart + k]) * 31; k = k + 1; }};
      h = h * 31 + tlen;
      h = h * 31 + th;
    }};
  }};
  ^h;
}}

!lex_is_ident_start(c: int) -> int {{
  ?((c >= 97 && c <= 122) || (c >= 65 && c <= 90) || c == 95 || c == 36) {{ ^1; }} : {{ ^0; }};
}}

!lex_is_ident_part(c: int) -> int {{
  ?(lex_is_ident_start(c) == 1 || (c >= 48 && c <= 57)) {{ ^1; }} : {{ ^0; }};
}}

!lex_is_two(a: int, b: int) -> int {{
  ?(a == 61 && b == 61) {{ ^1; }} : (a == 33 && b == 61) {{ ^1; }} : (a == 60 && b == 61) {{ ^1; }} : (a == 62 && b == 61) {{ ^1; }} : (a == 38 && b == 38) {{ ^1; }} : (a == 124 && b == 124) {{ ^1; }} : (a == 45 && b == 62) {{ ^1; }} : {{ ^0; }};
}}

// golden vindo do oraculo independente (transcricao de vmTokenize em Python)
!lex_scan_expected() -> int {{
  ^{checksum};
}}

!lex_count_embedded() -> int {{
{arr}
  n = {n};
  cnt = 0;
  i = 0;
  while (i < n) {{
    c = src[i];
    ?(c == 32 || c == 9 || c == 13 || c == 10) {{
      i = i + 1;
    }} : (c == 47 && i + 1 < n && src[i + 1] == 47) {{
      while (i < n && src[i] != 10) {{ i = i + 1; }};
    }} : (c == 34) {{
      i = i + 1;
      while (i < n && src[i] != 34) {{ ?(src[i] == 92 && i + 1 < n) {{ i = i + 1; }}; i = i + 1; }};
      ?(i < n) {{ i = i + 1; }};
      cnt = cnt + 1;
    }} : (c >= 48 && c <= 57) {{
      while (i < n && src[i] >= 48 && src[i] <= 57) {{ i = i + 1; }};
      cnt = cnt + 1;
    }} : (lex_is_ident_start(c) == 1) {{
      while (i < n && lex_is_ident_part(src[i]) == 1) {{ i = i + 1; }};
      cnt = cnt + 1;
    }} : {{
      ?(i + 1 < n && lex_is_two(src[i], src[i + 1]) == 1) {{ i = i + 2; }} : {{ i = i + 1; }};
      cnt = cnt + 1;
    }};
  }};
  ^cnt;
}}

!lex_count_expected() -> int {{
  ^{tokens};
}}

!lex_gate() -> int {{
  ok = 0;
  ?(lex_scan_embedded() == lex_scan_expected() && lex_count_embedded() == lex_count_expected()) {{
    ok = 1;
  }};
  ^ok;
}}
'''


def render(path):
    data, csum, ntok = oracle(path)
    return TEMPLATE.format(src=os.path.basename(path), n=len(data), cap=CAP,
                           arr=arr_literal(data), checksum=csum, tokens=ntok), csum, ntok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', help='módulo .lin cujo texto será auto-tokenizado')
    ap.add_argument('--out', help='escreve o módulo gerado neste caminho')
    a = ap.parse_args()

    if not os.path.isfile(a.source):
        print('lin0_selflex: fonte não encontrada: %s' % a.source, file=sys.stderr)
        return 2

    text, csum, ntok = render(a.source)
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(text)
    print('checksum=%d' % csum)
    print('tokens=%d' % ntok)
    return 0


if __name__ == '__main__':
    sys.exit(main())
