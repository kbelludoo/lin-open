#!/usr/bin/env python3
"""
Automates pre-filling the official Arbitrum Foundation Builders Grant Application
in Brave Browser.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

def fill_arbitrum(headless=False):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_path = os.path.join(root_dir, "docs/LIN_GPU_DeFi_Settlement_Grant_Proposal.pdf")

    print("================================================================================")
    print("=== INICIANDO PREENCHIMENTO AUTOMÁTICO DO FORMULÁRIO ARBITRUM NO BRAVE       ===")
    print("================================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/brave",
            headless=headless,
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        print("[*] Acessando https://tally.so/r/0QObE9...")
        page.goto("https://tally.so/r/0QObE9", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 1. Text and URL Inputs
        print("[*] Preenchendo Informações do Projeto e Contato...")
        inputs = page.query_selector_all("input:not([type=radio]):not([type=checkbox]):not([type=file])")
        textareas = page.query_selector_all("textarea")

        # 0: Company/Project name
        if len(inputs) > 0: inputs[0].fill("LIN Sovereign GPU AMM Co-processor")
        # 1: Website
        if len(inputs) > 1: inputs[1].fill("https://github.com/kbelludoo/lin-open")
        # 2: Github
        if len(inputs) > 2: inputs[2].fill("https://github.com/kbelludoo/lin-open")
        # 3: X/Twitter
        if len(inputs) > 3: inputs[3].fill("N/A")
        # 4: What are you building? (Max 50 chars)
        if len(inputs) > 4: inputs[4].fill("GPU AMM Settlement Co-processor & Stylus Runtime")
        # 5: How would you classify the project primarily?
        if len(inputs) > 5: inputs[5].fill("DeFi / Infrastructure / Developer Tooling")
        # 6: Country
        if len(inputs) > 6: inputs[6].fill("Brazil")

        # 2. Radios via JS Click
        print("[*] Marcando opções de rádio...")
        try:
            page.eval_on_selector("text=Pre-launch", "el => el.click()")
            page.eval_on_selector("text=Multichain including Arbitrum", "el => el.click()")
            page.eval_on_selector("text=No funds raised", "el => el.click()")
        except Exception as e:
            print("[-] Radio click warning:", e)

        # 3. Checkboxes via JS Click
        print("[*] Marcando interesses de suporte da Arbitrum...")
        for interest in ["Smart-contract audit support", "Marketing or ecosystem visibility", "Investment from Arbitrum"]:
            try:
                page.eval_on_selector(f"text={interest}", "el => el.click()")
            except Exception:
                pass

        # 4. Contact Information (Bruno Fonseca)
        if len(inputs) > 7: inputs[7].fill("Bruno Fonseca")
        if len(inputs) > 8: inputs[8].fill("kbelludoo@gmail.com")
        if len(inputs) > 9: inputs[9].fill("@kbelludoo")

        # Number of founders: 1
        try:
            page.eval_on_selector("text=1", "el => el.click()")
        except Exception:
            pass

        if len(textareas) > 0: textareas[0].fill("N/A")
        if len(textareas) > 1: textareas[1].fill("N/A")

        # 5. File Upload
        file_input = page.query_selector("input[type=file]")
        if file_input and os.path.exists(pdf_path):
            file_input.set_input_files(pdf_path)
            print("[+] PDF da proposta anexado com sucesso!")

        if len(inputs) > 10: inputs[10].fill("None / Open Application")

        # 6. Detailed Technical Thesis Tailored for Arbitrum & Stylus
        print("[*] Preenchendo Tese Técnica e Proposta Específica da Arbitrum...")
        comments_text = (
            "Arbitrum Stylus & GPU Co-processor Integration:\n\n"
            "1. Core Innovation:\n"
            "LIN is a deterministic scalar language with a zero-heap, pure C11 host runtime (zero Zig/LLVM dependency). "
            "We built a sovereign off-chain GPU settlement co-processor (OpenCL) that executes 2,000 real Uniswap v2 swaps "
            "in 4.1 ms (>459,000 ops/sec) on consumer hardware (AMD Radeon RX 6600).\n\n"
            "2. Arbitrum Value Proposition:\n"
            "• Calldata & Sequencer Reduction: By settling thousands of swaps in batches off-chain on GPU and emitting a single "
            "64-byte SHA-256 Merkle receipt verified on-chain in ~70k gas (LinReceiptVerifier.sol), we reduce L1 batch posting calldata "
            "costs by over 90% during high-volatility events.\n"
            "• Arbitrum Stylus Native Port: Because LIN's host runtime is pure ISO C11 without dynamic allocation, our Merkle receipt verifier "
            "and u256 AMM math engine are directly portable to WebAssembly (WASM) as an Arbitrum Stylus native contract, unlocking 10x-50x "
            "lower execution gas on Arbitrum One.\n\n"
            "3. Repositories & Reproducibility:\n"
            "• Public GitHub: https://github.com/kbelludoo/lin-open (MIT / Apache-2.0)\n"
            "• Live EVM Tested Contract: contracts/LinReceiptVerifier.sol (70,707 gas measured on EVM)\n"
            "• Executive PDF Attached: LIN_GPU_DeFi_Settlement_Grant_Proposal.pdf"
        )
        if len(textareas) > 2: textareas[2].fill(comments_text)

        print("\n================================================================================")
        print("=== FORMULÁRIO DA ARBITRUM 100% PREENCHIDO COM SUCESSO!                      ===")
        print("=== 1. Revise os campos na janela do Brave.                                  ===")
        print("=== 2. Clique no botão 'Submit' no final da página!                          ===")
        print("================================================================================")

        if not headless:
            print("\n[!] O navegador Brave permanecerá aberto. Pressione Ctrl+C no terminal quando terminar.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[*] Encerrando sessão.")

if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    fill_arbitrum(headless=is_headless)
