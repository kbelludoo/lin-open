# linp_c0 — stage-0 da irma linp. So `cc -std=c11 -Wall -Wextra`, sem Zig/Go.
# Linka o SHA-256 REAL do LIN (../lin_c/lin_sha256.c) — seguranca reusada, nao copiada.
# Nao toca em nenhum arquivo existente do repo (dir aditivo + target proprio).
CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -I../lin_c
BIN = bin/linp_c0
LIN_SHA = ../lin_c/lin_sha256.c

all: $(BIN)

$(BIN): linp_c0.c $(LIN_SHA)
	@mkdir -p bin
	$(CC) $(CFLAGS) -o $(BIN) linp_c0.c $(LIN_SHA)

clean:
	rm -rf bin

.PHONY: all clean
