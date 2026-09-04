"""Experimental evidence adapter. Business classification and AMM math run in LIN.
RPC snapshots and token metadata are supplied evidence, not consensus proofs.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
C0 = ROOT / 'transpile/c/bin/lin_c0'
RUN = ROOT / 'transpile/c/bin/lin_bc1_run'
CORE = ROOT / 'examples/defi_settlement_proof/u256_settlement_engine.lin'
POLICY = ROOT / 'examples/defi_reconciliation_pilot/defi_reconciler.lin'
U256 = (1 << 256) - 1
NO_LOG = (1 << 32) - 1
SYNC = '0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'
SWAP = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
NAMES = {1:'STATUS_CONCILIATED', -1:'ERR_AMOUNT_MISMATCH',
 -2:'ERR_REVERTED_ON_CHAIN', -3:'ERR_SLIPPAGE_BREACH',
 -4:'ERR_POOL_MISATTRIBUTION', -5:'ERR_DECIMALS_SCALE',
 -6:'ERR_DUPLICATE_OPERATION', -7:'ERR_MISSING_OPERATION',
 -8:'ERR_EVENT_ORDER', -9:'UNVERIFIED_OR_UNSUPPORTED',
 -10:'ERR_TOKEN_MISMATCH', -11:'ERR_INPUT_MISMATCH',
 -12:'ERR_GAS_MISMATCH', -13:'ERR_CLIENT_STATUS'}
LEAF = b'LIN:RECON:LCR4:LEAF:2\x00'
NODE = b'LIN:RECON:LCR4:NODE:2\x00'


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha(x):
    return hashlib.sha256(x).digest()


def uint(x, bits=256):
    if isinstance(x, bool) or not (isinstance(x, int) or
            isinstance(x, str) and re.fullmatch(r'0|[1-9][0-9]*', x)):
        raise ValueError('expected canonical unsigned integer')
    n = int(x)
    if not 0 <= n < (1 << bits):
        raise ValueError('unsigned integer out of range')
    return n


def hx(x, length):
    if not isinstance(x, str) or not re.fullmatch('0x[0-9a-fA-F]{%d}' % (2*length), x):
        raise ValueError('invalid fixed-length hex')
    return x.lower()


def quantity(x, bits=256):
    if not isinstance(x, str) or not re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', x):
        raise ValueError('invalid RPC quantity')
    return uint(int(x, 16), bits)


def words(x):
    x = uint(x)
    return [((x >> (64*i)) & ((1 << 64)-1)) -
            (1 << 64 if (x >> (64*i+63)) & 1 else 0) for i in range(4)]


class Engine:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.source = directory / 'reconciliation_linked.lin'
        self.image = directory / 'reconciliation.linbc'
        self.source.write_bytes(CORE.read_bytes() + b'\n' + POLICY.read_bytes())
        subprocess.run([str(C0), 'image', str(self.source), '-o', str(self.image)],
                       check=True, capture_output=True, text=True, timeout=60)
        self.raw = self.image.read_bytes()
        self.file_digest = sha(self.raw)
        self.loader_digest = sha(b'linbc1:img:' + self.raw[:-32])
        if self.raw[-32:] != self.loader_digest:
            raise ValueError('image self-hash mismatch')
        self.policy_digest = sha(self.source.read_bytes())
        self.check_identity()

    def check_identity(self):
        if self.image.read_bytes() != self.raw:
            raise ValueError('image changed after compilation')
        # --hex passes the exact immutable bytes checked here to the loader,
        # avoiding a check/read race on a mutable image path.
        p = subprocess.run([str(RUN), '--hex', self.raw.hex(), '--verify'],
                           check=True, capture_output=True, text=True, timeout=30)
        self.check_loader(p.stdout)

    def check_loader(self, output):
        m = re.search(r'img_sha256="([0-9a-f]{64})"', output)
        if not m or bytes.fromhex(m[1]) != self.loader_digest:
            raise ValueError('loader digest differs from domain hash')

    def invoke(self, function, args):
        self.check_identity()
        p = subprocess.run([str(RUN), '--hex', self.raw.hex(), function,
                            *map(str, args)], check=True, capture_output=True,
                           text=True, timeout=60)
        self.check_loader(p.stdout)
        result = re.search(r'\bresult=(-?\d+)\b', p.stdout)
        steps = re.search(r'\bsteps=(\d+)\b', p.stdout)
        if not result or not steps or 'status="EVALUATED"' not in p.stdout:
            raise ValueError('malformed VM execution receipt')
        return int(result[1]), int(steps[1])


def identity(e):
    return e['chain_id'], e['tx_hash'], e['log_index']


def decode_bundle(bundle):
    """Explicit transaction scope; never infer bot ownership from a pool scan.
    Pair metadata is externally supplied; caller must independently validate it.
    Each transaction uses the ordered raw receipt, not a map of latest events.
    """
    chain = uint(bundle['chain_id'], 64)
    if chain != 1:
        raise ValueError('pilot supports Ethereum mainnet snapshots only')
    scope = [hx(h, 32) for h in bundle['scope_tx_hashes']]
    if len(set(scope)) != len(scope):
        raise ValueError('duplicate transaction in declared scope')
    pools = {hx(k,20): v for k,v in bundle['pools'].items()}
    receipts = {}
    blocks = {hx(b['hash'],32): b for b in bundle['blocks']}
    for response in bundle['receipt_responses']:
        r = response.get('result')
        if response.get('error') or not isinstance(r, dict):
            raise ValueError('missing/failed receipt: cannot conclude omission')
        tx = hx(r['transactionHash'],32)
        if tx in receipts:
            raise ValueError('duplicate RPC receipt')
        receipts[tx] = r
    if set(scope) != set(receipts):
        raise ValueError('scope and receipt set differ')
    events = []
    seen_block_logs = set()
    for tx in scope:
        r = receipts[tx]
        bh = hx(r['blockHash'],32)
        bn = quantity(r['blockNumber'],64)
        block = blocks.get(bh)
        if block is None or quantity(block['number'],64) != bn:
            raise ValueError('receipt/header mismatch')
        txs = [hx(t if isinstance(t,str) else t['hash'],32) for t in block['transactions']]
        ti = quantity(r['transactionIndex'],32)
        if ti >= len(txs) or txs[ti] != tx:
            raise ValueError('transaction not at claimed block position')
        success = quantity(r['status'],8)
        if success not in (0,1):
            raise ValueError('invalid receipt status')
        gas = quantity(r['gasUsed']) * quantity(r['effectiveGasPrice'])
        uint(gas)
        base = dict(chain_id=chain, tx_hash=tx, block_hash=bh, block_number=bn,
                    chain_success=success, gas_cost=gas)
        if not success:
            if r['logs']:
                raise ValueError('reverted transaction cannot have committed logs')
            events.append(dict(base, log_index=NO_LOG, event_order=0,
                pool='0x'+'00'*20, token_in='0x'+'00'*20, token_out='0x'+'00'*20,
                decimals=0, amount_in=0, actual_out=0, reserve_in=0,
                reserve_out=0, formula_supported=0))
            continue
        pending = {}
        orders = Counter()
        previous = -1
        found = 0
        for log in r['logs']:
            li = quantity(log['logIndex'],32)
            if li == NO_LOG or li <= previous or (bh,li) in seen_block_logs:
                raise ValueError('invalid, repeated or unordered logIndex')
            previous = li
            seen_block_logs.add((bh,li))
            if (hx(log['transactionHash'],32) != tx or hx(log['blockHash'],32) != bh
                or quantity(log['blockNumber'],64) != bn
                or quantity(log['transactionIndex'],32) != ti
                or log.get('removed') is not False):
                raise ValueError('log provenance mismatch')
            address = hx(log['address'],20)
            topics = [hx(t,32) for t in log['topics']]
            if address not in pools or not topics:
                continue
            topic = topics[0]
            if topic == SYNC:
                if len(topics) != 1:
                    raise ValueError('invalid Sync topics')
                data = bytes.fromhex(hx(log['data'],64)[2:])
                reserves = [int.from_bytes(data[i:i+32],'big') for i in (0,32)]
                for n in reserves: uint(n,112)
                pending[address] = reserves
            elif topic == SWAP:
                if len(topics) != 3 or address not in pending:
                    raise ValueError('Swap lacks preceding same-pool Sync')
                # For canonical V2 the pair emits Sync immediately before Swap
                # among its own events. Transfer events from tokens may precede.
                data = bytes.fromhex(hx(log['data'],128)[2:])
                ain0,ain1,out0,out1 = [int.from_bytes(data[i:i+32],'big')
                                      for i in range(0,128,32)]
                post0,post1 = pending.pop(address)
                simple = ((ain0>0 and ain1==0 and out0==0 and out1>0) or
                          (ain1>0 and ain0==0 and out1==0 and out0>0))
                if not simple:
                    raise ValueError('unsupported flash/multi-sided swap; not conciliable')
                meta = pools[address]
                token0,token1 = hx(meta['token0'],20),hx(meta['token1'],20)
                if ain0:
                    ain,out,rin,rout = ain0,out1,post0-ain0,post1+out1
                    tin,tout,dec = token0,token1,meta['decimals1']
                else:
                    ain,out,rin,rout = ain1,out0,post1-ain1,post0+out0
                    tin,tout,dec = token1,token0,meta['decimals0']
                uint(rin,112); uint(rout,112)
                if not rin or not rout:
                    raise ValueError('invalid reconstructed reserves')
                events.append(dict(base, log_index=li, event_order=orders[address],
                    pool=address, token_in=tin, token_out=tout, decimals=uint(dec,8),
                    amount_in=ain, actual_out=out, reserve_in=rin, reserve_out=rout,
                    formula_supported=int(meta.get('rule')=='v2_exact_input_997')))
                orders[address] += 1
                found += 1
            else:
                # Do not reuse a Sync across another event emitted by this pool.
                pending.pop(address, None)
        if not found:
            raise ValueError('scoped successful transaction has no supported swap')
    return events


def read_clients(path):
    path = Path(path)
    if path.suffix.lower() == '.csv':
        with path.open(newline='') as f: return list(csv.DictReader(f))
    rows = json.loads(path.read_text())
    if not isinstance(rows,list): raise ValueError('client JSON must be a list')
    return rows


def normalize_client(r):
    r = dict(r)
    for f,bits in [('chain_id',64),('log_index',32),('event_order',32),
            ('reported_out',256),('amount_in',256),('min_out',256),
            ('gas_cost',256),('decimals',8),('success',8)]:
        r[f] = uint(r[f],bits)
    if r['success'] not in (0,1): raise ValueError('invalid client success')
    r['tx_hash'] = hx(r['tx_hash'],32)
    for f in ('pool','token_in','token_out'): r[f]=hx(r[f],20)
    return r


def reconcile(engine, events, rows):
    normalized = [normalize_client(r) for r in rows]
    by_id = {}
    for r in normalized: by_id.setdefault(identity(r),[]).append(r)
    facts = {identity(e):e for e in events}
    if len(facts)!=len(events): raise ValueError('duplicate evidence identity')
    findings = []
    for key in sorted(set(facts)|set(by_id)):
        e = facts.get(key)
        clients = by_id.get(key,[])
        r = clients[0] if clients else None
        # Inputs are validated before entering the scalar ABI.
        reported = r['reported_out'] if r else 0
        actual = e['actual_out'] if e else 0
        amount = e['amount_in'] if e else 0
        rin = e['reserve_in'] if e else 0
        rout = e['reserve_out'] if e else 0
        args = words(reported)+words(actual)+words(r['min_out'] if r else 0)+[
            len(clients), int(e is not None), e['chain_success'] if e else 0,
            r['success'] if r else 0, int(bool(e and r and e['pool']==r['pool'])),
            int(bool(e and r and e['event_order']==r['event_order'])),
            r['decimals'] if r else 0, e['decimals'] if e else 0,
            e['formula_supported'] if e else 0,
            int(bool(e and r and e['token_in']==r['token_in'] and e['token_out']==r['token_out'])),
            int(bool(e and r and e['amount_in']==r['amount_in'])),
            int(bool(e and r and e['gas_cost']==r['gas_cost']))]+words(amount)+words(rin)+words(rout)
        status,steps = engine.invoke('reconcile',args)
        if status not in NAMES: raise ValueError('unknown classifier status')
        findings.append(dict(identity=list(key), status=status, diagnosis=NAMES[status],
            steps=steps, reported_out=reported, actual_out=actual,
            delta=reported-actual, evidence=e, clients=clients,
            certainty='observed_field_difference' if status not in (1,-9) else
                ('matched_within_declared_scope' if status==1 else 'unverified'),
            mev_attribution='not_evaluated'))
    return findings


def encode_lcr4(f, engine, evidence_digest):
    # No invented provenance for missing evidence. Those findings remain in JSON.
    e = f['evidence']
    if e is None: raise ValueError('cannot issue on-chain receipt without evidence')
    delta = f['delta']
    if not -(1<<255) <= delta < (1<<255):
        raise ValueError('delta exceeds int256; no wrapping allowed')
    kind = 1 if e['chain_success'] else 2
    raw = b'LCR4'+bytes([2,1,kind,0])
    raw += struct.pack('<Q',e['chain_id'])
    raw += bytes.fromhex(e['block_hash'][2:])+bytes.fromhex(e['tx_hash'][2:])
    raw += bytes.fromhex(e['pool'][2:])+struct.pack('<I',e['log_index'])
    raw += uint(f['reported_out']).to_bytes(32,'big')
    raw += uint(f['actual_out']).to_bytes(32,'big')
    raw += delta.to_bytes(32,'big',signed=True)+struct.pack('<q',f['status'])
    raw += engine.file_digest+engine.loader_digest
    raw += struct.pack('<QQ',e['block_number'],f['steps'])
    raw += evidence_digest+sha(canonical(f['clients']))+engine.policy_digest
    if len(raw)!=384: raise ValueError('invalid LCR4 size')
    return raw


def merkle(records):
    if not records: raise ValueError('empty batch has no root')
    levels = [[sha(LEAF+r) for r in records]]
    while len(levels[-1])>1:
        old=levels[-1]
        levels.append([sha(NODE+old[i]+old[min(i+1,len(old)-1)])
                       for i in range(0,len(old),2)])
    paths=[]
    for index in range(len(records)):
        at=index; path=[]
        for level in levels[:-1]:
            path.append(level[min(at^1,len(level)-1)].hex()); at//=2
        paths.append(path)
    return levels[-1][0],paths


def verify_inclusion(record, index, count, path, expected_root):
    if not 0<=index<count or len(record)!=384 or record[:6]!=b'LCR4\x02\x01': return False
    if record[6] not in (1,2) or record[7]!=0: return False
    node=sha(LEAF+record); width=count; at=index; pos=0
    try:
        while width>1:
            sibling=bytes.fromhex(path[pos]); pos+=1
            if len(sibling)!=32: return False
            if at%2==0:
                if at+1==width and sibling!=node: return False
                node=sha(NODE+node+sibling)
            else: node=sha(NODE+sibling+node)
            at//=2; width=(width+1)//2
    except (ValueError,IndexError,TypeError): return False
    return pos==len(path) and node==expected_root
