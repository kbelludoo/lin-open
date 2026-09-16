// SPDX-License-Identifier: BSD-3-Clause
// Excerpt of compound-finance/compound-protocol contracts/CToken.sol
// commit a3214f67b73310d547e00fc578e8355911c9d376
// Copyright 2020 Compound Labs, Inc.
// The function body below is an exact substring of the pinned CToken.sol.
// Full-file pin: sha256 b64790f41ef851b09856af286ce8253b95ef34fda4ae836f924a519e8f792785
// git blob b8c878c79c75855808f6e7303099a367c8bad98b
//
    function exchangeRateStoredInternal() virtual internal view returns (uint) {
        uint _totalSupply = totalSupply;
        if (_totalSupply == 0) {
            /*
             * If there are no tokens minted:
             *  exchangeRate = initialExchangeRate
             */
            return initialExchangeRateMantissa;
        } else {
            /*
             * Otherwise:
             *  exchangeRate = (totalCash + totalBorrows - totalReserves) / totalSupply
             */
            uint totalCash = getCashPrior();
            uint cashPlusBorrowsMinusReserves = totalCash + totalBorrows - totalReserves;
            uint exchangeRate = cashPlusBorrowsMinusReserves * expScale / _totalSupply;

            return exchangeRate;
        }
    }
