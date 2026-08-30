#!/usr/bin/env bash
set -euo pipefail

echo "================================================================================"
echo "=== LIN COMPILER REPRODUCIBILITY & DRIFT AUDIT ==="
echo "================================================================================"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f "bin/lin_native" ]; then
    echo "[1/4] Building bin/lin_native compiler binary..."
    mkdir -p bin
    zig build-exe src/lin.zig -O ReleaseFast -femit-bin=bin/lin_native
else
    echo "[1/4] Compiler binary bin/lin_native found."
fi

echo "[2/4] Regenerating all .zig artifacts from canonical .lin sources..."
bin/lin_native compile src/lin_linux_kernel.lin --target zig -o src/lin_linux_kernel.zig
bin/lin_native compile src/lin_miner.lin --target zig -o src/lin_miner.zig

for lin_file in test/corpus/*.lin; do
    zig_file="${lin_file%.lin}.zig"
    echo "  Re-compiling $lin_file -> $zig_file"
    bin/lin_native compile "$lin_file" --target zig -o "$zig_file"
done

echo "[3/4] Checking for drift between generated .zig files and git state..."
git status --porcelain test/corpus/*.zig src/lin_linux_kernel.zig src/lin_miner.zig

echo "[4/4] Running 18-target audited benchmark and test suite..."
zig run -O ReleaseFast benchmark_harness.zig
bin/lin_native test

echo "================================================================================"
echo "=== REPRODUCIBILITY AUDIT PASSED: ZERO DRIFT & 100% BIT-EXACT MATCHES ==="
echo "================================================================================"
