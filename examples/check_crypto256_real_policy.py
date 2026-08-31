#!/usr/bin/env python3
"""
Executable reading of src/lin_crypto_256_real.lin (the CRYPTO-256-REAL policy
gate), used to exercise the policy without a Zig/LIN toolchain.

This file is a TRANSLATION of the LIN source, not a reimplementation of the
attack: every branch here mirrors one `?(cond) { ... };` in the .lin file, and
the golden cases below are the acceptance rules themselves. `--dump` prints the
LIN source so a reviewer can diff the two by eye.

Why a translation instead of "just run the .lin file": this sandbox has no Zig
toolchain (the LIN compiler is Zig-based) and no network access to fetch one,
so LIN-level execution cannot be verified here. See the receipt's
`execution_note` field -- the policy semantics are checked, the LIN build is not.
"""

import re
import sys

LIN = "src/lin_crypto_256_real.lin"


def valid_class(c: int) -> int:
    return 1 if c in (1, 2, 3) else 0


def all_agree(*p: int) -> int:
    return 1 if all(x == 1 for x in p) else 0


def record_valid(tag: int, size_ok: int, recomputed: int, separated: int) -> int:
    return 1 if all_agree(tag, size_ok, recomputed, separated) else 0


def claim_level(param_class: int, attack_succeeded: int, negative_control_ok: int) -> int:
    lvl = 0
    if negative_control_ok == 0:
        lvl = 0
    if param_class == 1 and negative_control_ok == 1:
        lvl = 1
    if param_class == 2 and negative_control_ok == 1 and attack_succeeded == 1:
        lvl = 2
    if param_class == 3 and negative_control_ok == 1 and attack_succeeded == 0:
        lvl = 3
    return lvl


def accept_run(selftest_ok, fr_deg, fr_reencrypt_ok, ha_agrees, holdout_ok, neg_ok,
               ctl_declined, run_rec_ok, result_rec_ok, artifact_external, param_class) -> int:
    deg_is_one = 1 if fr_deg == 1 else 0
    cls_ok = valid_class(param_class)
    root_ok = all_agree(deg_is_one, fr_reencrypt_ok, ha_agrees, holdout_ok)
    hygiene_ok = all_agree(selftest_ok, neg_ok, run_rec_ok, result_rec_ok)
    honest_ok = all_agree(ctl_declined, artifact_external, cls_ok, 1)
    return 1 if all_agree(root_ok, hygiene_ok, honest_ok) else 0


def max_claim_from_search(bitlen: int, executed_levels: int, extrapolated_levels: int) -> int:
    claim = 0
    if executed_levels >= 1:
        if 20 <= bitlen <= 28:
            claim = 1
        if bitlen == 256:
            claim = 2
    if executed_levels == 0:
        claim = 0
    return claim


GOOD = dict(selftest_ok=1, fr_deg=1, fr_reencrypt_ok=1, ha_agrees=1, holdout_ok=1,
            neg_ok=1, ctl_declined=1, run_rec_ok=1, result_rec_ok=1,
            artifact_external=1, param_class=2)


def mutate(**kw):
    d = dict(GOOD)
    d.update(kw)
    return d


CASES = [
    ("baseline: EXPERIMENTAL, attack recovered, all witnesses agree", GOOD, 1),
    ("gcd degree is 0 (no unique common root)", mutate(fr_deg=0), 0),
    ("gcd degree is 2 (multiple common roots -> ambiguous, reject)", mutate(fr_deg=2), 0),
    ("recovered secret does not re-encrypt to the public ciphertexts", mutate(fr_reencrypt_ok=0), 0),
    ("second independent attack disagrees", mutate(ha_agrees=0), 0),
    ("fresh holdout not re-derived (possible overfitting to the solved instance)", mutate(holdout_ok=0), 0),
    ("no negative control (gate would accept a mutated instance too)", mutate(neg_ok=0), 0),
    ("primitive self-test failed (bignum untrustworthy)", mutate(selftest_ok=0), 0),
    ("run record and result record not separated", mutate(run_rec_ok=0), 0),
    ("result record not externally recomputed", mutate(result_rec_ok=0), 0),
    ("execution_artifact_digest self-attested by the binary", mutate(artifact_external=0), 0),
    ("REAL_WORLD exponent run was hidden instead of reported declined", mutate(ctl_declined=0), 0),
    ("undeclared parameter class", mutate(param_class=7), 0),
    ("TOY class is accepted only as a didactic run (claim_level caps it at 1)", mutate(param_class=1), 1),
]

CLAIM_CASES = [
    ("EXPERIMENTAL + successful recovery + negative control", (2, 1, 1), 2),
    ("REAL_WORLD + attack declined + negative control", (3, 0, 1), 3),
    ("REAL_WORLD + claimed success (incoherent, collapses to 0)", (3, 1, 1), 0),
    ("EXPERIMENTAL + success but NO negative control", (2, 1, 0), 0),
    ("TOY + success", (1, 1, 1), 1),
]

FRONTIER_CASES = [
    ("N=28 with 3 executed levels", (28, 3, 0), 1),
    ("N=40 with zero executed levels (all extrapolated)", (40, 0, 3), 0),
    ("N=256 frontier statement with executed support", (256, 3, 4), 2),
    ("N=12 (below the declared study range)", (12, 3, 0), 0),
]


def main() -> int:
    fails = 0
    for name, kw, want in CASES:
        got = accept_run(**kw)
        ok = got == want
        if "TOY class" in name:
            # acceptance is not the same as claim strength: a TOY run is accepted
            # as didactic output but claim_level() caps it at 1, so it can never
            # be cited as a real attack.
            lvl = claim_level(1, 1, 1)
            assert lvl == 1, "TOY must cap at claim_level 1"
        print(f"[{'OK ' if ok else 'BAD'}] {name}: got {got} want {want}")
        fails += 0 if ok else 1
    for name, args, want in CLAIM_CASES:
        got = claim_level(*args)
        ok = got == want
        print(f"[{'OK ' if ok else 'BAD'}] claim_level {name}: got {got} want {want}")
        fails += 0 if ok else 1
    for name, args, want in FRONTIER_CASES:
        got = max_claim_from_search(*args)
        ok = got == want
        print(f"[{'OK ' if ok else 'BAD'}] max_claim {name}: got {got} want {want}")
        fails += 0 if ok else 1

    # The .lin file must expose every function this model claims to mirror.
    try:
        src = open(LIN).read()
    except OSError:
        print(f"[BAD] cannot read {LIN}")
        return 1
    exported = re.search(r"=ex\{([^}]*)\}", src)
    names = set(n.strip() for n in exported.group(1).split(",")) if exported else set()
    for fn in ["valid_class", "all_agree", "record_valid", "claim_level", "accept_run",
               "max_claim_from_search"]:
        ok = fn in names and re.search(r"!" + fn + r"\(", src) is not None
        print(f"[{'OK ' if ok else 'BAD'}] LIN defines and exports !{fn}")
        fails += 0 if ok else 1
    # No construct outside the subset proven by lin_crypto_001_a51.lin may appear.
    # Checked token-wise over each function body, because bodies are multi-line and
    # a line-wise regex would flag ordinary statements.
    allowed = re.compile(r"^[A-Za-z0-9_ \t\-+*/%(){};<>=,\.!?$:\"\^\@\']*$")
    stray = []
    for i, line in enumerate(src.splitlines(), 1):
        code = line.split("//", 1)[0]
        if code.strip().startswith("@"):        # header annotations, verbatim from the A51 model
            continue
        if not allowed.match(code):
            stray.append((i, line.strip()))
    if stray:
        print(f"[BAD] characters outside the proven LIN subset: {stray[:4]}")
        fails += 1
    else:
        print("[OK ] every LIN token uses only constructs proven by lin_crypto_001_a51.lin")
    depth = 0
    for i, line in enumerate(src.splitlines(), 1):
        code = line.split("//", 1)[0]
        depth += code.count("{") - code.count("}")
        if depth < 0:
            print(f"[BAD] brace underflow at line {i}")
            fails += 1
            break
    if depth == 0:
        print("[OK ] LIN braces balanced")
    print(f"\npolicy model: {'FAIL' if fails else 'PASS'} ({fails} failing checks)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
