#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/verify_compute_receipt.py — Independent Zero-Trust Compute Receipt Oracle.
Pure Python standard library (hashlib, struct, json, ast).
Zero dependencies. Does NOT trust the receipt generator.

Verifies:
  1. Structural integrity: computes sha256(artifact || out || steps || sp || in)
     and compares bit-exact with the declared Merkle root.
  2. Cryptographic binding: if --source is provided, asserts sha256(source) == artifact.
  3. Execution replay & fraud detection: if --source is provided, independently
     replays the arithmetic expression with int64 wrapping semantics and asserts
     replayed_output == receipt.output.

Usage:
  python3 tools/verify_compute_receipt.py --receipt <receipt.rulel|json> [--source "<source_code>"]
"""

from __future__ import annotations
import argparse
import ast
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

# Wrapping 64-bit signed integer arithmetic (matching LinVM / lin_w*)
INT64_MIN = -0x8000000000000000
INT64_MAX = 0x7FFFFFFFFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF

def to_i64(val: int) -> int:
    val = val & MASK64
    if val >= 0x8000000000000000:
        val -= 0x10000000000000000
    return val

class LinScalarEvaluator(ast.NodeVisitor):
    def __init__(self, var_x: int):
        self.var_x = to_i64(var_x)

    def visit_BinOp(self, node: ast.BinOp) -> int:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return to_i64(left + right)
        elif isinstance(node.op, ast.Sub):
            return to_i64(left - right)
        elif isinstance(node.op, ast.Mult):
            return to_i64(left * right)
        elif isinstance(node.op, (ast.FloorDiv, ast.Div)):
            if right == 0:
                raise ZeroDivisionError("Division by zero in LinVM expression")
            if left == INT64_MIN and right == -1:
                return INT64_MIN
            # C-style truncation toward zero
            sign = -1 if (left < 0) ^ (right < 0) else 1
            return sign * (abs(left) // abs(right))
        elif isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("Modulo by zero in LinVM expression")
            if left == INT64_MIN and right == -1:
                return 0
            sign = -1 if left < 0 else 1
            return sign * (abs(left) % abs(right))
        elif isinstance(node.op, ast.BitAnd):
            return to_i64(left & right)
        elif isinstance(node.op, ast.BitOr):
            return to_i64(left | right)
        elif isinstance(node.op, ast.BitXor):
            return to_i64(left ^ right)
        elif isinstance(node.op, ast.LShift):
            if right < 0 or right >= 64:
                return 0
            return to_i64(left << right)
        elif isinstance(node.op, ast.RShift):
            if right < 0 or right >= 64:
                return 0
            return to_i64(left >> right)
        raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> int:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return to_i64(-operand)
        elif isinstance(node.op, ast.UAdd):
            return to_i64(operand)
        elif isinstance(node.op, ast.Invert):
            return to_i64(~operand)
        raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> int:
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            res = False
            if isinstance(op, ast.Eq):
                res = (left == right)
            elif isinstance(op, ast.NotEq):
                res = (left != right)
            elif isinstance(op, ast.Lt):
                res = (left < right)
            elif isinstance(op, ast.LtE):
                res = (left <= right)
            elif isinstance(op, ast.Gt):
                res = (left > right)
            elif isinstance(op, ast.GtE):
                res = (left >= right)
            else:
                raise ValueError(f"Unsupported compare op: {type(op).__name__}")
            if not res:
                return 0
            left = right
        return 1

    def visit_Name(self, node: ast.Name) -> int:
        if node.id in ("x", "inp", "input"):
            return self.var_x
        raise ValueError(f"Undefined variable in expression: {node.id}")

    def visit_Constant(self, node: ast.Constant) -> int:
        if isinstance(node.value, int):
            return to_i64(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def generic_visit(self, node):
        raise ValueError(f"Unsupported syntax in expression: {type(node).__name__}")

def replay_expression(source: str, input_val: int) -> int:
    expr = source.strip()
    if expr.startswith("return "):
        expr = expr[7:].strip()
    expr = expr.rstrip("; \t\r\n")
    # Replace single '=' comparisons if present or handle C operators
    # Lin uses ==, !=, <, <=, >, >=
    parsed = ast.parse(expr, mode="eval")
    evaluator = LinScalarEvaluator(input_val)
    return evaluator.visit(parsed.body)

def parse_receipt(text: str) -> dict:
    t = text.strip()
    res = {}
    if t.startswith("{"):
        d = json.loads(t)
        res["artifact"] = d.get("artifact", "")
        res["input"] = int(d.get("input", 0))
        res["output"] = int(d.get("output", 0))
        res["steps"] = int(d.get("steps", 0))
        res["sp_at_ret"] = int(d.get("sp_at_ret", 0))
        res["merkle_root"] = d.get("merkle_root", "")
    else:
        for line in t.splitlines():
            line = line.strip()
            if line.startswith(".a="):
                res["artifact"] = line[3:].strip('"')
            elif line.startswith(".i="):
                res["input"] = int(line[3:].strip('"'))
            elif line.startswith(".o="):
                res["output"] = int(line[3:].strip('"'))
            elif line.startswith(".s="):
                res["steps"] = int(line[3:].strip('"'))
            elif line.startswith(".p="):
                res["sp_at_ret"] = int(line[3:].strip('"'))
            elif line.startswith(".m="):
                res["merkle_root"] = line[3:].strip('"')
    return res

def verify_receipt(receipt_data: dict, source: str | None = None) -> tuple[bool, str]:
    art_str = receipt_data.get("artifact", "")
    if art_str.startswith("sha256:"):
        art_hex = art_str[7:]
    else:
        art_hex = art_str
    
    if len(art_hex) != 64:
        return False, f"Invalid artifact digest length: {len(art_hex)}"
    
    try:
        art_bytes = bytes.fromhex(art_hex)
    except ValueError:
        return False, "Invalid hex in artifact digest"

    out_val = receipt_data.get("output", 0)
    steps_val = receipt_data.get("steps", 0)
    sp_val = receipt_data.get("sp_at_ret", 0)
    inp_val = receipt_data.get("input", 0)
    stored_merkle = receipt_data.get("merkle_root", "")
    if stored_merkle.startswith("sha256:"):
        stored_merkle = stored_merkle[7:]

    # 64-byte canonical leaf packing
    leaf = art_bytes + struct.pack("<qQQq", out_val, steps_val, sp_val, inp_val)
    recalculated_merkle = hashlib.sha256(leaf).hexdigest()

    if recalculated_merkle != stored_merkle:
        return False, f"TAMPERED_MERKLE_ROOT: calculated sha256:{recalculated_merkle} != stored sha256:{stored_merkle}"

    # If source is provided, execute replay check
    if source is not None:
        source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source_digest != art_hex:
            return False, f"SOURCE_DIGEST_MISMATCH: sha256(source)={source_digest} != receipt artifact={art_hex}"

        try:
            replayed_out = replay_expression(source, inp_val)
        except Exception as e:
            return False, f"EXECUTION_ERROR: failed to replay source: {e}"

        if replayed_out != out_val:
            return False, f"OUTPUT_FRAUD_DETECTED: replayed f({inp_val})={replayed_out} != receipt output={out_val}"

        return True, f"FULL_CONSENSUS: Merkle root verified and execution replayed (f({inp_val}) = {out_val})"

    return True, f"STRUCTURAL_ONLY: Merkle root matches leaf fields (execution not replayed; pass --source to verify execution)"

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify LIN Compute Receipt independently")
    parser.add_argument("--receipt", required=True, help="Path to receipt file (.rulel or .json)")
    parser.add_argument("--source", help="Source code string or path to source file for replay verification")
    args = parser.parse_args()

    rec_path = Path(args.receipt)
    if not rec_path.exists():
        print(f"FAIL: receipt file not found: {rec_path}", file=sys.stderr)
        return 1

    rec_text = rec_path.read_text(encoding="utf-8")
    data = parse_receipt(rec_text)

    source_content = None
    if args.source:
        src_path = Path(args.source)
        if src_path.exists() and src_path.is_file():
            source_content = src_path.read_text(encoding="utf-8")
        else:
            source_content = args.source

    ok, msg = verify_receipt(data, source_content)
    if ok:
        print(f"PASS: {msg}")
        return 0
    else:
        print(f"FAIL: {msg}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
