# C transpilation of the LIN Stage-0 C-expression pipeline.
# See README.md for the Zig -> C mapping and semantic decisions.

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -std=c11
CPPFLAGS = -Ilin_c

SRCS = lin_c/lin_common.c lin_c/lin_token.c lin_c/lin_ast.c \
       lin_c/lin_parse.c lin_c/lin_vm.c lin_c/lin_sha256.c \
       lin_c/lin_region.c lin_c/lin_abi.c
HDRS = lin_c/lin_common.h lin_c/lin_token.h lin_c/lin_ast.h \
       lin_c/lin_parse.h lin_c/lin_vm.h lin_c/lin_sha256.h \
       lin_c/lin_region.h lin_c/lin_abi.h
# V1 (R6): HOST-ABI-1 intrinsics + LINBC1 fail-closed loader.
BC1_SRCS = lin_c/lin_str.c lin_c/lin_linbc1.c
BC1_HDRS = lin_c/lin_str.h lin_c/lin_linbc1.h
TARGET = bin/test_c_expr
EDGE   = bin/test_overflow_edges
SHA    = bin/test_sha256
REGION = bin/test_region
ABI    = bin/test_abi
CTX    = bin/test_context
C0FEATURE = bin/test_c0_features
XVER   = bin/lin_c_receipt
BC1    = bin/lin_bc1_run
BC1T   = bin/test_linbc1
# Compiler 0 host: compiles and runs .lin source WITHOUT Zig (V2/V5 path).
C0     = bin/lin_c0
JIT_BIN = bin/test_c0_jit

all: $(TARGET) $(EDGE) $(SHA) $(REGION) $(ABI) $(CTX) $(C0FEATURE) $(XVER) $(BC1) $(BC1T) $(C0) $(JIT_BIN)

$(TARGET): test/test_c_expr.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_c_expr.c $(SRCS)

$(EDGE): test/test_overflow_edges.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_overflow_edges.c $(SRCS)

$(SHA): test/test_sha256.c lin_c/lin_sha256.c lin_c/lin_sha256.h
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_sha256.c lin_c/lin_sha256.c

$(REGION): test/test_region.c lin_c/lin_region.c lin_c/lin_region.h
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_region.c lin_c/lin_region.c

test-region: $(REGION)
	./$(REGION)

$(ABI): test/test_abi.c lin_c/lin_abi.c lin_c/lin_abi.h \
		lin_c/lin_region.c lin_c/lin_region.h lin_c/lin_common.c lin_c/lin_common.h
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_abi.c \
		lin_c/lin_abi.c lin_c/lin_region.c lin_c/lin_common.c

test-abi: $(ABI)
	./$(ABI)

$(CTX): test/test_context.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_context.c $(SRCS) -pthread

test-context: $(CTX)
	./$(CTX)

$(C0FEATURE): test/test_c0_features.c tool/lin_c0_front.c lin_c0_front.h \
		$(SRCS) $(BC1_SRCS) $(BC1_HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(C0FLAGS) -o $@ test/test_c0_features.c \
		tool/lin_c0_front.c $(SRCS) $(BC1_SRCS)

test-c0-features: $(C0FEATURE)
	./$(C0FEATURE)

# Independent C implementation of the cross-version execution receipt. This is
# the second implementation behind `lin crosscheck-c` (compiler/lin.zig).
$(XVER): tool/lin_c_receipt.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ tool/lin_c_receipt.c $(SRCS)

# `test` runs the verbatim port of the original suite (exit code = verdict).
test: $(TARGET)
	./$(TARGET)

# Edge probes: Zig wrapping semantics at the INT64 boundaries (UB in naive C).
test-edges: $(EDGE)
	./$(EDGE)

# SHA-256 against the FIPS 180-4 published digests.
test-sha256: $(SHA)
	./$(SHA)

# Build the cross-version receipt emitter used by `lin crosscheck-c`.
xver: $(XVER)

# ---- V1: LINBC1 host (emenda R6) ------------------------------------------
$(BC1): tool/lin_bc1_run.c $(SRCS) $(HDRS) $(BC1_SRCS) $(BC1_HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ tool/lin_bc1_run.c $(SRCS) $(BC1_SRCS)

$(BC1T): test/test_linbc1.c $(SRCS) $(HDRS) $(BC1_SRCS) $(BC1_HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_linbc1.c $(SRCS) $(BC1_SRCS)

# ---- Compiler 0 host (V2/V5: .lin source without Zig) ---------------------
# Front-end ported from compiler/lin.zig (parse_fn_type_infos:5287,
# vmTokenize:5678, VmComp:5733, vmBuild:6296); interpreter is the audited
# vm_exec (lin_c/lin_vm.c). Goldens: P1_LINVM_SELFHOST.rulel §3 and
# docs/LINVM0_V2_FRONTIER.rulel (value AND steps are bit-exact oracles).
C0_SRCS = tool/lin_c0.c tool/lin_c0_front.c tool/lin_c0_check.c tool/lin_c0_gpu.c tool/lin_c0_jit.c $(SRCS) $(BC1_SRCS)
C0_HDRS = lin_c0_front.h tool/lin_c0_gpu.h tool/lin_opencl_dyn.h tool/lin_c0_jit.h tool/lin_tcc_dyn.h $(HDRS) $(BC1_HDRS)
C0FLAGS = -I. -Ilin_c

$(C0): $(C0_SRCS) $(C0_HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(C0FLAGS) -o $@ $(C0_SRCS) -ldl

c0: $(C0)

# The three no-Zig gates, in one command (nothing below touches `zig`).
test-c0: $(C0)
	@../../test/verify_c0.sh $(C0)

test-c0-jit: $(C0)
	@../../test/verify_c0_jit.sh $(C0)

$(JIT_BIN): test/test_c0_jit.c tool/lin_c0_jit.c tool/lin_c0_jit.h tool/lin_tcc_dyn.h tool/lin_c0_front.c $(SRCS) $(BC1_SRCS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(C0FLAGS) -o $@ test/test_c0_jit.c tool/lin_c0_jit.c tool/lin_c0_front.c $(SRCS) $(BC1_SRCS) -ldl

test-jit: $(JIT_BIN)
	./$(JIT_BIN)

.PHONY: c0 test-c0 test-c0-jit test-jit test-region test-abi test-context test-c0-features

# G(V1): golden vectors + corrupted-image fuzz (100% fail-closed).
test-linbc1: $(BC1T)
	./$(BC1T)

# Cross-host round-trip: the LIN emitter (src/lin_linbc_emit.lin), executed by
# the Zig LinVM, recomputes the self-hash fold of the fixture image from its
# own transcribed tables; the C11 loader derives the same fold from the raw
# bytes. Equal values = emitter and loader agree on the format (LINBC1) and on
# the hash domain (linbc1:img:) across two independent hosts.
# Requires zig-out/bin/lin_native at the repo root (zig build -Dgpu=false).
LIN_NATIVE ?= ../../zig-out/bin/lin_native
roundtrip-linbc1: $(BC1T)
	@printf 'LIN fold:  '; L=$$($(LIN_NATIVE) vm ../../src/lin_linbc_emit.lin lb_selfhash_fold | sed -n 's/.*value=\(-\?[0-9]*\).*/\1/p'); echo "$$L"; \
	printf 'C11 fold:  '; C=$$(./$(BC1T) --print-fold); echo "$$C"; \
	if [ "$$L" = "$$C" ]; then echo "ROUNDTRIP-LINBC1: CONSENSUS — emitter(LIN) == loader(C11)"; \
	else echo "ROUNDTRIP-LINBC1: DIVERGENCE DETECTED"; exit 1; fi

clean:
	rm -rf bin

.PHONY: all test test-edges test-sha256 test-region test-abi test-context test-c0-features test-linbc1 roundtrip-linbc1 clean
