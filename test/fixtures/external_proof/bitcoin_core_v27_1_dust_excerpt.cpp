// MIT excerpt of bitcoin/bitcoin v27.1 (commit 1088a98f5aad080cc6cca2da174f206509fcda6c)
// Files: src/policy/policy.cpp GetDustThreshold+IsDust
//        src/policy/policy.h DUST_RELAY_TX_FEE
// Full-file pins live in the external proof harness. Not a Core fork.

CAmount GetDustThreshold(const CTxOut& txout, const CFeeRate& dustRelayFeeIn)
{
    // "Dust" is defined in terms of dustRelayFee,
    // which has units satoshis-per-kilobyte.
    // If you'd pay more in fees than the value of the output
    // to spend something, then we consider it dust.
    // A typical spendable non-segwit txout is 34 bytes big, and will
    // need a CTxIn of at least 148 bytes to spend:
    // so dust is a spendable txout less than
    // 182*dustRelayFee/1000 (in satoshis).
    // 546 satoshis at the default rate of 3000 sat/kvB.
    // A typical spendable segwit P2WPKH txout is 31 bytes big, and will
    // need a CTxIn of at least 67 bytes to spend:
    // so dust is a spendable txout less than
    // 98*dustRelayFee/1000 (in satoshis).
    // 294 satoshis at the default rate of 3000 sat/kvB.
    if (txout.scriptPubKey.IsUnspendable())
        return 0;

    size_t nSize = GetSerializeSize(txout);
    int witnessversion = 0;
    std::vector<unsigned char> witnessprogram;

    // Note this computation is for spending a Segwit v0 P2WPKH output (a 33 bytes
    // public key + an ECDSA signature). For Segwit v1 Taproot outputs the minimum
    // satisfaction is lower (a single BIP340 signature) but this computation was
    // kept to not further reduce the dust level.
    // See discussion in https://github.com/bitcoin/bitcoin/pull/22779 for details.
    if (txout.scriptPubKey.IsWitnessProgram(witnessversion, witnessprogram)) {
        // sum the sizes of the parts of a transaction input
        // with 75% segwit discount applied to the script size.
        nSize += (32 + 4 + 1 + (107 / WITNESS_SCALE_FACTOR) + 4);
    } else {
        nSize += (32 + 4 + 1 + 107 + 4); // the 148 mentioned above
    }

    return dustRelayFeeIn.GetFee(nSize);
}

bool IsDust(const CTxOut& txout, const CFeeRate& dustRelayFeeIn)
{
    return (txout.nValue < GetDustThreshold(txout, dustRelayFeeIn));
}

// --- from policy.h ---
/* Min feerate for defining dust.
 * Changing the dust limit changes which transactions are
 * standard and should be done with care and ideally rarely. It makes sense to
 * only increase the dust limit after prior releases were already not creating
 * outputs below the new threshold */
static constexpr unsigned int DUST_RELAY_TX_FEE{3000};
/** Default for -minrelaytxfee, minimum relay fee for transactions */
*/
static constexpr unsigned int DUST_RELAY_TX_FEE{3000};
static constexpr unsigned int DEFAULT_MIN_RELAY_TX_FEE{1000};
