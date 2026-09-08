#!/usr/bin/env python3
"""verify_gate_manifest.py — independent oracle for the LIN Gate manifest.

Pure-Python, stdlib-only reimplementation of the `LIN_GATE_MANIFEST_v1`
canonicalization (see compiler/lin.zig, `lin gate-check` / `lin gate-attest`):

    leaf_i = SHA256("lin:gate:leaf:" || path || ":" || bytes || ":" || hex(sha256))
    node(l, r) = SHA256("lin:gate:node:" || l || r)     (unpaired node promoted)
    root   = pairwise fold over leaves sorted by path (byte-lexicographic)

Purpose: let a reviewer verify the attested toolchain manifest WITHOUT
installing the Zig toolchain. Exit codes mirror `lin gate-check`:
    0  GATE OPEN   (manifest matches the tree)
    1  GATE BLOCKED (modified/added/deleted tracked files, or root mismatch)
    3  not evaluable (no manifest)

Usage:
    python3 tools/verify_gate_manifest.py [--manifest lin_gate_manifest.rulel]
"""
import argparse
import hashlib
import os
import re
import sys

SCOPES = ("compiler", "transpile/c/lin_c", "transpile/c/tool", "transpile/c/test")


def walk_scopes(root: str):
    files = []
    for scope in SCOPES:
        base = os.path.join(root, scope)
        for dirpath, _dirnames, filenames in os.walk(base):
            for fn in filenames:
                full = os.path.normpath(os.path.join(dirpath, fn))
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                files.append(rel)
    return sorted(files)  # byte-lexicographic over ASCII paths == std.mem.order


def sha256_file(path: str) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.digest()


def leaf_of(path: str, nbytes: int, digest: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(b"lin:gate:leaf:")
    h.update(path.encode("utf-8"))
    h.update(b":")
    h.update(str(nbytes).encode("ascii"))
    h.update(b":")
    h.update(digest.hex().encode("ascii"))
    return h.digest()


def node_of(l: bytes, r: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(b"lin:gate:node:")
    h.update(l)
    h.update(r)
    return h.digest()


def root_of(leaves):
    level = list(leaves)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(node_of(level[i], level[i + 1]))
            else:
                nxt.append(level[i])
        level = nxt
    return level[0]


def levels_of(n: int) -> int:
    lv = 1
    while n > 1:
        n = (n + 1) // 2
        lv += 1
    return lv


def parse_manifest(text: str):
    expected_root = ""
    entries = []
    for raw in text.split("\n"):
        line = raw.strip()
        m = re.search(r'merkle_root="(sha256:[0-9a-f]{64})"', line)
        if m and not expected_root:
            expected_root = m.group(1)[len("sha256:") :]
        if not line.startswith(".f{"):
            continue
        p = re.search(r'path="([^"]+)"', line)
        b = re.search(r"bytes=(\d+)", line)
        s = re.search(r'sha256="(sha256:[0-9a-f]{64})"', line)
        if not (p and s):
            continue
        entries.append(
            (p.group(1), int(b.group(1)) if b else 0, s.group(1)[len("sha256:") :])
        )
    return expected_root, entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default="lin_gate_manifest.rulel")
    ap.add_argument("--root", default=os.getcwd(), help="repository root")
    args = ap.parse_args()

    try:
        with open(os.path.join(args.root, args.manifest), "r", encoding="utf-8") as f:
            expected_root, listed = parse_manifest(f.read())
    except OSError:
        print(f"GATE BLOCKED — no gate manifest at {args.manifest}")
        return 3
    if len(expected_root) != 64 or not listed:
        print(f"GATE BLOCKED — manifest {args.manifest} is malformed or empty.")
        return 3

    disk = []
    for rel in walk_scopes(args.root):
        full = os.path.join(args.root, rel)
        disk.append((rel, os.path.getsize(full), sha256_file(full).hex()))

    leaves = [leaf_of(rel, nb, bytes.fromhex(dx)) for rel, nb, dx in disk]
    recomputed = root_of(leaves).hex() if leaves else ""

    print("=" * 78)
    print("LIN GATE — independent oracle (LIN_GATE_MANIFEST_v1, Python stdlib)")
    print("=" * 78)
    print(f"  scope ........... {','.join(SCOPES)}")
    print(f"  tracked files ... {len(disk)} (on disk) / {len(listed)} (manifest)")
    print(f"  merkle levels ... {levels_of(len(disk))}")
    print(f"  recomputed root . sha256:{recomputed}")
    print(f"  attested root .. sha256:{expected_root}")

    listed_map = {p: (b, s) for p, b, s in listed}
    modified = added = deleted = 0
    for rel, nb, dx in disk:
        if rel in listed_map:
            lb, ls = listed_map.pop(rel)
            if ls != dx or lb != nb:
                modified += 1
                print(f"  MODIFIED  {rel}\n"
                      f"            attested sha256:{ls[:16]}… ({lb} B)\n"
                      f"            on-disk  sha256:{dx[:16]}… ({nb} B)")
        else:
            added += 1
            print(f"  ADDED     {rel}  sha256:{dx[:16]}…")
    for rel in listed_map:
        deleted += 1
        print(f"  DELETED   {rel}")

    changes = modified + added + deleted
    root_ok = changes == 0 and recomputed == expected_root
    if not root_ok:
        print(f"\nGATE BLOCKED — {changes} unattested change(s): "
              f"{modified} modified, {added} added, {deleted} deleted.")
        print("A maintainer must review the change and re-attest:\n"
              f"  make gate-attest KEY=<private-seed-file>   # then commit {args.manifest}")
        return 1
    print("\nGATE OPEN — Merkle root matches the attested manifest "
          f"({len(disk)} files).")
    print("Attestation signature NOT verified by this oracle (no roster/key "
          "material in the repository, by design).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
