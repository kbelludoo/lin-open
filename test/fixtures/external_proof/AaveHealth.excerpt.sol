// SPDX-License-Identifier: MIT
// Excerpt of aave/aave-v3-core v1.19.4 (commit b74526a7bc67a3a117a1963fc871b3eb8cea8435).
// Upstream SPDX on these files still reads BUSL-1.1; LICENSE.md Change Date
// 27 January 2023 elapsed, Change License MIT. Full files are pinned beside
// this excerpt as PercentageMath.sol / WadRayMath.sol / GenericLogic.sol.
// Bytes below are copied verbatim from those three files.

// --- PercentageMath.sol ---
  uint256 internal constant PERCENTAGE_FACTOR = 1e4;
  uint256 internal constant HALF_PERCENTAGE_FACTOR = 0.5e4;
      result := div(add(mul(value, percentage), HALF_PERCENTAGE_FACTOR), PERCENTAGE_FACTOR)

// --- WadRayMath.sol ---
  uint256 internal constant WAD = 1e18;
  uint256 internal constant RAY = 1e27;
      c := div(add(mul(a, WAD), div(b, 2)), b)

// --- GenericLogic.sol calculateUserAccountData (health) ---
    vars.healthFactor = (vars.totalDebtInBaseCurrency == 0)
      ? type(uint256).max
      : (vars.totalCollateralInBaseCurrency.percentMul(vars.avgLiquidationThreshold)).wadDiv(
        vars.totalDebtInBaseCurrency
      );

// --- GenericLogic.sol calculateAvailableBorrows ---
    uint256 availableBorrowsInBaseCurrency = totalCollateralInBaseCurrency.percentMul(ltv);
