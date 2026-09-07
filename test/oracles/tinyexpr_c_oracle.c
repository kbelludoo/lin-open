#include "../fixtures/external_proof/tinyexpr.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * Oraculo C oficial compilado com test/fixtures/external_proof/tinyexpr.c
 */

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Uso: %s \"<expressao>\"\n", argv[0]);
        return 1;
    }

    int err = 0;
    double r = te_interp(argv[1], &err);
    if (err != 0) {
        printf("ERROR %d\n", err);
        return 1;
    }

    printf("RESULT %.6f\n", r);
    return 0;
}
