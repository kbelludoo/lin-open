#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One auditor command: dataset.json -> LCR2 root + manifest + independent verify.

No Zig. Needs Python 3 stdlib and the C11 host (`make -C transpile/c all`) so
the image digest can be read from lin_bc1_run. Wraps emit_batch_receipt.py +
verify_batch_receipt.py.

Always prints steps_bound=false: the 208 B LCR2 records bind (img, inputs,
oracle outputs, status) and do **not** bind VM step counts.

  python3 tools/lin_auditor.py --dataset test/pilot_harness/mainnet_real_swaps_2000.json
  make audit
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMIT = ROOT / "tools" / "emit_batch_receipt.py"
VERIFY = ROOT / "tools" / "verify_batch_receipt.py"

# Pinned Anvil/Foundry figures (docs/GRANT_ADDENDUM_ERRATA_2026_09.md). Not remeasured here.
ANVIL_SETTLE_BATCH_GAS = 70133
COST_PER_SWAP_USD = 0.00210


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out-dir", default="/tmp/lin-audit")
    ap.add_argument("--out-manifest", default="")
    ap.add_argument("--out-bin", default="")
    ap.add_argument("--run-id", type=int, default=1)
    a = ap.parse_args()

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = Path(a.out_manifest) if a.out_manifest else out_dir / "manifest.json"
    blob = Path(a.out_bin) if a.out_bin else out_dir / "records.bin"
    manifest.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    em = subprocess.run(
        [sys.executable, str(EMIT), "--dataset", a.dataset,
         "--out-manifest", str(manifest), "--out-bin", str(blob),
         "--run-id", str(a.run_id)],
        cwd=str(ROOT),
    )
    if em.returncode != 0:
        return em.returncode
    t_emit = time.perf_counter()
    vf = subprocess.run(
        [sys.executable, str(VERIFY), "--manifest", str(manifest), "--bin", str(blob)],
        cwd=str(ROOT),
    )
    t_end = time.perf_counter()
    if vf.returncode != 0:
        return vf.returncode

    m = json.loads(manifest.read_text(encoding="utf-8"))
    verify_s = t_end - t_emit
    total_s = t_end - t0
    steps_bound = bool(m.get("steps_bound", False))
    print("LIN AUDITOR")
    print(f"  dataset:        {a.dataset}")
    print(f"  count:          {m.get('count')}")
    print(f"  record_bytes:   {m.get('record_bytes', 208)}")
    print(f"  merkle_root:    {m.get('merkle_root')}")
    print(f"  records_sha256: {m.get('records_sha256')}")
    print(f"  img_digest:     {m.get('img_digest')}")
    print(f"  manifest:       {manifest}")
    print(f"  bin:            {blob}")
    print(f"  emit_s:         {t_emit - t0:.4f}")
    print(f"  verify_s:       {verify_s:.4f}")
    print(f"  total_s:        {total_s:.4f}")
    print(f"  steps_bound:    {str(steps_bound).lower()}  (LCR2 steps field is 0)")
    print(f"  anvil_gas:      {ANVIL_SETTLE_BATCH_GAS} settleBatch fresh root (Foundry/Anvil, not Mainnet)")
    print(f"  cost_per_swap:  ${COST_PER_SWAP_USD:.5f} @ 20 gwei, $3k ETH, amortized / 2000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
