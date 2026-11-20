"""Renders docs/user-guide.md to a one-page PDF (docs/user-guide.pdf) with reportlab."""
import os, re, sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, OUT = os.path.join(ROOT, "docs", "user-guide.md"), os.path.join(ROOT, "docs", "user-guide.pdf")
ASCII = {"\u2192": "->", "\u2212": "-", "\u00f7": "/", "\u00d7": "x", "\u2013": "-", "\u2014": "-", "\u2019": "'"}

def inline(t):
    for k, v in ASCII.items(): t = t.replace(k, v)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)

def build():
    blue = colors.HexColor("#1F4E79")
    body = ParagraphStyle("b", fontName="Helvetica", fontSize=8.6, leading=11.2, spaceAfter=4.5)
    h1 = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=blue, spaceAfter=6)
    cell = ParagraphStyle("c", parent=body, fontSize=8.2, leading=10, spaceAfter=0)
    story, rows = [], []
    for line in open(SRC, encoding="utf-8").read().splitlines():
        if line.startswith("# "): story.append(Paragraph(inline(line[2:]), h1))
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "): continue
            rows.append([Paragraph(("<b>%s</b>" % inline(c)) if not rows else inline(c), cell) for c in cells])
        else:
            if rows:
                t = Table(rows, colWidths=[34 * mm, 143 * mm])
                t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEBF7")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C4D0")),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]))
                story += [t, Spacer(1, 6)]; rows = []
            if line.strip(): story.append(Paragraph(inline(line), body))
    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=12 * mm,
                            title="Enterprise BI Suite - user guide", author="Enterprise BI Suite")
    doc.build(story)
    from pypdf import PdfReader
    n = len(PdfReader(OUT).pages)
    print(f"wrote {OUT} ({n} page{'s' if n != 1 else ''})")
    return n

if __name__ == "__main__":
    sys.exit(0 if build() == 1 else 1)
