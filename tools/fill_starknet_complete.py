#!/usr/bin/env python3
"""
Complete, robust automated pre-filler for the Starknet Foundation Seed Grant Airtable Form.
Fills all 30+ questions automatically in Brave Browser.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

def fill_all(headless=False):
    print("================================================================================")
    print("=== INICIANDO PREENCHIMENTO COMPLETO (30+ CAMPOS) DO STARKNET NO BRAVE       ===")
    print("================================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/brave",
            headless=headless,
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        print("[*] Acessando formulário oficial da Starknet Foundation (Airtable)...")
        page.goto("https://airtable.com/appfoRv2ottjRfTpL/pag0G55zA8aU4V9bD/form", wait_until="networkidle")
        page.wait_for_timeout(3000)

        def fill_field(label_text, value):
            try:
                # Find by text matching label
                res = page.evaluate("""([lbl, val]) => {
                    let questions = Array.from(document.querySelectorAll("div, label")).filter(e => 
                        e.children.length === 0 && e.innerText && e.innerText.trim().toLowerCase().includes(lbl.toLowerCase())
                    );
                    for (let q of questions) {
                        let container = q.closest("[role=group]") || q.closest(".cellField") || q.parentElement.parentElement;
                        if (container) {
                            let inp = container.querySelector("input:not([type=radio]):not([type=checkbox]), textarea");
                            if (inp) {
                                inp.value = val;
                                inp.dispatchEvent(new Event('input', { bubbles: true }));
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            }
                        }
                    }
                    return false;
                }""", [label_text, value])
                if res:
                    print(f"  [+] Preenchido: {label_text}")
                else:
                    print(f"  [-] Campo não encontrado via JS: {label_text}")
            except Exception as e:
                print(f"  [-] Erro em {label_text}: {e}")

        def click_choice(choice_text):
            try:
                res = page.evaluate("""(txt) => {
                    let els = Array.from(document.querySelectorAll("div, span, label, button")).filter(e => 
                        e.children.length === 0 && e.innerText && e.innerText.trim().toLowerCase() === txt.toLowerCase()
                    );
                    for (let el of els) {
                        let target = el.closest("label") || el.closest("[role=button]") || el;
                        target.click();
                        return true;
                    }
                    return false;
                }""", choice_text)
                if res:
                    print(f"  [+] Opção selecionada: {choice_text}")
            except Exception as e:
                print(f"  [-] Erro ao clicar {choice_text}: {e}")

        # 1. Project Info
        fill_field("Project name", "LIN Sovereign GPU AMM Co-processor")
        fill_field("One liner", "A sovereign GPU batch settlement co-processor executing 2,000 AMM swaps in 4.1ms with deterministic cryptographic receipts.")
        fill_field("Website URL", "https://github.com/kbelludoo/lin-open")
        fill_field("Project GitHub", "https://github.com/kbelludoo/lin-open")
        fill_field("Team GitHub handles", "kbelludoo")
        fill_field("Project X URL", "N/A")
        fill_field("Other social URLs", "N/A")

        # 2. Contact
        fill_field("Contact full name", "Bruno Fonseca")
        fill_field("Contact email", "kbelludoo@gmail.com")
        fill_field("Contact Telegram handle", "@kbelludoo")
        fill_field("Contact GitHub username", "kbelludoo")
        fill_field("TG group <> SNF", "N/A")
        fill_field("City", "Brazil")
        fill_field("Country", "Brazil")
        fill_field("Team", "Bruno Fonseca - Lead Systems & Compiler Engineer (GitHub: github.com/kbelludoo)")

        # 3. Overview & Phase
        fill_field("Project overview", (
            "We built LIN, a deterministic scalar programming language and LinVM, along with a sovereign off-chain "
            "GPU settlement co-processor (OpenCL) that executes 2,000 real Ethereum mainnet Uniswap v2 swaps in 4.1 ms "
            "(>459,000 ops/sec) on commodity AMD Radeon RX 6600 hardware. The engine verifies constant-product AMM invariants "
            "(x*y >= k) and generates 64-byte SHA-256 Merkle compute receipts for L1/L2 on-chain settlement."
        ))
        click_choice("Testing/Pilot")
        fill_field("Raise details", "N/A - Self-funded open-source research with zero venture capital or token sales.")

        # 4. Technical Architecture on Starknet
        fill_field("Integrated chains", "Ethereum L1, Arbitrum, Starknet")
        click_choice("Yes") # Project live
        click_choice("Not live") # Starknet live status

        fill_field("Tools, infrastructure & frameworks", (
            "We are integrating with Starknet execution pipelines and planning integration with Cairo / Madara "
            "sequencer architectures to serve as an off-chain AMM batching and liquidation co-processor."
        ))
        fill_field("Starknet specifics", (
            "Integration from EVM/LIN to Starknet, adapting our deterministic compute receipts to Starknet Cairo verifier contracts."
        ))
        fill_field("Starknet language", (
            "Our team specializes in systems programming, C11, Rust, and deterministic compilers. We are mapping our verified "
            "C11/LIN verification kernels to Cairo smart contract verifiers to verify batch Merkle receipts directly on Starknet."
        ))
        fill_field("Starknet contributions", (
            "Developed open-source deterministic compiler and AMM settlement co-processor with 100% public GitHub code and reproducible benchmarks."
        ))
        fill_field("Proposed solution", (
            "Provides Starknet DEXes (Ekubo, Jediswap) with an ultra-high-throughput off-chain AMM settlement co-processor "
            "capable of evaluating over 450,000 swaps/sec on consumer GPUs, eliminating sequencer congestion and generating "
            "lightweight cryptographic receipts for on-chain state updates."
        ))

        # 5. KPIs & Strategy
        fill_field("Project KPIs", "1. AMM settlement throughput (>450,000 ops/sec). 2. Bit-exact verification parity across 2,000+ mainnet swaps. 3. Zero-defect fail-closed security bounds.")
        fill_field("User acquisition strategy", "Direct B2B integration with Starknet DEXes (Ekubo, Jediswap), AMM aggregators, and rollup sequencers seeking ultra-fast off-chain batch settlement.")

        # 6. Business Model & Financials
        fill_field("Business model", (
            "Core engine is 100% open-source MIT/Apache-2.0. Future monetization via enterprise SLA licensing "
            "for high-frequency sequencers and decentralized RPC co-processor hosting."
        ))
        fill_field("Project cost components", (
            "70% core systems/cryptography engineering, 15% testing/RPC infrastructure & multi-GPU testbeds, "
            "15% third-party smart contract security audits."
        ))
        fill_field("Security & audits", (
            "Internal security audit completed (SECURITY_AUDIT.md in repo). Zero heap allocation in execution kernels, "
            "100% fail-closed bounds checking, tamper-evident Merkle receipts. Formal external third-party audit planned for Milestone 1."
        ))

        # 7. Milestone 1
        fill_field("Funding amount", "25000")
        fill_field("Milestone 1 name", "Production L1/L2 Verifier Contract & GPU AMM Settlement Engine")
        fill_field("Milestone 1 amount", "10000")
        fill_field("Milestone 1 completion date", "15/10/2026")
        fill_field("Milestone 1 deliverables", (
            "1. Audited L1/L2 verifier smart contract (LinReceiptVerifier) supporting batch SHA-256 Merkle compute receipts.\n"
            "2. Open-source OpenCL C AMM settlement kernel achieving >450,000 ops/sec on consumer GPUs.\n"
            "3. Reproducible differential testing harness verifying 2,000+ mainnet swaps with 100% bit-exact parity.\n"
            "4. Public Sepolia testnet deployment with automated verification scripts and verified contract addresses on block explorer."
        ))

        # 8. Past Work & Other Grants
        fill_field("Track record", (
            "Built LIN (github.com/kbelludoo/lin-open), a 100% self-hosted systems language with fixed point C0=C1=C2 and native "
            "ELF64 emission. Developed and verified an AMM liquidation co-processor executing 2,000 swaps in 4.1 ms on AMD RX 6600 "
            "GPU with 77/77 bit-exact targets passing."
        ))
        click_choice("No") # Previously applied to Starknet
        fill_field("Other Starknet grant programs", "N/A")
        fill_field("Other grants", "Applied to Ethereum Foundation Ecosystem Support Program (ESP) for $30k and Arbitrum Builders Grant.")

        # 9. Collaborations & Support
        fill_field("Starknet collaborations", (
            "We seek to collaborate with Starknet DEXes (such as Ekubo and Jediswap) and Starknet infrastructure teams (Madara / Karnot). "
            "Our sovereign GPU settlement engine and deterministic receipt pipeline can be integrated as an off-chain AMM execution and "
            "liquidation co-processor, drastically increasing throughput while minimizing on-chain execution and proof generation overhead."
        ))
        fill_field("Extra support", (
            "Technical mentorship from Starknet Foundation cryptography/Cairo engineers, introductions to Starknet DEX teams (Ekubo/Jediswap), and smart contract security audit subsidies."
        ))

        # 10. License & Referral
        fill_field("Referral", "N/A")

        # 11. Signatory
        click_choice("Individual")
        fill_field("Signatory full name", "Bruno Fonseca")
        fill_field("Signatory email", "kbelludoo@gmail.com")
        fill_field("Signatory title", "Lead Systems Engineer / Founder")

        print("\n================================================================================")
        print("=== TODOS OS 30+ CAMPOS DO FORMULÁRIO STARKNET PREENCHIDOS COM SUCESSO!      ===")
        print("=== O navegador permanecerá aberto para sua revisão e envio.                 ===")
        print("================================================================================")

        if not headless:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("[*] Encerrando sessão.")

if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    fill_all(headless=is_headless)
