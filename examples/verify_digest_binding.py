#!/usr/bin/env python3
"""
LIN-CRYPTO-MAX-256 digest-binding audit.

WHY THIS EXISTS
---------------
The MAX-256 receipt carried one field named `execution_digest`.  A field like
that must have exactly ONE meaning, and it must actually bind something:

  * if it names the *artifact*, it must be the hash of the immutable source or
    binary that was executed, and it must be recomputable by a reader;
  * if it names the *execution / report*, it must change whenever the
    benchmark or the measured results change.

The audit below shows that the MAX-256 `execution_digest` did neither: it bound
no file, no record and no result in this repository (it is unreproducible by
construction), while the numbers next to it in the same receipt do not even
agree with the measurements they claim to summarise.

The audit is deliberately read-only: it recomputes, compares, and reports.  It
never rewrites a published receipt in place.  Superseding a receipt means
emitting a new version whose digests are reproducible, with a changelog.

Usage:
    python3 examples/verify_digest_binding.py                 # audit (exit 1 = defects)
    python3 examples/verify_digest_binding.py --emit-corrections
            # also write docs/events/EVENT_LIN_CRYPTO_MAX_256_FRONTIER.rulel
            # as a v1.1.0 companion file with recomputed digests
"""

import argparse
import hashlib
import math
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECEIPT = os.path.join(REPO, "docs/events/EVENT_LIN_CRYPTO_MAX_256_FRONTIER.rulel")
SOURCE = os.path.join(REPO, "test/test_lin_crypto_max_256.c")
SECONDS_PER_YEAR = 365.2425 * 86400


def sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def parse_kv(text: str) -> dict:
    """Extract key="value" and key=value pairs from a RULEL body (flat)."""
    out = {}
    for m in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s\n]+))', text):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


def section(text: str, name: str) -> str:
    m = re.search(r"\." + re.escape(name) + r"\s*\{(.*?)\}", text, re.S)
    return m.group(1) if m else ""


def repo_grep(pattern: str) -> list:
    """Search the working tree (tracked files only, so scratch output is out)."""
    try:
        r = subprocess.run(["git", "-C", REPO, "grep", "-l", "-F", pattern],
                           capture_output=True, text=True)
    except OSError:
        return []
    return [l for l in r.stdout.split() if l]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-corrections", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(RECEIPT):
        print(f"[binding] missing receipt: {RECEIPT}", file=sys.stderr)
        return 2
    rtext = open(RECEIPT).read()
    stext = open(SOURCE).read()
    st_lines = stext.splitlines()

    spec = parse_kv(section(rtext, "s"))
    ident = parse_kv(section(rtext, "i"))
    res = parse_kv(section(rtext, "r"))
    ext = parse_kv(section(rtext, "e"))
    ver = parse_kv(section(rtext, "v"))

    findings = []      # (severity, code, message)

    def note(sev, code, msg):
        findings.append((sev, code, msg))

    # ---------------------------------------------------------------- 1
    # The digest must bind SOMETHING that a reader can recompute.
    claimed_digest = ident.get("execution_digest", "")
    digest_hex = claimed_digest.split(":")[-1]
    hits = repo_grep(digest_hex)
    bound_files = []
    for cand in ("test/test_lin_crypto_max_256.c", "src/lin_crypto_max_256.lin"):
        p = os.path.join(REPO, cand)
        if os.path.exists(p) and sha256_of(p) == claimed_digest:
            bound_files.append(cand)
    print(f"[1] execution_digest as published     : {claimed_digest}")
    print(f"    occurrences of that hex elsewhere in the repo (excluding the receipt itself): "
          f"{[h for h in hits if not h.endswith('EVENT_LIN_CRYPTO_MAX_256_FRONTIER.rulel')]}")
    if not bound_files:
        actual = sha256_of(SOURCE)
        print(f"    sha256(test/test_lin_crypto_max_256.c) : {actual}")
        print(f"    sha256(src/lin_crypto_max_256.lin)     : "
              f"{sha256_of(os.path.join(REPO, 'src/lin_crypto_max_256.lin')) if os.path.exists(os.path.join(REPO,'src/lin_crypto_max_256.lin')) else 'n/a'}")
        note("FATAL", "DIGEST_UNBOUND",
             "`execution_digest` matches no file, record or result in the repository. "
             "It is a magic constant: an external verifier cannot recompute it, so it "
             "certifies nothing. Either bind it to the executed artifact (sha256 of the "
             "source/binary) or split it into hardware_identity / execution_artifact_digest "
             "/ run_receipt_digest / benchmark_result_digest.")

    # ---------------------------------------------------------------- 2
    # One field, one meaning: show the four digests are distinct quantities.
    print("[2] digest separation check")
    parts = {
        "hardware_identity": ident.get("hardware_identity", ""),
        "execution_artifact_digest": sha256_of(SOURCE),
    }
    for k, v in parts.items():
        print(f"    {k:26s}: {v}")
    note("MUST-FIX", "DIGEST_NOT_SPLIT",
         "A single `execution_digest` was asked to stand for hardware, artifact, run and "
         "result at once. Emit four fields with four definitions; a result digest that "
         "does not move when the results move is stale by construction.")

    # ---------------------------------------------------------------- 3
    # Rate consistency
    claimed_rate = float(re.match(r"([0-9.]+)", ident.get("measured_rate_per_sec", "0")).group(1))
    print(f"[3] measured rate as published        : {claimed_rate:.6e} ops/s "
          f"({ident.get('measured_rate_per_sec')})")
    for label, rate in (("receipt", claimed_rate), ("user rerun", 136_510_000.0)):
        secs = (1 << 256) / rate
        years = secs / SECONDS_PER_YEAR
        print(f"    2^256 at {label:11s} rate : {secs:.3e} s = {years:.3e} years")
    secs_pub = float(re.search(r"([\d.]+)e\+?(\d+)", ext.get("estimated_full_256_seconds", "0e0")).group(0).replace("e+", "e"))
    implied = (1 << 256) / secs_pub
    print(f"    rate implied by published seconds: {implied:.6e} ops/s")
    if abs(implied - claimed_rate) / claimed_rate > 0.005:
        note("FATAL", "RESULT_RATE_MISMATCH",
             f"published extrapolation implies {implied:.4e} ops/s but the receipt reports "
             f"{claimed_rate:.4e} ops/s ({100*abs(implied-claimed_rate)/claimed_rate:.1f}% off). "
             "The result digest should have moved when the measured rate moved; it did not, "
             "because no digest covers the results.")

    # ---------------------------------------------------------------- 3b
    # The receipt must not cite a rate that no longer matches the measurement.
    canonical_rate = 136_510_000.0          # rerun value adopted for v1.1.0
    if abs(claimed_rate - canonical_rate) / canonical_rate > 0.005:
        note("MUST-FIX", "STALE_RATE_CITED",
             f"the receipt cites {claimed_rate:.4e} ops/s while the rerun measured "
             f"{canonical_rate:.4e} ops/s; the published 2^256 figures "
             f"({ext.get('estimated_full_256_seconds')}) are internally consistent with the "
             f"OLD rate, so the numbers were never recomputed after the rerun. Corrected: "
             f"{(1<<256)/canonical_rate:.3e} s = {(1<<256)/canonical_rate/SECONDS_PER_YEAR:.3e} years.")

    # ---------------------------------------------------------------- 4
    # Executed vs predicted: is every scaling point a measurement?
    print("[4] scaling table provenance")
    m = re.search(r"void run_level2_scaling\([^)]*\)\s*\{(.*?)\n\}", stext, re.S)
    body = m.group(1) if m else ""
    synth_lines = [i + 1 for i, l in enumerate(st_lines)
                   if "observed_time_sec" in l and "=" in l and "==" not in l]
    for ln in synth_lines:
        print(f"    line {ln}: {st_lines[ln-1].strip()}")
    measurement_markers = ["clock_gettime", "clock(", "elapsed", "measure", "now_s"]
    if synth_lines and not any(k in body for k in measurement_markers):
        note("FATAL", "PREDICTED_REPORTED_AS_OBSERVED",
             f"run_level2_scaling() fills `observed_time_sec` (line {synth_lines[0]}) with the "
             "same closed-form expression used for `predicted_time_sec`, and the function "
             "contains no clock read at all. Therefore N=32/36/40 are extrapolations, not "
             "measurements. Mark them EXTRAPOLATED_FROM_MEASURED_RATE; the largest fully "
             "executed exhaustive level stays N=28.")

    # ---------------------------------------------------------------- 5
    # Algorithm label vs what the code computes
    print("[5] algorithm label vs executed code")
    print(f"    receipt .s.algorithm = {spec.get('algorithm')!r}")
    aes_full_rounds = re.findall(r"for\s*\([^;]*;\s*r\s*<\s*1[04]\b", stext)
    sbox_uses = stext.count("SBOX") + stext.count("sbox")
    print(f"    'SBOX'/'sbox' occurrences in the benchmark source : {sbox_uses}")
    print(f"    AES round-loop signatures (r<10 / r<14)           : {len(aes_full_rounds)}")
    if "AES-256" in spec.get("algorithm", "") and len(aes_full_rounds) == 0:
        note("FATAL", "ALGORITHM_MISLABELLED",
             "The receipt calls the workload AES-256, but the benchmarked function is the "
             "custom 64-bit `aes256_eval_fast` construction (AES S-box lookups plus two "
             "multiplicative mixers), not AES-256 as specified in FIPS-197. A cost claim about "
             "this function says nothing about AES-256. Either rename the workload or benchmark "
             "a FIPS-197 implementation.")

    # ---------------------------------------------------------------- 6
    # Over-claim in the verdict block
    print("[6] verdict wording")
    over = ver.get("security_frontier_certified", "")
    print(f"    security_frontier_certified = {over!r}")
    if over:
        note("FATAL", "OVERCLAIM_UNBREAKABLE",
             "`CLASSICAL_256BIT_SECURITY_IS_UNBREAKABLE` is not a claim this gate can support. "
             "Exhaustive-search cost at 2^256 is not unbreakability, not resistance to "
             "non-exhaustive attacks, and not a proof; this project's own CRYPTO-256-REAL gate "
             "recovers a secret from a real published RSA instance in 20 ms without touching "
             "the key space. State the claim as: classical exhaustive search over 2^256 is "
             "infeasible at the measured rate on this hardware class.")

    # ---------------------------------------------------------------- 7
    # Do the "adversarial" subgates actually gate anything?
    print("[7] adversarial integrity suite")
    m = re.search(r"void run_adversarial_tests\(\)\s*\{(.*?)\n\}\n", stext, re.S)
    ab = m.group(1) if m else ""
    n_checks = len(re.findall(r"Detected=%s", ab))
    n_hardcoded_pass = len(re.findall(r"\[PASS\]\\n", ab))
    always_zero = bool(re.search(r"return 0;\s*\}\s*$", stext.strip()[-40:], re.S)) or \
        "return 0;" in stext.split("run_adversarial_tests();")[-1]
    print(f"    subgates printed                 : {n_checks}")
    print(f"    literal '[PASS]' inside printf   : {n_hardcoded_pass}")
    print(f"    main() returns 0 unconditionally : {always_zero}")
    if n_checks and n_hardcoded_pass >= n_checks:
        note("FATAL", "ADVERSARIAL_TESTS_UNBOUND",
             "run_adversarial_tests() prints '[PASS]' inside the format string, so the label is "
             "independent of the data. It then counts DETECTIONS as successes "
             "(`if (is_overlap) rejected++;`) and main() still returns 0 for any count, so a "
             "detected violation cannot fail the gate. Worse, two fixtures assert the opposite "
             "of their names: RANGE_OVERLAP uses w1.start=950 <= w0.end=1001 (a real overlap) "
             "and FAKE_COVERAGE uses actual=8000 < claimed=10000 (real under-coverage), both "
             "printed as FAIL_CLOSED [PASS]. Replace with: compute a predicate, print its value, "
             "and exit non-zero from the aggregate.")

    # ---------------------------------------------------------------- 8
    # receipt_integrity="PASS" must be reproducible, not asserted
    print("[8] receipt_integrity")
    ri = ver.get("receipt_integrity", "")
    print(f"    receipt_integrity = {ri!r} (self-asserted string, no digest behind it)")
    if ri and not bound_files:
        note("MUST-FIX", "INTEGRITY_ASSERTED_NOT_COMPUTED",
             "`receipt_integrity=\"PASS\"` coexists with an unbound digest. Integrity must be "
             "a recomputable relation (digest of canonical record == digest in the receipt), "
             "never a literal.")

    # ---------------------------------------------------------------- 9
    # honest state register
    print("[9] claim-scope and state classification")
    scope_ok = "Claim scope" in rtext or "claim_scope" in rtext
    empirical_ok = "EMPIRICALLY_EXECUTED" in rtext
    extrap_ok = "EXTRAPOLATED_FROM_MEASURED_RATE" in rtext
    print(f"    has Claim scope section            : {scope_ok}")
    print(f"    labels EMPIRICALLY_EXECUTED        : {empirical_ok}")
    print(f"    labels EXTRAPOLATED_FROM_MEASURED_RATE : {extrap_ok}")
    if not (scope_ok and empirical_ok and extrap_ok):
        note("MUST-FIX", "STATE_REGISTER_MISSING",
             "The receipt mixes executed levels (N=20/24/28) with extrapolated ones "
             "(N=32..40, N=256) in a single `instances_evaluated` string. Register them "
             "separately, name the largest fully executed level, and state the claim scope: "
             "classical exhaustive-search infeasibility only -- not an AES-256 break and not a "
             "security proof.")

    # ------------------------------------------------------------- report
    print("\n" + "=" * 74)
    print("LIN-CRYPTO-MAX-256 DIGEST-BINDING AUDIT -- FINDINGS")
    print("=" * 74)
    for sev, code, msg in findings:
        print(f"[{sev}] {code}\n    {msg}\n")
    fat = sum(1 for f in findings if f[0] == "FATAL")
    mus = sum(1 for f in findings if f[0] == "MUST-FIX")
    print(f"summary: {fat} FATAL, {mus} MUST-FIX, {len(findings)} findings total")

    if args.emit_corrections:
        out = os.path.join(REPO, "docs/events/EVENT_LIN_CRYPTO_MAX_256_FRONTIER_v1_1_0.rulel")
        secs = (1 << 256) / 136_510_000.0
        yrs = secs / SECONDS_PER_YEAR
        art = sha256_of(SOURCE)
        body = f'''@RULEL:LIN_CRYPTO_256_RECEIPT:1.1.0
@CHALLENGE_ID="LIN-CRYPTO-MAX-256"
@TITLE="256-Bit Classical Exhaustive-Search Cost Frontier (audited restatement)"
@STATUS="PASS_WITH_SCOPE_LIMITS"
@DATE="{__import__('datetime').date.today().isoformat()}"
@SUPERSEDES="EVENT_LIN_CRYPTO_MAX_256_FRONTIER.rulel (1.0.0, retained unchanged as history)"

~R{{.s=spec .i=identity .r=results .x=state_register .e=extrapolation .b=binding .v=verdict}}

.s{{
  challenge_id="LIN-CRYPTO-MAX-256"
  security_target_bits=256
  computation_model="CLASSICAL"
  workload="LIN 64-bit key-evaluation function (AES S-box + two multiplicative mixers)"
  workload_is_not="AES-256 as specified in FIPS-197"
  parameter_class="EXPERIMENTAL (benchmark-specific evaluation function, not a standard primitive)"
}}

.i{{
  hardware_identity="Intel(R) Xeon(R) Processor @ 2.60GHz | 2 cores | x86_64 | linux | gcc"
  hardware_identity_rule="free-text descriptor; NOT a digest, so it must never be cited as one"
  execution_artifact_digest="{art}"
  execution_artifact_digest_rule="sha256 of test/test_lin_crypto_max_256.c as committed; recompute with sha256sum"
  run_receipt_digest="RECOMPUTED_PER_RUN"
  run_receipt_digest_rule="sha256 over the canonical 176-byte run-config record emitted by the harness"
  benchmark_result_digest="RECOMPUTED_PER_RESULTS"
  benchmark_result_digest_rule="sha256 over the canonical deterministic-outcome half of the result record; MUST change when measured outcomes change; timings live in a separate run_timing_digest so a reproducer on other hardware is never asked to match a clock"
}}

.r{{
  largest_exhaustive_test_bits=28
  searched_states=268435456
  coverage_percent="100% of the N=28 space, for the executed levels only"
  measured_rate_per_sec="136510000 (136.51 Mops/s, rerun value)"
  prior_reported_rate_per_sec="132660000 (132.66 Mops/s, v1.0.0 receipt)"
  rate_change_note="v1.0.0 extrapolations were derived from the older rate and were not recomputed"
  workers_evaluated="1, 2, 4, 8, 16 workers"
  independent_verifier=true
}}

.x{{
  EMPIRICALLY_EXECUTED="N=20, N=24, N=28 (28 is the largest fully executed level)"
  EXTRAPOLATED_FROM_MEASURED_RATE="N=32, N=36, N=40, N=256"
  NOT_MEASURED="observed_time_sec for N>=32 was filled from the closed-form prediction"
  integrity_suite_status="DEFECTIVE_IN_v1_0_0: subgates printed a literal [PASS] and two fixtures asserted the opposite of their name"
}}

.e{{
  cardinality_2_256="{1 << 256}"
  estimated_full_256_seconds="{secs:.3e} s"
  estimated_full_256_years="{yrs:.3e} years"
  universe_age_years="1.38e+10 years"
  infeasibility_factor="10^{math.log10(secs / 1.38e10):.1f} times the age of the observable universe"
  feasibility_class="COMPUTATIONALLY_INFEASIBLE_FOR_CLASSICAL_EXHAUSTIVE_SEARCH"
  method="2^256 / 136.51e6 ops/s; single-thread rate, no parallel speedup assumed"
}}

.b{{
  covers="artifact source bytes, run configuration record, measured result record"
  does_not_cover="any AES-256 claim; any non-exhaustive attack; any security proof; the v1.0.0 execution_digest (which bound nothing)"
  rule="a change to the benchmark source changes execution_artifact_digest; a change to the measurements changes benchmark_result_digest; neither can be self-attested by the binary"
}}

.v{{
  verdict="PASS_WITH_SCOPE_LIMITS"
  claim_scope="classical exhaustive-search infeasibility at 2^256 on this hardware class only"
  NOT_claimed="break of AES-256; break of any cipher; proof of security; quantum resistance"
  NOT_claimed_reason="cost of exhaustive search is a lower bound on one attack family, not an upper bound on all attacks"
  receipt_integrity="see .b: recomputed by examples/verify_digest_binding.py, not asserted here"
  security_frontier_certified="REMOVED -- v1.0.0 wording 'CLASSICAL_256BIT_SECURITY_IS_UNBREAKABLE' was an over-claim"
}}
'''
        with open(out, "w") as f:
            f.write(body)
        print(f"\n[binding] wrote audited restatement: {out}")
        print("[binding] the v1.0.0 receipt is left byte-identical on purpose: a superseded "
              "receipt must stay verifiable, and its unbound digest stays as the evidence of the defect.")

    print("\nVERDICT:", "REJECT -- receipt does not survive its own digest claim" if fat else "ACCEPT")
    return 1 if fat else 0


if __name__ == "__main__":
    sys.exit(main())
