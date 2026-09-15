#!/usr/bin/env python3
"""Paridade DDC do transpiler linp-em-LIN: src/linp_from_py.lin == oraculo Python.
Reusa o mini-interprete de test/verify_lint_from_html.py (mesmo subset).
Prova: (1) selftest do subset usado; (2) .pyx do corpus -> .linp byte-identico
nos dois lados; (3) negativos com mesma sentenca de rejeito."""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))
import verify_lint_from_html as W

SRC = os.path.join(ROOT, "src", "linp_from_py.lin")
GOLD = os.path.join(ROOT, "transpile", "c", "linp_c0", "golden")
PYORACLE = "/home/k/Downloads/FloppyURL-main/transpile_py_to_linp.py"

spec = importlib.util.spec_from_file_location("pyoracle", PYORACLE)
pyo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pyo)

FAILS = []


def check(n, c, d=""):
    print(f"[{'PASS' if c else 'FAIL'}] linp-lin:{n}" + (f" — {d}" if d else ""))
    if not c:
        FAILS.append(n)


def main():
    fns = W.load_fns(SRC)
    print(f"[linp-lin] {len(fns)} funcoes de src/linp_from_py.lin")
    cases = [
        ("lp_eq", ["a", "a"], 1), ("lp_eq", ["a", "b"], 0),
        ("lp_atoi", ["1800000"], 1800000), ("lp_atoi", ["64x"], 64),
        ("lp_isnum", ["800"], 1), ("lp_isnum", ["8a"], 0), ("lp_isnum", [""], 0),
        ("lp_badpath", ["a/../b"], 1), ("lp_badpath", ["/x"], 1), ("lp_badpath", ["a/b"], 0),
        ("lp_badchunk", ["63"], 1), ("lp_badchunk", ["64"], 0),
        ("lp_badchunk", ["1800000"], 0), ("lp_badchunk", ["1800001"], 1),
        ("lp_num", [800], "800"), ("lp_num", [0], "0"),
    ]
    bad = 0
    for fn, args, want in cases:
        W.STEPS[0] = 0
        try:
            got = W.run_fn(fn, args, fns)
        except Exception as e:
            got = f"ERR:{e}"
        if got != want:
            print(f"  SELFTEST FAIL {fn}{args}: {got!r} != {want!r}")
            bad += 1
    check("selftest interprete+helpers", bad == 0, f"{bad} falhas" if bad else "")

    # positivo: .pyx golden -> .linp byte-identico nos 2 lados + igual ao pinado
    pyx = open(os.path.join(GOLD, "demo.pyx"), encoding="utf-8").read()
    want = open(os.path.join(GOLD, "demo.linp"), encoding="utf-8").read()
    W.STEPS[0] = 0
    got_lin = W.run_fn("linp_py", [pyx], fns)
    got_py = pyo.transpile(pyx)
    check("LIN==golden==PY demo.pyx", got_lin == want == got_py,
          f"steps={W.STEPS[0]}" if got_lin == want == got_py else
          f"LIN={got_lin[:60]!r} PY={got_py[:60]!r}")

    # variantes validas extras
    extra = [
        'job("x")\npack("f.lin")\n',
        '# c\njob("j")\n\npack("a/b.lin", algo="gzip", chunk=64)\n',
        'job("j")\npack("a.lin", algo="brotli")\n',
        'job("j")\npack("a.lin", chunk=100)\n',
    ]
    for src in extra:
        W.STEPS[0] = 0
        lin = W.run_fn("linp_py", [src], fns)
        py = pyo.transpile(src)
        check(f"paridade {src.splitlines()[0:2]!r}", lin == py, lin[:50].replace("\n", "|"))

    # negativos: mesma sentenca (rejeita / aceita-igual)
    negs = [
        ('import os\njob("x")\npack("a")\n', True),
        ('job("x")\nfor i in r:\n pack("a")\n', True),
        ('job("x")\npack("/etc/passwd")\n', True),
        ('job("x")\npack("a", algo="lzma")\n', True),
        ('job("x")\npack("a", chunk=10)\n', True),
        ('pack("a")\n', True),
        ('job("x")\npack("a")\npack("b")\n', True),
        ('job("a")\njob("b")\npack("c")\n', True),
        ('job("x")\npack("a", algo="deflate", algo="gzip")\n', True),
        ('job("x")\npack("a", bogus="1")\n', True),
        ('job("x")\npack("a"\n', True),
        ('job("x")\npack("a", chunk=64)\n', False),
        ('job("x")\npack("a.lin", chunk=100, algo="brotli")\n', True),
    ]
    for src, must_rej in negs:
        W.STEPS[0] = 0
        lin = W.run_fn("linp_py", [src], fns)
        try:
            py = pyo.transpile(src)
            pyrej = False
        except Exception:
            pyrej = True
        linrej = isinstance(lin, str) and lin.startswith("LINP_REJ")
        ok = (linrej == must_rej == pyrej) or (not must_rej and not linrej and lin == py)
        check(f"neg {src.splitlines()[0][:28]!r}", ok, f"LIN={str(lin)[:26]!r}")
    print(f"[linp-lin] PARIDADE: {'ALL PASS' if not FAILS else FAILS}")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
