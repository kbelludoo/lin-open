.PHONY: all build build-gpu build-cpu test test-cpu attestation-gate guard-unit xver gate gate-attest ci-gate lint clean

# LIN build/test Makefile (2026-08-31)
#
# Modes:
#   make build        -> GPU build via `zig build` (links OpenCL/ROCm; needs CL headers)
#   make build-cpu    -> CPU-only build via `zig build -Dgpu=false`
#                        (no OpenCL toolchain required; uses a local CL stub;
#                         GPU commands fail gracefully)
#   make test         -> GPU build + check all src/examples .lin + receipt round-trip
#   make test-cpu     -> CPU-only build + same checks (no OpenCL needed)
#   make attestation-gate
#                     -> asserts the attestation guard fails closed on commands
#                        that have no computed evidence, and that the real
#                        receipt/Merkle, Ed25519 notary and N-Version paths pass
#   make xver         -> build the C11 port and cross-check it against the Zig
#                        LinVM (same expression, same bytecode, same Merkle root)
#   make gate         -> LIN Gate: fail unless the tracked toolchain still hashes
#                        to the Merkle root attested in lin_gate_manifest.rulel
#   make gate-attest  -> re-attest that root after a human reviewed the change
#                        (KEY=<seed> signs it with Ed25519; `lin gate-keygen`
#                         mints the key and the public roster it verifies against)
#   make ci-gate      -> the whole PR gate (gate + honesty + N-Version + integrity)

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
	@echo; echo "== attestation honesty gate =="
	@$(MAKE) --no-print-directory attestation-gate

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
	@echo; echo "== attestation honesty gate (cpu) =="
	@$(MAKE) --no-print-directory attestation-gate

# Unit tests for the guard table itself (no build required).
guard-unit:
	zig test compiler/lin_attestation_guard.zig

# Standalone run of the attestation honesty specification (includes the
# N-Version cross-check, which builds transpile/c itself).
attestation-gate: guard-unit
	@./test/attestation_honesty.sh $(BIN)

# N-Version: run the shared oracle corpus through the Zig LinVM and through the
# independent C11 port, and compare their canonical Merkle roots.
xver: build-cpu
	@$(MAKE) -C transpile/c xver
	@$(BIN) crosscheck-c

# LIN Gate: recompute the Merkle root of the tracked toolchain
# (compiler/**, transpile/c/lin_c|tool|test/**) and compare it with the root
# attested in lin_gate_manifest.rulel. A PR that changes any of those files
# without re-attesting fails here — that is what .github/workflows/lin_gate.yml
# runs on every pull request.
GATE_ROSTER := $(wildcard lin_gate_roster.rulel)

gate: build-cpu
ifeq ($(GATE_ROSTER),)
	@$(BIN) gate-check
else
	@$(BIN) gate-check --roster $(GATE_ROSTER)
endif

# Human action: accept a reviewed change to the toolchain by committing a new
# attested root together with the change. With KEY=<seed file> the attestation
# is signed with Ed25519; `lin gate-keygen` mints a key and its public roster.
gate-attest: build-cpu
ifeq ($(KEY),)
	@$(BIN) gate-attest
else
	@$(BIN) gate-attest --key $(KEY) --key-id $(or $(KEY_ID),gate-maintainer)
endif

# The full PR gate, in the order CI runs it.
ci-gate: gate attestation-gate xver
	@$(BIN) integrity

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
	@rm -rf zig-out zig-cache .zig-cache bin/lin_native /tmp/lin_rec.rulel simulated_attestations.log
