'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const childProcess = require('child_process');
const solc = require('solc');
const { AbiCoder, id } = require('ethers');
const { createVM } = require('@ethereumjs/vm');
const {
  createAddressFromString,
  hexToBytes,
  bytesToBigInt,
  bytesToHex,
} = require('@ethereumjs/util');

const candidateRoot = path.resolve(__dirname, '..');
const LIN_ROOT = fs.existsSync(path.join(candidateRoot, 'experiments/uniswap_v2'))
  ? candidateRoot
  : path.join(candidateRoot, 'lin-open');
const UPSTREAM = process.env.UNISWAP_V2_PERIPHERY
  ? path.resolve(process.env.UNISWAP_V2_PERIPHERY)
  : path.join(LIN_ROOT, '..', 'uniswap-v2-periphery');
const LIN_FILE = path.join(LIN_ROOT, 'experiments/uniswap_v2/get_amount_out.lin');
const U256_FILE = path.join(LIN_ROOT, 'experiments/uniswap_v2/u256_get_amount_out.lin');
const C0 = path.join(LIN_ROOT, 'transpile/c/bin/lin_c0');
const RECEIPT = path.join(LIN_ROOT, 'transpile/c/bin/lin_c_receipt');
const U64 = 1n << 64n;
const S64 = 1n << 63n;
const BASE16 = 1n << 16n;

function compileOriginal() {
  const source = fs.readFileSync(
    path.join(UPSTREAM, 'contracts/libraries/UniswapV2Library.sol'),
    'utf8',
  );
  const safeMath = fs.readFileSync(
    path.join(UPSTREAM, 'contracts/libraries/SafeMath.sol'),
    'utf8',
  );
  const input = {
    language: 'Solidity',
    sources: {
      'contracts/libraries/UniswapV2Library.sol': { content: source },
      'contracts/libraries/SafeMath.sol': { content: safeMath },
      '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol': {
        content:
          'pragma solidity >=0.5.0; interface IUniswapV2Pair {' +
          ' function getReserves() external view returns ' +
          '(uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast); }',
      },
      'Harness.sol': {
        content:
          'pragma solidity >=0.5.0; ' +
          'import "./contracts/libraries/UniswapV2Library.sol"; ' +
          'contract Harness { ' +
          'function getAmountOut(uint amountIn, uint reserveIn, uint reserveOut) ' +
          'external pure returns (uint amountOut) { ' +
          'return UniswapV2Library.getAmountOut(amountIn, reserveIn, reserveOut); } }',
      },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { '*': { '*': ['evm.deployedBytecode.object'] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((e) => e.severity === 'error');
  if (errors.length) {
    throw new Error(errors.map((e) => e.formattedMessage).join('\n'));
  }
  const bytecode =
    output.contracts &&
    output.contracts['Harness.sol'] &&
    output.contracts['Harness.sol'].Harness &&
    output.contracts['Harness.sol'].Harness.evm.deployedBytecode.object;
  if (!bytecode) throw new Error('Solidity compiler emitted no runtime bytecode');
  const commit = childProcess
    .execFileSync('git', ['-C', UPSTREAM, 'rev-parse', 'HEAD'], { encoding: 'utf8' })
    .trim();
  return { source, bytecode, commit, compiler: solc.version() };
}

async function makeEvm(bytecode) {
  const vm = await createVM();
  const target = createAddressFromString(
    '0x1111111111111111111111111111111111111111',
  );
  const caller = createAddressFromString(
    '0x2222222222222222222222222222222222222222',
  );
  await vm.stateManager.putCode(target, hexToBytes('0x' + bytecode));
  return { vm, target, caller };
}

async function runSolidity(ctx, args) {
  const encoded = AbiCoder.defaultAbiCoder().encode(
    ['uint256', 'uint256', 'uint256'],
    args,
  );
  const calldata =
    id('getAmountOut(uint256,uint256,uint256)').slice(0, 10) + encoded.slice(2);
  const result = await ctx.vm.evm.runCall({
    to: ctx.target,
    caller: ctx.caller,
    data: hexToBytes(calldata),
    gasLimit: 1000000n,
  });
  if (result.execResult.exceptionError) {
    return { reverted: result.execResult.exceptionError.error };
  }
  return {
    value: bytesToBigInt(result.execResult.returnValue),
    gas: Number(result.execResult.executionGasUsed || 0n),
  };
}

function runLin(args) {
  const result = childProcess.spawnSync(
    C0,
    ['vmfull', LIN_FILE, 'get_amount_out', ...args.map((x) => x.toString())],
    { encoding: 'utf8' },
  );
  const match = /value=(-?\d+) steps=(\d+)/.exec(result.stdout || '');
  if (result.status !== 0 || !match) {
    throw new Error(
      'LIN failed: status=' + result.status + '\n' + (result.stdout || '') + (result.stderr || ''),
    );
  }
  return { value: BigInt(match[1]), steps: Number(match[2]) };
}

function signedWord(word) {
  return (word >= S64 ? word - U64 : word).toString();
}

function u256Words(value) {
  const out = [];
  let rest = value;
  for (let i = 0; i < 4; i++) {
    out.push(signedWord(rest & (U64 - 1n)));
    rest >>= 64n;
  }
  if (rest !== 0n) throw new Error('uint256 ABI value does not fit');
  return out;
}

function runLinU256(args) {
  const limbs = [];
  let steps = null;
  for (let outLimb = 0; outLimb < 16; outLimb++) {
    const result = childProcess.spawnSync(
      C0,
      [
        'vmfull', U256_FILE, 'get_amount_out_u256_limb',
        ...u256Words(args[0]), ...u256Words(args[1]), ...u256Words(args[2]),
        String(outLimb),
      ],
      { encoding: 'utf8' },
    );
    const match = /value=(-?\d+) steps=(\d+)/.exec(result.stdout || '');
    if (result.status !== 0 || !match) {
      throw new Error('LIN u256 failed: status=' + result.status + '\n' +
        (result.stdout || '') + (result.stderr || ''));
    }
    const value = BigInt(match[1]);
    if (value < 0n) return { status: value, steps: Number(match[2]) };
    if (value >= BASE16) throw new Error('LIN u256 emitted an invalid limb');
    if (steps === null) steps = Number(match[2]);
    if (Number(match[2]) !== steps) throw new Error('LIN u256 step count changed');
    limbs.push(value);
  }
  let value = 0n;
  for (let i = 15; i >= 0; i--) value = value * BASE16 + limbs[i];
  return { status: 0n, value, steps };
}

function oracle(args) {
  const amountIn = args[0];
  const reserveIn = args[1];
  const reserveOut = args[2];
  if (amountIn <= 0n || reserveIn <= 0n || reserveOut <= 0n) return 0n;
  const amountInWithFee = amountIn * 997n;
  const numerator = amountInWithFee * reserveOut;
  const denominator = reserveIn * 1000n + amountInWithFee;
  return numerator / denominator;
}

function nextVector(state) {
  state.value =
    (state.value * 6364136223846793005n + 1442695040888963407n) &
    ((1n << 63n) - 1n);
  const amountIn = 1n + (state.value % 1000000n);
  state.value =
    (state.value * 6364136223846793005n + 1442695040888963407n) &
    ((1n << 63n) - 1n);
  const reserveIn = 1n + (state.value % 1000000000n);
  state.value =
    (state.value * 6364136223846793005n + 1442695040888963407n) &
    ((1n << 63n) - 1n);
  const reserveOut = 1n + (state.value % 1000000000n);
  return [amountIn, reserveIn, reserveOut];
}

function parseReceipt(text) {
  const field = (name) => {
    const re = new RegExp('\\b' + name + '=(?:"([^"]*)"|([^\\s]+))');
    const match = re.exec(text);
    if (!match) throw new Error('receipt field missing: ' + name);
    return match[1] || match[2];
  };
  return {
    expr: field('expr'),
    env: field('env'),
    result: BigInt(field('result')),
    steps: BigInt(field('steps')),
    sp: BigInt(field('sp_at_ret')),
    code: field('code_sha256'),
    root: field('root').replace('sha256:', ''),
  };
}

function sha(domain, data) {
  return crypto
    .createHash('sha256')
    .update(Buffer.from(domain))
    .update(data)
    .digest();
}

function receiptRoot(receipt) {
  const source = sha('lin:xver:source:', Buffer.from(receipt.expr));
  const env = sha('lin:xver:env:', Buffer.from(receipt.env));
  const code = Buffer.from(receipt.code, 'hex');
  const exec = sha(
    'lin:xver:exec:',
    Buffer.from(receipt.result + ':' + receipt.steps + ':' + receipt.sp),
  );
  const node = (left, right) =>
    crypto
      .createHash('sha256')
      .update(Buffer.from('node:'))
      .update(left)
      .update(right)
      .digest();
  return bytesToHex(node(node(source, env), node(code, exec))).slice(2);
}

async function main() {
  if (!fs.existsSync(LIN_FILE)) {
    throw new Error('generated LIN file is missing: ' + LIN_FILE);
  }
  const original = compileOriginal();
  const evm = await makeEvm(original.bytecode);
  const fixed = [
    [2n, 100n, 100n],
    [10000n, 50000n, 100000n],
    [1n, 1n, 1n],
    [999999n, 999999999n, 777777777n],
  ];
  const state = { value: 20260904n };
  for (let i = 0; i < 128; i++) fixed.push(nextVector(state));

  let gasTotal = 0;
  let linSteps = null;
  for (const args of fixed) {
    const solidity = await runSolidity(evm, args);
    const lin = runLin(args);
    const expected = oracle(args);
    if (
      solidity.reverted ||
      solidity.value !== expected ||
      lin.value !== expected ||
      solidity.value !== lin.value
    ) {
      throw new Error(
        'valid-vector divergence for ' +
          args.join(',') +
          ': solidity=' +
          JSON.stringify(solidity) +
          ' lin=' +
          JSON.stringify(lin) +
          ' oracle=' +
          expected,
      );
    }
    gasTotal += solidity.gas;
    if (linSteps === null) linSteps = lin.steps;
    if (lin.steps !== linSteps) {
      throw new Error('LIN step count changed for equivalent function path');
    }
  }

  const invalidArgs = [0n, 100n, 100n];
  const invalidSolidity = await runSolidity(evm, invalidArgs);
  const invalidLin = runLin(invalidArgs);

  const productionArgs = [
    1000000000000000000n,
    5000000000000000000n,
    10000000000000000000n,
  ];
  const productionSolidity = await runSolidity(evm, productionArgs);
  const productionLin = runLin(productionArgs);
  const productionU256 = runLinU256(productionArgs);
  if (productionSolidity.reverted || productionU256.status !== 0n ||
      productionU256.value !== productionSolidity.value) {
    throw new Error('uint256 production divergence: solidity=' +
      JSON.stringify(productionSolidity) + ' u256=' + JSON.stringify(productionU256));
  }

  const expr = '((a * 997) * c) / ((b * 1000) + (a * 997))';
  const env = 'a=10000,b=50000,c=100000';
  const receiptText = childProcess.execFileSync(
    RECEIPT,
    ['--expr', expr, '--env', env],
    { encoding: 'utf8' },
  );
  const receipt = parseReceipt(receiptText);
  const recomputed = receiptRoot(receipt);
  if (recomputed !== receipt.root) {
    throw new Error('receipt root failed independent recomputation');
  }
  if (receipt.result !== 16624n) throw new Error('receipt result mismatch');

  console.log('UPSTREAM_REPO=https://github.com/Uniswap/v2-periphery');
  console.log('UPSTREAM_COMMIT=' + original.commit);
  console.log('SOLC=' + original.compiler);
  console.log('SOLIDITY_RUNTIME_BYTES=' + original.bytecode.length / 2);
  console.log('VALID_VECTORS=' + fixed.length);
  console.log('VALID_PARITY=PASS');
  console.log('LIN_C0_PROFILE=vmfull (C11, zig=false)');
  console.log('LIN_STEPS=' + linSteps);
  console.log('EVM_GAS_AVG=' + (gasTotal / fixed.length).toFixed(2));
  console.log(
    'INVALID_INPUT=solidity_' +
      (invalidSolidity.reverted ? 'REVERT' : 'NO_REVERT') +
      ',lin_sentinel=' +
      invalidLin.value,
  );
  console.log(
    'PRODUCTION_SCALAR_SCALE=' +
      (productionSolidity.value === productionLin.value ? 'PASS' : 'BLOCKED_UINT256'),
  );
  console.log('PRODUCTION_SOLIDITY_VALUE=' + productionSolidity.value);
  console.log('PRODUCTION_LIN_VALUE=' + productionLin.value);
  console.log('PRODUCTION_U256_VALUE=' + productionU256.value);
  console.log('PRODUCTION_U256_PARITY=PASS');
  console.log('PRODUCTION_U256_STEPS_PER_LIMB=' + productionU256.steps);
  console.log('RECEIPT=PASS');
  console.log('RECEIPT_ROOT=sha256:' + receipt.root);
  console.log('RECEIPT_RESULT=' + receipt.result);
  console.log('RECEIPT_STEPS=' + receipt.steps);
  console.log('RECEIPT_SP=' + receipt.sp);
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
