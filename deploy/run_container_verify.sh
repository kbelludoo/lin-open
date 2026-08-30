#!/usr/bin/env bash
# LIN-ATTEST-009: Automated Container & Multi-Environment Replay Harness
# Can be run under Docker, Podman, or standalone CI/CD runners.
set -euo pipefail

BUNDLE_PATH="${1:-bundle_attestation.rulel}"
OUTPUT_RECEIPT="${2:-consensus_receipt.rulel}"

echo "================================================================================"
echo "=== LIN-ATTEST-009: CONTAINERIZED / MULTI-ENVIRONMENT REPLAY RUNNER          ==="
echo "================================================================================"
echo "Bundle:          ${BUNDLE_PATH}"
echo "Output Receipt:  ${OUTPUT_RECEIPT}"
echo "Execution Mode:  HERMETIC MULTI-RUNTIME CROSS-VERIFICATION"
echo ""

zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL src/lin.zig -- cross-verify "${BUNDLE_PATH}" -o "${OUTPUT_RECEIPT}"

echo ""
echo "--------------------------------------------------------------------------------"
echo "MULTI-RUNTIME EQUIVALENCE: VERIFIED (Bit-exact consensus achieved)"
echo "================================================================================"
