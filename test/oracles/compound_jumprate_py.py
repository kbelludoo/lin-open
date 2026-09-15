# Independent Python IRM oracle (arbitrary-precision ints).
# Not the LIN runtime. Used only by test/prove_compound_jumprate_external.py.

BASE = 10**18


def py_muldiv(a: int, b: int, d: int) -> int:
    return 0 if d == 0 else (a * b) // d


def py_util(cash: int, borrows: int, reserves: int) -> int:
    if borrows == 0:
        return 0
    denom = cash + borrows - reserves
    if denom <= 0:
        return 0
    return py_muldiv(borrows, BASE, denom)


def py_borrow(
    cash: int,
    borrows: int,
    reserves: int,
    base_b: int,
    mult_b: int,
    jump_b: int,
    kink: int,
) -> int:
    util = py_util(cash, borrows, reserves)
    if util <= kink:
        return py_muldiv(util, mult_b, BASE) + base_b
    return py_muldiv(util - kink, jump_b, BASE) + py_muldiv(kink, mult_b, BASE) + base_b


def py_supply(
    cash: int,
    borrows: int,
    reserves: int,
    base_b: int,
    mult_b: int,
    jump_b: int,
    kink: int,
    rf: int,
) -> int:
    if rf > BASE:
        return 0
    br = py_borrow(cash, borrows, reserves, base_b, mult_b, jump_b, kink)
    return py_muldiv(py_util(cash, borrows, reserves), py_muldiv(br, BASE - rf, BASE), BASE)


def u64_wrap_muldiv(a: int, b: int, d: int) -> int:
    return 0 if d == 0 else ((a * b) & ((1 << 64) - 1)) // d
