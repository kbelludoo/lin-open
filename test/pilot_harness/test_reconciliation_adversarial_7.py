#!/usr/bin/env python3
"""Seven controlled mutations, historical arithmetic, receipt and identity gates.
Default fixtures are SYNTHETIC; no network authenticity or commercial claim.
--bundle/--client runs the same adapter against supplied RPC/customer snapshots.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import tempfile
from reconciliation_support import (ROOT, RUN, Engine, NAMES, NO_LOG, SWAP, SYNC,
    U256, canonical, decode_bundle, encode_lcr4, hx, merkle, read_clients,
    reconcile, sha, verify_inclusion, words)


def historical_vectors():
    path=ROOT/'test/pilot_harness/test_live_ethereum_settlement.py'
    tree=ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and
                t.id=='REAL_MAINNET_TRANSACTIONS' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('historical vectors missing')


def ref_out(a,r,o):
    # Independent integer oracle with Solidity-style checked intermediates.
    fee=a*997; den=r*1000+fee; num=fee*o
    if not a or not r or not o: return -1,0
    if max(fee,r*1000,den,num)>U256: return -2,0
    return 1,num//den


def fixtures():
    # Receipts are constructed test data. Never reuse real transaction hashes
    # for synthetic records, including the controlled reverted transaction.
    h=lambda n:'0x'+format(n,'064x')
    address=lambda n:'0x'+format(n,'040x')
    pool=address(101); t0=address(201); t1=address(202)
    bh=h(9001)
    bundle=dict(evidence_class='synthetic',chain_id=1,scope_tx_hashes=[],
        pools={pool:dict(token0=t0,token1=t1,decimals0=18,decimals1=6,
                        rule='v2_exact_input_997')},blocks=[],receipt_responses=[])
    clients=[]; log_index=0
    block=dict(hash=bh,number=hex(1),transactions=[],baseFeePerGas=hex(7))
    cases=[[(10**18,10**24,10**12)],[(500,100000,200000)],
           [(1<<65,1<<90,1<<80)],[(29,1000,3000)],
           [(100,10000,20000),(200,10100,19803)],[]]
    for ti,swaps in enumerate(cases):
        tx=h(ti+1)
        bundle['scope_tx_hashes'].append(tx); block['transactions'].append(tx)
        receipt=dict(transactionHash=tx,blockHash=bh,blockNumber=hex(1),
            transactionIndex=hex(ti),status=hex(int(bool(swaps))),
            gasUsed=hex(21000),effectiveGasPrice=hex(10),logs=[])
        for order,(a,r,o) in enumerate(swaps):
            status,out=ref_out(a,r,o)
            assert status==1
            post=(r+a,o-out)
            for topic,data,topics in [(SYNC,post,[SYNC]),
                    (SWAP,(a,0,0,out),[SWAP,h(301),h(302)])]:
                receipt['logs'].append(dict(address=pool,topics=topics,
                    data='0x'+''.join(format(v,'064x') for v in data),
                    logIndex=hex(log_index),transactionHash=tx,blockHash=bh,
                    blockNumber=hex(1),transactionIndex=hex(ti),removed=False))
                log_index+=1
            clients.append(dict(chain_id=1,tx_hash=tx,log_index=log_index-1,
                event_order=order,pool=pool,token_in=t0,token_out=t1,decimals=6,
                amount_in=a,reported_out=out,min_out=0,gas_cost=210000,success=1))
        if not swaps:
            clients.append(dict(chain_id=1,tx_hash=tx,log_index=NO_LOG,event_order=0,
                pool=address(0),token_in=address(0),token_out=address(0),decimals=0,
                amount_in=0,reported_out=0,min_out=0,gas_cost=210000,success=0))
        bundle['receipt_responses'].append(dict(jsonrpc='2.0',id=ti,result=receipt))
    bundle['blocks'].append(block)
    return bundle,clients


def require(condition,message):
    if not condition: raise AssertionError(message)


def run_tests(engine):
    bundle,clients=fixtures()
    events=decode_bundle(bundle)
    clean=reconcile(engine,events,clients)
    require(all(f['status']==1 for f in clean),'clean fixture false positive')
    # CSV/file order is irrelevant: explicit event_order belongs to each event.
    reversed_clean=reconcile(engine,events,list(reversed(clients)))
    require(all(f['status']==1 for f in reversed_clean),'row order false positive')
    cases=[]
    r=deepcopy(clients); r.append(deepcopy(r[0])); cases.append(('duplicate',r,[-6]))
    r=deepcopy(clients); del r[0]; cases.append(('omission',r,[-7]))
    r=deepcopy(clients); r[0]['reported_out']+=1; cases.append(('one_base_unit',r,[-1]))
    r=deepcopy(clients); r[0]['decimals']=18; r[0]['reported_out']*=10**12
    cases.append(('decimal_metadata_and_scale',r,[-5]))
    r=deepcopy(clients); r[0]['pool']='0x'+'ab'*20; cases.append(('wrong_pool',r,[-4]))
    r=deepcopy(clients); r[4]['event_order'],r[5]['event_order']=1,0
    cases.append(('same_pool_event_order',r,[-8,-8]))
    r=deepcopy(clients); r[-1]['success']=1; r[-1]['reported_out']=100
    cases.append(('reverted_marked_success',r,[-2]))
    results=[]
    for name,rows,expected in cases:
        findings=reconcile(engine,events,rows)
        observed=sorted(f['status'] for f in findings if f['status']!=1)
        require(observed==sorted(expected),f'{name}: {observed} != {expected}')
        results.append(dict(case=name,expected=expected,observed=observed,passed=True))
    # Additional boundaries prevent an implementation that only labels fixtures.
    extra=[]
    for field,value,expected in [('min_out',clients[0]['reported_out']+1,-3),
            ('gas_cost',210001,-12),('amount_in',clients[0]['amount_in']+1,-11),
            ('token_out','0x'+'aa'*20,-10),('success',0,-13)]:
        rows=deepcopy(clients); rows[0][field]=value
        require(reconcile(engine,events,rows)[0]['status']==expected,field)
        extra.append(field)
    # A ratio alone is not a proven decimals error.
    rows=deepcopy(clients); rows[0]['reported_out']*=10**12
    require(reconcile(engine,events,rows)[0]['status']==-1,'ratio must not infer cause')
    rows=deepcopy(clients); rows[0]['reported_out']+=1<<64
    require(reconcile(engine,events,rows)[0]['status']==-1,'high-word-only mismatch lost')
    missing=deepcopy(clients); missing[0]['tx_hash']='0x'+'aa'*32
    status={f['status'] for f in reconcile(engine,events,missing)}
    require(-9 in status and -7 in status,'unknown evidence must remain unverified')
    altered=deepcopy(events); altered[0]['reserve_in']+=10**23
    require(reconcile(engine,altered,clients)[0]['status']==-9,'AMM arithmetic not checked')
    invalid=deepcopy(bundle)
    invalid['receipt_responses'][0]['result']['logs'].reverse()
    try: decode_bundle(invalid)
    except ValueError: pass
    else: raise AssertionError('unordered RPC logs accepted')
    invalid=deepcopy(bundle); invalid['receipt_responses'][0]['result']['blockHash']='0x'+'ff'*32
    try: decode_bundle(invalid)
    except ValueError: pass
    else: raise AssertionError('wrong block accepted')
    for bad in (-1,U256+1,1.0,True,'1e18'):
        rows=deepcopy(clients); rows[0]['reported_out']=bad
        try: reconcile(engine,events,rows)
        except ValueError: pass
        else: raise AssertionError('invalid u256 accepted')
    # Unsigned comparison, including top-bit and carry boundaries.
    rng=random.Random(404)
    comparisons=[(0,0),(0,U256),(U256,0),(1<<63,(1<<63)-1),
                 (1<<255,(1<<255)-1)]
    comparisons += [(rng.getrandbits(256),rng.getrandbits(256)) for _ in range(30)]
    for a,b in comparisons:
        got,_=engine.invoke('reconcile_cmp',words(a)+words(b))
        require(got==((a>b)-(a<b)),'u256 comparison mismatch')
    # Historical numbers remain unverified snapshots, not authenticated receipts.
    historical=[]
    for v in historical_vectors():
        a,r,o=v['amount_in'],v['reserve_in'],v['reserve_out']
        status,out=ref_out(a,r,o)
        args=words(a)+words(r)+words(o)
        st,_=engine.invoke('settle_u256_word',args+[-1])
        actual=sum((engine.invoke('settle_u256_word',args+[i])[0]&((1<<64)-1))<<(64*i)
                   for i in range(4))
        require(st==status==1 and actual==out==v['expected_out_real'],'historical arithmetic')
        historical.append(dict(tx_hash=v['tx_hash'],arithmetic_match=True,
                               provenance_verified=False))
    # Checked arithmetic boundaries, including overflowing intermediary products.
    for a,r,o in [(0,1,1),(1,0,1),(1,1,0),(U256,1,1),(1,U256,1),(1,1,U256)]:
        expected,_=ref_out(a,r,o)
        st,_=engine.invoke('settle_u256_word',words(a)+words(r)+words(o)+[-1])
        require(st==expected,'AMM boundary status')
    records=[encode_lcr4(f,engine,sha(canonical(bundle))) for f in clean]
    root,paths=merkle(records)
    from verify_reconciliation_receipts import verify as independent_verify
    independent_report=audit_bundle(engine,bundle,clients)
    verdict=independent_verify(independent_report,root,engine.raw)
    require(verdict['inclusions_verified']==len(records),'independent verifier')
    legacy=deepcopy(independent_report)
    legacy_raw=bytearray.fromhex(legacy['receipts'][0]['record_hex']); legacy_raw[4]=1
    legacy['receipts'][0]['record_hex']=legacy_raw.hex()
    try: independent_verify(legacy,root,engine.raw)
    except ValueError: pass
    else: raise AssertionError('legacy LCR4 v1 accepted as v2')
    for change in ('record','path','root','image'):
        candidate=deepcopy(independent_report); expected=root; image=engine.raw
        if change=='record':
            raw=bytearray.fromhex(candidate['receipts'][0]['record_hex']); raw[136]^=1
            candidate['receipts'][0]['record_hex']=raw.hex()
        elif change=='path': candidate['receipts'][0]['path'][0]='00'*32
        elif change=='root': expected=bytes(32)
        else: image=engine.raw[:-1]+bytes([engine.raw[-1]^1])
        try: independent_verify(candidate,expected,image)
        except ValueError: pass
        else: raise AssertionError('independent verifier accepted '+change)
    mutations=0
    for i,record in enumerate(records):
        require(verify_inclusion(record,i,len(records),paths[i],root),'valid inclusion')
        for offset in [16,48,80,104,136,168,208,240,288,320,352]:
            raw=bytearray(record); raw[offset]^=1
            require(not verify_inclusion(bytes(raw),i,len(records),paths[i],root),'tampered leaf')
            mutations+=1
        path=list(paths[i]); path[0]='00'*32
        require(not verify_inclusion(record,i,len(records),path,root),'tampered path')
        require(not verify_inclusion(record,i,len(records),paths[i],bytes(32)),'wrong root')
        require(not verify_inclusion(record,i,len(records),paths[i]+['00'*32],root),'extra path')
    overflow=deepcopy(clean[0]); overflow['delta']=1<<255
    try: encode_lcr4(overflow,engine,bytes(32))
    except ValueError: pass
    else: raise AssertionError('signed delta wrapped')
    damaged=bytearray(engine.raw); damaged[-1]^=1
    p=subprocess.run([str(RUN),'--hex',bytes(damaged).hex(),'--verify'],capture_output=True,text=True)
    require(p.returncode!=0 and 'selfhash' in p.stdout,'loader accepted corrupt image')
    engine.image.write_bytes(bytes(damaged))
    try:
        try: engine.invoke('reconcile_cmp',words(0)+words(0))
        except ValueError: pass
        else: raise AssertionError('image identity mutation accepted')
    finally: engine.image.write_bytes(engine.raw)
    return dict(evidence_class='synthetic_adversarial_and_unverified_historical',
        adversarial_cases=results,detected_cases=len(results),total_cases=7,
        clean_operations=len(clean),false_positives=0,
        false_positive_rate_on_fixture=0.0,comparison_vectors=len(comparisons),
        historical_arithmetic=historical,merkle_leaf_mutations_rejected=mutations,
        independent_verifier_negative_cases=4,
        additional_policy_checks=extra,raw_image_sha256=engine.file_digest.hex(),
        loader_domain_sha256=engine.loader_digest.hex(),
        live_mainnet_receipt_gate='NOT_RUN_NO_AUTHENTICATED_RPC_SNAPSHOT',
        customer_reconciliation_gate='NOT_RUN_NO_CUSTOMER_EXPORT',
        manual_hours_saved=None,economic_benefit=None,
        commercial_ready=False)


def audit_bundle(engine,bundle,rows):
    events=decode_bundle(bundle)
    findings=reconcile(engine,events,rows)
    evidence_digest=sha(canonical(bundle))
    receipts=[]
    for f in findings:
        try:
            raw=encode_lcr4(f,engine,evidence_digest)
            receipts.append(dict(identity=f['identity'],record_hex=raw.hex()))
        except ValueError as exc:
            f['receipt_unavailable']=str(exc)
    if receipts:
        root,paths=merkle([bytes.fromhex(r['record_hex']) for r in receipts])
        for i,(r,path) in enumerate(zip(receipts,paths)):
            r.update(index=i,count=len(receipts),path=path)
        root=root.hex()
    else: root=None
    return dict(evidence_class=bundle.get('evidence_class','supplied_rpc_snapshot_unverified'),
        source_authenticity_verified=False,evidence_sha256=evidence_digest.hex(),
        operations=len(findings),conciliated=sum(f['status']==1 for f in findings),
        discrepancies=sum(f['status'] not in (1,-9) for f in findings),
        unverified=sum(f['status']==-9 for f in findings),
        false_positive_rate=None,manual_hours_saved=None,economic_benefit=None,
        mev_attribution='not_evaluated',findings=findings,receipts=receipts,
        merkle_root=root,raw_image_sha256=engine.file_digest.hex(),
        loader_domain_sha256=engine.loader_digest.hex(),
        policy_source_sha256=engine.policy_digest.hex(),
        host_runner_sha256=sha(RUN.read_bytes()).hex(),
        compiler_sha256=sha((ROOT/'transpile/c/bin/lin_c0').read_bytes()).hex())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--client',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if bool(args.bundle)!=bool(args.client): parser.error('--bundle and --client are required together')
    subprocess.run(['make','-C',str(ROOT/'transpile/c'),'c0','bin/lin_bc1_run'],check=True)
    with tempfile.TemporaryDirectory(prefix='lin-reconciliation-') as directory:
        engine=Engine(directory)
        if args.bundle:
            report=audit_bundle(engine,json.loads(args.bundle.read_text()),read_clients(args.client))
            report['bundle_file_sha256']=sha(args.bundle.read_bytes()).hex()
            report['client_file_sha256']=sha(args.client.read_bytes()).hex()
        else: report=run_tests(engine)
        output=json.dumps(report,indent=2,sort_keys=True)
        if args.out:
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_text(output+'\n')
            args.out.with_suffix('.linbc').write_bytes(engine.raw)
            args.out.with_suffix('.linked.lin').write_bytes(engine.source.read_bytes())
        print(output)


if __name__=='__main__': main()
