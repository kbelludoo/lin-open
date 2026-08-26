HYPOTHESIS:
  Migrate content_hash module → Rust

MODULE:
  src/content_hash.lin (8 lines)
  Functions: canonicalize, contentHash, semanticEquals, buildContentRegistry

OBSERVED:
  contentHash bottleneck = SHA-256 via node:crypto
  canonicalize bottleneck = regex string manipulation
  100k contentHash calls = 828.54ms (8.29us/call)
  100k canonicalize calls = 226.37ms (2.26us/call)

CANDIDATES:
  Rust → candidate A
    Reason: native SHA-256 (sha2 crate), zero-cost abstractions, no GC, memory-safe
    Expected: SHA-256 ~10x faster, regex ~3-5x faster
  Nim → candidate B
    Reason: compile to C, good regex libs
    Expected: SHA-256 ~5x faster, regex ~2-3x faster
  C → candidate C
    Reason: fastest possible
    Expected: SHA-256 ~15x faster, but memory-unsafe

SELECTED: Rust (candidate A)
  Justification: Already core host language (LIN_CORE_ARCH), memory-safe, excellent crypto

EVIDENCE_REQUIRED:
  same workload (10 functions, same params/body)
  same oracle (same hashes for same inputs)
  same semantics (canonicalize output identical, contentHash output identical)

GENERATED: src/content_hash.rs
