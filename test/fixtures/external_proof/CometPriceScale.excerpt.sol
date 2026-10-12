// SPDX-License-Identifier: GPL-2.0-or-later
// EXCERPT ONLY — not the full Comet contract.
// Upstream: compound-finance/comet
//   path: contracts/CometWithExtendedAssetList.sol  (mulPrice / divPrice / absorb)
//   commit: f766f51583c23acc33b2a7824654ef2029a96804
//   git blob: 3490e984d133789aa1afe2e8f7e37a11d2512396
//   file sha256: c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961
// CometCore.sol scales blob 534f2701b6c8e683f9294112b0bcc23878d39fe6
//   sha256: 1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78
// BUSL-1.1 Change Date 2025-12-31 elapsed; Change License GPL-2.0-or-later.
//
// From CometCore.sol:
//     uint8 internal constant PRICE_FEED_DECIMALS = 8;
//     uint64 internal constant PRICE_SCALE = uint64(10 ** PRICE_FEED_DECIMALS);
//     uint64 internal constant BASE_INDEX_SCALE = 1e15;
//     uint64 internal constant FACTOR_SCALE = 1e18;
//
// Exact helpers + borrow/absorb uses (must be substrings of the live file):

    function mulFactor(uint n, uint factor) internal pure returns (uint) {
        return n * factor / FACTOR_SCALE;
    }

    function mulPrice(uint n, uint price, uint64 fromScale) internal pure returns (uint) {
        return n * price / fromScale;
    }

    function signedMulPrice(int n, uint price, uint64 fromScale) internal pure returns (int) {
        return n * signed256(price) / int256(uint256(fromScale));
    }

    function divPrice(uint n, uint price, uint64 toScale) internal pure returns (uint) {
        return n * toScale / price;
    }

                uint newAmount = mulPrice(
                    userCollateral[account][asset.asset].balance,
                    getPrice(asset.priceFeed),
                    asset.scale
                );
                liquidity += signed256(mulFactor(
                    newAmount,
                    asset.borrowCollateralFactor
                ));

                uint256 value = mulPrice(seizeAmount, getPrice(assetInfo.priceFeed), assetInfo.scale);
                deltaValue += mulFactor(value, assetInfo.liquidationFactor);

        uint256 deltaBalance = divPrice(deltaValue, basePrice, uint64(baseScale));
