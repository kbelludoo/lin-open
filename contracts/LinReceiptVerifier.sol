// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title LinReceiptVerifier
 * @notice Anchors off-chain LIN GPU batch Merkle roots on L1 + spot-checks inclusion on-chain.
 * @dev TRUST MODEL (honesto): `settleBatch` e trusted-sequencer (onlyOwner).
 *      Nao verifica o lote inteiro on-chain; ancora a raiz para auditoria
 *      off-chain via `verifySwapInclusion`. Use `settleBatchWithInclusionProof`
 *      para amarrar pelo menos 1 folha valida (invariante k + Merkle) no ato
 *      do settlement. Leaf EVM = sha256(abi.encodePacked(rIn,rOut,aIn,aOut))
 *      com uint256 de 32B big-endian; DIFERENTE da folha LCR2 off-chain
 *      (208B + dominios LIN:LEAF:1/NODE:1, ver tools/emit_batch_receipt.py).
 *      `gasSavedEstimate = swapCount * 100000` e ESTIMATIVA (swap L1 ~100k),
 *      nao medicao; gas real de deploy/settle e medido em
 *      test/contracts/test_lin_verifier.py quando solcx/web3 disponivel.
 */
contract LinReceiptVerifier {
    struct SwapRecord {
        uint256 reserveIn;
        uint256 reserveOut;
        uint256 amountIn;
        uint256 amountOut;
    }

    struct BatchHeader {
        uint256 batchId;
        uint256 swapCount;
        bytes32 merkleRoot;
        bytes32 kernelSourceHash;
        uint64 timestamp;
        address sequencer;
    }

    event BatchSettled(
        uint256 indexed batchId,
        bytes32 indexed merkleRoot,
        uint256 swapCount,
        uint256 gasSavedEstimate
    );

    event BatchSettledWithProof(
        uint256 indexed batchId,
        bytes32 indexed merkleRoot,
        uint256 swapCount,
        uint256 spotIndex
    );

    address public immutable owner;
    mapping(uint256 => bytes32) public settledBatches;
    mapping(bytes32 => bool) public verifiedMerkleRoots;

    error BatchAlreadySettled(uint256 batchId);
    error InvalidSwapInvariant(uint256 swapIndex);
    error MerkleRootMismatch(bytes32 expected, bytes32 actual);
    error InvalidInclusionProof(uint256 spotIndex);
    error Unauthorized();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Verifies a single Uniswap v2 constant product invariant:
     *         (reserveIn * 1000 + amountIn * 997) * (reserveOut - amountOut) >= reserveIn * reserveOut * 1000
     */
    function verifyConstantProduct(
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 amountIn,
        uint256 amountOut
    ) public pure returns (bool) {
        if (amountOut >= reserveOut) return false;
        uint256 balanceInAdjusted = (reserveIn * 1000) + (amountIn * 997);
        uint256 balanceOutAdjusted = reserveOut - amountOut;
        uint256 kBefore = reserveIn * reserveOut * 1000;
        return (balanceInAdjusted * balanceOutAdjusted) >= kBefore;
    }

    /**
     * @notice Computes leaf hash for a single swap entry in LIN format (SHA-256).
     */
    function computeSwapLeaf(
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 amountIn,
        uint256 amountOut
    ) public pure returns (bytes32) {
        return sha256(abi.encodePacked(reserveIn, reserveOut, amountIn, amountOut));
    }

    /**
     * @notice Computes leaf hash for a raw LCR2 canonical 208-byte record:
     *         sha256("LIN:LEAF:1" || record).
     */
    function computeLCR2Leaf(bytes calldata record) public pure returns (bytes32) {
        return sha256(abi.encodePacked("LIN:LEAF:1", record));
    }

    /**
     * @notice Verifies an LCR2 Merkle inclusion proof against an LCR2 batch root.
     *         Parent node hash: sha256("LIN:NODE:1" || left || right).
     */
    function verifyLCR2Inclusion(
        bytes calldata record,
        bytes32[] calldata proof,
        uint256 index,
        bytes32 root
    ) public pure returns (bool) {
        bytes32 hash = computeLCR2Leaf(record);
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 proofElement = proof[i];
            if ((index >> i) & 1 == 1) {
                hash = sha256(abi.encodePacked("LIN:NODE:1", proofElement, hash));
            } else {
                hash = sha256(abi.encodePacked("LIN:NODE:1", hash, proofElement));
            }
        }
        return hash == root;
    }

    /**
     * @notice Verifies a Merkle inclusion proof for a swap leaf against the settled batch Merkle root.
     */
    function verifySwapInclusion(
        bytes32 leaf,
        bytes32[] calldata proof,
        uint256 index,
        bytes32 root
    ) public pure returns (bool) {
        bytes32 hash = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 proofElement = proof[i];
            if ((index >> i) & 1 == 1) {
                hash = sha256(abi.encodePacked(proofElement, hash));
            } else {
                hash = sha256(abi.encodePacked(hash, proofElement));
            }
        }
        return hash == root;
    }

    /**
     * @notice Settles a LIN GPU batch on L1 (trusted sequencer).
     * @dev Ancora sem verificar proof; auditoria e off-chain via
     *      verifySwapInclusion + tools/verify_batch_receipt.py.
     * @param header Metadata of the batch computed off-chain on GPU.
     */
    function settleBatch(
        BatchHeader calldata header
    ) external onlyOwner returns (bool) {
        if (settledBatches[header.batchId] != bytes32(0)) {
            revert BatchAlreadySettled(header.batchId);
        }

        settledBatches[header.batchId] = header.merkleRoot;
        verifiedMerkleRoots[header.merkleRoot] = true;

        // ESTIMATIVA, nao medicao: swap L1 ~100k gas; settle ~25k fixo.
        // Gas real medido em test/contracts/test_lin_verifier.py (solcx).
        uint256 gasSavedEstimate = header.swapCount * 100000;

        emit BatchSettled(
            header.batchId,
            header.merkleRoot,
            header.swapCount,
            gasSavedEstimate
        );

        return true;
    }

    /**
     * @notice Settles with an on-chain spot-check: invariant k + inclusion proof.
     * @dev Garante que a raiz ancorada contem pelo menos 1 swap valido.
     *      Reverte com InvalidSwapInvariant ou InvalidInclusionProof.
     */
    function settleBatchWithInclusionProof(
        BatchHeader calldata header,
        SwapRecord calldata spot,
        bytes32[] calldata proof,
        uint256 spotIndex
    ) external onlyOwner returns (bool) {
        if (settledBatches[header.batchId] != bytes32(0)) {
            revert BatchAlreadySettled(header.batchId);
        }
        if (!verifyConstantProduct(spot.reserveIn, spot.reserveOut, spot.amountIn, spot.amountOut)) {
            revert InvalidSwapInvariant(spotIndex);
        }
        bytes32 leaf = computeSwapLeaf(spot.reserveIn, spot.reserveOut, spot.amountIn, spot.amountOut);
        if (!verifySwapInclusion(leaf, proof, spotIndex, header.merkleRoot)) {
            revert InvalidInclusionProof(spotIndex);
        }
        settledBatches[header.batchId] = header.merkleRoot;
        verifiedMerkleRoots[header.merkleRoot] = true;
        emit BatchSettledWithProof(header.batchId, header.merkleRoot, header.swapCount, spotIndex);
        return true;
    }
}
