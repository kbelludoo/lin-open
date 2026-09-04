'use strict';

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');

const candidateRoot = path.resolve(__dirname, '..');
const LIN_ROOT = fs.existsSync(path.join(candidateRoot, 'experiments/uniswap_v2'))
  ? candidateRoot
  : path.join(candidateRoot, 'lin-open');
const LIN_FILE = path.join(LIN_ROOT, 'experiments/uniswap_v2/u256_get_amount_out.lin');
const C0 = path.join(LIN_ROOT, 'transpile/c/bin/lin_c0');
const U256 = (1n << 256n) - 1n;
const U64 = 1n << 64n;
const S64 = 1n << 63n;
const BASE16 = 1n << 16n;

function signedWord(word) {
  return (word >= S64 ? word - U64 : word).toString();
}

function words(value) {
  const out = [];
  let rest = value;
  for (let i = 0; i < 4; i++) {
    out.push(signedWord(rest & (U64 - 1n)));
    rest >>= 64n;
  }
  if (rest !== 0n) throw new Error('value does not fit uint256: ' + value);
  return out;
}

function runLimb(amountIn, reserveIn, reserveOut, limb) {
  const args = [
    ...words(amountIn),
    ...words(reserveIn),
    ...words(reserveOut),
    String(limb),
  ];
  const result = childProcess.spawnSync(
    C0,
    ['vmfull', LIN_FILE, 'get_amount_out_u256_limb', ...args],
    { encoding: 'utf8' },
  );
  const match = /value=(-?\d+) steps=(\d+)/.exec(result.stdout || '');
  if (result.status !== 0 || !match) {
    throw new Error(
      'LIN u256 limb failed: status=' + result.status + '\n' +
      (result.stdout || '') + (result.stderr || ''),
    );
  }
  return { value: BigInt(match[1]), steps: Number(match[2]) };
}

function runU256(args) {
  const limbs = [];
  let steps = null;
  for (let i = 0; i < 16; i++) {
    const result = runLimb(args[0], args[1], args[2], i);
    if (result.value < 0n) return { status: result.value, steps: result.steps };
    if (result.value >= BASE16) throw new Error('invalid limb: ' + result.value);
    if (steps === null) steps = result.steps;
    if (result.steps !== steps) throw new Error('non-deterministic limb step count');
    limbs.push(result.value);
  }
  let value = 0n;
  for (let i = 15; i >= 0; i--) value = value * BASE16 + limbs[i];
  return { status: 0n, value, steps };
}

function oracle([amountIn, reserveIn, reserveOut]) {
  if (amountIn === 0n || reserveIn === 0n || reserveOut === 0n) return null;
  const amountInWithFee = amountIn * 997n;
  const numerator = amountInWithFee * reserveOut;
  const denominator = reserveIn * 1000n + amountInWithFee;
  if (amountInWithFee > U256 || numerator > U256 || denominator > U256) return null;
  return numerator / denominator;
}

function checkValid(args) {
  const result = runU256(args);
  const expected = oracle(args);
  if (expected === null) throw new Error('test vector is not valid for SafeMath: ' + args);
  if (result.status !== 0n || result.value !== expected) {
    throw new Error('u256 mismatch: args=' + args + ' result=' + JSON.stringify(result) + ' expected=' + expected);
  }
  return result;
}

function checkInvalid(args, expectedStatus) {
  const result = runU256(args);
  if (result.status !== expectedStatus) {
    throw new Error('invalid vector mismatch: args=' + args + ' result=' + JSON.stringify(result) + ' expected status=' + expectedStatus);
  }
  return result;
}

function main() {
  const vectors = [
    [2n, 100n, 100n],
    [10000n, 50000n, 100000n],
    [1000000000000000000n, 5000000000000000000n, 10000000000000000000n],
    [1n << 200n, 1n, 1n << 40n],
  ];
  const results = vectors.map(checkValid);
  checkInvalid([0n, 100n, 100n], -1n);
  checkInvalid([1n << 200n, 1n, 1n << 100n], -2n);

  console.log('U256_REPRESENTATION=16xuint16_limbs_little_endian');
  console.log('U256_ABI=four_raw_u64_words_per_input_as_signed_i64');
  console.log('U256_VALID_PARITY=PASS');
  console.log('U256_SMALL_RESULT=' + results[0].value);
  console.log('U256_PRODUCTION_RESULT=' + results[2].value);
  console.log('U256_HIGH_WORD_RESULT=' + results[3].value);
  console.log('U256_STEPS_PER_LIMB=' + results[2].steps);
  console.log('U256_INVALID_ZERO=status_-1');
  console.log('U256_INVALID_OVERFLOW=status_-2');
}

main();
