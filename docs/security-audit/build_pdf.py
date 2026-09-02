#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Montagem do PDF do relatorio de auditoria (usado por gen_report.py).

Mantem a apresentacao separada dos dados: altere FINDINGS em gen_report.py e
rode `python docs/security-audit/gen_report.py` de novo.
"""
import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, Image,
                                KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

# ---------------------------------------------------------------------------
# pt-BR: o conteudo e escrito sem acentos (para sobreviver a qualquer fonte);
# na renderizacao registramos DejaVu, entao as formas acentuadas sao aplicadas
# aqui, somente na prosa -- nunca em codigo, caminhos de arquivo ou nas issues.
# ---------------------------------------------------------------------------
_ACCENT = {}
for _a, _b in [
    ("Seguranca", "Segurança"), ("seguranca", "segurança"),
    ("Relatorio", "Relatório"), ("relatorio", "relatório"),
    ("Metodologica", "Metodológica"), ("metodologica", "metodológica"),
    ("Criterios", "Critérios"), ("criterios", "critérios"),
    ("Evidencia", "Evidência"), ("evidencia", "evidência"),
    ("Condicoes", "Condições"), ("condicoes", "condições"),
    ("Exploravel", "Explorável"), ("exploravel", "explorável"),
    ("Verificacao", "Verificação"), ("verificacao", "verificação"),
    ("Verificacoes", "Verificações"), ("verificacoes", "verificações"),
    ("verificador", "verificador"),
    ("Confianca", "Confiança"), ("confianca", "confiança"),
    ("Ancora", "Âncora"), ("ancora", "âncora"),
    ("CRITICA", "CRÍTICA"), ("critica", "crítica"), ("Critica", "Crítica"),
    ("critico", "crítico"), ("criticos", "críticos"),
    ("MEDIA", "MÉDIA"), ("media", "média"), ("Media", "Média"),
    ("padrao", "padrão"), ("Padrao", "Padrão"), ("padroes", "padrões"),
    ("historico", "histórico"), ("Historico", "Histórico"),
    ("unico", "único"), ("unica", "única"), ("Unico", "Único"), ("Unica", "Única"),
    ("numero", "número"), ("Numero", "Número"),
    ("pagina", "página"), ("Pagina", "Página"),
    ("codigo", "código"), ("Codigo", "Código"),
    ("nivel", "nível"), (" Nivel", "Nível"),
    ("publico", "público"), ("publica", "pública"),
    ("proprio", "próprio"), ("propria", "própria"),
    ("ultimo", "último"), ("ultima", "última"),
    ("serie", "série"), ("grafico", "gráfico"), ("graficos", "gráficos"),
    ("execucao", "execução"), ("Execucao", "Execução"),
    ("aplicavel", "aplicável"),
    ("nao", "não"), ("Nao", "Não"),
    ("analog", "análogo"), ("analogo", "analógico"),
    ("saida", "saída"), ("saidas", "saídas"),
    ("situacao", "situação"), ("relacao", "relação"),
    ("Sequencia", "Sequência"), ("sequencia", "sequência"),
    ("Rotulos", "Rótulos"), ("rotulo", "rótulo"), ("rotulos", "rótulos"),
    ("Introducao", "Introdução"), ("regra", "regra"),
    ("adicional", "adicional"), ("Relatorio.", "Relatório."),
]:
    _ACCENT[_a] = _b
for _a, _b in [
    ("Acao", "Ação"), ("acao", "ação"), ("acoes", "ações"), ("Acoes", "Ações"),
    ("alegacao", "alegação"), ("Alegacao", "Alegação"), ("alegoes", "alegações"),
    ("adulteracao", "adulteração"), ("aplicacao", "aplicação"),
    ("atestacao", "atestação"), ("comparacao", "comparação"),
    ("conclusao", "conclusão"), ("condicao", "condição"), ("condicoes", "condições"),
    ("confirmacao", "confirmação"), ("correcao", "correção"), ("Correcao", "Correção"),
    ("decisao", "decisão"), ("documentacao", "documentação"),
    ("duplicacao", "duplicação"), ("edicao", "edição"), ("execucao", "execução"),
    ("Execucao", "Execução"), ("funcao", "função"), ("geracao", "geração"),
    ("historico", "histórico"), ("Historico", "Histórico"),
    ("implementacao", "implementação"), ("implementacoes", "implementações"),
    ("injecao", "injeção"), ("inspecao", "inspeção"), ("instrucoes", "instruções"),
    ("logica", "lógica"), ("mecanica", "mecânica"), ("mitigacao", "mitigação"),
    ("obrigatoria", "obrigatória"), ("obrigatorias", "obrigatórias"),
    ("obrigatorio", "obrigatório"), ("obrigatorios", "obrigatórios"),
    ("permissao", "permissão"), ("posicao", "posição"), ("pratica", "prática"),
    ("publicacao", "publicação"), ("re-execucao", "re-execução"),
    ("renderizacao", "renderização"), ("resolucao", "resolução"), ("revisao", "revisão"),
    ("revogacao", "revogação"), ("rotulo", "rótulo"), ("secao", "seção"),
    ("Secao", "Seção"), ("secoes", "seções"), ("sensacao", "sensação"),
    ("sessao", "sessão"), ("validacao", "validação"), ("Validacao", "Validação"),
    ("sao", "são"), ("Sao", "São"), ("tambem", "também"), ("alem", "além"),
    ("ate", "até"), ("ja", "já"), ("voce", "você"), ("apesar", "apesar"),
    ("Repita", "Repita"), ("emitida", "emitida"),
]:
    _ACCENT[_a] = _b
for _a, _b in [
    ("Recomendacoes", "Recomenda\u00e7\u00f5es"), ("recomendacoes", "recomenda\u00e7\u00f5es"),
    ("recomendacao", "recomenda\u00e7\u00e3o"),
    ("Documentacao", "Documenta\u00e7\u00e3o"), ("documentacao", "documenta\u00e7\u00e3o"),
    ("Condicoes", "Condi\u00e7\u00f5es"), ("Correcao", "Corre\u00e7\u00e3o"),
    ("Acao", "A\u00e7\u00e3o"), ("Como", "Como"), ("Onde", "Onde"), ("Achados", "Achados"),
    ("Impacto", "Impacto"),
]:
    _ACCENT[_a] = _b
_KEYS = sorted(_ACCENT, key=len, reverse=True)
_ACRE = re.compile(r"(?<![A-Za-z0-9_/\-.])(" + "|".join(re.escape(k) for k in _KEYS) + r")(?![A-Za-z0-9])")


def pt(text):
    """Formas acentuadas do pt-BR em prosa ja escapada (nao toca codigo/caminhos)."""
    return _ACRE.sub(lambda m: _ACCENT[m.group(1)], text)

MARGIN = 2.0 * cm
PAGE_W, PAGE_H = A4
BODY_W = PAGE_W - 2 * MARGIN

DEJA = "/usr/share/fonts/truetype/dejavu"
FONT, FONT_B, FONT_M = "DejaVu", "DejaVu-Bold", "DejaVuMono"


def _fonts():
    try:
        pdfmetrics.registerFont(TTFont(FONT, os.path.join(DEJA, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_B, os.path.join(DEJA, "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_M, os.path.join(DEJA, "DejaVuSansMono.ttf")))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_B, italic=FONT, boldItalic=FONT_B)
        return True
    except Exception:
        return False


def styles():
    ss = getSampleStyleSheet()
    mono_ok = _fonts()
    f = FONT if mono_ok else "Helvetica"
    fb = FONT_B if mono_ok else "Helvetica-Bold"
    fm = FONT_M if mono_ok else "Courier"
    st = {}
    st["cover_t"] = ParagraphStyle("cover_t", fontName=fb, fontSize=23, leading=28,
                                   textColor=colors.HexColor("#111827"), alignment=TA_CENTER)
    st["cover_s"] = ParagraphStyle("cover_s", fontName=f, fontSize=12, leading=16,
                                   textColor=colors.HexColor("#374151"), alignment=TA_CENTER)
    st["cover_m"] = ParagraphStyle("cover_m", fontName=fm, fontSize=8.5, leading=12,
                                   textColor=colors.HexColor("#6B7280"), alignment=TA_CENTER)
    st["h1"] = ParagraphStyle("h1", fontName=fb, fontSize=15.5, leading=19,
                              textColor=colors.HexColor("#111827"), spaceBefore=6, spaceAfter=7)
    st["h2"] = ParagraphStyle("h2", fontName=fb, fontSize=11.6, leading=15,
                              textColor=colors.HexColor("#B91C1C"), spaceBefore=8, spaceAfter=4)
    st["h3"] = ParagraphStyle("h3", fontName=fb, fontSize=10.2, leading=13.5,
                              textColor=colors.HexColor("#111827"), spaceBefore=6, spaceAfter=3)
    st["p"] = ParagraphStyle("p", fontName=f, fontSize=8.9, leading=12.4,
                             textColor=colors.HexColor("#1F2937"), alignment=TA_JUSTIFY,
                             spaceAfter=4)
    st["small"] = ParagraphStyle("small", fontName=f, fontSize=8.0, leading=11.0,
                                 textColor=colors.HexColor("#374151"), alignment=TA_JUSTIFY)
    st["li"] = ParagraphStyle("li", parent=st["p"], leftIndent=9, bulletIndent=1, spaceAfter=2.5)
    st["mono"] = ParagraphStyle("mono", fontName=fm, fontSize=6.9, leading=9.0,
                                textColor=colors.HexColor("#111827"))
    st["cell"] = ParagraphStyle("cell", fontName=f, fontSize=8.0, leading=10.6,
                                textColor=colors.HexColor("#1F2937"))
    st["cellm"] = ParagraphStyle("cellm", fontName=fm, fontSize=6.9, leading=9.2,
                                 textColor=colors.HexColor("#374151"))
    st["chip"] = ParagraphStyle("chip", fontName=fb, fontSize=6.6, leading=8.2,
                                textColor=colors.white, alignment=TA_CENTER)
    st["iss"] = ParagraphStyle("iss", fontName=fm, fontSize=6.6, leading=8.6,
                               textColor=colors.HexColor("#111827"))
    return st


class NumberedCanvas:
    """Canvas que desenha cabecalho e rodape em toda pagina (menos a capa)."""

    @staticmethod
    def factory(title):
        from reportlab.pdfgen import canvas as _canvas

        class _C(_canvas.Canvas):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self._saved = []

            def showPage(self):
                self._saved.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._saved)
                for state in self._saved:
                    self.__dict__.update(state)
                    if self._pageNumber > 1:
                        self._decorate(total, title)
                    super().showPage()
                super().save()

            def _decorate(self, total, title):
                self.saveState()
                self.setFont(FONT if FONT in pdfmetrics.getRegisteredFontNames() else "Helvetica", 6.8)
                self.setFillColor(colors.HexColor("#9CA3AF"))
                self.drawString(MARGIN, PAGE_H - MARGIN + 0.55 * cm, title)
                self.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 0.55 * cm,
                                     "confidencial / uso interno")
                self.setStrokeColor(colors.HexColor("#E5E7EB"))
                self.setLineWidth(0.5)
                self.line(MARGIN, PAGE_H - MARGIN + 0.4 * cm, PAGE_W - MARGIN, PAGE_H - MARGIN + 0.4 * cm)
                self.line(MARGIN, MARGIN - 0.42 * cm, PAGE_W - MARGIN, MARGIN - 0.42 * cm)
                self.drawCentredString(PAGE_W / 2.0, MARGIN - 0.85 * cm,
                                       "pagina %d de %d" % (self._pageNumber, total))
                self.restoreState()
        return _C


def chip(text, color_hex, st):
    t = Table([[Paragraph(text, st["chip"])]], colWidths=[2.25 * cm], rowHeights=[0.42 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color_hex)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t


def kv_box(rows, st, width=None, bg="#F9FAFB"):
    width = width or BODY_W
    data = [[Paragraph(pt(k), st["cell"]), Paragraph(v, st["cell"])] for k, v in rows]
    t = Table(data, colWidths=[width * 0.19, width * 0.81])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E5E7EB")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def code_block(text, st):
    lines = [l for l in text.rstrip("\n").split("\n")]
    body = "<br/>".join(l.replace(" ", "&nbsp;") if l.strip() else "&nbsp;" for l in lines)
    t = Table([[Paragraph(body, st["mono"])]], colWidths=[BODY_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, colors.HexColor("#B91C1C")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build(out_path, here, FINDINGS, STRENGTHS, WEAKNESSES, RECS, CATS, CAT_SHORT,
          SEV_COLORS, SEV_LABEL, REPORT_TITLE, PROJECT, DATE, make_issue, charts, wrap, esc):
    import html as _html
    st = styles()

    # a prosa dos achados recebe as formas acentuadas uma unica vez (aqui), para
    # que tabelas, detalhe do achado e o texto da issue fiquem consistentes; o
    # bloco de evidencia (codigo) e os caminhos permanecem crus.
    for _f in FINDINGS:
        for _k in ("title", "why", "exp", "impact", "fix"):
            _f[_k] = pt(_f[_k])
        _f["accept"] = [pt(x) for x in _f["accept"]]
    doc = BaseDocTemplate(out_path, pagesize=A4,
                          leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=MARGIN, bottomMargin=MARGIN,
                          title=REPORT_TITLE, author="auditoria de seguranca (Arena agent)",
                          subject="LIN / lin-open")
    frame = Frame(MARGIN, MARGIN, BODY_W, PAGE_H - 2 * MARGIN, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    cover_frame = Frame(MARGIN, MARGIN, BODY_W, PAGE_H - 2 * MARGIN, id="cover",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[cover_frame]),
                          PageTemplate(id="main", frames=[frame])])

    donut, bars = charts(here)
    S = []
    P = lambda t, s="p": Paragraph(pt(t), st[s])

    # ---------- capa ----------
    S += [Spacer(1, 2.1 * cm)]
    band = Table([[P("<font color='white'><b>AUDITORIA DE SEGURANCA</b></font>", "cover_t")]],
                 colWidths=[BODY_W], rowHeights=[0.95 * cm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#111827")),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    S += [band, Spacer(1, 0.9 * cm), P(REPORT_TITLE, "cover_t"), Spacer(1, 0.35 * cm),
          P(PROJECT, "cover_s"), Spacer(1, 0.2 * cm),
          P("Data: <b>%s</b>" % DATE, "cover_s"), Spacer(1, 1.15 * cm)]
    S += [kv_box([
        ("Escopo",
         "Arvore de trabalho do repositorio no commit <font face='DejaVuMono'>fe4a10b</font> "
         "(branch <font face='DejaVuMono'>arena/01a05f60-lin-open</font>, PR #55) e seu historico git "
         "completo (7 commits). Superficies auditadas: <font face='DejaVuMono'>compiler/</font> "
         "(Zig 0.13.0, Stage0, 19 023 linhas), <font face='DejaVuMono'>transpile/c/</font> (host C11: "
         "runtime de confianca <font face='DejaVuMono'>lin_c/</font> + ferramentas "
         "<font face='DejaVuMono'>tool/</font>), <font face='DejaVuMono'>src/*.lin</font> (44 arquivos, "
         "incluindo o front-end escrito em LIN de #46), <font face='DejaVuMono'>test/</font> "
         "(verificadores bash/python), <font face='DejaVuMono'>.github/</font> (CI), "
         "<font face='DejaVuMono'>benchmarks/verify_receipt.{html,js}</font> (unica superificie de "
         "navegador do repo), <font face='DejaVuMono'>docs/</font> e "
         "<font face='DejaVuMono'>redteam/</font> (prior art)."),
        ("Fora de escopo",
         "Prova formal do parser/typechecker inteiro (19k linhas lidas por amostragem dirigida), "
         "binarios publicados (nenhum neste ambiente), e o comportamento do runtime OpenCL real "
         "(ja coberto por <font face='DejaVuMono'>SECURITY_AUDIT.md</font> + "
         "<font face='DejaVuMono'>redteam/fake_ocl.c</font>, referenciado como prior art)."),
        ("Ambiente dos testes",
         "Zig 0.13.0 real obtido via wheel <font face='DejaVuMono'>ziglang==0.13.0</font> em venv "
         "isolado; Stage0 construido com <font face='DejaVuMono'>zig build -Dgpu=false "
         "-Doptimize=ReleaseFast</font>; host C11 (<font face='DejaVuMono'>lin_c0</font>, "
         "<font face='DejaVuMono'>lin_bc1_run</font>, <font face='DejaVuMono'>lin_c_receipt</font>) "
         "construido com <font face='DejaVuMono'>cc</font>. As duas implementacoes foram exercitadas "
         "nos mesmos vetores (ver 'Validacao nas duas versoes')."),
    ], st), Spacer(1, 0.75 * cm)]
    S += [P("<b>Nota metodologica - como cada categoria foi mapeada para esta stack</b>", "h3"),
          code_block(
              "Projeto sem banco, sem ORM, sem framework web, sem sessao/usuario e sem multi-tenancy:\n"
              "as cinco categorias classicas foram traduzidas para os equivalentes desta stack.\n"
              "\n"
              "  1. BANCO SEM TRANCA (isolamento de tenant)  ->  ANCORA DE CONFIANCA / ESCOPO DA\n"
              "     VERIFICACAO: em um verificador de integridade, o equivalente de 'filtrar por\n"
              "     tenant' e resolver a identidade/confianca a partir de algo que NAO esta no\n"
              "     objeto verificado. Auditado em: attest-verify, notary-verify, bundle/cert verify,\n"
              "     gate-check/verify_gate_manifest.py, escopo do Merkle root vs arquivos reais.\n"
              "  2. PERMISSAO DEFINIDA NO NAVEGADOR          ->  DECISAO DE CONFIANCA DO LADO ERRADO:\n"
              "     a pagina benchmarks/verify_receipt.html (e o .js) decidem 'verificado' no\n"
              "     cliente; e o gate cuja verificacao de assinatura e opcional e re-atestando por\n"
              "     quem adulterou.\n"
              "  3. IDOR (objeto por ID sem checar posse)    ->  REFERENCIA NAO VALIDADA: indices e\n"
              "     comprimentos vindos de dados nao confiaveis (secoes/opcode/call/local da imagem\n"
              "     LINBC1), nomes resolvidos por comprimento, e caminhos de arquivo escritos/executados\n"
              "     sem validacao (src/lin.zig, .lin_ast_check.zig, LIN_ZIG).\n"
              "  4. CHAVES EXPOSTAS                          ->  aplicada literalmente: seeds/keys\n"
              "     Ed25519, defaults publicos que viram segredo real (authority.key, seed_prefix),\n"
              "     ausencia de validacao de startup, tokens/acoes na CI, historico git, bundle do\n"
              "     frontend.\n"
              "  5. XSS / INPUT SEM TRATAMENTO               ->  renderizacao nao-escapada na unica\n"
              "     pagina HTML (nenhuma encontrada: so textContent), injecao no codigo Zig gerado a\n"
              "     partir de input LIN, seguranca de memoria no parsing de bytes hostis em C11, e\n"
              "     higiene de shell/python (shell=True, quoting, /tmp previsivel).", st),
          Spacer(1, 0.5 * cm),
          P("Ferramentas: leitura dirigida + grep padrao por categoria, e execucao de PoCs (forja de "
            "roster, forja de receipt, adulteracao de compilador + re-atestateo, imagens LINBC1 "
            "mutadas, nomes com prefixo comum, nesting profundo) nos dois hosts. Nada foi reportado "
            "sem estar verificado no codigo ou medido; o que nao se aplica esta dito como tal.", "small")]
    S += [NextPageTemplate("main"), PageBreak()]

    # ---------- resumo executivo ----------
    sev_count = {}
    for f in FINDINGS:
        sev_count[f["sev"]] = sev_count.get(f["sev"], 0) + 1
    S += [P("1. Resumo executivo", "h1"),
          P("A auditoria encontrou <b>%d achados</b>: <b>%d criticos</b>, <b>%d altos</b>, <b>%d "
            "medios</b>, <b>%d baixos</b> e <b>%d informativos</b>. O padrao dominante nao e um bug de "
            "implementacao e sim a <b>ausencia de ancora de confianca</b>: os quatro mecanismos que o "
            "projeto apresenta como prova (atestado, certificado, quorum de testemunhas e receipt) "
            "verificam dados auto-declarados, e a pagina que 'verifica' o receipt decide isso no "
            "navegador. Em contrapartida, a maquina de baixo - o loader LINBC1 e a LinVM C11 - mostrou-se "
            "rigorosa e fail-closed em todos os testes hostis que rodamos, incluindo os dois "
            "verificadores independentes e o verificador Zig."
            % (len(FINDINGS), sev_count.get("critica", 0), sev_count.get("alta", 0),
               sev_count.get("media", 0), sev_count.get("baixa", 0), sev_count.get("informativa", 0)), "p")]
    charts_tbl = Table([[Image(donut, width=7.3 * cm, height=7.3 * cm * 2.9 / 4.4, kind="proportional"),
                         Image(bars, width=8.4 * cm, height=8.4 * cm * 2.7 / 6.6, kind="proportional")]],
                       colWidths=[BODY_W * 0.46, BODY_W * 0.54])
    charts_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    S += [charts_tbl, Spacer(1, 0.25 * cm)]

    hstyle = ParagraphStyle("hh", parent=st["cell"], textColor=colors.white, fontName=st["mono"].fontName)
    rows = [[Paragraph("Sev.", hstyle), Paragraph("ID", hstyle), Paragraph("Achado", hstyle),
             Paragraph("Onde", hstyle), Paragraph("Cat", hstyle)]]
    for f in FINDINGS:
        rows.append([chip(pt(SEV_LABEL[f["sev"]]), SEV_COLORS[f["sev"]], st),
                     Paragraph(f["id"], st["cell"]),
                     Paragraph(pt(_html.escape(f["title"])), st["cell"]),
                     Paragraph(_html.escape(f["files"].split(",")[0]), st["cellm"]),
                     Paragraph(f["cat"], st["cell"])])
    t = Table(rows, colWidths=[2.35 * cm, 1.15 * cm, BODY_W - 8.75 * cm, 4.35 * cm, 0.9 * cm],
              repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E5E7EB")),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    for i, f in enumerate(FINDINGS, start=1):
        style.append(("BACKGROUND", (1, i), (-1, i),
                      colors.HexColor("#FFFFFF") if i % 2 else colors.HexColor("#F9FAFB")))
        style.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(SEV_COLORS[f["sev"]])))
    t.setStyle(TableStyle(style))
    S += [P("Tabela de achados (indice)", "h3"), t, Spacer(1, 0.2 * cm)]

    S += [P("Validacao nas duas versoes (Zig Stage0 x LinVM/C11)", "h3"),
          P("Todos os vetores relevantes foram executados nas duas implementacoes. Concordancia nos "
            "goldens funcionais (<font face='DejaVuMono'>vms_gate</font> = value 1 em 8 511 500 passos "
            "em ambos; <font face='DejaVuMono'>lex_gate</font>, "
            "<font face='DejaVuMono'>lex_scan_embedded</font> e as rotas 'fonte' e 'imagem' identicas) "
            "e <b>divergencia apenas nos limites</b>: o host C11 recusa "
            "<font face='DejaVuMono'>C0_LIMIT_TOO_MANY_TOKENS</font> onde o Zig aceita 60 000 "
            "parenteses aninhados (fail-closed, correto). Os achados F-01, F-02, F-06 e F-07 sao de "
            "rota Zig (o host C11 nao implementa atestacao/quorum); F-03 e F-10 aparecem nos dois; "
            "F-04/F-05/F-08/F-09 sao de repositorio/CI.", "small")]

    # ---------- pontos fortes / fracos ----------
    S += [PageBreak(), P("2. Pontos fortes verificados (o que esta protegido)", "h1")]
    for title, body in STRENGTHS:
        S += [KeepTogether([P("<font color='#059669'>[OK]</font> " + _html.escape(title), "h3"),
                            P(body, "small"), Spacer(1, 0.08 * cm)])]
    S += [Spacer(1, 0.2 * cm), P("3. Riscos centrais", "h1")]
    for title, body in WEAKNESSES:
        S += [KeepTogether([P("<font color='#B91C1C'>[!]</font> " + _html.escape(title), "h3"),
                            P(body, "small"), Spacer(1, 0.08 * cm)])]

    # ---------- achados detalhados por categoria ----------
    S += [PageBreak(), P("4. Achados detalhados por categoria", "h1"),
          P("Cada achado traz severidade, arquivo:linha, trecho de evidência, o motivo pelo qual é "
            "explorável, condições de explorabilidade, impacto e correção sugerida. As linhas foram "
            "confirmadas no código do commit auditado.", "small"), Spacer(1, 0.1 * cm)]
    for code, label in CATS:
        items = [f for f in FINDINGS if f["cat"] == code]
        S += [P("4.%d  %s" % (CATS.index((code, label)) + 1, label), "h2")]
        if not items:
            S += [P("Nenhum achado nesta categoria.", "small"), Spacer(1, 0.15 * cm)]
            continue
        for f in items:
            blk = [Table([[chip(pt(SEV_LABEL[f["sev"]]), SEV_COLORS[f["sev"]], st),
                           P("<b>%s</b> - %s" % (f["id"], _html.escape(f["title"])), "cell")]],
                         colWidths=[2.65 * cm, BODY_W - 2.65 * cm],
                         style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
                                           ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                                           ("LEFTPADDING", (0, 0), (-1, -1), 5),
                                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])),
                         Spacer(1, 0.06 * cm),
                         kv_box([("Arquivo:linha", _html.escape(f["files"]))], st,
                                bg="#FEF2F2"),
                         P("Evidencia", "h3"), code_block(f["evidence"], st),
                         kv_box([("Por que é explorável", pt(_html.escape(f["why"]))),
                                 ("Condicoes de explorabilidade", pt(_html.escape(f["exp"]))),
                                 ("Impacto", pt(_html.escape(f["impact"]))),
                                 ("Correcao sugerida", pt(_html.escape(f["fix"])))], st),
                         P("Criterios de aceite", "h3")]
            for c in f["accept"]:
                blk.append(P("<font color='#059669'>[ ]</font> " + _html.escape(c), "li"))
            blk.append(Spacer(1, 0.28 * cm))
            S += blk

    # ---------- recomendacoes ----------
    S += [PageBreak(), P("5. Recomendacoes priorizadas", "h1")]
    rows = [[Paragraph("P", st["chip"]), Paragraph(pt("Acao"), st["chip"]),
             Paragraph("Como", st["chip"]), Paragraph(pt("Achados"), st["chip"])]]
    for p, title, how in RECS:
        rows.append([Paragraph("<b>%s</b>" % p, st["cell"]), Paragraph(pt(_html.escape(title)), st["cell"]),
                     Paragraph(pt(_html.escape(how)), st["cell"]), Paragraph("", st["cell"])])
    mapping = {"P1": "F-01, F-02, F-03, F-04, F-06", "P2": "F-05, F-07", "P3": "F-08, F-09, F-10, F-11"}
    for i, (p, _, _) in enumerate(RECS, start=1):
        rows[i][3] = Paragraph(mapping.get(p, ""), st["cellm"])
    t = Table(rows, colWidths=[0.85 * cm, 5.5 * cm, BODY_W - 9.05 * cm, 2.7 * cm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E5E7EB")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                           ("BACKGROUND", (0, 1), (0, 3), colors.HexColor("#B91C1C")),
                           ("TEXTCOLOR", (0, 1), (0, 3), colors.white),
                           ("BACKGROUND", (0, 4), (0, 5), colors.HexColor("#D97706")),
                           ("TEXTCOLOR", (0, 4), (0, 5), colors.white),
                           ("BACKGROUND", (0, 6), (0, -1), colors.HexColor("#2563EB")),
                           ("TEXTCOLOR", (0, 6), (0, -1), colors.white)]))
    S += [t, Spacer(1, 0.25 * cm),
          P("Sequencia sugerida: (i) P1 de ancoranca (F-01/F-02) primeiro, porque sem âncora qualquer "
            "outro controle e decorativo; (ii) P1 de rotulos/re-execucao do receipt (F-03) e permissoes "
            "de chave (F-04/F-06), que sao mudancas pequenas e fecham as superficies externas; (iii) P2 "
            "no CI/gate e paths; (iv) P3 como higiene.", "small")]

    # ---------- issues ----------
    S += [PageBreak(), P("6. ISSUES PARA O GITHUB", "h1"),
          P("Bloco por achado acionavel, pronto para copiar e colar (tambem gravado em "
            "<font face='DejaVuMono'>docs/security-audit/issues/</font>). Os delimitadores "
            "<font face='DejaVuMono'>--- ISSUE n ---</font> / "
            "<font face='DejaVuMono'>--- FIM ISSUE n ---</font> existem so para marcar o inicio/fim do "
            "bloco e nao fazem parte da issue. F-10 e F-11 foram agrupados numa unica issue de "
            "correcao de documentacao/higiene para evitar spam.", "small"),
          Spacer(1, 0.15 * cm)]
    groups = [[f] for f in FINDINGS if f["sev"] in ("critica", "alta", "media")]
    groups.append([f for f in FINDINGS if f["sev"] in ("baixa", "informativa") and f["id"] != "F-10"])
    groups.append([f for f in FINDINGS if f["id"] in ("F-10", "F-11")])
    groups = [g for g in groups if g]
    import shutil
    shutil.rmtree(os.path.join(here, "issues"), ignore_errors=True)
    os.makedirs(os.path.join(here, "issues"), exist_ok=True)
    for n, g in enumerate(groups, start=1):
        primary = g[0]
        slug, text = make_issue(primary, n)
        if len(g) > 1:
            extra = ["", "## Achados agrupados neste ticket", ""]
            for f in g[1:]:
                extra.append("- **%s (%s)** - %s" % (f["id"], f["sev"], f["title"]))
                extra.append("  - Evidencia: `%s`" % f["files"])
                extra.append("  - Aceite: " + "; ".join(f["accept"]))
            text = text.replace("## Impacto", "\n".join(extra) + "\n\n## Impacto", 1)
        path = os.path.join(here, "issues", "%02d-%s.md" % (n, slug))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        body = "<br/>".join((l.replace(" ", "&nbsp;") if l.strip() else "&nbsp;")
                            for l in _html.escape(text).split("\n"))
        S += [Table([[Paragraph("<font face='DejaVuMono' size='8'><b>--- ISSUE %d ---</b></font>&nbsp;&nbsp;"
                                "<font size='7'>arquivo: docs/security-audit/issues/%02d-%s.md</font>"
                                "<br/>%s<br/><font face='DejaVuMono' size='8'><b>--- FIM ISSUE %d ---</b></font>"
                                % (n, n, slug, body, n), st["iss"])]],
                     colWidths=[BODY_W],
                     style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
                                       ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D1D5DB")),
                                       ("LINEBEFORE", (0, 0), (0, -1), 2.2,
                                        colors.HexColor(SEV_COLORS[primary["sev"]])),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                       ("TOPPADDING", (0, 0), (-1, -1), 5),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])),
              Spacer(1, 0.3 * cm)]
    S += [P("Nenhuma das issues foi aberta no GitHub por esta auditoria: o objetivo era produzir o "
            "material revisavel. Para abrir tudo de uma vez: "
            "<font face='DejaVuMono'>for f in docs/security-audit/issues/*.md; do gh issue create "
            "--title \"$(head -1 $f | sed 's/^# //')\" --body-file $f; done</font>", "small")]

    doc.build(S, canvasmaker=NumberedCanvas.factory(pt(REPORT_TITLE)))
    return out_path
