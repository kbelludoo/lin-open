#!/usr/bin/env python3
"""
verify_compiler0_manifest.py — confere `compiler0_manifest.rulel` (sem Zig).

O que ele mede
--------------
Para cada módulo do front-end compiler0 (`src/linvm0_compiler/*.lin`):

  1. o SHA-256 da FONTE confere com o pinado;
  2. a IMAGEM LINBC1 emitida pelo host C11 (`lin_c0 image`) tem os bytes, o
     SHA-256 e o fold pinados — e é reproduzível byte a byte entre duas
     execuções (determinismo do emissor, risco 2 de docs/LINBC1_FORMAT.rulel);
  3. o self-lex (primeiros 256 bytes do próprio texto, gerado por
     `test/lin0_selflex.py`) reproduz o checksum e a contagem pinados, vindos
     do oráculo independente;
  4. a RAIZ AGREGADA sobre os três módulos confere com a pinada.

Nada aqui chama `zig`. O único binário usado é `transpile/c/bin/lin_c0`
(construído por `make -C transpile/c c0`, só com `cc`).

Uso
---
    python3 test/verify_compiler0_manifest.py           # verifica (exit != 0 divergiu)
    python3 test/verify_compiler0_manifest.py --emit    # (re)escreve o manifesto
                                                        # a partir do medido agora

R5 (sem overclaim): `--emit` existe porque os valores são MEDIÇÕES, não
assertivas — mas o manifesto só deve ser re-emitido junto da mudança que os
alterou, e a raiz agregada é o que impede re-emitir um módulo de cada vez.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, 'compiler0_manifest.rulel')
LIN_C0 = os.environ.get('LIN_C0', os.path.join(ROOT, 'transpile/c', 'bin', 'lin_c0'))
DOMAIN = b'linvm:c0:manifest:'

MODULES = [
    ('lin_lexer_selfhost', 'src/linvm0_compiler/lin_lexer_selfhost.lin'),
    ('lin_expr_eval', 'src/linvm0_compiler/lin_expr_eval.lin'),
    ('lin_lower_selfhost', 'src/linvm0_compiler/lin_lower_selfhost.lin'),
]

FIELD_RE = {
    'source': re.compile(r'source="([^"]*)"'),
    'src_sha256': re.compile(r'src_sha256="([0-9a-f]{64})"'),
    'img_sha256': re.compile(r'img_sha256="([0-9a-f]{64})"'),
    'img_bytes': re.compile(r'img_bytes=(\d+)'),
    'fold': re.compile(r'fold=(-?\d+)'),
    'selflex_checksum': re.compile(r'selflex_checksum=(-?\d+)'),
    'selflex_tokens': re.compile(r'selflex_tokens=(\d+)'),
}
ROOT_RE = re.compile(r'root="sha256:([0-9a-f]{64})"')
IMAGE_RE = re.compile(
    r'\.image\{ bytes=(\d+) fns=(\d+) ins=(\d+) profile=(\d+) fold=(-?\d+) '
    r'sha256=([0-9a-f]{64}) img="([0-9a-f]{64})"')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def lin_c0_image(source, out=None):
    """Roda `lin_c0 image` e devolve o registro .image{} parsed."""
    cmd = [LIN_C0, 'image', source]
    if out:
        cmd += ['-o', out]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError('lin_c0 image %s falhou (rc=%d): %s'
                           % (source, p.returncode, (p.stdout + p.stderr).strip()[:400]))
    m = IMAGE_RE.search(p.stdout)
    if not m:
        raise RuntimeError('lin_c0 image %s: saída sem .image{}: %s'
                           % (source, p.stdout.strip()[:400]))
    return {
        'img_bytes': int(m.group(1)),
        'fns': int(m.group(2)),
        'ins': int(m.group(3)),
        'profile': int(m.group(4)),
        'fold': int(m.group(5)),
        'img_sha256': m.group(6),
        'img': m.group(7),
    }


def selflex_oracle(source):
    """(checksum, tokens) do oráculo independente, via test/lin0_selflex.py."""
    sys.path.insert(0, os.path.join(ROOT, 'test'))
    try:
        import lin0_selflex
    finally:
        sys.path.pop(0)
    _, csum, ntok = lin0_selflex.oracle(source)
    return csum, ntok


def measure():
    """Mede tudo agora. Retorna a lista de dicionários canônicos."""
    if not os.path.exists(LIN_C0):
        raise SystemExit('verify_compiler0_manifest: %s não existe — '
                         'construa com `make -C transpile/c c0`' % LIN_C0)
    out = []
    import tempfile
    for name, rel in MODULES:
        src = os.path.join(ROOT, rel)
        if not os.path.isfile(src):
            raise SystemExit('verify_compiler0_manifest: falta %s' % rel)
        img = lin_c0_image(src)
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, 'a.linbc')
            b = os.path.join(td, 'b.linbc')
            lin_c0_image(src, a)
            lin_c0_image(src, b)
            with open(a, 'rb') as fa, open(b, 'rb') as fb:
                if fa.read() != fb.read():
                    raise SystemExit('verify_compiler0_manifest: %s — imagem NÃO '
                                     'reproduzível entre duas execuções' % name)
        csum, ntok = selflex_oracle(src)
        out.append({
            'name': name,
            'source': rel,
            'src_sha256': sha256_file(src),
            'img_bytes': img['img_bytes'],
            'img_sha256': img['img_sha256'],
            'fold': img['fold'],
            'selflex_checksum': csum,
            'selflex_tokens': ntok,
        })
    return out


def canon_line(m):
    return '%s|%s|%d|%s|%d|%d|%d\n' % (
        m['name'], m['src_sha256'], m['img_bytes'], m['img_sha256'],
        m['fold'], m['selflex_checksum'], m['selflex_tokens'])


def aggregate_root(mods):
    h = hashlib.sha256()
    h.update(DOMAIN)
    for m in mods:
        h.update(canon_line(m).encode('utf-8'))
    return h.hexdigest()


def render_manifest(mods, root):
    lines = [
        '@RULEL:COMPILER0_MANIFEST:1.0.0',
        '~R{.m=modules .r=root .h=scope}',
        '',
        '# Manifesto das imagens LINBC1 do front-end compiler0 (V2/B2), sem Zig.',
        '#',
        '# Cada linha abaixo e uma MEDICAO do host C11 (transpile/c/bin/lin_c0,',
        '# construido so com `cc`) cruzada com o oraculo independente de',
        '# test/lin0_selflex.py. Conferir: python3 test/verify_compiler0_manifest.py',
        '# Re-emitir (so junto da mudanca que alterou as medicoes):',
        '#   python3 test/verify_compiler0_manifest.py --emit',
        '#',
        '# Escopo honesto (R5): isto pina as IMAGENS do front-end em LIN e o seu',
        '# self-lex. NAO e o ponto fixo C0=C1=C2, e `check`/`lint` continuam no',
        '# Stage0 Zig — ver docs/LINVM0_V2_FRONTIER.rulel.',
        '.m{',
    ]
    for m in mods:
        lines.append(
            '  .mod{ name="%s" source="%s" src_sha256="%s" img_bytes=%d '
            'img_sha256="%s" fold=%d selflex_checksum=%d selflex_tokens=%d }'
            % (m['name'], m['source'], m['src_sha256'], m['img_bytes'],
               m['img_sha256'], m['fold'], m['selflex_checksum'],
               m['selflex_tokens']))
    lines += [
        '}',
        '.r{ domain="linvm:c0:manifest:" root="sha256:%s" }' % root,
        '.h{ host="C11-lin_c0" zig=false compiler="transpile/c/tool/lin_c0*.c" '
        'oracle="test/lin0_selflex.py" selflex_cap=256 '
        'note="imagens reproduziveis byte a byte; raiz agrega os 3 modulos" }',
        '',
    ]
    return '\n'.join(lines)


def parse_manifest(text):
    mods = []
    for block in re.findall(r'\.mod\{([^}]*)\}', text):
        m = {}
        name = re.search(r'name="([^"]*)"', block)
        if not name:
            continue
        m['name'] = name.group(1)
        for key, rx in FIELD_RE.items():
            g = rx.search(block)
            if not g:
                raise SystemExit('verify_compiler0_manifest: .mod %s sem campo %s'
                                 % (m['name'], key))
            v = g.group(1)
            m[key] = v if key in ('source', 'src_sha256', 'img_sha256') else int(v)
        mods.append(m)
    r = ROOT_RE.search(text)
    if not r:
        raise SystemExit('verify_compiler0_manifest: manifesto sem .r{ root="sha256:..." }')
    return mods, r.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--emit', action='store_true',
                    help='(re)escreve compiler0_manifest.rulel a partir do medido agora')
    a = ap.parse_args()

    if a.emit:
        mods = measure()
        root = aggregate_root(mods)
        with open(MANIFEST, 'w', encoding='utf-8') as f:
            f.write(render_manifest(mods, root))
        print('compiler0_manifest.rulel re-emitido: %d módulos, root=sha256:%s'
              % (len(mods), root))
        return 0

    if not os.path.isfile(MANIFEST):
        print('verify_compiler0_manifest: %s não existe (gere com --emit)' % MANIFEST,
              file=sys.stderr)
        return 2

    with open(MANIFEST, encoding='utf-8') as f:
        pinned_mods, pinned_root = parse_manifest(f.read())
    live = measure()
    fail = 0

    by_name = {m['name']: m for m in pinned_mods}
    for m in live:
        p = by_name.get(m['name'])
        if not p:
            print('NOK  %s: ausente do manifesto' % m['name'])
            fail += 1
            continue
        for k in ('source', 'src_sha256', 'img_bytes', 'img_sha256', 'fold',
                  'selflex_checksum', 'selflex_tokens'):
            if p[k] != m[k]:
                print('NOK  %s: %s pinado=%r medido=%r' % (m['name'], k, p[k], m[k]))
                fail += 1
            else:
                print('ok   %s: %s=%s' % (m['name'], k, m[k]))
    for name in by_name:
        if name not in {m['name'] for m in live}:
            print('NOK  %s: pinado no manifesto mas não medido' % name)
            fail += 1

    live_root = aggregate_root(live)
    if live_root != pinned_root:
        print('NOK  raiz agregada: pinada=%s medida=%s' % (pinned_root, live_root))
        fail += 1
    else:
        print('ok   raiz agregada sha256:%s' % live_root)

    if fail:
        print('COMPILER0-MANIFEST: FAIL (%d divergências)' % fail)
        return 1
    print('COMPILER0-MANIFEST: PASS (%d módulos, imagens + self-lex + raiz agregada)'
          % len(live))
    return 0


if __name__ == '__main__':
    sys.exit(main())
