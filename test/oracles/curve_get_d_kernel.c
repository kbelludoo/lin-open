/*
 * Transpilable C11 kernel of Curve 3-coin get_D for SMALL balances.
 * Constraints for lin_from_c: no pointers, no structs, no __int128, no floats.
 * Naive uint64 * / — overflows silently on 1e12-scale D*D; the improved LIN
 * clone uses 128-bit muldiv (src/lin_curve_stableswap.lin).
 *
 * This file exists so the C→LIN transpiler (if-else, /=) has a monetary
 * kernel to emit. It is not the production oracle (see curve_stableswap_c11.c).
 */
#include <stdint.h>

uint64_t curve_get_d_small(uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp) {
    uint64_t S;
    uint64_t D;
    uint64_t Ann;
    uint64_t i;
    S = x0 + x1 + x2;
    if (S == 0) {
        return 0;
    } else {
        D = S;
        Ann = amp * 3;
        for (i = 0; i < 255; i = i + 1) {
            uint64_t D_P;
            uint64_t Dprev;
            D_P = D;
            D_P = D_P * D / (x0 * 3);
            D_P = D_P * D / (x1 * 3);
            D_P = D_P * D / (x2 * 3);
            Dprev = D;
            D = (Ann * S + D_P * 3) * D / ((Ann - 1) * D + 4 * D_P);
            if (D > Dprev) {
                if (D - Dprev <= 1) {
                    i = 255;
                }
            } else {
                if (Dprev - D <= 1) {
                    i = 255;
                }
            }
        }
        return D;
    }
}
