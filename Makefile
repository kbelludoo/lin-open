# Union of both sides: master's attestation/gate targets and the cryptanalysis
# gate targets added on this branch.
.PHONY: all build build-gpu build-cpu test test-cpu lint clean c0 test-c0 c0-gate gate-nozig \
        crypto256-real crypto256-audit \
        attestation-gate guard-unit xver gate gate-attest ci-gate \
        linvm0-gate

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

# ---- seleção do Compilador 0 -------------------------------------------------
# Com Zig no ambiente o Compilador 0 é o Stage0 (compiler/lin.zig): verificador
# de tipos completo, MIR, GPU, receipts. Sem Zig, a cadeia não para — ela cai no
# Compilador 0 da LinVM: o host C11 (`lin_c0`) compila o subconjunto
# LINVM-1/i64 e reproduz, bit a bit, os goldens medidos no Stage0.
#   make c0        -> constrói o host (só precisa de cc)
#   make c0-gate   -> provas do caminho sem Zig (docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel)
#   make gate-nozig -> recomputa a raiz do LIN Gate em python3, sem binário Zig
ZIG_FOUND := $(shell command -v zig >/dev/null 2>&1 && echo 1 || echo 0)
ZIG_GUARD = @if [ "$(ZIG_FOUND)" != 1 ]; then \
  echo "zig não existe neste ambiente — este alvo constrói o Stage0 Zig."; \
  echo "Sem Zig, o Compilador 0 é a LinVM (host C11, só precisa de cc):"; \
  echo "  make c0 && make c0-gate"; \
  echo "Fronteira honesta: subconjunto LINVM-1/i64; nada de typecheck/MIR/GPU/receipts."; \
  echo "Especificação: docs/V2_LINVM_AS_COMPILER0_NOZIG.rulel"; \
  exit 127; \
fi

BUILD_GPU := zig build -Doptimize=ReleaseFast
BUILD_CPU := zig build -Dgpu=false -Doptimize=ReleaseFast
BIN := zig-out/bin/lin_native

all: test

build: build-gpu

build-gpu:
	$(ZIG_GUARD)
	$(BUILD_GPU)

build-cpu:
	$(ZIG_GUARD)
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
	$(ZIG_GUARD)
	zig test compiler/lin_attestation_guard.zig

# --------------------------------------------------------------------------
# COMPILADOR 0 = LinVM (host C11). Nenhum Zig em parte alguma.
#
#   make c0         -> constrói transpile/c/bin/lin_c0 (vm/info/image/roundtrip)
#   make test-c0    -> vetores dourados transcritos do Stage0
#   make c0-gate    -> goldens publicados reproduzidos sem Zig + gate do loader
#                      LINBC1 + round-trip fonte->imagem->host + consenso de fold
#   make gate-nozig -> recomputa a raiz do LIN Gate (python3) sem o binário Zig
#
# Uso diário, sem Zig:  ./transpile/c/bin/lin_c0 vm arquivo.lin [fn args...]
# substitui `lin vm`. `lin check`, `lin lint`, receipts e o pipeline GPU
# continuam exigindo o Stage0: o caminho sem Zig NÃO finge ser eles.
# --------------------------------------------------------------------------
.PHONY: c0 test-c0 c0-gate gate-nozig
c0:
	@$(MAKE) -C transpile/c c0

test-c0:
	@$(MAKE) -C transpile/c test-c0

c0-gate:
	@$(MAKE) -C transpile/c c0 test-c0 test-linbc1 test-edges test-sha256
	@./test/verify_c0.sh transpile/c/bin/lin_c0
	@$(MAKE) -C transpile/c roundtrip-linbc1-noc
	@echo "c0-gate: Compilador 0 (LinVM/C11) verde — nenhum Zig foi executado"

gate-nozig:
	@python3 test/verify_gate_manifest.py

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

# LINVM0 front-end gate (V2/B2): verifies the LIN lexer and expression evaluator
# that start the compiler0 self-host. This is EXPERIMENTAL (see
# docs/LINVM0_V2_FRONTIER.rulel); it does NOT yet build the full compiler or
# the C0=C1=C2 fixed point.
linvm0-gate: build-cpu
	@./verify_linvm0.sh $(BIN)

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
	@rm -rf zig-out zig-cache .zig-cache bin/lin_native /tmp/lin_rec.rulel \
	        $(BIN_BIND) simulated_attestations.log
