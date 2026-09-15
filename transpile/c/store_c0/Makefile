# Native STORE (store_c0) - C11 Storage Engine with Real SHA-256 Merkle Tree
# Implements formal contract in STORE_SPEC.rulel

CC       ?= cc
CFLAGS   ?= -O2 -Wall -Wextra -std=c11 -pedantic
CPPFLAGS ?= -I../lin_c -I.

SRCS     = store_c0.c ../lin_c/lin_sha256.c
HDRS     = store_c0.h ../lin_c/lin_sha256.h
TARGET   = bin/test_store_c0

.PHONY: all test clean

all: $(TARGET)

$(TARGET): test_store_c0.c $(SRCS) $(HDRS)
	@mkdir -p bin
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ test_store_c0.c $(SRCS)

test: $(TARGET)
	@echo "==> Executing store_c0 Invariant Test Suite..."
	./$(TARGET)
	@echo "==> Verifying Python Oracle Cross-Check & Self-Test..."
	python3 oracle_store.py --self-test
	@echo "==> Executing Python Oracle Exhaustive Crash Matrix..."
	python3 oracle_store.py --crash-matrix

clean:
	rm -rf bin test_data_*
