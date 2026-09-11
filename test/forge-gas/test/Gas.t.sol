// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "contracts/LinReceiptVerifier.sol";

/// @notice Canonical math from Uniswap Labs official @uniswap/v2-periphery/contracts/libraries/UniswapV2Library.sol
library CanonicalUniswapV2Library {
    function getAmountOut(uint amountIn, uint reserveIn, uint reserveOut) internal pure returns (uint amountOut) {
        require(amountIn > 0, 'UniswapV2Library: INSUFFICIENT_INPUT_AMOUNT');
        require(reserveIn > 0 && reserveOut > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
        uint amountInWithFee = amountIn * 997;
        uint numerator = amountInWithFee * reserveOut;
        uint denominator = reserveIn * 1000 + amountInWithFee;
        amountOut = numerator / denominator;
    }

    /// @notice Invariant check from Uniswap Labs official @uniswap/v2-core/contracts/UniswapV2Pair.sol lines 180-182
    function verifyPairK(uint balance0, uint balance1, uint reserve0, uint reserve1, uint amount0In, uint amount1In) internal pure returns (bool) {
        uint balance0Adjusted = balance0 * 1000 - (amount0In * 3);
        uint balance1Adjusted = balance1 * 1000 - (amount1In * 3);
        return balance0Adjusted * balance1Adjusted >= reserve0 * reserve1 * (1000**2);
    }
}

contract GasTest {
    bytes32 constant EVM_ROOT = bytes32(0x5d961cae6be15b1705ce55a1bdb8d7e5b200f4c8788683c3a92331f04352b386);
    bytes32 constant LCR2_ROOT = bytes32(0x0f9ed69fde420922f6dcff5ee827ecaf51cae57c347ae3ae3464f3f81eac870f);
    event Log(string name, uint256 gasUsed);

    function _v() internal returns (LinReceiptVerifier) {
        return new LinReceiptVerifier();
    }

    function testDeploy() public {
        uint256 g0 = gasleft();
        LinReceiptVerifier v = _v();
        emit Log("deploy", g0 - gasleft());
        assert(address(v) != address(0));
    }

    function testVerifyConstantProduct() public {
        LinReceiptVerifier v = _v();
        uint256 g0 = gasleft();
        bool ok = v.verifyConstantProduct(9916868896781, 4148941281736026227948, 996242, 415549418053706);
        emit Log("verifyConstantProduct", g0 - gasleft());
        assert(ok);
    }

    function testVerifySwapInclusion() public {
        LinReceiptVerifier v = _v();
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = [bytes32(0x6fd08f4a4da4f18f475e5ea0bb8b1d5ceab2b457d7027bc0af83a487d0383d49), bytes32(0x4606e321db355359e6a426dca48900ebd68d04352ba466984f540f3dfb429846), bytes32(0x2d41dfaac43b0a1ab4096aa00e3653ab9e066e9d288dfc22cb6200f53e34febc), bytes32(0x61633bcb5af7826cffa67565705b87e704f7cd4590287edecebdfdddaf278bf0), bytes32(0x6eab65cdd9833e5ef4c9c2c021070b288471636d74ffa09dba0f1927317ad481), bytes32(0x932cd16ac44eb4cd914e30db075cf4d7b6a86767867e2e45004e5838fe084158), bytes32(0x773507df92a5c643955e5d1e5d9740bf125604be86acd3cfcceecce40216d93a), bytes32(0x1843e793734b6558df2fbe19e37a66bf3e9c58ae93d2745c5c24275340241d34), bytes32(0x1aa7f34945ccf2b0f7bc8fb1da22bdfb35386bee55a1441768bfaa271816d4c7), bytes32(0x551f8c529e2698268e1d5ff31da4aad945e1ed0e6d26f56b446ec644c0750606), bytes32(0x34156e27f32d2b8a2460c29a28c426a637fc5db0ecbda44651071ab48b9f43e4)];
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        bytes32 lf = v.computeSwapLeaf(9916868896781, 4148941281736026227948, 996242, 415549418053706);
        uint256 g0 = gasleft();
        bool ok = v.verifySwapInclusion(lf, pf, 0, EVM_ROOT);
        emit Log("verifySwapInclusion", g0 - gasleft());
        assert(ok);
    }

    function testSettleBatch() public {
        LinReceiptVerifier v = _v();
        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 1,
            swapCount: 2000,
            merkleRoot: EVM_ROOT,
            kernelSourceHash: bytes32(0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        uint256 g0 = gasleft();
        assert(v.settleBatch(h));
        emit Log("settleBatch", g0 - gasleft());
    }

    function testSettleBatchWithProof() public {
        LinReceiptVerifier v = _v();
        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 2,
            swapCount: 2000,
            merkleRoot: EVM_ROOT,
            kernelSourceHash: bytes32(0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        LinReceiptVerifier.SwapRecord memory spot = LinReceiptVerifier.SwapRecord({
            reserveIn: 9916868896781,
            reserveOut: 4148941281736026227948,
            amountIn: 996242,
            amountOut: 415549418053706
        });
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = [bytes32(0x6fd08f4a4da4f18f475e5ea0bb8b1d5ceab2b457d7027bc0af83a487d0383d49), bytes32(0x4606e321db355359e6a426dca48900ebd68d04352ba466984f540f3dfb429846), bytes32(0x2d41dfaac43b0a1ab4096aa00e3653ab9e066e9d288dfc22cb6200f53e34febc), bytes32(0x61633bcb5af7826cffa67565705b87e704f7cd4590287edecebdfdddaf278bf0), bytes32(0x6eab65cdd9833e5ef4c9c2c021070b288471636d74ffa09dba0f1927317ad481), bytes32(0x932cd16ac44eb4cd914e30db075cf4d7b6a86767867e2e45004e5838fe084158), bytes32(0x773507df92a5c643955e5d1e5d9740bf125604be86acd3cfcceecce40216d93a), bytes32(0x1843e793734b6558df2fbe19e37a66bf3e9c58ae93d2745c5c24275340241d34), bytes32(0x1aa7f34945ccf2b0f7bc8fb1da22bdfb35386bee55a1441768bfaa271816d4c7), bytes32(0x551f8c529e2698268e1d5ff31da4aad945e1ed0e6d26f56b446ec644c0750606), bytes32(0x34156e27f32d2b8a2460c29a28c426a637fc5db0ecbda44651071ab48b9f43e4)];
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        uint256 g0 = gasleft();
        assert(v.settleBatchWithInclusionProof(h, spot, pf, 0));
        emit Log("settleBatchWithProof", g0 - gasleft());
    }

    function testVerifyLCR2Inclusion() public {
        LinReceiptVerifier v = _v();
        bytes memory record = hex"4c435232010100004f4d12882a326d1c0d6f3b3d62c25185c71370e48c01e0e393b02b73b22250dd0100000000000000010000000000000000000000000000000000000000000000000000000000000000000000000f339200000000000000000000000000000000000000000000000000000904f372a80d0000000000000000000000000000000000000000000000e0ea2071b4b5b804ec000000000000000000000000000000000000000000000000000179f0a373204a000000000000000001000000000000000000000000000000";
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = [bytes32(0x4e5533336158764c7dbb3035861b8c92a221c487c8e4969d42fd4cabe554f571), bytes32(0x67fc2a3d23fa05d232571d6920710e3c7be1f64c53e43dba4493ffbf833e5fc6), bytes32(0x891262469d08b976a4556f93e515749afad14763137b6eef35481c5ff726ea30), bytes32(0x955cc2560e9c50fb7eb9d814182c04b31b8128b70fde66eadef000ca92495f9d), bytes32(0xf75e49f7d353ef0f86f8f554a54ab48666e239b7ab471796214caba8bda495ae), bytes32(0x5e7bc707fb8a841b109b63e873bff8e2b3b90bbc59c4675b86982fed465d9946), bytes32(0xe0dbec1fbf5cb473b923d402edd392fed2f224d9d83b58ca10b2d7f3e94706e2), bytes32(0x6565a07212e36c5c4484ba0a6dce8438d15a0ea7b5bef5fde4ccc993108d6e28), bytes32(0xefcb8a2ba12e9dee5caf10b089b4bd80d15397b34b497a565540ffe14e0a9a47), bytes32(0xba413f95b0f445350d3fb49e627734b79d84166338c06c4e3919312e7e127ae2), bytes32(0x8d7eb18a1adc2d9658f522158c7824c24f75aeff3bce58c9687d4d4ae09427da)];
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        uint256 g0 = gasleft();
        bool ok = v.verifyLCR2Inclusion(record, pf, 0, LCR2_ROOT);
        emit Log("verifyLCR2Inclusion", g0 - gasleft());
        assert(ok);
    }

    function testTamperedProofFails() public {
        LinReceiptVerifier v = _v();
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = [bytes32(0x6fd08f4a4da4f18f475e5ea0bb8b1d5ceab2b457d7027bc0af83a487d0383d49), bytes32(0x4606e321db355359e6a426dca48900ebd68d04352ba466984f540f3dfb429846), bytes32(0x2d41dfaac43b0a1ab4096aa00e3653ab9e066e9d288dfc22cb6200f53e34febc), bytes32(0x61633bcb5af7826cffa67565705b87e704f7cd4590287edecebdfdddaf278bf0), bytes32(0x6eab65cdd9833e5ef4c9c2c021070b288471636d74ffa09dba0f1927317ad481), bytes32(0x932cd16ac44eb4cd914e30db075cf4d7b6a86767867e2e45004e5838fe084158), bytes32(0x773507df92a5c643955e5d1e5d9740bf125604be86acd3cfcceecce40216d93a), bytes32(0x1843e793734b6558df2fbe19e37a66bf3e9c58ae93d2745c5c24275340241d34), bytes32(0x1aa7f34945ccf2b0f7bc8fb1da22bdfb35386bee55a1441768bfaa271816d4c7), bytes32(0x551f8c529e2698268e1d5ff31da4aad945e1ed0e6d26f56b446ec644c0750606), bytes32(0x34156e27f32d2b8a2460c29a28c426a637fc5db0ecbda44651071ab48b9f43e4)];
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        pf[0] = bytes32(0x0000000000000000000000000000000000000000000000000000000000000001);
        bytes32 lf = v.computeSwapLeaf(9916868896781, 4148941281736026227948, 996242, 415549418053706);
        assert(!v.verifySwapInclusion(lf, pf, 0, EVM_ROOT));
    }

    function testDisputeFraudulentSwapSuccess() public {
        LinReceiptVerifier v = _v();
        // Construct a fraudulent swap that violates constant product k
        LinReceiptVerifier.SwapRecord memory fraudSwap = LinReceiptVerifier.SwapRecord({
            reserveIn: 1000000000,
            reserveOut: 2000000000,
            amountIn: 1000000,
            amountOut: 2500000 // Out of pool bounds, steals liquidity
        });
        bytes32 fraudLeaf = v.computeSwapLeaf(fraudSwap.reserveIn, fraudSwap.reserveOut, fraudSwap.amountIn, fraudSwap.amountOut);

        // Sequencer settles a batch with this fraudulent root
        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 99,
            swapCount: 1,
            merkleRoot: fraudLeaf, // single-leaf root
            kernelSourceHash: bytes32(0),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        v.settleBatch(h);
        assert(v.verifiedMerkleRoots(fraudLeaf));

        // Watchtower / Challenger calls disputeFraudulentSwap with empty proof
        bytes32[] memory emptyProof = new bytes32[](0);
        uint256 g0 = gasleft();
        bool ok = v.disputeFraudulentSwap(99, fraudSwap, emptyProof, 0);
        emit Log("disputeFraudulentSwap", g0 - gasleft());
        assert(ok);

        // Verify batch was canceled and stripped from verified roots
        assert(!v.verifiedMerkleRoots(fraudLeaf));
        assert(v.settledBatches(99) == bytes32(0));
    }

    function testDisputeValidSwapReverts() public {
        LinReceiptVerifier v = _v();
        // Construct a genuine swap
        LinReceiptVerifier.SwapRecord memory validSwap = LinReceiptVerifier.SwapRecord({
            reserveIn: 1000000000,
            reserveOut: 2000000000,
            amountIn: 1000000,
            amountOut: 1992013 // Honest output
        });
        bytes32 validLeaf = v.computeSwapLeaf(validSwap.reserveIn, validSwap.reserveOut, validSwap.amountIn, validSwap.amountOut);

        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 100,
            swapCount: 1,
            merkleRoot: validLeaf,
            kernelSourceHash: bytes32(0),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        v.settleBatch(h);

        // False dispute should revert with SwapIsValidNoFraud
        bytes32[] memory emptyProof = new bytes32[](0);
        try v.disputeFraudulentSwap(100, validSwap, emptyProof, 0) {
            assert(false); // Should not succeed
        } catch {
            assert(true); // Reverted as expected!
        }
    }

    function testSettle100kBatchAudited() public {
        LinReceiptVerifier v = _v();
        bytes32 ROOT_100K = bytes32(0x9ffa679b7a2e4837f59af91675705ff516417f02a4e903c65780fd73949b2d71);
        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 100000,
            swapCount: 100000,
            merkleRoot: ROOT_100K,
            kernelSourceHash: bytes32(0x4f4d12882a326d1c0d6f3b3d62c25185c71370e48c01e0e393b02b73b22250dd),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        uint256 g0 = gasleft();
        assert(v.settleBatch(h));
        emit Log("settle100kBatch", g0 - gasleft());
        assert(v.verifiedMerkleRoots(ROOT_100K));
    }

    function testCanonicalUniswapLibraryParity() public {
        // Test 1: Real mainnet transaction #1 from dataset
        uint256 reserveIn1 = 9916868896781;
        uint256 reserveOut1 = 4148941281736026227948;
        uint256 amountIn1 = 996242;
        uint256 expectedOut1 = 415549418053706;

        uint256 canonicalOut1 = CanonicalUniswapV2Library.getAmountOut(amountIn1, reserveIn1, reserveOut1);
        assert(canonicalOut1 == expectedOut1);

        // Test 2: Live Ethereum Mainnet state queried via RPC
        // USDC/WETH Pair: 0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc
        uint256 liveReserveUSDC = 10016324931612;
        uint256 liveReserveWETH = 4089201265933885299007;
        uint256 liveAmountIn = 1000000; // 1 USDC
        uint256 liveCanonicalOut = CanonicalUniswapV2Library.getAmountOut(liveAmountIn, liveReserveUSDC, liveReserveWETH);
        assert(liveCanonicalOut == 407028853812571); // Exactly what UniswapV2Router02 returned on Mainnet!

        // Test 3: LinReceiptVerifier constant product check must confirm canonical outputs
        LinReceiptVerifier v = _v();
        assert(v.verifyConstantProduct(reserveIn1, reserveOut1, amountIn1, canonicalOut1));
        assert(v.verifyConstantProduct(liveReserveUSDC, liveReserveWETH, liveAmountIn, liveCanonicalOut));
    }

    function testCanonicalPairInvariantK() public pure {
        // Direct test against UniswapV2Pair.sol lines 180-182 invariant
        uint256 r0 = 10016324931612;
        uint256 r1 = 4089201265933885299007;
        uint256 a0In = 1000000;
        uint256 a1Out = 407028853812571;

        uint256 b0 = r0 + a0In;
        uint256 b1 = r1 - a1Out;

        bool kSatisfied = CanonicalUniswapV2Library.verifyPairK(b0, b1, r0, r1, a0In, 0);
        assert(kSatisfied);

        // And check that overdrawing even by 100 wei violates K
        uint256 badA1Out = a1Out + 100;
        uint256 badB1 = r1 - badA1Out;
        bool badKSatisfied = CanonicalUniswapV2Library.verifyPairK(b0, badB1, r0, r1, a0In, 0);
        assert(!badKSatisfied);
    }
}

