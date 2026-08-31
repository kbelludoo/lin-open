.PHONY: all build build-gpu build-cpu test test-cpu lint clean crypto256-real crypto256-audit

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

# --------------------------------------------------------------------------
# LIN-CRYPTO-256-REAL: a real cryptanalysis gate (no Zig required).
#
#   pillar A  exhaustive frontier .......... (LIN-CRYPTO-MAX-256, measured cost)
#   pillar B  published attack on public parameters ... test/test_lin_crypto_256_real.c
#   pillar C  independent cleanroom reproduction ...... examples/verify_crypto256_real_cleanroom.py
#
# These targets deliberately do NOT depend on build-cpu: they must run on a
# machine with no Zig toolchain, or the "independent reproduction" pillar would
# require trusting our build pipeline.
BIN_BIND := /tmp/lin-crypto-256-real
CRYPTO_REAL_SRC := test/test_lin_crypto_256_real.c

.PHONY: crypto256-real
crypto256-real:
	@echo "== build the cryptanalysis gate =="
	@gcc -O2 -std=gnu11 -Wall -Wextra -o $(BIN_BIND) $(CRYPTO_REAL_SRC) -lm
	@echo "== run it (primitive self-test -> attacks -> holdout -> negative control) =="
	@$(BIN_BIND)
	@echo "== adversarial suite of the independent verifier (must all be REJECTED) =="
	@python3 examples/verify_crypto256_real_cleanroom.py --self-test
	@echo "== cleanroom reproduction of the run (no solver code imported) =="
	@python3 examples/verify_crypto256_real_cleanroom.py
	@echo "== LIN policy gate (executable reading; .lin needs Zig to compile) =="
	@python3 examples/check_crypto256_real_policy.py

# Bind a receipt whose digests are recomputable, then audit MAX-256's digest
# binding (the one field that carried four meanings and bound none).
#
# The audit's expected outcome on the v1.0.0 receipt is a REJECT: it is a
# defect-reporting tool, not a pass/fail gate, so its exit status is reported
# rather than propagated.  CI asserts the specific findings are still present.
.PHONY: crypto256-audit
crypto256-audit:
	@echo "== bind the CRYPTO-256-REAL receipt (refuses to write a bad one) =="
	@python3 examples/bind_crypto256_real_receipt.py
	@echo "== rebinding must be byte-reproducible =="
	@cp docs/events/EVENT_LIN_CRYPTO_256_REAL.rulel /tmp/lin_crypto256_real_1.rulel
	@python3 examples/bind_crypto256_real_receipt.py > /dev/null
	@cmp -s /tmp/lin_crypto256_real_1.rulel docs/events/EVENT_LIN_CRYPTO_256_REAL.rulel \
	  && echo "  receipt rebinds byte-identically" \
	  || { echo "  FAIL: receipt is not reproducible"; exit 1; }
	@echo "== MAX-256 digest-binding audit (reports defects; expect VERDICT: REJECT) =="
	@python3 examples/verify_digest_binding.py --emit-corrections; \
	  rc=$$?; \
	  if [ $$rc -eq 0 ]; then echo "  note: audit now PASSES -- the v1.0.0 defects were fixed; " 	    "update the audit expectations if that was intentional"; \
	  else echo "  audit reported its findings (exit $$rc, expected while v1.0.0 stands)"; fi
	@echo "== superseded v1.0.0 receipt must remain untouched (supersede, never rewrite) =="
	@git diff --quiet docs/events/EVENT_LIN_CRYPTO_MAX_256_FRONTIER.rulel \
	  && echo "  v1.0.0 byte-identical" || { echo "  FAIL: v1.0.0 receipt was modified"; exit 1; }

clean:
	@rm -rf zig-out zig-cache .zig-cache bin/lin_native /tmp/lin_rec.rulel $(BIN_BIND)
