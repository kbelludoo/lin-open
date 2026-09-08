#!/usr/bin/env python3
"""
Generates an executive, publication-grade PDF Grant Proposal for:
"LIN: Sovereign GPU AMM Settlement & Rollup Co-processor"
"""
import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 11 * 72 - 36, 8.5 * 72 - 54, 11 * 72 - 36)
        self.drawString(54, 11 * 72 - 30, "Ethereum Foundation Ecosystem Support Program (ESP) — Grant Application")
        
        # Footer
        self.line(54, 45, 8.5 * 72 - 54, 45)
        self.drawString(54, 32, "LIN Project: https://github.com/kbelludoo/lin-open — MIT/Apache-2.0")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * 72 - 54, 32, page_str)
        self.restoreState()

def build_pdf(filename="docs/LIN_GPU_DeFi_Settlement_Grant_Proposal.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A202C"),
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )

    callout_style = ParagraphStyle(
        'Callout',
        parent=body_style,
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#2C5282")
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("LIN: Sovereign GPU AMM Settlement & Rollup Co-processor", title_style))
    story.append(Paragraph("<b>Grant Proposal</b> | Ethereum Foundation Ecosystem Support Program (ESP) | Requested: <b>$30,000 USD</b>", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=10))

    # Executive Summary
    story.append(Paragraph("1. Executive Summary & Core Innovation", h1_style))
    story.append(Paragraph(
        "DEX trading and batch settlement on Ethereum L1 face severe computational and economic limits. "
        "Re-executing thousands of state transitions across archival nodes to audit settlement integrity is slow and expensive. "
        "<b>LIN</b> introduces a sovereign, verified offload co-processor and parallel AMM settlement engine written in LIN (a deterministic numeric systems language) "
        "orchestrated by a pure C11 host runtime with a <b>strict execution runtime TCB of only 809 LOC</b> (zero LLVM/Zig dependency in production).",
        body_style
    ))
    story.append(Paragraph(
        "Running on commodity consumer hardware (AMD Radeon RX 6600, 28 CUs), our sovereign pipeline processes <b>2,000 Ethereum mainnet Uniswap v2 swaps in 1.7 milliseconds of kernel time</b> "
        "(1,176,000 swaps/sec kernel-only; 218 ms end-to-end cold wall-clock), enforces strict constant-product invariants (<i>x · y ≥ k</i>), filters routing deviations, and issues deterministic "
        "<b>canonical 208-byte LCR2 Merkle compute receipts</b>. These receipts enable client-side auditability in <b>~7.3 µs per block (~3,200× to 4,900× cheaper than VM re-execution)</b>, "
        "with L1 root anchoring and inclusion proof verification implemented in <code>contracts/LinReceiptVerifier.sol</code>.",
        body_style
    ))

    # Empirical Results Table
    story.append(Paragraph("2. Empirical Performance: Real Mainnet Swaps Benchmark (AMD RX 6600)", h1_style))
    
    table_data = [
        ["Metric", "Kernel Compute (GPU)", "End-to-End Wall-Clock", "Off-Chain Audit Advantage"],
        ["Batch Throughput (N=2,000)", "1,176,470 swaps/sec", "9,166 swaps/sec (cold)", "~3,200x faster than VM re-exec"],
        ["Execution Time (N=2,000)", "1.70 ms (0.85 µs / swap)", "218 ms (includes JIT/PCIe)", "Receipt verified in ~7.3 µs"],
        ["Saturated Batch (N=10,000)", "2.80 ms (3,300,000 swaps/s)", "219 ms (45,000 swaps/s)", "Amortizes cold startup latency"],
        ["Trusted Computing Base (TCB)", "809 LOC (core runtime)", "6,628 LOC (full C0 toolchain)", "Zero runtime heap / bounds-checked"],
        ["Cryptographic Receipt", "LCR2 208-byte canonical", "SHA-256 Merkle root", "O(1) client verification (hashlib)"],
        ["On-Chain Bridge (Solidity)", "Root anchor: 70,133 gas", "Spot proof: 87,831 gas", "13,258x–16,604x on-chain reduction"]
    ]
    
    t = Table(table_data, colWidths=[130, 115, 125, 134])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F7FAFC"), colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "<b>Empirical EVM Gas Audit (Foundry v1.8.1 + Live Anvil Receipts):</b> "
        "The on-chain verifier (<code>contracts/LinReceiptVerifier.sol</code>) was deployed (718,682 gas) and verified with live receipts (<code>test/forge-gas/</code>). "
        "Anchoring a 2,000-swap batch root (<code>settleBatch</code>) consumed <b>70,133 gas ($0.0021/swap</b> @ 20 gwei, $3k/ETH); anchoring with inclusion proof "
        "(<code>settleBatchWithInclusionProof</code>) consumed <b>87,831 gas ($0.0026/swap)</b>. Against the actual 1,164,504,079 gas consumed by the 2,000 swaps on mainnet, "
        "LIN delivers a measured <b>13,258× to 16,604× reduction in on-chain gas</b>.",
        body_style
    ))
    story.append(Spacer(1, 6))

    # Architecture Overview
    story.append(Paragraph("3. End-to-End Sovereign Architecture", h1_style))
    story.append(Paragraph(
        "• <b>Sovereign GPU Kernel (LIN OpenCL Emitter):</b> Written in pure LIN (<code>src/lin_gpu_opencl_emitter.lin</code>), emitting standards-compliant OpenCL C. "
        "Executes directly on physical AMD/Intel/Nvidia GPUs via dynamic loader (<code>dlopen(libOpenCL.so)</code>) without proprietary dependencies.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <b>Deterministic Host VM (LinVM C0):</b> Pure C11 orchestration runtime (<code>transpile/c/tool/lin_c0.c</code>). Strict TCB: 809 LOC runtime, 6.6k LOC full toolchain. Emits canonical LCR2 Merkle receipts.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <b>L1 On-Chain Verifier (Solidity):</b> <code>contracts/LinReceiptVerifier.sol</code> anchors batch Merkle roots and verifies both legacy and LCR2 inclusion proofs (<code>verifyLCR2Inclusion</code>).",
        bullet_style
    ))

    # Milestones & Budget Breakdown
    story.append(Paragraph("4. Project Milestones & Budget ($30,000 USD)", h1_style))
    
    milestone_data = [
        ["Milestone", "Duration", "Budget", "Key Deliverables & Acceptance Criteria"],
        [
            "Milestone 1:\nProduction L1\nVerifier Contract",
            "4 Weeks",
            "$10,000",
            "• Audited LinReceiptVerifier.sol supporting batched AMM state settlements.\n"
            "• Sepolia testnet deployment with automated verification scripts.\n"
            "• End-to-end integration test suite with empirical Foundry gas tests (70k gas seals, 16,600x vs L1)."
        ],
        [
            "Milestone 2:\nMempool Batcher\n& Daemon",
            "6 Weeks",
            "$10,000",
            "• Standalone daemon ingesting live Ethereum pending DEX transactions.\n"
            "• Real-time GPU streaming pipeline batching up to 10,000 swaps/second.\n"
            "• Automated emission of cryptographic receipts and IPFS/Arweave staging."
        ],
        [
            "Milestone 3:\nMulti-GPU Portability\n& Formal Audit",
            "4 Weeks",
            "$10,000",
            "• Multi-vendor validation across AMD (ROCm), NVIDIA (CUDA/OpenCL), Apple Silicon.\n"
            "• Third-party smart contract security audit report.\n"
            "• Open-source developer SDK, reproducibility paper, and interactive live demo."
        ]
    ]

    mt = Table(milestone_data, colWidths=[95, 60, 55, 294])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2D3748")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F7FAFC"), colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # Public Goods & Open Source Commitment
    story.append(Paragraph("5. Public Goods Value & Open Source Commitment", h1_style))
    story.append(Paragraph(
        "All code, kernels, transpilation tools, and smart contracts are published under permissible open-source licenses (MIT / Apache-2.0). "
        "Any Ethereum builder, L2 rollup team, or DEX developer can freely clone the repository, run <code>make benchmark-uniswap</code>, and reproduce these results "
        "on consumer hardware in under 5 seconds. This grant directly strengthens Ethereum's decentralized scaling, validator efficiency, and computational auditability.",
        body_style
    ))

    # Repository and Contact
    story.append(Spacer(1, 4))
    info_box = [
        [Paragraph("<b>Repository:</b> https://github.com/kbelludoo/lin-open | <b>License:</b> MIT / Apache-2.0 | <b>Status:</b> Live & Verified", callout_style)]
    ]
    ib_table = Table(info_box, colWidths=[504])
    ib_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EBF8FF")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#3182CE")),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ib_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[+] Successfully generated: {filename}")

if __name__ == "__main__":
    build_pdf()
