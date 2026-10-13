// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/data/Keys.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later

pragma solidity ^0.8.0;

library KeysExcerpt {
    bytes32 public constant MAX_PNL_FACTOR = keccak256(abi.encode("MAX_PNL_FACTOR"));
    bytes32 public constant MAX_PNL_FACTOR_FOR_TRADERS = keccak256(abi.encode("MAX_PNL_FACTOR_FOR_TRADERS"));
    bytes32 public constant MAX_PNL_FACTOR_FOR_ADL = keccak256(abi.encode("MAX_PNL_FACTOR_FOR_ADL"));
}
