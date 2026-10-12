// SPDX-License-Identifier: GPL-2.0-or-later
// EXCERPT ONLY — not the full Comet contract.
// Upstream: compound-finance/comet
//   path: contracts/CometWithExtendedAssetList.sol  (accrueInternal tracking + divBaseWei)
//   commit: f766f51583c23acc33b2a7824654ef2029a96804
//   git blob: 3490e984d133789aa1afe2e8f7e37a11d2512396
//   file sha256: c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961
// CometCore.sol scales blob 534f2701b6c8e683f9294112b0bcc23878d39fe6
//   sha256: 1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78
// BUSL-1.1 Change Date 2025-12-31 elapsed; Change License GPL-2.0-or-later.
//
// From CometCore.sol:
//     uint64 internal constant BASE_ACCRUAL_SCALE = 1e6;
//     uint64 internal constant BASE_INDEX_SCALE = 1e15;
//     uint64 internal constant FACTOR_SCALE = 1e18;
//
// From CometWithExtendedAssetList.sol constructor:
//     baseScale = uint64(10 ** decimals_);
//
// Exact tracking + helpers (must be substrings of the live file):

            if (totalSupplyBase >= baseMinForRewards) {
                trackingSupplyIndex += safe64(divBaseWei(baseTrackingSupplySpeed * timeElapsed, totalSupplyBase));
            }
            if (totalBorrowBase >= baseMinForRewards) {
                trackingBorrowIndex += safe64(divBaseWei(baseTrackingBorrowSpeed * timeElapsed, totalBorrowBase));
            }

    function mulFactor(uint n, uint factor) internal pure returns (uint) {
        return n * factor / FACTOR_SCALE;
    }

    function divBaseWei(uint n, uint baseWei) internal view returns (uint) {
        return n * baseScale / baseWei;
    }
