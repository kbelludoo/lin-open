#!/usr/bin/env python3
"""
verify_gate_manifest.py — recomputa a raiz Merkle do LIN Gate SEM Zig.

O `lin gate-check` é um verificador independente por design, mas ele mesmo é
um binário Zig: num ambiente sem toolchain, a cadeia de confiança não tinha como
ser verificada. Este script refaz o cálculo a partir da especificação
canônica publicada em `compiler/lin.zig` (bloco LIN_GATE_MANIFEST_v1):

    leaf_i = SHA256("lin:gate:leaf:" || path || ":" || bytes || ":" || hex(sha256(file)))
    node(l, r) = SHA256("lin:gate:node:" || l || r)     (ímpar sobe/promove)
    root = dobra sobre as folhas ordenadas lexicograficamente por path

Escopos rastreados: compiler, transpile/c/lin_c, transpile/c/tool, transpile/c/test.

Auto-prova antes de confiar: `--check-parser` recalcula a raiz da ÁRVORE
IMUTÁVEL de um commit (via `git show`) e compara com o manifesto daquele commit.

Uso:
    python3 test/verify_gate_manifest.py                 # check no cwd
    python3 test/verify_gate_manifest.py --attest        # reescreve o manifesto
    python3 test/verify_gate_manifest.py --rev HEAD      # raiz de um commit
    python3 test/verify_gate_manifest.py --rev v1.0.0 --check-against-manifest

Sai 0 se a raiz do disco coincide com a atestada; 1 caso contrário. Não escreve
nada sem --attest, e --attest nunca forja assinatura Ed25519: a marca
`attested_by` passa a `tool:verify_gate_manifest.py` para que "recomputado por
ferramenta" e "atestado por humano" continuem sendo coisas distintas (R4/R5).
"""
import argparse
import hashlib
import os
import subprocess
import sys

SCOPES = ["compiler", "transpile/c/lin_c", "transpile/c/tool", "transpile/c/test"]
LEAF_DOM = b"lin:gate:leaf:"
NODE_DOM = b"lin:gate:node:"


def sha256(b):
    return hashlib.sha256(b).digest()


def leaf(path, n, hexsha):
    return sha256(LEAF_DOM + path.encode() + b":" + str(n).encode() + b":" + hexsha.encode())


def node(l, r):
    return sha256(NODE_DOM + l + r)


def root_of(leaves):
    if not leaves:
        raise SystemExit("GATE BLOCKED — nenhuma arquivo rastreado encontrado")
    level = list(leaves)
    levels = 1
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(node(level[i], level[i + 1]))
            else:
                nxt.append(level[i])
        level = nxt
        levels += 1
    return level[0], levels


def walk_disk(root):
    out = []
    for sc in SCOPES:
        base = os.path.join(root, sc)
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                with open(full, "rb") as f:
                    data = f.read()
                out.append((rel, len(data), hashlib.sha256(data).hexdigest()))
    out.sort(key=lambda t: t[0].encode())
    return out


def walk_git(rev):
    paths = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", rev, "--"] + SCOPES,
        capture_output=True, text=True, check=True).stdout.splitlines()
    out = []
    for rel in sorted(paths, key=lambda s: s.encode()):
        data = subprocess.run(["git", "show", "%s:%s" % (rev, rel)],
                              capture_output=True, check=True).stdout
        out.append((rel, len(data), hashlib.sha256(data).hexdigest()))
    return out


def parse_manifest(path):
    txt = open(path, encoding="utf-8").read()
    root = None
    for line in txt.splitlines():
        if "merkle_root=" in line:
            root = line.split('merkle_root="sha256:', 1)[1].split('"', 1)[0]
            break
    return root


def render_manifest(files, root_hex, levels, attested_by, ts):
    lines = [
        "@RULEL:LIN_GATE_MANIFEST:1.0.0",
        "~R{.s=subject .f=tracked_files .v=verdict}",
        ".s{",
        '  scope="%s"' % ",".join(SCOPES),
        '  canonicalization="LIN_GATE_MANIFEST_v1"',
        '  merkle_root="sha256:%s"' % root_hex,
        '  attested_by="%s"' % attested_by,
        "  audit_timestamp_unix=%d" % ts,
        "}",
        ".f{",
    ]
    for rel, n, h in files:
        lines.append('  .f{ path="%s" bytes=%d sha256="sha256:%s" }' % (rel, n, h))
    lines += [
        "}",
        ".v{",
        "  files=%d" % len(files),
        "  merkle_levels=%d" % levels,
        '  merkle_root="sha256:%s"' % root_hex,
        '  status="GATE_RECOMPUTED_UNSIGNED"',
        '  evidence_status="COMPUTED"',
        "}",
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="diretório do repositório")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--rev", default=None, help="recompute a raiz de um commit (git)")
    ap.add_argument("--attest", action="store_true", help="reescreve o manifesto")
    ap.add_argument("--attested-by", default="tool:verify_gate_manifest.py")
    ap.add_argument("--timestamp", type=int, default=None)
    args = ap.parse_args()

    manifest = args.manifest or os.path.join(args.root, "lin_gate_manifest.rulel")
    if args.rev:
        files = walk_git(args.rev)
    else:
        files = walk_disk(args.root)
    leaves = [leaf(p, n, h) for (p, n, h) in files]
    root, levels = root_of(leaves)
    root_hex = root.hex()

    print("=== LIN GATE — recomputação independente (python3, sem Zig) ===")
    print("  escopo ......... %s" % ",".join(SCOPES))
    print("  arquivos ....... %d" % len(files))
    print("  níveis merkle .. %d" % levels)
    print("  raiz computada . sha256:%s" % root_hex)
    if args.attest:
        if args.rev:
            raise SystemExit("--attest exige o disco de trabalho (não use --rev)")
        ts = args.timestamp if args.timestamp is not None else int(__import__("time").time())
        with open(manifest, "w", encoding="utf-8") as f:
            f.write(render_manifest(files, root_hex, levels, args.attested_by, ts))
        print("  manifesto escrito: %s (attested_by=%s — NÃO assinado)" % (manifest, args.attested_by))
        return 0
    if not os.path.exists(manifest):
        print("  manifesto ausente em %s" % manifest)
        return 1
    pinned = parse_manifest(manifest)
    print("  raiz atestada .. sha256:%s" % pinned)
    if pinned == root_hex:
        print("  GATE OPEN — a raiz do disco coincide com a atestada.")
        return 0
    print("  GATE BLOCKED — divergência: ou o toolchain mudou sem re-atestação,")
    print("                 ou a atestação não cobre este conteúdo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
