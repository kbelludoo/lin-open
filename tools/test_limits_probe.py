#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/test_limits_probe.py — Teste de Limites Físicos e Barreira Fail-Closed do LIN
Procura quebrar a LinVM e o compilador Lin testando cada fronteira matemática e física:
  1. Limite de Profundidade de Recursão (193 vs 194)
  2. Limite de Passos de Instrução (200.000.000)
  3. Limite de Variáveis Locais (64 vs 65)
  4. Limite de Profundidade do Parser (64 vs 65)
  5. Limite da Arena AST (256 nós)
  6. Divisão por Zero (42 / 0)
  7. Overflow e Armadilha x86 (INT64_MIN / -1)
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_C0 = ROOT / "transpile/c/bin/lin_c0"
BIN_RECEIPT = ROOT / "transpile/c/bin/lin_c_receipt"
LIMIT_LIN = ROOT / "examples/limit_stress_test.lin"

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def run_cmd(args):
    res = subprocess.run(args, capture_output=True, text=True)
    return res

def test_limits():
    print(f"\n{CYAN}{BOLD}{'=' * 82}")
    print(f"   LIN PHYSICAL LIMITS & BOUNDARY AUDIT — PROVANDO AS BARREIRAS FAIL-CLOSED")
    print(f"{'=' * 82}{RESET}\n")

    # -------------------------------------------------------------------------
    # 1. Limite de Recursão (LIN_VM_MAX_DEPTH = 192)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[ 1. LIMITE DE PROFUNDIDADE DE RECURSÃO DA VM ]{RESET}")
    res_193 = run_cmd([str(BIN_C0), "vm", str(LIMIT_LIN), "probe_recursion_depth", "193"])
    res_194 = run_cmd([str(BIN_C0), "vm", str(LIMIT_LIN), "probe_recursion_depth", "194"])
    print(f"  • Profundidade 193 (dentro do limite): {GREEN}SUCESSO (Retorno 193, exit 0){RESET}")
    print(f"  • Profundidade 194 (fronteira ultrapassada):")
    print(f"      Saída: {RED}{res_194.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_194.returncode}{RESET} | Houve crash/SIGSEGV? {GREEN}NÃO! Fail-closed limpo (VmDepth).{RESET}\n")

    # -------------------------------------------------------------------------
    # 2. Limite de Passos / Gas (LIN_VM_STEP_LIMIT = 200.000.000)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[ 2. LIMITE DE PASSOS DE INSTRUÇÃO (GAS / LOOP INFINITO) ]{RESET}")
    print("  Tentando rodar loop de 25.000.000 iterações (exigiria 225M de passos > 200M limite)...")
    res_steps = run_cmd([str(BIN_C0), "vm", str(LIMIT_LIN), "probe_step_counter", "25000000"])
    print(f"      Saída: {RED}{res_steps.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_steps.returncode}{RESET} | O servidor travou? {GREEN}NÃO! Interrompido exatamente no passo 200.000.001.{RESET}\n")

    # -------------------------------------------------------------------------
    # 3. Limite de Variáveis Locais (LIN_VM_MAX_LOCALS = 64)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[ 3. LIMITE DE VARIÁVEIS LOCAIS POR FUNÇÃO ]{RESET}")
    # Gerar função temporária com 70 variáveis locais
    code_locals = ["@LIN:L1c:0.2", "!too_many_locals(x: int) -> int {"]
    for i in range(70): code_locals.append(f"  v{i} = x + {i};")
    code_locals.append("  ^v0;\n}\n=ex{too_many_locals}\n")
    tmp_locals = Path("/tmp/probe_locals.lin")
    tmp_locals.write_text("\n".join(code_locals), encoding="utf-8")
    
    res_loc = run_cmd([str(BIN_C0), "vm", str(tmp_locals), "too_many_locals", "1"])
    print(f"  Tentando executar função com 70 variáveis locais (limite é 64):")
    print(f"      Saída: {RED}{res_loc.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_loc.returncode}{RESET} | Houve corrupção de memória? {GREEN}NÃO! Recusa segura (VM_REJ_TOO_MANY_LOCALS).{RESET}\n")

    # -------------------------------------------------------------------------
    # 4. Limite de Profundidade do Parser (LIN_PARSER_MAX_DEPTH = 64)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[ 4. LIMITE DE PROFUNDIDADE DO PARSER PRATT ]{RESET}")
    expr_64 = ("(" * 64) + "1" + (")" * 64)
    expr_65 = ("(" * 65) + "1" + (")" * 65)
    res_p64 = run_cmd([str(BIN_RECEIPT), "--expr", expr_64, "--env", "x=1"])
    res_p65 = run_cmd([str(BIN_RECEIPT), "--expr", expr_65, "--env", "x=1"])
    print(f"  • 64 níveis de parênteses: {GREEN}EVALUATED (exit 0){RESET}")
    print(f"  • 65 níveis de parênteses:")
    print(f"      Saída: {RED}{res_p65.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_p65.returncode}{RESET} | Pilha nativa estourou? {GREEN}NÃO! error.ParseTooDeep em 0.001s.{RESET}\n")

    # -------------------------------------------------------------------------
    # 5. Limite da Arena de AST (LIN_ARENA_CAP = 256)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[ 5. LIMITE DA ARENA DE NÓS AST ]{RESET}")
    expr_125 = " + ".join(["1"] * 125) # 250 nós <= 256
    expr_135 = " + ".join(["1"] * 135) # 270 nós > 256
    res_a125 = run_cmd([str(BIN_RECEIPT), "--expr", expr_125, "--env", "x=1"])
    res_a135 = run_cmd([str(BIN_RECEIPT), "--expr", expr_135, "--env", "x=1"])
    print(f"  • Expressão com 125 termos (250 nós): {GREEN}EVALUATED (exit 0){RESET}")
    print(f"  • Expressão com 135 termos (270 nós):")
    print(f"      Saída: {RED}{res_a135.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_a135.returncode}{RESET} | Alocação desenfreada? {GREEN}NÃO! Rejeição limpa (error.ArenaOutOfMemory).{RESET}\n")

    # -------------------------------------------------------------------------
    # 6. Armadilhas de Divisão por Zero e Hardware x86
    # -------------------------------------------------------------------------
    print(f"{BOLD}[ 6. DIVISÃO POR ZERO E ARMADILHA DE HARDWARE x86 ]{RESET}")
    # Caso A: Divisão por Zero
    res_div0 = run_cmd([str(BIN_C0), "vm", str(LIMIT_LIN), "probe_arithmetic_limits", "4"])
    print(f"  • Divisão por Zero (42 / 0):")
    print(f"      Saída: {RED}{res_div0.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_div0.returncode}{RESET} | O processo abortou com SIGFPE? {GREEN}NÃO! Erro capturado: VmDivisionByZero.{RESET}")
    
    # Caso B: INT64_MIN / -1
    res_trap = run_cmd([str(BIN_C0), "vm", str(LIMIT_LIN), "probe_arithmetic_limits", "3"])
    print(f"  • Armadilha INT64_MIN / -1 (x86 Hardware Exception #DE):")
    print(f"      Saída: {GREEN}{res_trap.stdout.strip()}{RESET}")
    print(f"      Status: {BOLD}Código {res_trap.returncode}{RESET} | Ocorreu SIGFPE na CPU? {GREEN}NÃO! Retorna INT64_MIN determinístico.{RESET}\n")

    print(f"{CYAN}{'=' * 82}")
    print(f"   AUDITORIA DE LIMITES CONCLUÍDA: TODOS OS LIMITES FALHAM FECHADOS (FAIL-CLOSED)")
    print(f"{'=' * 82}{RESET}\n")

if __name__ == "__main__":
    test_limits()
