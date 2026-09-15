# lint_c0 — stage-0 da irma lint. So `cc -std=c11 -Wall -Wextra`, sem Zig/Go.
# Nao toca em nenhum arquivo existente do repo (dir aditivo + target proprio).
CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra
BIN = bin/lint_c0

all: $(BIN)

$(BIN): lint_c0.c
	@mkdir -p bin
	$(CC) $(CFLAGS) -o $(BIN) lint_c0.c

clean:
	rm -rf bin

.PHONY: all clean
