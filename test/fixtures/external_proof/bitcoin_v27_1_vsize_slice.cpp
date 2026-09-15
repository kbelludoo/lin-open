/* SLICE of bitcoin/bitcoin v27.1 src/policy/policy.cpp
 * commit 1088a98f5aad080cc6cca2da174f206509fcda6c
 * full-file sha256 cd442c9e4e40a4811fe6256109020b7567bb777dce5ac8398cf8664de2ccb2d5
 * git blob d08ec4fb7f75c33ff68c1790d39e1671456baa44
 * MIT. Not the full translation unit — GetVirtualTransactionSize(weight) only.
 */
int64_t GetVirtualTransactionSize(int64_t nWeight, int64_t nSigOpCost, unsigned int bytes_per_sigop)
{
    return (std::max(nWeight, nSigOpCost * bytes_per_sigop) + WITNESS_SCALE_FACTOR - 1) / WITNESS_SCALE_FACTOR;
}

