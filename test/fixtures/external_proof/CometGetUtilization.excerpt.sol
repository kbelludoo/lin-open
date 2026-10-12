// SPDX-License-Identifier: GPL-2.0-or-later
// EXCERPT ONLY — not the full Comet contract.
// Upstream: compound-finance/comet
//   path: contracts/CometWithExtendedAssetList.sol  (getUtilization)
//   commit: f766f51583c23acc33b2a7824654ef2029a96804
//   git blob: 3490e984d133789aa1afe2e8f7e37a11d2512396
//   file sha256: c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961
// CometCore.sol FACTOR_SCALE blob 534f2701b6c8e683f9294112b0bcc23878d39fe6
//   sha256: 1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78
// BUSL-1.1 Change Date 2025-12-31 elapsed; Change License GPL-2.0-or-later.
//
// From CometCore.sol:
//     uint64 internal constant FACTOR_SCALE = 1e18;
//
// Exact getUtilization body (must be a substring of the live file):

    function getUtilization() override public view returns (uint) {
        uint totalSupply_ = presentValueSupply(baseSupplyIndex, totalSupplyBase);
        uint totalBorrow_ = presentValueBorrow(baseBorrowIndex, totalBorrowBase);
        if (totalSupply_ == 0) {
            return 0;
        } else {
            return totalBorrow_ * FACTOR_SCALE / totalSupply_;
        }
    }
