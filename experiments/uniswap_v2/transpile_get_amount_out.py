#!/usr/bin/env python3
"""Transpile the pure getAmountOut slice from Uniswap V2 Solidity to LIN.

This is deliberately a narrow, checked transpiler: it accepts the exact
UniswapV2Library.getAmountOut arithmetic shape and refuses to emit LIN when
the upstream function changes. It is not a general Solidity compiler.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


FUNCTION_RE = re.compile(
    r"function\s+getAmountOut\s*\([^)]*\).*?\{(?P<body>.*?)\n\s*\}",
    re.DOTALL,
)


def git_commit(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


def transpile(source: str, commit: str) -> str:
    match = FUNCTION_RE.search(source)
    if not match:
        raise SystemExit("getAmountOut was not found in upstream source")
    body = match.group("body")

    required = [
        "amountIn.mul(997)",
        "amountInWithFee.mul(reserveOut)",
        "reserveIn.mul(1000).add(amountInWithFee)",
        "amountOut = numerator / denominator",
    ]
    missing = [needle for needle in required if needle not in body]
    if missing:
        raise SystemExit(
            "upstream getAmountOut shape changed; missing: " + ", ".join(missing)
        )

    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"""@LIN:MODULE:2.0.0
@TRANSPILATION{{
  upstream_repo="https://github.com/Uniswap/v2-periphery"
  upstream_file="contracts/libraries/UniswapV2Library.sol"
  upstream_function="getAmountOut"
  upstream_commit="{commit}"
  upstream_sha256="{source_sha}"
}}
// Solidity require() paths are represented by deterministic zero sentinels
// in this scalar, value-only LIN host. Valid settlement inputs are exact.
!get_amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int {{
  ?(amount_in <= 0 | reserve_in <= 0 | reserve_out <= 0) {{
    ^ 0;
  }} : {{
    amount_in_with_fee = amount_in * 997;
    numerator = amount_in_with_fee * reserve_out;
    denominator = (reserve_in * 1000) + amount_in_with_fee;
    ?(denominator <= 0) {{
      ^ 0;
    }} : {{
      ^ numerator / denominator;
    }}
  }}
}}

=ex{{get_amount_out}}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_path = args.repo / "contracts/libraries/UniswapV2Library.sol"
    source = source_path.read_text(encoding="utf-8")
    args.output.write_text(transpile(source, git_commit(args.repo)), encoding="utf-8")
    print(f"generated {args.output}")


if __name__ == "__main__":
    main()
