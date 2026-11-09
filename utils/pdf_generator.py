"""PDF rendering for drafts (English and Hindi) using fpdf2 + HarfBuzz text shaping.

The input is the plain-text draft — including any edits the user made in the
app — so the PDF always matches what the user approved. Conventions in the
text:
  * a line followed by a line of dashes is a heading
  * the first paragraph (the DRAFT banner) is drawn in a shaded box
  * lines containing [MISSING …] / [ADD …] (or the Hindi equivalents) are highlighted
"""
from __future__ import annotations

import re
from datetime import date

from fpdf import FPDF

from config import FONTS_DIR

NAVY = (20, 50, 92)
SAFFRON_LIGHT = (253, 236, 214)
GREY = (90, 98, 110)
BANNER_BG = (238, 242, 248)
MARK_RE = re.compile(r"\[(MISSING|ADD|अनुपलब्ध|जोड़ें):")


class _DraftPDF(FPDF):
    def __init__(self, title: str, lang: str):
        super().__init__(format="A4")
        self.doc_title = title
        self.lang = lang
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(True, margin=18)
        self.add_font("NotoSans", "", str(FONTS_DIR / "NotoSans-Regular.ttf"))
        self.add_font("NotoSans", "B", str(FONTS_DIR / "NotoSans-Bold.ttf"))
        self.add_font("NotoSans", "I", str(FONTS_DIR / "NotoSans-Italic.ttf"))
        # NyayaSetuSans = Noto Sans Devanagari merged with Noto Sans (built with fontTools, see assets/fonts/README.md).
        # One font covering both scripts avoids fpdf2's per-glyph fallback, which mis-shapes mixed Hindi/English runs.
        self.add_font("NSans", "", str(FONTS_DIR / "NyayaSetuSans-Regular.ttf"))
        self.add_font("NSans", "B", str(FONTS_DIR / "NyayaSetuSans-Bold.ttf"))
        try:
            self.set_text_shaping(True)
            self.shaping = True
        except Exception:  # uharfbuzz missing: Hindi conjuncts may render imperfectly
            self.shaping = False
        self.base = "NSans"
        self.set_title(title)
        self.set_creator("NyayaSetu")

    def header(self):
        self.set_draw_color(*NAVY)
        self.set_fill_color(255, 153, 51)
        self.rect(0, 0, 70, 1.6, "F")
        self.set_fill_color(*NAVY)
        self.rect(70, 0, 70, 1.6, "F")
        self.set_fill_color(19, 136, 8)
        self.rect(140, 0, 70, 1.6, "F")
        self.set_y(8)
        self.set_font("NotoSans", "B", 8.5)
        self.set_text_color(*NAVY)
        self.cell(0, 5, "NyayaSetu", new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.base, "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 4, self.doc_title, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-13)
        self.set_font("NotoSans", "", 7.5)
        self.set_text_color(*GREY)
        msg = ("Draft prepared with NyayaSetu — not filed, not a legal notice. Verify all facts before use."
               if self.lang == "en" else "NyayaSetu द्वारा तैयार मसौदा — दर्ज नहीं, कानूनी नोटिस नहीं। उपयोग से पहले सभी तथ्य जाँचें।")
        self.set_font(self.base, "", 7.5)
        self.cell(0, 5, msg, align="L")
        self.set_font("NotoSans", "", 7.5)
        self.cell(0, 5, f"{self.page_no()}/{{nb}}", align="R")


def _blocks(text: str) -> list[tuple[str, str]]:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[tuple[str, str]] = []
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append(("p", "\n".join(para)))
            para.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if line and re.fullmatch(r"-{3,}", nxt):
            flush()
            out.append(("h", line.strip()))
            i += 2
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        if re.match(r"^(\d+\.|-)\s", line.strip()):
            flush()
            out.append(("li", line.strip()))
            i += 1
            continue
        para.append(line)
        i += 1
    flush()
    return out


def text_to_pdf(text: str, title: str, lang: str = "en") -> bytes:
    pdf = _DraftPDF(title, lang)
    pdf.alias_nb_pages()
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font(pdf.base, "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(width, 7.5, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    first_para = True
    for kind, val in _blocks(text):
        if kind == "h":
            pdf.ln(1.5)
            pdf.set_font(pdf.base, "B", 11)
            pdf.set_text_color(*NAVY)
            pdf.multi_cell(width, 6, val, new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(220, 225, 232)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(1.5)
            continue
        pdf.set_text_color(25, 30, 38)
        if kind == "p" and first_para and re.match(r"^(DRAFT|NYAYASETU)", val):
            pdf.set_font(pdf.base, "", 8.5)
            pdf.set_fill_color(*BANNER_BG)
            top = pdf.get_y()
            height = pdf.multi_cell(width - 5, 4.6, val, dry_run=True, output="HEIGHT")
            # shaded box first (measured with a dry run), then the text on top of it
            pdf.rect(pdf.l_margin, top, width, height + 3, "F")
            pdf.set_xy(pdf.l_margin + 2.5, top + 1.5)
            pdf.multi_cell(width - 5, 4.6, val, new_x="LMARGIN", new_y="NEXT")
            pdf.set_y(top + height + 3)
            pdf.ln(3)
            first_para = False
            continue
        first_para = False
        pdf.set_font(pdf.base, "", 10)
        highlight = bool(MARK_RE.search(val))
        if highlight:
            pdf.set_fill_color(*SAFFRON_LIGHT)
        if kind == "li":
            m = re.match(r"^(\d+\.|-)\s+(.*)$", val, re.S)
            marker, body = (m.group(1), m.group(2)) if m else ("-", val)
            marker = "•" if marker == "-" else marker
            pdf.set_x(pdf.l_margin + 2)
            pdf.cell(7, 5.4, marker)
            pdf.multi_cell(width - 9, 5.4, body, fill=highlight, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.8)
        else:
            for line in val.split("\n"):
                hl = bool(MARK_RE.search(line))
                if hl:
                    pdf.set_fill_color(*SAFFRON_LIGHT)
                pdf.multi_cell(width, 5.4, line, fill=hl, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    pdf.ln(4)
    pdf.set_font("NotoSans", "I", 7.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(width, 4, f"Generated on {date.today().isoformat()} by NyayaSetu (AI-assisted legal information and document-preparation tool). "
                             "Highlighted lines contain fields you must complete or check.", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
