#!/usr/bin/env python3
"""
Gera graficos comparativos das fases M1-A (Mojo), M1-B.1 (LinVM Keccak Core)
e M1-B Completo (Escopo Grant) a partir de docs/m1_phase_comparison.csv.
"""

import csv
import os
import matplotlib.pyplot as plt
import numpy as np

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, "docs", "m1_phase_comparison.csv")
    svg_path = os.path.join(base_dir, "docs", "m1_phase_comparison.svg")
    png_path = os.path.join(base_dir, "docs", "m1_phase_comparison.png")

    labels = []
    m1_a = []
    m1_b1 = []
    m1_b_full = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels.append(row["dimension_label"])
            m1_a.append(float(row["m1_a_mojo"]))
            m1_b1.append(float(row["m1_b1_linvm"]))
            m1_b_full.append(float(row["m1_b_complete_scope"]))

    y = np.arange(len(labels))
    height = 0.25

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    # Cores
    color_m1_a = "#ff7b72"      # Laranja/Rosa (Mojo)
    color_m1_b1 = "#58a6ff"     # Azul vivo (LinVM M1-B.1)
    color_m1_full = "#3fb950"   # Verde (Escopo Grant Financiado)

    r1 = ax.barh(y + height, m1_a, height, label="M1-A: Protótipo Mojo 1.0+ (Entregue)", color=color_m1_a, alpha=0.9, edgecolor="#30363d")
    r2 = ax.barh(y, m1_b1, height, label="M1-B.1 & M1-B.2: Núcleo Keccak & Absorção LinVM (Entregue)", color=color_m1_b1, alpha=0.9, edgecolor="#30363d")
    r3 = ax.barh(y - height, m1_b_full, height, label="M1-B Completo: Escopo Restante do Grant", color=color_m1_full, alpha=0.85, edgecolor="#30363d", linestyle="--")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, color="#c9d1d9", fontsize=10, fontweight="bold")
    ax.set_xticks([0.0, 0.5, 1.0])
    ax.set_xticklabels(["Não Implementado", "Parcial / Em Progresso", "Validado & Integrado"], color="#8b949e", fontsize=9)
    ax.set_xlim(0, 1.15)

    ax.grid(axis="x", color="#30363d", linestyle=":", alpha=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#30363d")
    ax.spines["bottom"].set_color("#30363d")

    ax.tick_params(colors="#8b949e")

    plt.title("Lin-Audit Ethereum — Matriz de Maturidade Técnica M1\n(Mojo 1.0+ vs LinVM M1-B.1 vs Escopo Financiado M1-B)",
              color="#f0f6fc", fontsize=12, fontweight="bold", pad=15)

    ax.legend(facecolor="#161b22", edgecolor="#30363d", labelcolor="#c9d1d9", loc="lower right", fontsize=9)

    plt.tight_layout()
    plt.savefig(png_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.savefig(svg_path, facecolor=fig.get_facecolor(), edgecolor="none")
    print(f"Graficos gerados com sucesso:\n- {png_path}\n- {svg_path}")

if __name__ == "__main__":
    main()
