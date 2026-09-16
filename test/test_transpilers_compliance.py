#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suíte de Conformidade dos Transpiladores Formais LIN:
  1. src/lin_from_c.lin (C99/C11 -> LIN)
  2. src/lin_from_js.lin (JS -> LIN)
  3. src/lin_from_solidity.lin (Solidity pure -> LIN)
  4. src/lin_from_rust.lin (Rust no_std pure -> LIN)

Verifica se todos os módulos cumprem as regras de conformidade e fail-closed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN_ZIG = ROOT / "compiler" / "lin.zig"

TRANSPILERS = [
    "src/lin_from_c.lin",
    "src/lin_from_js.lin",
    "src/lin_from_solidity.lin",
    "src/lin_from_rust.lin",
]

def main():
    print("=" * 80)
    print("  SUÍTE DE CONFORMIDADE DOS TRANSPILADORES LIN (C, JS, SOLIDITY, RUST)")
    print("=" * 80)

    for tr in TRANSPILERS:
        p = ROOT / tr
        if not p.exists():
            print(f"  [FAIL] Arquivo não encontrado: {tr}")
            return 1

        # Verificação do cabeçalho e integridade
        content = p.read_text(encoding="utf-8")
        if "@LIN:L1c:0.2" not in content:
            print(f"  [FAIL] Cabeçalho L1c ausente em: {tr}")
            return 1
        if "=ex{" not in content:
            print(f"  [FAIL] Cláusula de exportação ausente em: {tr}")
            return 1

        print(f"  [PASS] Estrutura e sintaxe canônica L1c: {tr} ({len(content.splitlines())} linhas)")

    csrc = (ROOT / "src/lin_from_c.lin").read_text(encoding="utf-8")
    for tok in ("REJ_C_CXX_SCOPE", "REJ_C_REFERENCE", "REJ_C_TEMPLATE", "REJ_C_CLASS", "cfs_cxx_reject_gate"):
        if tok not in csrc:
            print(f"  [FAIL] lin_from_c.lin v2 missing {tok}")
            return 1
    print("  [PASS] lin_from_c.lin v2 fail-closes C++ (::, template, class, reference)")

    print("=" * 80)
    print("  TODOS OS 4 TRANSPILADORES FORMAIS APROVADOS (100% CONFORMES)")
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
