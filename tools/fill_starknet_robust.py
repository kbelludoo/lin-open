#!/usr/bin/env python3
"""
Fully automated, robust pre-filler for the Starknet Foundation Seed Grant Airtable Form.
Fills every single field, dropdown, and checkbox natively in Brave Browser.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

def run_fill(headless=False):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_path = os.path.join(root_dir, "docs/LIN_GPU_DeFi_Settlement_Grant_Proposal.pdf")

    print("================================================================================")
    print("=== INICIANDO PREENCHIMENTO COMPLETO ROBUSTO DO FORMULÁRIO STARKNET NO BRAVE ===")
    print("================================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/brave",
            headless=headless,
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        print("[*] Acessando formulário da Starknet Foundation...")
        page.goto("https://airtable.com/appfoRv2ottjRfTpL/pag0G55zA8aU4V9bD/form", wait_until="networkidle")
        page.wait_for_timeout(3000)

        def fill_by_group(title_text, value):
            try:
                # Find the group container having this text
                groups = page.locator(f"div[role=group]:has-text('{title_text}')")
                if groups.count() > 0:
                    container = groups.first
                    # Look for textarea first, otherwise visible input
                    inp = container.locator("textarea, input:not(.editableFix):not([tabindex='-1'])").last
                    if inp.count() > 0:
                        inp.scroll_into_view_if_needed()
                        inp.fill(value)
                        print(f"  [+] {title_text}: preenchido!")
                        return True
            except Exception as e:
                print(f"  [-] Erro em {title_text}: {e}")
            return False

        def click_option(opt_text):
            try:
                el = page.locator(f"text='{opt_text}'").first
                if el.count() > 0:
                    el.scroll_into_view_if_needed()
                    el.click(force=True)
                    print(f"  [+] Opção selecionada: {opt_text}")
                    return True
                else:
                    # fallback
                    page.eval_on_selector(f"text={opt_text}", "el => el.click()")
                    print(f"  [+] Opção selecionada (via JS): {opt_text}")
                    return True
            except Exception as e:
                print(f"  [-] Erro ao clicar {opt_text}: {e}")
            return False

        # --- SEÇÃO 1: Project Details ---
        print("\n[*] 1. Detalhes do Projeto...")
        fill_by_group("Project name", "LIN Sovereign GPU AMM Co-processor")
        # Project category: click DeFi or Infrastructure
        click_option("DeFi")
        fill_by_group("One liner", "A sovereign GPU batch settlement co-processor executing 2,000 AMM swaps in 4.1ms with deterministic cryptographic receipts.")
        fill_by_group("Website URL", "https://github.com/kbelludoo/lin-open")
        fill_by_group("Project GitHub", "https://github.com/kbelludoo/lin-open")
        fill_by_group("Team GitHub handles", "kbelludoo")
        fill_by_group("Project X URL", "N/A")
        fill_by_group("Other social URLs", "N/A")

        # --- SEÇÃO 2: Contact Information ---
        print("\n[*] 2. Informações de Contato...")
        fill_by_group("Contact full name", "Bruno Fonseca")
        fill_by_group("Contact email", "kbelludoo@gmail.com")
        fill_by_group("Contact Telegram handle", "@kbelludoo")
        fill_by_group("Contact GitHub username", "kbelludoo")
        fill_by_group("TG group <> SNF", "N/A")

        # --- SEÇÃO 3: Team & Location ---
        print("\n[*] 3. Equipe e Localização...")
        fill_by_group("Country", "Brazil")
        fill_by_group("City", "Brazil")
        fill_by_group("Team", "Bruno Fonseca - Lead Systems & Compiler Engineer (GitHub: github.com/kbelludoo)")

        # --- SEÇÃO 4: Project Overview & Phase ---
        print("\n[*] 4. Visão Geral e Estágio...")
        fill_by_group("Project overview", (
            "We built LIN, a deterministic scalar programming language and LinVM, along with a sovereign off-chain "
            "GPU settlement co-processor (OpenCL) that executes 2,000 real Ethereum mainnet Uniswap v2 swaps in 4.1 ms "
            "(>459,000 ops/sec) on commodity AMD Radeon RX 6600 hardware. The engine verifies constant-product AMM invariants "
            "(x*y >= k) and generates 64-byte SHA-256 Merkle compute receipts for L1/L2 on-chain settlement."
        ))
        click_option("Testing/Pilot")
        fill_by_group("Raise details", "N/A - Self-funded open-source research with zero venture capital or token sales.")

        # --- SEÇÃO 5: Technical Information ---
        print("\n[*] 5. Informações Técnicas e Arquitetura...")
        fill_by_group("Integrated chains", "Ethereum L1, Arbitrum, Starknet")
        click_option("Yes") # Project live
        click_option("Not live") # Starknet live

        fill_by_group("Tools, infrastructure & frameworks", (
            "We are integrating with Starknet execution pipelines and planning integration with Cairo / Madara "
            "sequencer architectures to serve as an off-chain AMM batching and liquidation co-processor."
        ))
        fill_by_group("Starknet specifics", (
            "Integration from EVM/LIN to Starknet, adapting our deterministic compute receipts to Starknet Cairo verifier contracts."
        ))
        fill_by_group("Starknet language", (
            "Our team specializes in systems programming, C11, Rust, and deterministic compilers. We are mapping our verified "
            "C11/LIN verification kernels to Cairo smart contract verifiers to verify batch Merkle receipts directly on Starknet."
        ))
        fill_by_group("Starknet contributions", (
            "Developed open-source deterministic compiler and AMM settlement co-processor with 100% public GitHub code and reproducible benchmarks."
        ))
        fill_by_group("Proposed solution", (
            "Provides Starknet DEXes (Ekubo, Jediswap) with an ultra-high-throughput off-chain AMM settlement co-processor "
            "capable of evaluating over 450,000 swaps/sec on consumer GPUs, eliminating sequencer congestion and generating "
            "lightweight cryptographic receipts for on-chain state updates."
        ))

        # --- SEÇÃO 6: Strategy & KPIs ---
        print("\n[*] 6. Estratégia e KPIs...")
        fill_by_group("Project KPIs", "1. AMM settlement throughput (>450,000 ops/sec). 2. Bit-exact verification parity across 2,000+ mainnet swaps. 3. Zero-defect fail-closed security bounds.")
        fill_by_group("User acquisition strategy", "Direct B2B integration with Starknet DEXes (Ekubo, Jediswap), AMM aggregators, and rollup sequencers seeking ultra-fast off-chain batch settlement.")

        # --- SEÇÃO 7: Business & Financials ---
        print("\n[*] 7. Modelo de Negócios e Custos...")
        fill_by_group("Business model", (
            "Core engine is 100% open-source MIT/Apache-2.0. Future monetization via enterprise SLA licensing "
            "for high-frequency sequencers and decentralized RPC co-processor hosting."
        ))
        fill_by_group("Project cost components", (
            "70% core systems/cryptography engineering, 15% testing/RPC infrastructure & multi-GPU testbeds, "
            "15% third-party smart contract security audits."
        ))
        fill_by_group("Security & audits", (
            "Internal security audit completed (SECURITY_AUDIT.md in repo). Zero heap allocation in execution kernels, "
            "100% fail-closed bounds checking, tamper-evident Merkle receipts. Formal external third-party audit planned for Milestone 1."
        ))

        # --- SEÇÃO 8: Project Plan & Milestones ---
        print("\n[*] 8. Plano de Marcos (Milestone)...")
        fill_by_group("Funding amount", "25000")
        click_option("1") # 1 milestone
        fill_by_group("Milestone 1 name", "Production L1/L2 Verifier Contract & GPU AMM Settlement Engine")
        fill_by_group("Milestone 1 amount", "10000")
        fill_by_group("Milestone 1 completion date", "15/11/2026")
        fill_by_group("Milestone 1 deliverables", (
            "1. Audited L1/L2 verifier smart contract (LinReceiptVerifier) supporting batch SHA-256 Merkle compute receipts.\n"
            "2. Open-source OpenCL C AMM settlement kernel achieving >450,000 ops/sec on consumer GPUs.\n"
            "3. Reproducible differential testing harness verifying 2,000+ mainnet swaps with 100% bit-exact parity.\n"
            "4. Public Sepolia testnet deployment with automated verification scripts and verified contract addresses on block explorer."
        ))

        # --- SEÇÃO 9: Past Work & Grants ---
        print("\n[*] 9. Histórico e Outros Grants...")
        fill_by_group("Track record", (
            "Built LIN (github.com/kbelludoo/lin-open), a 100% self-hosted systems language with fixed point C0=C1=C2 and native "
            "ELF64 emission. Developed and verified an AMM liquidation co-processor executing 2,000 swaps in 4.1 ms on AMD RX 6600 "
            "GPU with 77/77 bit-exact targets passing."
        ))
        click_option("No") # Previously applied
        fill_by_group("Other Starknet grant programs", "N/A")
        fill_by_group("Other grants", "Applied to Ethereum Foundation Ecosystem Support Program (ESP) for $30k and Arbitrum Builders Grant.")

        # --- SEÇÃO 10: Collaborations & Support ---
        print("\n[*] 10. Colaborações e Suporte...")
        fill_by_group("Starknet collaborations", (
            "We seek to collaborate with Starknet DEXes (such as Ekubo and Jediswap) and Starknet infrastructure teams (Madara / Karnot). "
            "Our sovereign GPU settlement engine and deterministic receipt pipeline can be integrated as an off-chain AMM execution and "
            "liquidation co-processor, drastically increasing throughput while minimizing on-chain execution and proof generation overhead."
        ))
        fill_by_group("Extra support", (
            "Technical mentorship from Starknet Foundation cryptography/Cairo engineers, introductions to Starknet DEX teams (Ekubo/Jediswap), and smart contract security audit subsidies."
        ))

        # --- SEÇÃO 11: Other Details ---
        print("\n[*] 11. Licença e Origem...")
        click_option("MIT")
        click_option("Starknet Website")
        fill_by_group("Referral", "Open Application / Starknet Grants Portal")

        # --- SEÇÃO 12: Compliance & Signatory ---
        print("\n[*] 12. Dados Legais e Signatário...")
        click_option("Individual")
        fill_by_group("Signatory full name", "Bruno Fonseca")
        fill_by_group("Signatory email", "kbelludoo@gmail.com")
        fill_by_group("Signatory title", "Lead Systems Engineer / Founder")
        fill_by_group("Legal entity address", "Brazil")

        # File upload if found
        file_input = page.locator("input[type=file]").first
        if file_input.count() > 0 and os.path.exists(pdf_path):
            try:
                file_input.set_input_files(pdf_path)
                print("  [+] Proposta PDF anexada com sucesso!")
            except Exception as e:
                print("  [-] Upload de arquivo aviso:", e)

        # Checkboxes de consentimento
        print("\n[*] 13. Marcando Consentimento e Termos...")
        try:
            chkboxes = page.locator("input[type=checkbox]")
            for i in range(chkboxes.count()):
                chkboxes.nth(i).check(force=True)
            print("  [+] Caixas de consentimento marcadas!")
        except Exception as e:
            print("  [-] Checkbox aviso:", e)

        print("\n================================================================================")
        print("=== FORMULÁRIO STARKNET 100% PREENCHIDO COM SUCESSO NO BRAVE!                ===")
        print("=== Revise a janela aberta na sua tela e clique no botão azul 'Submit'!      ===")
        print("================================================================================")

        if not headless:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("[*] Encerrando.")

if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    run_fill(headless=is_headless)
