#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Third oracle: Compound JumpRate math on the experimental uint64 profile.

Python arbitrary-precision int — not the C11 limb clone and not LinVM.
After the exact integer formula, this oracle applies the documented uint64
fail-closed rules (quotient that does not fit uint64 returns 0; cash+borrows
underflow vs reserves returns 0).

This is not Solidity uint256 / mainnet cToken parity.
"""
from __future__ import annotations

U64 = (1 << 64) - 1
BASE = 10**18
BLOCKS = 2_102_400
KINK = 800_000_000_000_000_000
MULT_YEAR = 40_000_000_000_000_000
JUMP_YEAR = 1_090_000_000_000_000_000


def i64_wrap(x: int) -> int:
    x = x & U64
    return x - (1 << 64) if x >= 2**63 else x


def muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = (int(a) * int(b)) // int(d)
    if q > U64:
        return 0
    return q


def utilization(cash: int, borrows: int, reserves: int) -> int:
    if borrows == 0:
        return 0
    if cash > U64 - borrows:
        return 0
    total = cash + borrows
    if total < reserves:
        return 0
    denom = total - reserves
    if denom == 0:
        return 0
    return muldiv(borrows, BASE, denom)


def borrow_rate(
    cash: int,
    borrows: int,
    reserves: int,
    base_block: int,
    mult_block: int,
    jump_block: int,
    kink: int,
) -> int:
    util = utilization(cash, borrows, reserves)
    if util <= kink:
        return muldiv(util, mult_block, BASE) + base_block
    normal = muldiv(kink, mult_block, BASE) + base_block
    return muldiv(util - kink, jump_block, BASE) + normal


def supply_rate(
    cash: int,
    borrows: int,
    reserves: int,
    base_block: int,
    mult_block: int,
    jump_block: int,
    kink: int,
    reserve_factor: int,
) -> int:
    if reserve_factor > BASE:
        return 0
    br = borrow_rate(
        cash, borrows, reserves, base_block, mult_block, jump_block, kink
    )
    rate_to_pool = muldiv(br, BASE - reserve_factor, BASE)
    return muldiv(utilization(cash, borrows, reserves), rate_to_pool, BASE)


def multiplier_lin(mult_year: int, kink: int) -> int:
    """LIN reorder: (mult_year * BASE / kink) / blocks. Fits uint64 intermediates."""
    if kink == 0:
        return 0
    return muldiv(muldiv(mult_year, BASE, kink), 1, BLOCKS)


def multiplier_solidity(mult_year: int, kink: int) -> int:
    """Exact Solidity uint256: (mult_year * BASE) / (blocks * kink)."""
    if kink == 0:
        return 0
    return (mult_year * BASE) // (BLOCKS * kink)


def solidity_util_reverts(cash: int, borrows: int, reserves: int) -> bool:
    """Solidity 0.8 checked `cash + borrows - reserves` reverts on underflow."""
    if borrows == 0:
        return False
    return cash + borrows < reserves


def blocks_kink_overflows_u64(kink: int) -> bool:
    return BLOCKS * kink > U64


def floor_div_identity(x: int, y: int, z: int) -> bool:
    """floor(x/(y*z)) == floor(floor(x/z)/y) for positive integers."""
    if y <= 0 or z <= 0:
        return True
    return (x // (y * z)) == ((x // z) // y)
