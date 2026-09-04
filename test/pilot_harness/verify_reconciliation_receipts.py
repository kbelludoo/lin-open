#!/usr/bin/env python3
"""Independent stdlib-only LCR4 inclusion checker; does not execute the LIN VM.
The expected root must come from a separately trusted channel.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def verify(report, expected_root, image):
    if len(expected_root)!=32: raise ValueError('expected root must be 32 bytes')
    digest=hashlib.sha256(image).digest()
    domain=hashlib.sha256(b'linbc1:img:'+image[:-32]).digest()
    if len(image)<32 or image[-32:]!=domain: raise ValueError('image self-hash')
    entries=report['receipts']
    if not entries: raise ValueError('empty receipt set')
    if report['merkle_root']!=expected_root.hex(): raise ValueError('untrusted report root differs')
    seen=set()
    for item in entries:
        raw=bytes.fromhex(item['record_hex'])
        if len(raw)!=384 or raw[:6]!=b'LCR4\x02\x01' or raw[6] not in (1,2) or raw[7]!=0:
            raise ValueError('noncanonical LCR4')
        if raw[208:240]!=digest or raw[240:272]!=domain: raise ValueError('wrong image identity')
        reported=int.from_bytes(raw[104:136],'big')
        actual=int.from_bytes(raw[136:168],'big')
        delta=int.from_bytes(raw[168:200],'big',signed=True)
        if reported-actual!=delta: raise ValueError('inconsistent delta')
        if raw[6]==2 and (actual!=0 or int.from_bytes(raw[100:104],'little')!=0xffffffff):
            raise ValueError('noncanonical reverted receipt')
        status=struct.unpack_from('<q',raw,200)[0]
        if status!=1 and status not in range(-13,0): raise ValueError('unknown status')
        position=item['index']; width=item['count']
        if type(position)!=int or type(width)!=int or width!=len(entries) or not 0<=position<width:
            raise ValueError('invalid position/count')
        if position in seen: raise ValueError('duplicate position')
        seen.add(position)
        node=hashlib.sha256(b'LIN:RECON:LCR4:LEAF:2\x00'+raw).digest()
        path=iter(item['path'])
        while width>1:
            try: sibling=bytes.fromhex(next(path))
            except StopIteration: raise ValueError('short path') from None
            if len(sibling)!=32: raise ValueError('invalid sibling')
            if position&1: joined=sibling+node
            else:
                if position+1==width and sibling!=node: raise ValueError('odd-leaf padding')
                joined=node+sibling
            node=hashlib.sha256(b'LIN:RECON:LCR4:NODE:2\x00'+joined).digest()
            position//=2; width=(width+1)//2
        if next(path,None) is not None or node!=expected_root: raise ValueError('inclusion mismatch')
    return dict(inclusions_verified=len(entries),image_identity_verified=True,
        execution_verified=False,chain_authenticity_verified=False,
        report_metrics_verified=False,scope_completeness_verified=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--expected-root',required=True)
    p.add_argument('--image',type=Path,required=True)
    a=p.parse_args()
    try:
        result=verify(json.loads(a.report.read_text()),bytes.fromhex(a.expected_root),a.image.read_bytes())
    except (ValueError,KeyError,TypeError) as exc:
        p.exit(1,'REJECTED: '+str(exc)+'\n')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__': main()
