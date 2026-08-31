.PHONY: all build build-gpu build-cpu test test-cpu lint clean

# LIN build/test Makefile (2026-08-31)
#
# Modes:
#   make build        -> GPU build via `zig build` (links OpenCL/ROCm; needs CL headers)
#   make build-cpu    -> CPU-only build via `zig build -Dgpu=false`
#                        (no OpenCL toolchain required; uses a local CL stub;
#                         GPU commands fail gracefully)
#   make test         -> GPU build + check all src/examples .lin + receipt round-trip
#   make test-cpu     -> CPU-only build + same checks (no OpenCL needed)

BUILD_GPU := zig build -Doptimize=ReleaseFast
BUILD_CPU := zig build -Dgpu=false -Doptimize=ReleaseFast
BIN := zig-out/bin/lin_native

all: test

build: build-gpu

build-gpu:
	$(BUILD_GPU)

build-cpu:
	$(BUILD_CPU)

# CPU checks that need no GPU hardware (they only need a linked binary):
#   - version, parse+type-check+lint every .lin under src/ and examples/
#   - compute-receipt create -> verify round-trip
test: build-gpu
	@echo "== version =="; $(BIN) version
	@echo; echo "== check: all src/*.lin and examples/*.lin =="
	@fail=0; for f in $$(find src examples -name '*.lin' | sort); do \
	  out=$$($(BIN) check "$$f" 2>&1); \
	  if printf '%s' "$$out" | grep -q '^@RULEL:LIN_CHECK:1.0.0'; then echo "  OK   $$f"; else echo "  FAIL $$f"; fail=1; fi; \
	done; \
	if [ "$$fail" != 0 ]; then echo "test: one or more .lin files failed check"; exit 1; fi; \
	echo "test: all .lin files pass check"
	@echo; echo "== receipt round-trip =="
	@$(BIN) receipt create --source "return x * x;" --input 9 > /tmp/lin_rec.rulel
	@$(BIN) receipt verify --receipt /tmp/lin_rec.rulel

# Same checks but with the CPU-only build (no OpenCL toolchain needed).
test-cpu: build-cpu
	@echo "== version (cpu) =="; $(BIN) version
	@echo; echo "== check: all src/*.lin and examples/*.lin (cpu) =="
	@fail=0; for f in $$(find src examples -name '*.lin' | sort); do \
	  out=$$($(BIN) check "$$f" 2>&1); \
	  if printf '%s' "$$out" | grep -q '^@RULEL:LIN_CHECK:1.0.0'; then echo "  OK   $$f"; else echo "  FAIL $$f"; fail=1; fi; \
	done; \
	if [ "$$fail" != 0 ]; then echo "test-cpu: one or more .lin files failed check"; exit 1; fi; \
	echo "test-cpu: all .lin files pass check"
	@echo; echo "== receipt round-trip (cpu) =="
	@$(BIN) receipt create --source "return x * x;" --input 9 > /tmp/lin_rec.rulel
	@$(BIN) receipt verify --receipt /tmp/lin_rec.rulel

# Independent zero-trust receipt verification: recomputes the Merkle root
# with python3 / bash+openssl / node — no LIN binary involved. Requires
# python3, openssl and node (all present on ubuntu-latest CI runners).
.PHONY: verify-receipt
verify-receipt: build-cpu
	@echo "== independent receipt verification (python3) =="
	@python3 benchmarks/verify_receipt.py benchmarks/fixtures/receipt_sqr9.json
	@python3 benchmarks/verify_receipt.py benchmarks/fixtures/receipt_sqr9.rulel
	@echo "== independent receipt verification (bash + openssl) =="
	@bash benchmarks/verify_receipt.sh benchmarks/fixtures/receipt_sqr9.json
	@bash benchmarks/verify_receipt.sh benchmarks/fixtures/receipt_sqr9.rulel
	@echo "== independent receipt verification (node) =="
	@node benchmarks/verify_receipt.js benchmarks/fixtures/receipt_sqr9.json
	@node benchmarks/verify_receipt.js benchmarks/fixtures/receipt_sqr9.rulel
	@echo "== tamper must FAIL =="
	@sed 's/"output": "81"/"output": "82"/' benchmarks/fixtures/receipt_sqr9.json > /tmp/lin_tampered.json
	@if python3 benchmarks/verify_receipt.py /tmp/lin_tampered.json > /dev/null 2>&1; then \
	  echo "verify-receipt: tampered receipt PASSED (BUG)"; exit 1; \
	else echo "tampered receipt correctly rejected"; fi
	@rm -f /tmp/lin_tampered.json

clean:
	@rm -rf zig-out zig-cache .zig-cache bin/lin_native /tmp/lin_rec.rulel
