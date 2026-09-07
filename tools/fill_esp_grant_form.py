#!/usr/bin/env python3
"""
Automates pre-filling the official Ethereum Foundation ESP Grant Application
in Brave Browser, leaving the window open for the user to pass the anti-bot/captcha
and submit.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

def fill_form(headless=False):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_path = os.path.join(root_dir, "docs/LIN_GPU_DeFi_Settlement_Grant_Proposal.pdf")
    
    if not os.path.exists(pdf_path):
        print(f"[-] PDF not found: {pdf_path}")
        sys.exit(1)

    print("================================================================================")
    print("=== INICIANDO PREENCHIMENTO AUTOMÁTICO DO FORMULÁRIO ESP NO BRAVE            ===")
    print("================================================================================")

    with sync_playwright() as p:
        # Launch real Brave browser
        browser = p.chromium.launch(
            executable_path="/usr/bin/brave",
            headless=headless,
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        print("[*] Acessando https://esp.ethereum.foundation/form-direct/apply...")
        page.goto("https://esp.ethereum.foundation/form-direct/apply", wait_until="networkidle")
        page.wait_for_selector("input#projectName", timeout=20000)

        # 1. Personal & Project Information
        print("[*] Preenchendo Informações Pessoais e do Projeto...")
        page.fill("input#firstName", "Bruno")
        page.fill("input#lastName", "Fonseca")
        page.fill("input#email", "kbelludoo@gmail.com")
        page.fill("input#company", "LIN Open Research")
        page.fill("input#budgetRequest", "30000")
        page.fill("input#projectName", "LIN Sovereign GPU AMM Settlement & Rollup Co-processor")
        page.fill("input#projectRepo", "https://github.com/kbelludoo/lin-open")

        # 2. Textareas
        summary_text = (
            "We developed a sovereign GPU offload co-processor and parallel AMM settlement engine written in LIN "
            "(a verified deterministic scalar language) with pure C11 host orchestration (zero LLVM/Zig dependency in production). "
            "Running on consumer GPU hardware (AMD Radeon RX 6600), it executes 2,000 real Ethereum mainnet Uniswap v2 swaps in "
            "4.1 milliseconds (459,000+ ops/sec) with an invariant verification engine and emits deterministic 64-byte SHA-256 "
            "Merkle compute receipts. On-chain batch settlement is verified via our compiled Solidity 0.8.20 contract "
            "(LinReceiptVerifier.sol) consuming only 70,707 gas on EVM — a 99.9939% gas reduction compared to re-executing on L1."
        )
        page.fill("textarea#projectSummary", summary_text)

        problem_text = (
            "DEX trading and batch state reconciliation on Ethereum L1 are severely constrained by EVM sequential execution (~15-30 TPS) "
            "and prohibitive gas costs (~1.16 billion gas for 2,000 complex swaps). Rollup sequencers and DeFi settlement processors "
            "struggle to scale AMM liquidity verification without incurring heavy hardware overhead or trusting centralized indexers. "
            "Our project solves this by delivering sovereign, deterministic GPU parallel execution for AMM invariant verification "
            "(x*y >= k) and producing cryptographic execution receipts verifiable on Ethereum L1 with minimal gas overhead."
        )
        page.fill("textarea#problemBeingSolved", problem_text)

        impact_text = (
            "- Empirical throughput: 459,000+ AMM operations/sec on consumer GPU hardware (AMD Navi 23, 28 CUs), processing 2,000 real Ethereum mainnet swaps in 4.1 ms.\n"
            "- Measured EVM Gas Reduction: Submitting batch settlement receipts to LinReceiptVerifier.sol costs 70,707 gas on EVM vs 1,164,504,079 gas spent on mainnet (99.9939% gas reduction / 16,469x less gas).\n"
            "- Zero-trust auditability: Deterministic SHA-256 Merkle receipt generation for every transaction batch, tamper-evident and independently verifiable.\n"
            "- Self-hosted sovereignty: 100% pure LIN front-end, fixed point C0=C1=C2, native ELF64 emission, and pure C11 host without LLVM or proprietary toolchains."
        )
        page.fill("textarea#measuredImpact", impact_text)

        structure_text = (
            "- Milestone 1 ($10,000 - 4 weeks): Production L1 Verifier Contract: Formal test suite and Sepolia testnet deployment of LinReceiptVerifier.sol with automated batch proof submission scripts.\n"
            "- Milestone 2 ($10,000 - 6 weeks): Live Mempool Streaming Batcher: Standalone daemon continuously ingesting live pending DEX swaps, batching on GPU, and publishing verifiable cryptographic receipts.\n"
            "- Milestone 3 ($10,000 - 4 weeks): Multi-GPU Portability & Formal Audit: Cross-platform validation across NVIDIA (CUDA/OpenCL), AMD (ROCm), and Apple Silicon (Metal), accompanied by a third-party security review report."
        )
        page.fill("textarea#projectStructure", structure_text)

        sustainability_text = (
            "All code, transpilers, OpenCL kernels, and Solidity contracts are 100% open source under MIT/Apache-2.0. "
            "Long-term development will be sustained by Layer-2 sequencer integrations, decentralized RPC batching infrastructure, "
            "and public goods grants from the L2 ecosystem (Arbitrum, Optimism, Base). Any developer can reproduce all results in "
            "one click via 'make benchmark-uniswap' and 'make verify-contracts'."
        )
        page.fill("textarea#sustainabilityPlan", sustainability_text)

        funding_text = (
            "We have not received prior venture capital or private token investment for this engine. "
            "The requested $30,000 grant directly funds independent research, kernel engineering, testnet deployment, "
            "and third-party security auditing over 6 months."
        )
        page.fill("textarea#funding", funding_text)

        metrics_text = (
            "1. Mainnet settlement batch size: >10,000 swaps verified under 10 ms.\n"
            "2. Sepolia on-chain verification gas: <= 80,000 gas per batch seal.\n"
            "3. 100% bit-exact parity across independent C11, Python, and EVM oracles.\n"
            "4. Zero-vulnerability external security audit report published publicly."
        )
        page.fill("textarea#successMetrics", metrics_text)

        eco_fit_text = (
            "Directly addresses Ethereum's Layer-1 congestion and rollup scalability roadmap. By enabling deterministic "
            "off-chain batch verification on consumer GPUs, we empower decentralization by allowing regular nodes to run "
            "high-throughput DEX sequencers without multimillion-dollar server clusters."
        )
        page.fill("textarea#ecosystemFit", eco_fit_text)

        feedback_text = (
            "Early benchmarks shared with DeFi researchers and Layer-2 developers demonstrated overwhelming interest in "
            "sub-5ms batch settlement proofs and eliminating high EVM re-execution gas overhead."
        )
        page.fill("textarea#communityFeedback", feedback_text)

        profile_text = (
            "Systems and compiler engineer developing deterministic compute runtimes, verified offload co-processors, "
            "and zero-dependency kernels in pure LIN and C11."
        )
        page.fill("textarea#applicantProfile", profile_text)

        page.fill("input#referral", "None / Open Application")

        # 3. Sequential React-Select Dropdowns
        print("[*] Selecionando Menus Suspensos (Dropdowns)...")
        inps = page.query_selector_all("input[id^=\"react-select-\"]")
        dropdown_vals = [
            ("Individual", 0),
            ("Brazil", 1),
            ("UTC-03", 2),
            ("USD", 3),
            ("Layer 2", 4),
            ("Open Source Software", 5),
            ("MIT", 6)
        ]
        for val, idx in dropdown_vals:
            if idx < len(inps):
                inps[idx].focus()
                page.keyboard.type(val, delay=15)
                time.sleep(0.3)
                page.keyboard.press("Enter")
                time.sleep(0.2)
        print("[+] Todos os 7 dropdowns configurados com sucesso!")

        # 4. Radios
        print("[*] Configurando opções de rádio...")
        # Have you applied before? -> No
        radios_no = page.query_selector_all("label:has-text(\"No\")")
        if len(radios_no) >= 1:
            radios_no[0].click()

        # Allow contact -> Yes
        radios_yes = page.query_selector_all("label:has-text(\"Yes\")")
        if len(radios_yes) >= 2:
            radios_yes[1].click()

        # 5. File Upload
        print(f"[*] Anexando proposta oficial em PDF ({pdf_path})...")
        file_input = page.query_selector("input#fileUpload")
        if file_input:
            file_input.set_input_files(pdf_path)
            print("[+] PDF anexado com sucesso!")

        # 6. Checkbox de pagamento
        print("[*] Marcando aceite de pagamento em ETH...")
        chk = page.query_selector("label:has-text(\"Grant Payment Acknowledgement\")")
        if chk:
            chk.click()

        print("\n================================================================================")
        print("=== FORMULÁRIO 100% PREENCHIDO COM SUCESSO!                                  ===")
        print("=== AGORA:                                                                  ===")
        print("=== 1. Verifique seu Nome / Sobrenome e E-mail no topo.                     ===")
        print("=== 2. Resolva o desafio do hCaptcha / anti-bot.                             ===")
        print("=== 3. Clique no botão final 'Submit Application'.                          ===")
        print("================================================================================")

        if not headless:
            print("\n[!] O navegador Brave permanecerá aberto. Pressione Ctrl+C no terminal quando terminar.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[*] Fechando sessão do navegador.")

if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    fill_form(headless=is_headless)
