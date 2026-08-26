SELF-OPTIMIZE-02 RESULT:
  module: content_hash.lin
  baseline: MJS (Node.js v24.19.0)
  candidate: Rust v2 (pre-compiled regex, lazy_static)

MATRIX:
  canonicalize:
    MJS:     2.29 us/call
    Rust v1: 248.49 us/call  (+108x)
    Rust v2: 109.81 us/call  (+48x)
    v2 vs v1: 2.26x improvement

  contentHash:
    MJS:     8.26 us/call
    Rust v1: 252.79 us/call  (+30x)
    Rust v2: 110.89 us/call  (+13x)
    v2 vs v1: 2.28x improvement

  semanticEquals:
    MJS:    15.14 us/call
    Rust v2: 209.74 us/call  (+14x)

  buildContentRegistry:
    MJS:    76.08 us/call
    Rust v2: 1120.50 us/call (+15x)

MODULE-LEVEL DELTA: Rust v2 is 13-48x SLOWER than MJS

SEMANTIC EQUIVALENCE: FAIL
  MJS canonicalize:  313817cb68d86490
  Rust canonicalize: 2c22aa13d84f2fc5  ← DIFFERENT
  MJS contentHash:   060ad1cc47cbc1da
  Rust contentHash:  d6960c4815eeaef4  ← DIFFERENT

DECISION: REJECT (both semantic mismatch AND performance regression)

CAUSE_SEMANTIC: Likely difference in regex behavior or string normalization
  between V8 regex engine and Rust regex crate.
  Investigation needed to find exact divergence point.

CAUSE_PERFORMANCE: Even with pre-compiled regex, Rust string allocation
  overhead dominates. The MJS version benefits from V8's rope-based
  string representation and optimized regex cache.

LESSON: 
  1. Semantic equivalence must be verified BEFORE measuring performance.
  2. Naive porting to systems language can be slower AND semantically wrong.
  3. The V8 engine is highly optimized for string-heavy workloads.
  4. Rust advantages shine in different workload patterns (ownership, concurrency).

NEXT HYPOTHESIS (SELF-OPTIMIZE-03):
  Investigate WHY hashes differ. Fix semantic mismatch first.
  Only then consider if Rust is appropriate for this module at all.
  Alternative: this module may simply be better in MJS/V8.
