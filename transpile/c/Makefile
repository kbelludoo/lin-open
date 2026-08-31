# C transpilation of the LIN Stage-0 C-expression pipeline.
# See README.md for the Zig -> C mapping and semantic decisions.

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -std=c11
CPPFLAGS = -Ilin_c

SRCS = lin_c/lin_common.c lin_c/lin_token.c lin_c/lin_ast.c \
       lin_c/lin_parse.c lin_c/lin_vm.c
HDRS = lin_c/lin_common.h lin_c/lin_token.h lin_c/lin_ast.h \
       lin_c/lin_parse.h lin_c/lin_vm.h
TARGET = bin/test_c_expr
EDGE   = bin/test_overflow_edges

all: $(TARGET) $(EDGE)

$(TARGET): test/test_c_expr.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_c_expr.c $(SRCS)

$(EDGE): test/test_overflow_edges.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test/test_overflow_edges.c $(SRCS)

# `test` runs the verbatim port of the original suite (exit code = verdict).
test: $(TARGET)
	./$(TARGET)

# Edge probes: Zig wrapping semantics at the INT64 boundaries (UB in naive C).
test-edges: $(EDGE)
	./$(EDGE)

clean:
	rm -rf bin

.PHONY: all test clean
