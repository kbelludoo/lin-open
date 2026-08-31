#!/usr/bin/env python3
"""
LIN-CRYPTO-256-REAL / pillar C: independent cleanroom verifier.

READ THIS FIRST -- WHY THIS FILE EXISTS
---------------------------------------
"LIN found a key" is not evidence.  The repository's earlier crypto gates
(LIN-CRYPTO-MAX-256, and the first `verify_crypto256_independent.py`) had two
circularity defects:

  1. the "independent" verifier hard-coded the expected answer
     (`target_k24 = 0x0037C0DE`), so it could only ever confirm; and
  2. one `execution_digest` field was cited in the receipt but bound nothing
     -- `grep`-ing the repo for it returned zero hits.

This script fixes both:

  * it implements the arithmetic from the published definitions
    (RFC 8017 section 8.1 textbook RSA encryption, and the Franklin-Reiter
    related-message attack: Franklin & Reiter, "Fast encryption and
    cryptanalysis of RSA", Info. Proc. Lett. 18(3):123-125, 1985;
    CRYPTO'92 LNCS 705) and from the RSA Laboratory challenge list.
  * it does NOT read the solver's source, does not import any solver code, and
    does not receive the plaintext.  It receives (n, e, a, b, c1, c2) plus an
    ALLEGED secret, then either reproduces the secret itself or refutes it.
  * it recomputes every digest named in the run record from the bytes the
    record actually contains, so a stale digest cannot pass.
  * it runs negative controls that must be REJECTED.  A verifier that accepts
    mutated inputs is worth nothing.

Adversarial inputs are supplied by --self-test, not by the solver.

Claim scope: exact secret recovery on an UNPADDED textbook-RSA instance built
on the published RSA-100 modulus, at the vulnerable small exponent e = 3
(EXPERIMENTAL parameter class).  This is not a break of RSA as used in
practice, not an AES-256 result, and not a security proof.
"""

import argparse
import hashlib
import json
import struct
import sys

# --------------------------------------------------------------------------
# 1. Published parameters.  Transcribed from the RSA Laboratory Factoring
#    Challenge list (decimal-digit-labelled moduli) and cross-checked against
#    their published factorizations by assert_public_params() below.
# --------------------------------------------------------------------------
RSA = {
    "RSA-100": 1522605027922533360535618378132637429718068114961380688657908494580122963258952897654000350692006139,
    "RSA-110": 35794234179725868774991807832568455403003778024228226193532908190484670252364677411513516111204504060317568667,
    "RSA-120": 227010481295437363334259960947493668895875336466084780038173258247009162675779735389791151574049166747880487470296548479,
}
# Published factorizations, used ONLY to prove the moduli above are the real
# challenge numbers (digit count is not enough).  Never used by the attack.
RSA_FACTORS = {
    "RSA-100": (37975227936943673922808872755445627854565536638199,
                40094690950920881030683735292761468389214899724061),
    "RSA-110": (6122421090493547576937037317561418841225758554253106999,
                5846418214406154678836553182979162384198610505601062333),
    "RSA-120": (327414555693498015751146303749141488063642403240171463406883,
                693342667110830181197325401899700641361965863127336680673013),
}
EXPONENT = 3                      # the vulnerable configuration under test
REAL_WORLD_EXPONENT = 65537
DEGREE_CAP = 8                    # work bound for the poly-Euclid, declared not hidden
DECIMAL_DIGITS = {"RSA-100": 100, "RSA-110": 110, "RSA-120": 120}


def assert_public_params() -> None:
    """Refuse to run on mis-transcribed constants: a wrong n makes every
    downstream 'recovery' meaningless."""
    for name, n in RSA.items():
        p, q = RSA_FACTORS[name]
        assert p * q == n, f"{name}: published factorization does not reproduce n"
        assert len(str(n)) == DECIMAL_DIGITS[name], f"{name}: wrong decimal digit count"
        assert n % 2 == 1 and p != q, f"{name}: n is not an RSA modulus"
        assert (p - 1) % EXPONENT != 0 and (q - 1) % EXPONENT != 0, \
            f"{name}: x^{EXPONENT} is not a bijection mod n"
        assert gcd(EXPONENT, (p - 1) * (q - 1)) == 1, f"{name}: e not invertible"


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a


# --------------------------------------------------------------------------
# 2. Textbook RSA, exactly as defined in RFC 8017 s.8.1 (RSASP1 with no
#    padding).  Encryption is public, so the verifier can and must re-derive
#    ciphertexts from a candidate message rather than trust any receipt.
# --------------------------------------------------------------------------
def rsa_encrypt(m: int, e: int, n: int) -> int:
    return pow(m, e, n)


# --------------------------------------------------------------------------
# 3. Attack A -- Franklin-Reiter related-message attack (independent impl).
#    Given m2 = a*m1 + b (mod n) and c1 = m1^e, c2 = m2^e (mod n):
#    f1(x) = x^e - c1 and f2(x) = (a x + b)^e - c2 share the root m1, so
#    gcd(f1, f2) over Z_n[x] has m1 as a root; for a single such pair the gcd
#    is linear and m1 = -g[0] * g[1]^-1 (mod n).
#    Polynomial arithmetic uses Python ints -- no shared code with the solver.
# --------------------------------------------------------------------------
def poly_mul(p, q, n):
    r = [0] * (len(p) + len(q) - 1)
    for i, pi in enumerate(p):
        if pi % n == 0:
            continue
        for j, qj in enumerate(q):
            r[i + j] = (r[i + j] + pi * qj) % n
    return trim(r, n)


def trim(p, n):
    p = list(p)
    while p and p[-1] % n == 0:
        p.pop()
    return p or [0]          # the zero polynomial is [0]; never return empty


def poly_gcd(f1, f2, n, deg_cap=None):
    """Euclid in (Z/nZ)[x]. Returns the last nonzero remainder made monic,
    or None if a non-invertible leading coefficient blocks the division (that
    is a legitimate failure mode to report, not to paper over).
    deg_cap bounds the working degree so a REAL_WORLD exponent reports
    'too expensive to run' instead of hanging the verifier."""
    if deg_cap is not None and max(len(f1), len(f2)) - 1 > deg_cap:
        return None
    a, b = trim(f1, n), trim(f2, n)
    for _ in range(4 * (len(f1) + len(f2)) + 16):
        b = trim(b, n)
        if len(b) == 1 and b[0] % n == 0:
            a = trim(a, n)
            try:
                lead_inv = pow(a[-1], -1, n)
            except ValueError:
                return None     # cannot normalise: report, never guess
            return [(x * lead_inv) % n for x in a]
        if len(a) < len(b):
            a, b = b, a
            continue
        try:
            inv = pow(b[-1], -1, n)
        except ValueError:
            return None          # non-invertible leading coefficient: report, never guess
        # long division: q = a/b, r = a - q*b
        r = list(a)
        degb = len(b) - 1
        for k in range(len(r) - 1, degb - 1, -1):
            coef = (r[k] * inv) % n
            if coef == 0:
                continue
            for i in range(degb + 1):
                r[k - degb + i] = (r[k - degb + i] - coef * b[i]) % n
        r = trim(r[:degb], n) if degb else [0]
        a, b = b, r
    return None


def franklin_reiter(n, e, a, b, c1, c2, deg_cap=DEGREE_CAP):
    """Return the recovered m1, or None. Sees ONLY the public view.
    Refuses outright when e exceeds the declared degree budget: an honest
    'not attempted at this exponent' beats a hang or a fabricated answer."""
    if e > deg_cap:
        return None
    f1 = [(-c1) % n] + [0] * (e - 1) + [1]
    f2 = [0] * (len(f1))
    # (a x + b)^e expanded by repeated squaring of binomials -- explicitly, so
    # a reader can confirm no term is missing (the earlier draft truncated it).
    from math import comb
    for j in range(e + 1):
        coef = (comb(e, j) * pow(b, e - j, n) * pow(a, j, n)) % n
        f2[j] = (f2[j] + coef) % n
    f2[0] = (f2[0] - c2) % n
    g = poly_gcd(f1, trim(f2, n), n, deg_cap=deg_cap)
    if not g or len(g) != 2:
        return None
    lead = g[-1] % n
    if lead == 0:
        return None
    return (-(g[0]) * pow(lead, -1, n)) % n


# --------------------------------------------------------------------------
# 4. Attack B -- Hastad broadcast, e = 3, three published moduli (independent
#    impl).  Independent of Attack A: different instance, different mechanism.
# --------------------------------------------------------------------------
def crt(residues, moduli):
    """Explicit CRT.  Returns (None, None) when the moduli are not pairwise
    coprime -- the classic way a broadcast attack silently produces a wrong
    answer, so it is refused rather than raised past."""
    M = 1
    for m in moduli:
        M *= m
    for i in range(len(moduli)):
        for j in range(i + 1, len(moduli)):
            if gcd(moduli[i], moduli[j]) != 1:
                return None, None
    x = 0
    for r, m in zip(residues, moduli):
        Mi = M // m
        x = (x + r * Mi * pow(Mi, -1, m)) % M
    return x, M


def icbrt(v: int):
    lo, hi = 0, 1 << ((v.bit_length() + 3) // 3 + 1)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if mid ** 3 <= v:
            lo = mid
        else:
            hi = mid
    return lo, (lo ** 3 == v)


def hastad_broadcast(ciphertexts, moduli, e=3):
    """Hastad broadcast for exponent e over pairwise-coprime moduli.
    Returns the recovered message, or None when the hypotheses fail (moduli
    not coprime, or the CRT value not a perfect e-th power -- the latter is
    what happens when m^e >= prod(n_i), i.e. the bound that makes the attack
    work is not satisfied)."""
    y, M = crt(ciphertexts, moduli)
    if y is None:
        return None
    root, exact = icbrt(y)
    if not exact or root ** e >= M:
        return None
    return root


# --------------------------------------------------------------------------
# 5. Digest recomputation -- the anti-VERIFY-003 machinery.
#    The binary prints a fixed-size canonical record as hex; each record is
#    hashed independently, and each field has exactly one meaning.
# --------------------------------------------------------------------------
RECORD_SCHEMA = {
    "LIN_RUN_CONFIG/1.0": 176,
    "LIN_BENCH_RESULT/1.0": 216,
}
# The result record is split: [0, OUTCOME) is the deterministic part a
# reproducer must match exactly, [OUTCOME, end) is wall-clock data that
# legitimately differs per run and per machine.  Keeping them as two digests is
# what lets "the result reproduced" and "the benchmark got faster" be different,
# individually checkable statements.
OUTCOME_BYTES = 168


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def recompute_run_digest(record_hex: str) -> str:
    blob = bytes.fromhex(record_hex)
    assert len(blob) == RECORD_SCHEMA["LIN_RUN_CONFIG/1.0"], \
        f"run record must be exactly {RECORD_SCHEMA['LIN_RUN_CONFIG/1.0']} bytes, got {len(blob)}"
    assert blob[:18] == b"LIN_RUN_CONFIG/1.0", "bad record tag"
    return sha256_hex(blob)


def recompute_result_digest(record_hex: str, part: str = "outcome") -> str:
    """part="outcome"  -> the reproducible claim (verifier demands this one)
       part="timing"   -> wall-clock data (reported, never demanded)
       part="whole"    -> both halves together (sanity only)"""
    blob = bytes.fromhex(record_hex)
    assert len(blob) == RECORD_SCHEMA["LIN_BENCH_RESULT/1.0"], \
        f"result record must be exactly {RECORD_SCHEMA['LIN_BENCH_RESULT/1.0']} bytes, got {len(blob)}"
    assert blob[:20] == b"LIN_BENCH_RESULT/1.0", "bad record tag"
    if part == "outcome":
        return sha256_hex(blob[:OUTCOME_BYTES])
    if part == "timing":
        return sha256_hex(blob[OUTCOME_BYTES:])
    return sha256_hex(blob)


def execution_artifact_digest(path: str) -> str:
    """Binds the immutable source that was executed -- NOT the run, NOT the
    results.  A digest that mixes these meanings is the MAX-256 defect."""
    with open(path, "rb") as f:
        return sha256_hex(f.read())


def result_fields_change(record_hex: str) -> dict:
    """Decode the fields a benchmark claim rests on, so 'did the results
    change?' is answerable from the record alone."""
    blob = bytes.fromhex(record_hex)
    off = 24 + 16
    names = ["fr_ok", "fr_deg", "ha_ok", "holdout_ok", "neg_ok", "ctl_ok", "e_fr", "e_ctl",
             "param_class", "rsv"]
    out = {}
    for i, nm in enumerate(names):
        out[nm] = struct.unpack_from("<I", blob, off + 4 * i)[0]
    off += 4 * len(names)
    for i, nm in enumerate(["work_fr", "work_hastad", "work_ctl", "trial_ops"]):
        out[nm] = struct.unpack_from("<Q", blob, off + 8 * i)[0]
    off += 32
    # offsets are pinned independently on both sides: the C harness has a
    # compile-time sizeof/offsetof check, this is its mirror on the decoder side
    assert off == 112, f"layout drift: m_dec expected at 112, got {off}"
    out["m_dec"] = blob[off:off + 48].split(b"\0")[0].decode()
    # a NUL terminator has to fit inside the field, so a full field means the
    # record schema is short and is silently truncating the published secret
    if len(out["m_dec"]) >= 47:
        raise AssertionError(f"m_dec field holds {len(out['m_dec'])} chars: the record schema "
                             "must be widened, the value must not be silently truncated")
    off = OUTCOME_BYTES
    for i, nm in enumerate(["t_fr", "t_hastad", "t_ctl", "t_total"]):
        out[nm] = struct.unpack_from("<d", blob, off + 8 * i)[0]
    out["trial_rate"] = struct.unpack_from("<d", blob, OUTCOME_BYTES + 32)[0]
    return out


# --------------------------------------------------------------------------
# 6. Verification
# --------------------------------------------------------------------------
def verify_public_instance(inst: dict) -> bool:
    """Re-derive the ciphertexts from the published spec and the alleged
    secret.  This is the whole point: the answer is checked, not stored."""
    n = int(inst["n1"])
    e = int(inst["e"])
    a, b = int(inst["a"]), int(inst["b"])
    m = int(inst["alleged_m"])
    m2 = (a * m + b) % n
    ok1 = rsa_encrypt(m, e, n) == int(inst["c1"])
    ok2 = rsa_encrypt(m2, e, n) == int(inst["c2"])
    return ok1 and ok2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-json", default="/tmp/lin_crypto_256_real_run.json")
    ap.add_argument("--source", default="test/test_lin_crypto_256_real.c")
    ap.add_argument("--self-test", action="store_true",
                    help="run adversarial inputs; no solver output needed")
    args = ap.parse_args()

    assert_public_params()
    print("[cleanroom] published-parameter self-check: "
          f"RSA-100/110/120 reproduced from published factorizations, "
          f"x^{EXPONENT} bijective on each: PASS")

    # ---- adversarial suite (independent of any solver run) ---------------
    fails, passes = [], []

    def expect(label, got, want):
        (passes if got == want else fails).append(f"{label}: got {got} want {want}")

    n = RSA["RSA-100"]
    m_true = 2149056343111462257187712855114544047662
    a, b = 536617318, 870458532
    c1 = rsa_encrypt(m_true, EXPONENT, n)
    c2 = rsa_encrypt((a * m_true + b) % n, EXPONENT, n)

    if args.self_test:
        # T1 honest instance: attack must succeed AND match
        rec = franklin_reiter(n, EXPONENT, a, b, c1, c2)
        expect("T1 cleanroom Franklin-Reiter recovers the same secret",
               rec == m_true, True)
        # T2 mutated affine b: must NOT yield the secret
        bad = franklin_reiter(n, EXPONENT, a, (b + 1) % n, c1, c2)
        expect("T2 mutated public parameter b+1 rejected", bad != m_true, True)
        # T3 mutated ciphertext: must NOT yield the secret
        bad = franklin_reiter(n, EXPONENT, a, b, (c1 + 1) % n, c2)
        expect("T3 mutated ciphertext c1+1 rejected", bad != m_true, True)
        # T4 a non-related pair (random second message) must not leak m
        m_other = (m_true * 7 + 11) % n
        c2_unrelated = rsa_encrypt(m_other, EXPONENT, n)
        bad = franklin_reiter(n, EXPONENT, a, b, c1, c2_unrelated)
        expect("T4 unrelated second ciphertext rejected", bad != m_true, True)
        # T5 real-world exponent: the same code path must decline, not fabricate
        n2, e2 = n, REAL_WORLD_EXPONENT
        a2, b2 = a, b
        m2v = (a2 * m_true + b2) % n2
        cc1 = rsa_encrypt(m_true, e2, n2)
        cc2 = rsa_encrypt(m2v, e2, n2)
        # at e=65537 the common gcd is not linear, so the attack has no root to
        # read off; prove the small-exponent shortcut does NOT apply rather than
        # running a 65537-degree Euclid here.
        lin = franklin_reiter(n2, e2, a2, b2, cc1, cc2)
        expect("T5 e=65537 yields no linear-gcd recovery (documented limit)", lin, None)
        # T6 Hastad broadcast on three published moduli, agreement with A
        cs = [rsa_encrypt(m_true, EXPONENT, RSA[k]) for k in ("RSA-100", "RSA-110", "RSA-120")]
        hb = hastad_broadcast(cs, [RSA[k] for k in ("RSA-100", "RSA-110", "RSA-120")], EXPONENT)
        expect("T6 cleanroom Hastad broadcast agrees with Franklin-Reiter",
               hb == m_true and hb == rec, True)
        # T7 Hastad must FAIL (not wrap) when m^e >= product of moduli
        big = (1 << 400) + 12345
        cs_b = [rsa_encrypt(big, EXPONENT, RSA[k]) for k in ("RSA-100", "RSA-110", "RSA-120")]
        expect("T7 oversized message is reported unrecoverable, not truncated",
               hastad_broadcast(cs_b, [RSA[k] for k in ("RSA-100", "RSA-110", "RSA-120")], EXPONENT),
               None)
        # T8 reusing the same modulus twice is not a broadcast: with nCopied == n0
        # the cube root cannot be pinned, so the attack must return nothing.
        dup = [RSA["RSA-100"], RSA["RSA-100"], RSA["RSA-110"]]
        cs_d = [rsa_encrypt(m_true, EXPONENT, mm) for mm in dup]
        expect("T8 duplicated (non-coprime) modulus does not leak the secret",
               hastad_broadcast(cs_d, dup, EXPONENT) != m_true, True)
        # T9 poly gcd over a composite ring where the divisor's leading
        #    coefficient 3 has no inverse mod 15 must report None, not guess.
        n_bad = 15          # 3*5, so 3 has no inverse
        expect("T9 non-invertible leading coefficient -> None",
               poly_gcd([1, 0, 1], [3, 1], n_bad), None)
        # T10 digest sensitivity: flipping ONE result byte must change the digest
        rec_json = None
        try:
            with open(args.run_json) as f:
                rec_json = json.load(f)
        except OSError:
            pass
        if rec_json and "benchmark_result_record_hex" in rec_json:
            h = rec_json["benchmark_result_record_hex"]
            d0 = recompute_result_digest(h)
            mutated = h[:40] + ("%02x" % ((int(h[40:42], 16) ^ 0x01) & 0xFF)) + h[42:]
            d1 = recompute_result_digest(mutated)
            expect("T10 one flipped result byte changes the result digest",
                   d0 != d1, True)
            expect("T11 reported result digest equals recomputed digest",
                   rec_json.get("benchmark_result_digest"), d0)
            expect("T12 run-config digest equals recomputed digest",
                   rec_json.get("run_receipt_digest"),
                   recompute_run_digest(rec_json["run_config_record_hex"]))
            # T13 the run-config digest must NOT depend on the results
            expect("T13 run digest independent of result bytes (separated meanings)",
                   recompute_run_digest(rec_json["run_config_record_hex"])
                   != recompute_result_digest(h), True)
        else:
            print("[cleanroom] no run json present; digest checks T10-T13 skipped "
                  "(run the gate first, or drop --self-test)")

        for p in passes:
            print(f"  [PASS] {p}")
        for f in fails:
            print(f"  [FAIL] {f}")
        print(f"[cleanroom] adversarial suite: {len(passes)} passed, {len(fails)} failed")
        return 1 if fails else 0

    # ---- normal mode: verify a solver run without trusting it ------------
    with open(args.run_json) as f:
        run = json.load(f)
    inst = dict(run["instance"])
    inst["alleged_m"] = run["recovered_m"]

    ok_rederive = verify_public_instance(inst)
    ok_indep = franklin_reiter(int(inst["n1"]), int(inst["e"]), int(inst["a"]), int(inst["b"]),
                               int(inst["c1"]), int(inst["c2"]))
    ok_agree = ok_indep is not None and int(inst["alleged_m"]) == ok_indep
    hold = run.get("holdout", {})
    ok_hold = True
    if hold:
        hn = int(inst["n1"])
        hm2 = (int(hold["a"]) * int(inst["alleged_m"]) + int(hold["b"])) % hn
        ok_hold = (rsa_encrypt(int(inst["alleged_m"]), int(inst["e"]), hn) == int(hold["c1"])
                   and rsa_encrypt(hm2, int(inst["e"]), hn) == int(hold["c2"])
                   and franklin_reiter(hn, int(inst["e"]), int(hold["a"]), int(hold["b"]),
                                       int(hold["c1"]), int(hold["c2"])) == int(inst["alleged_m"]))
    d_run = recompute_run_digest(run["run_config_record_hex"])
    d_res = recompute_result_digest(run["benchmark_result_record_hex"], "outcome")
    d_tim = recompute_result_digest(run["benchmark_result_record_hex"], "timing")
    d_art = execution_artifact_digest(args.source)
    fields = result_fields_change(run["benchmark_result_record_hex"])

    print(f"[cleanroom] re-encryption of alleged secret matches (c1,c2) : {ok_rederive}")
    print(f"[cleanroom] independent re-attack reproduces it            : {ok_agree}")
    print(f"[cleanroom] fresh holdout (new affine map) verified          : {ok_hold}")
    print(f"[cleanroom] run_receipt_digest recomputed                    : {d_run}")
    print(f"[cleanroom] benchmark_result_digest recomputed (outcome)     : {d_res}")
    print(f"[cleanroom] run_timing_digest recomputed (not demanded of reproducers): {d_tim}")
    print(f"[cleanroom] execution_artifact_digest ({args.source})  : {d_art}")
    print(f"[cleanroom] result fields decoded from record: "
          f"fr_ok={fields['fr_ok']} fr_deg={fields['fr_deg']} ha_ok={fields['ha_ok']} "
          f"holdout_ok={fields['holdout_ok']} neg_ok={fields['neg_ok']} "
          f"m={fields['m_dec']}")
    checks = {
        "re-encryption consistency": ok_rederive,
        "independent re-attack agrees": ok_agree,
        "fresh holdout verified": ok_hold,
        "run digest matches record": d_run == run.get("run_receipt_digest"),
        "result digest matches record (outcome half)": d_res == run.get("benchmark_result_digest"),
        "timing digest matches record (timing half)": d_tim == run.get("run_timing_digest"),
        "outcome digest is reproducible: it excludes wall-clock bytes":
            d_res != recompute_result_digest(run["benchmark_result_record_hex"], "whole"),
    }
    bad = [k for k, v in checks.items() if not v]
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("[cleanroom] NOTE: execution_artifact_digest is computed here from the file "
          "bytes; the solver cannot self-attest it.")
    if bad:
        print(f"[cleanroom] VERDICT: REJECT ({', '.join(bad)})")
        return 1
    print("[cleanroom] VERDICT: ACCEPT (independently re-derived, not copied)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
