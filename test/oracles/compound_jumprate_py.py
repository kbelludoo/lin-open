#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python bigint oracle for the experimental uint64 JumpRate clone.

Not a Solidity uint256 / mainnet cToken oracle. Quotients that do not fit
non-negative signed i64 fail closed to 0 (LinVM `int` is signed).
"""
from __future__ import annotations

BASE = 10**18
KINK = 800_000_000_000_000_000
MULT_YEAR = 40_000_000_000_000_000
JUMP_YEAR = 1_090_000_000_000_000_000
BLOCKS = 2_102_400
I64_MAX = 2**63 - 1


def muldiv(a: int, b: int, d: int) -> int:
    if a < 0 or b < 0 or d <= 0:
        return 0
    q = (a * b) // d
    if q > I64_MAX:
        return 0
    return q


def utilization(cash: int, borrows: int, reserves: int) -> int:
    if borrows == 0:
        return 0
    if cash < 0 or borrows < 0 or reserves < 0:
        return 0
    if cash > I64_MAX - borrows:
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
    br = borrow_rate(cash, borrows, reserves, base_block, mult_block, jump_block, kink)
    rate_to_pool = muldiv(br, BASE - reserve_factor, BASE)
    return muldiv(utilization(cash, borrows, reserves), rate_to_pool, BASE)


def multiplier_per_block(mult_year: int, kink: int) -> int:
    if kink == 0:
        return 0
    return muldiv(muldiv(mult_year, BASE, kink), 1, BLOCKS)


def jump_per_block(jump_year: int) -> int:
    return muldiv(jump_year, 1, BLOCKS)


def solidity_multiplier_per_block(mult_year: int, kink: int) -> int:
    """Arbitrary-precision (mult_year * BASE) / (blocks * kink). Not uint64."""
    if kink == 0:
        return 0
    return (mult_year * BASE) // (BLOCKS * kink)
