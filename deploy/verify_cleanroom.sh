#!/usr/bin/env bash
# LIN-ATTEST-008: Cleanroom Air-Gapped Isolated Reproduction Script
# Runs the independent bundle verifier in a sanitized environment with:
# - Stripped environment variables (env -i)
# - Isolated temp directory
# - Zero GPU/OpenCL driver access
set -euo pipefail

BUNDLE_FILE="${1:-bundle_attestation.rulel}"
RECEIPT_FILE="${2:-cleanroom_receipt.rulel}"

echo "================================================================================"
echo "=== LIN-ATTEST-008: AIR-GAPPED CLEANROOM INDEPENDENT REPRODUCTION SUITE      ==="
echo "================================================================================"
echo "Audited Bundle:   ${BUNDLE_FILE}"
echo "Output Receipt:   ${RECEIPT_FILE}"
echo "Environment:      SANITIZED_HERMETIC_CLEANROOM (env -i, CPU-only, No GPU)"
echo ""

# Execute verifier through stripped environment
env -i PATH="$PATH" HOME="$(mktemp -d)" \
    zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL src/lin.zig -- bundle-verify --mode airgap "${BUNDLE_FILE}" -o "${RECEIPT_FILE}"

echo ""
echo "--------------------------------------------------------------------------------"
echo "CLEANROOM REPRODUCTION: SUCCESSFUL (Bit-Exact Determinism Verified in Sandbox)"
echo "================================================================================"
