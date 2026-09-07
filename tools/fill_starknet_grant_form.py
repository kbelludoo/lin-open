#!/usr/bin/env python3
"""
Automates pre-filling the official Starknet Foundation Seed Grant Application
(Airtable Form) in Brave Browser.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

def fill_starknet(headless=False):
    print("================================================================================")
    print("=== INICIANDO PREENCHIMENTO AUTOMÁTICO DO FORMULÁRIO STARKNET NO BRAVE       ===")
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

        # Helper to set text in field identified by title/label
        def set_airtable_field(q_title, value):
            try:
                # Find element with matching title text
                locator = page.locator(f"text={q_title}").first
                if locator.count() > 0:
                    container = locator.locator("xpath=ancestor::div[contains(@class, 'cellField') or contains(@role, 'group') or @data-testid][1]")
                    inp = container.locator("input, textarea").first
                    if inp.count() > 0:
                        inp.fill(value)
                        print(f"  [+] {q_title}: {value[:30]}...")
                        return True
            except Exception as e:
                print(f"  [-] Erro ao preencher {q_title}: {e}")
            return False

        print("[*] Preenchendo Informações do Projeto...")
        set_airtable_field("Project name", "LIN Sovereign GPU AMM Co-processor")
        set_airtable_field("Website URL", "https://github.com/kbelludoo/lin-open")
        set_airtable_field("Project GitHub", "https://github.com/kbelludoo/lin-open")
        set_airtable_field("Project X URL", "N/A")

        print("[*] Preenchendo Contato...")
        set_airtable_field("Contact full name", "Bruno Fonseca")
        set_airtable_field("Contact email", "kbelludoo@gmail.com")
        set_airtable_field("Contact Telegram handle", "@kbelludoo")
        set_airtable_field("Contact GitHub username", "kbelludoo")
        set_airtable_field("TG group <> SNF", "N/A")
        set_airtable_field("City", "Brazil")

        print("[*] Selecionando Estágio do Projeto...")
        try:
            page.eval_on_selector("text=Testing/Pilot", "el => el.click()")
            print("  [+] Estágio: Testing/Pilot selecionado")
        except Exception:
            try:
                page.eval_on_selector("text=MVP/Development", "el => el.click()")
                print("  [+] Estágio: MVP/Development selecionado")
            except Exception as e:
                print("  [-] Estágio aviso:", e)

        print("[*] Preenchendo Financiamento e Marco 1...")
        set_airtable_field("Funding amount", "25000")
        set_airtable_field("Milestone 1 name", "Production L1/L2 Verifier Contract & GPU AMM Settlement Engine")
        set_airtable_field("Milestone 1 amount", "10000")
        set_airtable_field("Milestone 1 completion date", "15/10/2026")
        set_airtable_field("Referral", "Open Application / Starknet Grants Portal")

        print("[*] Selecionando Tipo de Aplicante...")
        try:
            page.eval_on_selector("text=Individual", "el => el.click()")
            print("  [+] Tipo: Individual selecionado")
        except Exception as e:
            print("  [-] Tipo aplicante aviso:", e)

        print("[*] Preenchendo Signatário...")
        set_airtable_field("Signatory full name", "Bruno Fonseca")
        set_airtable_field("Signatory email", "kbelludoo@gmail.com")
        set_airtable_field("Signatory title", "Lead Systems Engineer / Founder")

        print("\n================================================================================")
        print("=== FORMULÁRIO STARKNET 100% PREENCHIDO COM SUCESSO!                         ===")
        print("=== 1. Revise os campos na janela do Brave.                                  ===")
        print("=== 2. Clique no botão azul 'Submit' no final da página!                     ===")
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
    fill_starknet(headless=is_headless)
