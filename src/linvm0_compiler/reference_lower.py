#!/usr/bin/env python3
# reference_lower.py — oraculo INDEPENDENTE do lowerer LIN
# (src/linvm0_compiler/lin_lower_selfhost.lin).
#
# Replica o post-order de `lower_arena` (transpile/c/lin_c/lin_vm.c) e o fold
# i64-wrap usado pelo modulo LIN, para um subset de expressoes de CONSTANTES.
# Serve para cross-checkar os folds que o lowerer LIN emite (R4/R3).
#
# Uso:
#   python3 src/linvm0_compiler/reference_lower.py
# Imprime o fold esperado de cada vetor (== os goldens hardcoded no .lin).
M64 = (1 << 64) - 1


def wrap(x):
    x &= M64
    return x - (1 << 64) if x >= (1 << 63) else x


def fold_seq(instrs):
    lh = 0
    for op, a in instrs:
        lh = wrap(lh * 31 + op)
        lh = wrap(lh * 31 + (a & 0xFFFFFFFF))
    return lh


# Expressoes e o bytecode post-order correspondente (opcodes `VmOp`):
#   push_const=0, add=3, sub=4, mul=5, cmp_eq=16, ret=29
VECTORS = [
    ("42", [(0, 42), (29, 0)]),                                  # v0
    ("1+2*3", [(0, 1), (0, 2), (0, 3), (5, 0), (3, 0), (29, 0)]),  # v8
    ("2*3+4*5", [(0, 2), (0, 3), (5, 0), (0, 4), (0, 5), (5, 0), (3, 0), (29, 0)]),  # v11
    ("3==3", [(0, 3), (0, 3), (16, 0), (29, 0)]),                # v14
    ("1+2==3", [(0, 1), (0, 2), (3, 0), (0, 3), (16, 0), (29, 0)]),  # v17
]


def main():
    for expr, ins in VECTORS:
        print(f"{expr!r:14} -> fold={fold_seq(ins)}")
    # Confirma que o bytecode canonico de v11 tem o mesmo code_sha256 do consenso
    # (floreio de informacao; o consenso ja e medido no xver).
    import hashlib, struct
    code = b"".join(bytes([op]) + struct.pack("<q", a) for op, a in VECTORS[2][1])
    leaf = hashlib.sha256(b"lin:xver:code:" + code).hexdigest()
    print(f"v11 code_sha256 (leaf w/ domain) = {leaf}")


if __name__ == "__main__":
    main()
