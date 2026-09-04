#!/usr/bin/env python3
"""Differential test for the single-execution U256 settlement ABI."""

import argparse
import hashlib
import random
import struct
import subprocess
from pathlib import Path

MODULUS = 1 << 256


def oracle(amount: int, reserve_in: int, reserve_out: int):
    if amount == 0 or reserve_in == 0 or reserve_out == 0:
        return -1, 0
    fee_amount = amount * 997
    if fee_amount >= MODULUS:
        return -2, 0
    denominator = reserve_in * 1000 + fee_amount
    if denominator >= MODULUS:
        return -2, 0
    numerator = fee_amount * reserve_out
    if numerator >= MODULUS:
        return -2, 0
    return 0, numerator // denominator


def invoke(host: Path, image: Path, values):
    command = [
        str(host),
        str(image),
        *(f"0x{value:064x}" for value in values),
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "u256_host failed")
    result_line = next(
        line for line in completed.stdout.splitlines() if line.startswith(".result{")
    )
    fields = dict(
        token.split("=", 1)
        for token in result_line.removeprefix(".result{").rstrip(" }").split()
    )
    return int(fields["status"]), int(fields["amount_out"], 16), fields


def verify_receipt(image: Path, values, status: int, output: int, fields):
    image_bytes = image.read_bytes()
    program_digest = hashlib.sha256(image_bytes).hexdigest()
    loader_digest = hashlib.sha256(b"linbc1:img:" + image_bytes[:-32]).hexdigest()
    input_bytes = b"".join(value.to_bytes(32, "big") for value in values)
    input_digest_bytes = hashlib.sha256(input_bytes).digest()
    input_digest = input_digest_bytes.hex()
    steps = int(fields["steps"])
    amount_bytes = output.to_bytes(32, "big")
    receipt_bytes = hashlib.sha256(
        b"lin:settlement:v1:"
        + bytes.fromhex(program_digest)
        + input_digest_bytes
        + struct.pack("<q", status)
        + amount_bytes
        + struct.pack("<Q", steps)
    ).hexdigest()

    expected = {
        "program_sha256": f"sha256:{program_digest}",
        "loader_digest": f"sha256:{loader_digest}",
        "input_sha256": f"sha256:{input_digest}",
        "receipt_sha256": f"sha256:{receipt_bytes}",
    }
    for key, expected_value in expected.items():
        if fields.get(key) != expected_value:
            raise AssertionError(
                f"receipt field {key} mismatch: got={fields.get(key)} "
                f"expected={expected_value}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        type=Path,
        default=Path("transpile/c/bin/u256_host"),
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=Path("examples/defi_settlement_proof/u256_settlement_engine.linbc"),
    )
    parser.add_argument("--vectors", type=int, default=1000)
    args = parser.parse_args()

    if not args.host.is_file() or not args.image.is_file():
        parser.error("run `make -C transpile/c u256` before this test")

    rng = random.Random(20260904)
    vectors = [
        (1, 1, 1),
        (2, 100, 100),
        (10000, 50000, 100000),
        (10**18, 5 * 10**18, 10**19),
        (0, 1, 1),
        (1, 0, 1),
        (1, 1, 0),
        (MODULUS - 1, 1, 1),
        (1, 1, MODULUS - 1),
    ]
    while len(vectors) < args.vectors:
        if len(vectors) % 2:
            # This range keeps the full numerator inside uint256 and exercises
            # non-zero high words without triggering the overflow branch.
            vectors.append(
                (
                    rng.randrange(1, 1 << 120),
                    rng.randrange(1, 1 << 120),
                    rng.randrange(1, 1 << 120),
                )
            )
        else:
            vectors.append(
                (
                    rng.randrange(1, MODULUS),
                    rng.randrange(1, MODULUS),
                    rng.randrange(1, MODULUS),
                )
            )

    counts = {-2: 0, -1: 0, 0: 0}
    for index, values in enumerate(vectors[: args.vectors]):
        expected_status, expected_output = oracle(*values)
        status, output, fields = invoke(args.host, args.image, values)
        if status != expected_status or output != expected_output:
            raise AssertionError(
                f"vector {index} mismatch: values={values} "
                f"got=({status}, {output}) expected=({expected_status}, {expected_output})"
            )
        verify_receipt(args.image, values, status, output, fields)
        if int(fields["steps"]) == 0 or fields["execution"] != "single_vm_call":
            raise AssertionError(f"vector {index} did not report one VM execution")
        counts[status] += 1

    print("U256_SINGLE_EXECUTION=PASS")
    print(f"VECTORS={len(vectors[:args.vectors])}")
    print(f"VALID={counts[0]}")
    print(f"INVALID_ZERO={counts[-1]}")
    print(f"OVERFLOW={counts[-2]}")


if __name__ == "__main__":
    main()
