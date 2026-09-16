/* LIN-eligible scalar subset of Bitcoin Core GetBlockSubsidy (MIT).
 * C++ consensus params reference removed; interval and genesis are arguments.
 * Negative height and interval<=0 fail-closed. Not compiled into the LIN TCB.
 */
#include <stdint.h>
typedef int64_t CAmount;

CAmount btc_subsidy_scalar(int64_t nHeight, int64_t interval, int64_t genesis)
{
    int64_t halvings;
    CAmount nSubsidy;
    if (nHeight < 0)
        return 0;
    if (interval <= 0)
        return 0;
    if (genesis < 0)
        return 0;
    halvings = nHeight / interval;
    if (halvings >= 64)
        return 0;
    nSubsidy = genesis;
    nSubsidy >>= halvings;
    return nSubsidy;
}
