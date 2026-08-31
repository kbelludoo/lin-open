# C transpilation of the LIN Stage-0 C-expression pipeline.
# See README.md for the Zig -> C mapping and semantic decisions.

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -std=c11
CPPFLAGS = -Ilin_c

SRCS = lin_c/lin_common.c lin_c/lin_token.c lin_c/lin_ast.c \
       lin_c/lin_parse.c lin_c/lin_vm.c lin_c/lin_sha256.c
HDRS = lin_c/lin_common.h lin_c/lin_token.h lin_c/lin_ast.h \
       lin_c/lin_parse.h lin_c/lin_vm.h lin_c/lin_sha256.h
# V1 (R6): HOST-ABI-1 intrinsics + LINBC1 fail-closed loader.
BC1_SRCS = lin_c/lin_str.c lin_c/lin_linbc1.c
BC1_HDRS = lin_c/lin_str.h lin_c/lin_linbc1.h
TARGET = bin/test_c_expr
EDGE   = bin/test_overflow_edges
SHA    = bin/test_sha256
XVER   = bin/lin_c_receipt
BC1    = bin/lin_bc1_run
BC1T   = bin/test_linbc1

all: $(TARGET) $(EDGE) $(SHA) $(XVER) $(BC1) $(BC1T)

$(TARGET): test/test_c_expr.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_c_expr.c $(SRCS)

$(EDGE): test/test_overflow_edges.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_overflow_edges.c $(SRCS)

$(SHA): test/test_sha256.c lin_c/lin_sha256.c lin_c/lin_sha256.h
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_sha256.c lin_c/lin_sha256.c

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

.PHONY: all test test-edges test-sha256 xver test-linbc1 roundtrip-linbc1 clean
