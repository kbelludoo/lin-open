#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-LIN POSIX bc auditor for published LRI1 remainder-identity receipts.

Python only decodes JSON / hex. GNU bc checks q*d+r==n and r<d on the
512-bit product. No LinVM, no gcc, no GMP.

  python3 examples/u512_coprocessor/verify_u512_bc_identity.py \\
      examples/u512_coprocessor/u512_coprocessor_evidence.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

UMAX = (1 << 256) - 1


def fail(msg: str) -> int:
    print("FAIL", msg)
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_u512_bc_identity.py <evidence.json>")
        return 2
    ev = json.loads(Path(sys.argv[1]).read_text())
    schema = ev.get("schema") or ""
    if schema != "LIN_U512_COPROCESSOR_EVIDENCE_1.13":
        return fail("schema")
    leaves = ev.get("lri1_leaves") or []
    if len(leaves) < 8:
        return fail(f"need 8 LRI1 leaves, got {len(leaves)}")
    body = ["scale=0"]
    names = []
    for leaf in leaves:
        n = int(leaf["n"], 0)
        d = int(leaf["d"], 0)
        q = int(leaf["q"], 0)
        r = int(leaf["r"], 0)
        a = int(leaf["a"], 0)
        b = int(leaf["b"], 0)
        if d <= 0 or q > UMAX:
            return fail(leaf.get("name") or "width")
        body += [
            f"n={n}", f"d={d}", f"q={q}", f"r={r}", f"a={a}", f"b={b}",
            "if (n != a*b) { print \"FAIL n\\n\"; halt }",
            "if (q*d+r != n) { print \"FAIL identity\\n\"; halt }",
            "if (r >= d) { print \"FAIL rge\\n\"; halt }",
            'print "OK\\n"',
        ]
        names.append(leaf.get("name") or "?")
    env = os.environ.copy()
    env["BC_LINE_LENGTH"] = "0"
    p = subprocess.run(["bc", "-q"], input="\n".join(body) + "\n",
                       capture_output=True, text=True, timeout=30, check=False, env=env)
    if p.returncode != 0 or "FAIL" in p.stdout:
        return fail((p.stdout + p.stderr).strip()[:200])
    oks = [ln for ln in p.stdout.splitlines() if ln.strip() == "OK"]
    if len(oks) != len(names):
        return fail(f"bc rows {len(oks)} want {len(names)}")
    print("PASS posix bc remainder identity")
    print("lri1_bc_identity", len(oks))
    print("names", ",".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
