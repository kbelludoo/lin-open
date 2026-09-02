#!/usr/bin/env python3
# verify_compiler0_manifest.py — confere (e sabe reemitir) o manifesto de imagens
# do compiler0-em-LIN (`compiler0_manifest.rulel`).
#
# Por que existe: as imagens LINBC1 do front-end escrito em LIN são o artefato
# congelado do passo compiler0. O manifesto pinna bytes + sha256 de cada uma e a
# raiz agregada. Este script:
#   1. regenera cada imagem chamando o HOST (`lin_c0 image <mod> -o ...`);
#   2. RECOMPUTA o auto-digest em Python, a partir dos bytes do arquivo, com a
#      regra do formato: SHA-256 de (imagem com o campo digest zerado) sob o
#      domínio `linbc1:img:` (docs/LINBC1_FORMAT.rulel §4) — ou seja, não confia
#      no hasher do carregador/emitidor para validar o que ele mesmo publicou;
#   3. confere byte-count e sha256 declarados;
#   4. recalcula a raiz agregada (fold sequencial documentado no manifesto,
#      domínio `lin:compiler0:leaf:` / `lin:compiler0:node:`) e compara com `.v`;
#   5. `--attest` regrava `.i`/`.x`/`.v` com as medidas correntes.
#
# Uso:
#   python3 test/verify_compiler0_manifest.py            # check (exit 1 se diverge)
#   python3 test/verify_compiler0_manifest.py --attest   # reatesta
import argparse
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMG_DOMAIN = b"linbc1:img:"          # docs/LINBC1_FORMAT.rulel §4
LEAF_DOMAIN = b"lin:compiler0:leaf:"
NODE_DOMAIN = b"lin:compiler0:node:"


def recompute_self_hash(img_bytes):
    """SHA-256("linbc1:img:" || imagem-sem-os-últimos-32-bytes) — a regra do
    FORMATO (docs/LINBC1_FORMAT.rulel §4, `lin_bc1_load` em `lin_c/lin_linbc1.c`):
    o auto-digest mora nos 32 bytes FINAIS do arquivo e cobre todo o corpo.
    Recalcular isto em Python valida o hash sem passar pelo C."""
    if len(img_bytes) < 160:
        raise ValueError("imagem curta demais (%d bytes)" % len(img_bytes))
    return hashlib.sha256(IMG_DOMAIN + img_bytes[:-32]).hexdigest()



def parse_images(text):
    recs = []
    for m in re.finditer(r'\.i\{\s*module\s*=\s*"([^"]+)"\s+bytes\s*=\s*(\d+)\s+sha256\s*=\s*"([0-9a-f]{64})"'
                         r'\s+gate\s*=\s*"([^"]+)"\s+value\s*=\s*(-?\d+)\s*\}', text):
        recs.append({"module": m.group(1), "bytes": int(m.group(2)), "sha": m.group(3),
                     "gate": m.group(4), "value": int(m.group(5))})
    return recs


def parse_root(text):
    m = re.search(r'\.v\{[^}]*merkle_root\s*=\s*"sha256:([0-9a-f]{64})"', text, re.S)
    return m.group(1) if m else None


def aggregate_root(recs):
    """Fold sequencial, na ordem declarada: r = leaf_1; r = node(r, leaf_i)."""
    def leaf(r):
        return hashlib.sha256(LEAF_DOMAIN + ("%s:%d:%s" % (r["module"], r["bytes"], r["sha"])).encode()).hexdigest()
    root = None
    for r in recs:
        lf = leaf(r)
        root = lf if root is None else hashlib.sha256(NODE_DOMAIN + (root + lf).encode()).hexdigest()
    return root


def rebuild(bin_path, module, out_path):
    r = subprocess.run([bin_path, "image", os.path.join(ROOT, module), "-o", out_path],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("lin_c0 image falhou para %s (rc=%d)" % (module, r.returncode))
    with open(out_path, "rb") as f:
        return f.read(), r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(ROOT, "compiler0_manifest.rulel"))
    ap.add_argument("--bin", default=os.path.join(ROOT, "transpile", "c", "bin", "lin_c0"))
    ap.add_argument("--attest", action="store_true", help="regrava .i/.v com as medidas correntes")
    ap.add_argument("--tmp", default="/tmp/c0manifest")
    a = ap.parse_args()

    text = open(a.manifest, encoding="utf-8").read()
    recs = parse_images(text)
    if not recs:
        raise SystemExit("nenhum registro .i{ module=... } em %s" % a.manifest)
    os.makedirs(a.tmp, exist_ok=True)

    fresh = []
    for r in recs:
        raw, out = rebuild(a.bin, r["module"], os.path.join(a.tmp, os.path.basename(r["module"]) + ".linbc"))
        m_img = re.search(r'\.image\{ bytes=(\d+)[^}]*\}', out)
        m_sha = re.search(r'img="([0-9a-f]{64})"', out)
        host_bytes, host_sha = int(m_img.group(1)), m_sha.group(1)
        py_sha = recompute_self_hash(raw)
        fresh.append({"module": r["module"], "bytes": len(raw), "sha": py_sha,
                      "gate": r["gate"], "value": r["value"]})
        tag = os.path.basename(r["module"])
        bad = []
        if len(raw) != host_bytes:
            bad.append("bytes arquivo %d != emitido %d" % (len(raw), host_bytes))
        if len(raw) != r["bytes"]:
            bad.append("bytes declarados %d != real %d" % (r["bytes"], len(raw)))
        if py_sha != host_sha:
            bad.append("self-hash Python %s != host %s" % (py_sha[:12], host_sha[:12]))
        if py_sha != r["sha"]:
            bad.append("self-hash %s != manifest %s" % (py_sha[:12], r["sha"][:12]))
        print("image  %-30s bytes=%-7d sha256=%s  %s" % (
            tag, len(raw), py_sha[:16], "OK" if not bad else "DIVERGE: " + "; ".join(bad)))
        if bad and not a.attest:
            return 1

    root = aggregate_root(fresh)
    declared = parse_root(text)
    ok_root = (declared == root)
    print("raiz   fold(dom=lin:compiler0:images:)  sha256:%s  %s" % (
        root[:16], "OK" if ok_root else "DIVERGE (declarada %s)" % (declared or "-")))
    if not ok_root and not a.attest:
        return 1

    # ---- .x: self-lex (o lexer LIN sobre o texto do front-end) ----
    # Conferido aqui só com o oráculo Python (sem VM); quem roda o módulo gerado
    # na LinVM é o gate shell. O objetivo é o pinnado não apodrecer em silêncio.
    xs = []
    for m in re.finditer(r'\.x\{\s*target\s*=\s*"([^"]+)"\s+bytes\s*=\s*(\d+)\s+tokens\s*=\s*(\d+)\s+checksum\s*=\s*(-?\d+)\s*\}', text):
        xs.append({"target": m.group(1), "bytes": int(m.group(2)), "tokens": int(m.group(3)),
                   "checksum": int(m.group(4))})
    ok_x = True
    if xs:
        sys.path.insert(0, os.path.join(ROOT, "test"))
        import lin0_selflex  # template/regenerador compartilhado com o gate
        for x in xs:
            data = open(os.path.join(ROOT, x["target"]), "rb").read()
            _, n, ntok, csum, _ = lin0_selflex.transplant(
                open(os.path.join(ROOT, "src", "linvm0_compiler", "lin_lexer_selfhost.lin"),
                     encoding="utf-8").read(), data)
            bad = [k for k, got, want in (("bytes", n, x["bytes"]), ("tokens", ntok, x["tokens"]),
                                          ("checksum", csum, x["checksum"])) if got != want]
            print("selflex %-30s bytes=%-4d tokens=%-3d checksum=%-20d %s" % (
                os.path.basename(x["target"]), n, ntok, csum,
                "OK" if not bad else "DIVERGE: " + ", ".join(bad)))
            if bad:
                ok_x = False
                if not a.attest:
                    return 1
    # reatestar .x é trabalho do gate (precisa da LinVM); aqui só .i/.v
    if a.attest:
        body = text
        for f in fresh:
            old = re.search(r'\.i\{\s*module\s*=\s*"%s".*?\n  \}' % re.escape(f["module"]),
                            body, re.S)
            new = ('.i{\n    module="%s" bytes=%d sha256="%s"\n    gate="%s" value=%d\n  }'
                   % (f["module"], f["bytes"], f["sha"], f["gate"], f["value"]))
            body = body[:old.start()] + new + body[old.end():]
        body = re.sub(r'(merkle_root\s*=\s*"sha256:)[0-9a-f]{64}(")', r'\g<1>%s\g<2>' % root, body)
        open(a.manifest, "w", encoding="utf-8").write(body)
        print("manifesto reatestado: %s" % os.path.relpath(a.manifest, ROOT))
    ok = (ok_root and ok_x) or a.attest
    print("COMPILER0-MANIFEST: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
