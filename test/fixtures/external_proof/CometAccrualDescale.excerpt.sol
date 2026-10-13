// SPDX-License-Identifier: BUSL-1.1
// Excerpt of compound-finance/comet@f766f51583c23acc33b2a7824654ef2029a96804
// contracts/CometWithExtendedAssetList.sol — constructor factor + updateBasePrincipal.
// Full-file pin (sha256/blob) is checked live by test/prove_comet_descale_external.py.
// Change License after 2025-12-31: GPL-2.0-or-later. Not a production contract.
pragma solidity 0.8.15;

/// @dev The scale for base tracking accrual (CometCore.sol)
uint64 internal constant BASE_ACCRUAL_SCALE = 1e6;

/// @notice Factor to divide by when accruing rewards in order to preserve 6 decimals (i.e. baseScale / 1e6)
uint internal immutable accrualDescaleFactor;

// constructor (relevant lines):
//   baseScale = uint64(10 ** decimals_);
//   if (baseScale < BASE_ACCRUAL_SCALE) revert BadDecimals();
//   accrualDescaleFactor = baseScale / BASE_ACCRUAL_SCALE;

function updateBasePrincipal(address account, UserBasic memory basic, int104 principalNew) internal {
    int104 principal = basic.principal;
    basic.principal = principalNew;

    if (principal >= 0) {
        uint indexDelta = uint256(trackingSupplyIndex - basic.baseTrackingIndex);
        basic.baseTrackingAccrued += safe64(uint104(principal) * indexDelta / trackingIndexScale / accrualDescaleFactor);
    } else {
        uint indexDelta = uint256(trackingBorrowIndex - basic.baseTrackingIndex);
        basic.baseTrackingAccrued += safe64(uint104(-principal) * indexDelta / trackingIndexScale / accrualDescaleFactor);
    }

    if (principalNew >= 0) {
        basic.baseTrackingIndex = trackingSupplyIndex;
    } else {
        basic.baseTrackingIndex = trackingBorrowIndex;
    }

    userBasic[account] = basic;
}
