"""
services/pdf/render.py — CV Markdown → PDF rendering core.

Extracted from callback-cv/cv_to_pdf.py.
Supports Segoe UI / Calibri fonts (fpdf2).

Entry points:
    render_to_bytes(markdown_text: str) -> bytes   — for FastAPI /render endpoint
    md_to_pdf(md_path, pdf_path=None)             — for local CLI use
"""

import io
import os
import re
from pathlib import Path

from fpdf import FPDF, FontFace

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = Path(_SCRIPT_DIR).parent.parent  # services/pdf/ → project root

# Load project .env so CAREER_AGENT_FONTS is available when running via uvicorn
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

# CAREER_AGENT_FONTS env var lets the host inject fonts without rebuilding the image.
# Default: project root fonts/ directory (absolute path — CWD-independent).
_env_fonts = os.environ.get("CAREER_AGENT_FONTS")
if _env_fonts:
    FONT_PATH = _env_fonts.rstrip("/\\") + "/"
else:
    FONT_PATH = str(_PROJECT_ROOT / "fonts") + os.sep


def _find_font(name: str, fallback: str) -> str:
    """Resolve font path: FONT_PATH/name → FONT_PATH/fallback → error."""
    primary = os.path.join(FONT_PATH, name)
    if os.path.exists(primary):
        return primary
    alt = os.path.join(FONT_PATH, fallback)
    if os.path.exists(alt):
        return alt
    raise FileNotFoundError(f"TTF Font file not found: {primary}")


FONTS = {
    "regular": _find_font("segoeui.ttf", "calibri.ttf"),
    "bold":    _find_font("segoeuib.ttf", "calibrib.ttf"),
    "italic":  _find_font("segoeuii.ttf", "calibrii.ttf"),
}
FONT_NAME = "SegoeUI"

# Status emoji → (symbol, text_color_rgb) for table cell rendering
_STATUS_CELLS = {
    "✅": (" ● ", (34, 139, 34)),
    "❌": (" ● ", (200, 0,   0)),
    "⚠️": (" ● ", (200, 130, 0)),
    "⚠":  (" ● ", (200, 130, 0)),
}

PAGE_MARGIN_L = 22
PAGE_MARGIN_R = 22
PAGE_MARGIN_T = 20
PAGE_MARGIN_B = 20

SECTION_KEYWORDS = {
    "SUMMARY", "EXPERIENCE", "CERTIFICATIONS", "EDUCATION", "SKILLS",
    # Ukrainian
    "ДОСВІД", "СЕРТИФІКАТИ", "СЕРТИФІКАЦІЇ", "ОСВІТА", "НАВИЧКИ", "РЕЗЮМЕ",
    # Russian
    "ОПЫТ", "СЕРТИФИКАТЫ", "ОБРАЗОВАНИЕ",
}

# Section/role header color — medium blue
_HEADER_COLOR: tuple[int, int, int] = (66, 133, 244)

KEY_RESULTS_RE = re.compile(
    r"^(key results?|key outcome|ключові результати|ключовий результат):?\s*$",
    re.IGNORECASE,
)


def is_section_header(text: str) -> bool:
    clean = text.strip()
    if clean in SECTION_KEYWORDS:
        return True
    if len(clean) >= 3 and clean == clean.upper() and re.match(r"^[A-ZА-ЯІЇЄЁ\s/&]+$", clean):
        return True
    return False


def strip_md_inline(text: str) -> str:
    """Strip markdown links and bold markers to plain text."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return text


def _recommendation_color(verdict_text: str) -> tuple[int, int, int]:
    v = verdict_text.lower()
    if "не подавать" in v:  return (200, 0, 0)
    if "с адаптацией" in v: return (200, 130, 0)
    if "подавать" in v:     return (34, 139, 34)
    return (100, 100, 100)


def _score_color(n: int) -> tuple[int, int, int]:
    if n >= 7: return (34, 139, 34)
    if n >= 4: return (200, 130, 0)
    return (200, 0, 0)


class CVDocument(FPDF):

    def setup_fonts(self) -> None:
        self.add_font(FONT_NAME, style="",  fname=FONTS["regular"])
        self.add_font(FONT_NAME, style="B", fname=FONTS["bold"])
        self.add_font(FONT_NAME, style="I", fname=FONTS["italic"])

    def draw_hr(self, before: int = 3, after: int = 3) -> None:
        self.ln(before)
        self.set_draw_color(190, 190, 190)
        self.set_line_width(0.1)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_line_width(0.2)
        self.set_draw_color(0, 0, 0)
        self.ln(after)

    def name_block(self, text: str) -> None:
        self.set_font(FONT_NAME, "B", 16)
        self.set_text_color(0, 0, 0)
        self.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def headline_block(self, text: str) -> None:
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(60, 60, 60)
        self.cell(0, 6, strip_md_inline(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def contacts_block(self, text: str) -> None:
        self.set_font(FONT_NAME, "", 10)
        self.set_text_color(80, 80, 80)
        parts = re.split(r"(\[[^\]]+\]\([^)]+\))", text)
        for part in parts:
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if m:
                self.set_text_color(17, 85, 204)
                self.write(5.5, m.group(1), link=m.group(2))
                self.set_text_color(80, 80, 80)
            elif part:
                self.write(5.5, strip_md_inline(part))
        self.ln(4)

    def section_header(self, text: str) -> None:
        self.ln(2)
        self.set_font(FONT_NAME, "B", 12)
        self.set_text_color(*_HEADER_COLOR)
        self.cell(0, 6.5, text.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def role_title(self, text: str) -> None:
        self.ln(1)
        self.set_font(FONT_NAME, "B", 12)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6.5, text, new_x="LMARGIN", new_y="NEXT")

    def company_line(self, text: str) -> None:
        self.set_font(FONT_NAME, "", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def link_line(self, label: str, url: str) -> None:
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(17, 85, 204)
        self.cell(0, 6, label, link=url, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def paragraph(self, text: str) -> None:
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(0, 0, 0)
        parts = re.split(r"(\[[^\]]+\]\([^)]+\))", text)
        has_links = any(re.match(r"\[[^\]]+\]\([^)]+\)", p) for p in parts)
        if not has_links:
            plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
            self.multi_cell(0, 6, plain, align="L")
            self.ln(1)
            return
        for part in parts:
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if m:
                self.set_text_color(17, 85, 204)
                self.write(6, m.group(1), link=m.group(2))
                self.set_text_color(0, 0, 0)
            elif part:
                self.set_text_color(0, 0, 0)
                plain_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", part)
                self.write(6, plain_text)
        self.ln(6)
        self.ln(1)

    def key_results_label(self, text: str) -> None:
        self.ln(2)
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(0, 0, 0)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def subsection_header(self, text: str) -> None:
        self.ln(1)
        self.set_font(FONT_NAME, "B", 11)
        self.set_text_color(40, 40, 40)
        self.cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def table_block(self, rows: list[list[str]]) -> None:
        if not rows or not rows[0]:
            return
        n_cols = len(rows[0])
        page_w = self.w - self.l_margin - self.r_margin
        col_w = page_w / n_cols
        headings_style = FontFace(emphasis="B", fill_color=(235, 235, 235))
        self.set_font(FONT_NAME, "", 10)
        self.ln(2)
        with self.table(
            headings_style=headings_style,
            line_height=5,
            width=page_w,
            col_widths=[col_w] * n_cols,
        ) as table:
            for row in rows:
                tr = table.row()
                cells = (row + [""] * n_cols)[:n_cols]
                for raw in cells:
                    clean = strip_md_inline(raw)
                    cell_style = None
                    for emoji, (symbol, color) in _STATUS_CELLS.items():
                        if emoji in clean:
                            clean = symbol
                            cell_style = FontFace(color=color)
                            break
                    if cell_style:
                        tr.cell(clean, style=cell_style)
                    else:
                        tr.cell(clean)
        self.ln(3)

    def quick_scan_block(self, lines: list[str]) -> None:
        kv: dict[str, str] = {}
        for line in lines:
            s = line.strip()
            if not s:
                continue
            m = re.match(r"^\*\*([^*:]+):?\*\*\s*(.+)$", s)
            if m:
                kv[m.group(1).strip()] = m.group(2).strip()

        self.ln(3)

        verdict = kv.get("Recommendation", kv.get("Рекомендация", kv.get("Verdict", kv.get("Вердикт", ""))))
        if verdict:
            self.set_font(FONT_NAME, "B", 14)
            self.set_text_color(*_recommendation_color(verdict))
            self.cell(0, 11, verdict.upper(), new_x="LMARGIN", new_y="NEXT")
            self.ln(3)

        score_str = kv.get("Fit score", kv.get("Фит скор", ""))
        if score_str:
            m = re.search(r"(\d+)", score_str)
            if m:
                n = int(m.group(1))
                s_color = _score_color(n)
                self.set_font(FONT_NAME, "B", 10)
                self.set_text_color(60, 60, 60)
                self.write(6, "Fit score: ")
                self.set_text_color(*s_color)
                self.write(6, f"{score_str} ")
                for i in range(10):
                    self.set_text_color(*(s_color if i < n else (180, 180, 180)))
                    self.write(6, "●" if i < n else "○")
                self.ln(8)

        page_width = self.w - self.l_margin - self.r_margin
        col_left  = page_width * 0.30
        col_right = page_width * 0.70
        skip = {"Verdict", "Вердикт", "Recommendation", "Рекомендация", "Fit score", "Фит скор"}

        for key, value in kv.items():
            if key in skip:
                continue
            self.set_text_color(0, 0, 0)
            self.set_font(FONT_NAME, "B", 10)
            x_label = self.get_x()
            y_before = self.get_y()
            self.multi_cell(col_left, 5, f"{key}:", align="L", border=0)
            y_after = self.get_y()
            self.set_xy(x_label + col_left, y_before)
            self.set_font(FONT_NAME, "", 10)
            self.multi_cell(col_right, 5, strip_md_inline(value), align="L", border=0)
            self.set_xy(self.l_margin, max(y_after, self.get_y()))
            self.ln(1)

        self.set_text_color(0, 0, 0)
        self.ln(2)

    def bullet_item(self, text: str) -> None:
        self.set_font(FONT_NAME, "", 12)
        self.set_text_color(0, 0, 0)
        plain = strip_md_inline(text)
        line_h = 6
        indent = 7
        text_w = self.w - self.l_margin - self.r_margin - indent
        if self.get_y() > self.h - self.b_margin - line_h:
            self.add_page()
        x0 = self.l_margin
        y0 = self.get_y()
        self.set_xy(x0, y0)
        self.cell(indent, line_h, "•")
        self.set_xy(x0 + indent, y0)
        self.multi_cell(text_w, line_h, plain, align="L")
        self.ln(0.5)


def render_md(pdf: CVDocument, text: str) -> None:
    lines = text.split("\n")
    i = 0
    is_cover = any(
        re.search(r"cover letter", line, re.IGNORECASE)
        for line in lines if line.strip().startswith("#")
    )

    # Detect CV-style header: a contacts line (markdown links) within the first few
    # non-empty lines. Cover letters / prose have none → skip header parsing so the
    # text renders as normal wrapped paragraphs. Otherwise the first lines get forced
    # into name_block/headline_block/contacts_block, which do NOT wrap and overflow.
    link_re = re.compile(r"\[[^\]]+\]\([^)]+\)")
    is_cv_header = False
    seen = 0
    for probe in lines:
        ps = probe.strip()
        if not ps:
            continue
        seen += 1
        if link_re.search(ps) and not ps.startswith("#") and not ps.startswith("---"):
            is_cv_header = True
            break
        if seen >= 4:
            break

    if is_cv_header:
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines):
            name = re.sub(r"[*#]", "", lines[i]).strip()
            pdf.name_block(name)
            i += 1

        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines):
            s = lines[i].strip()
            if not s.startswith("---") and not s.startswith("#") and not re.match(r"^\*\*[A-ZА-ЯІЇЄ]{2,}", s):
                is_contacts = bool(link_re.search(s))
                if is_contacts:
                    pdf.contacts_block(s)
                else:
                    pdf.headline_block(s)
                    i += 1
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    if i < len(lines):
                        s2 = lines[i].strip()
                        if not s2.startswith("---") and not s2.startswith("#"):
                            pdf.contacts_block(s2)
                i += 1

    first_divider = True

    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if not s:
            i += 1
            continue

        if s == "---":
            if first_divider:
                pdf.draw_hr(before=2, after=5)
                first_divider = False
            else:
                pdf.draw_hr(before=4, after=5)
            i += 1
            continue

        hm = re.match(r"^(#{1,6})\s+(.+)$", s)
        if hm:
            level = len(hm.group(1))
            heading = re.sub(r"[*]", "", hm.group(2)).strip()
            if heading.lower() == "quick scan":
                qs_lines = []
                i += 1
                while i < len(lines):
                    ls = lines[i].strip()
                    if ls.startswith("##") or ls == "---":
                        break
                    qs_lines.append(lines[i])
                    i += 1
                pdf.quick_scan_block(qs_lines)
                continue
            if is_cover and level == 1:
                pdf.name_block(heading)
            elif level <= 3:
                pdf.section_header(heading)
            else:
                pdf.subsection_header(heading)
            i += 1
            continue

        bm = re.match(r"^\*\*([^*]+)\*\*\s*$", s)
        if bm:
            inner = bm.group(1).strip()
            if is_section_header(inner):
                pdf.section_header(inner)
            else:
                pdf.role_title(inner)
            i += 1
            continue

        if s.startswith("|"):
            table_lines = []
            while i < len(lines):
                ts = lines[i].strip()
                if not ts.startswith("|"):
                    break
                table_lines.append(ts)
                i += 1
            rows = []
            for tl in table_lines:
                if re.match(r"^\|[-:\s|]+\|$", tl):
                    continue
                cells = [c.strip() for c in tl.strip("|").split("|")]
                rows.append(cells)
            if rows:
                pdf.table_block(rows)
            continue

        if "|" in s and not s.startswith("-") and not s.startswith("•"):
            pdf.company_line(s)
            i += 1
            continue

        if KEY_RESULTS_RE.match(s.rstrip(":")):
            label = s if s.endswith(":") else s + ":"
            pdf.key_results_label(label)
            i += 1
            continue

        blt = re.match(r"^[-•*]\s+(.+)$", s)
        if blt:
            pdf.bullet_item(blt.group(1))
            i += 1
            continue

        lm = re.match(r"^\[([^\]]+)\]\(([^)]+)\)\s*$", s)
        if lm:
            pdf.link_line(lm.group(1), lm.group(2))
            i += 1
            continue

        if is_section_header(s):
            pdf.section_header(s)
            i += 1
            continue

        pdf.paragraph(s)
        if is_cover:
            pdf.ln(3)
        i += 1


def _build_pdf(markdown_text: str) -> CVDocument:
    pdf = CVDocument(orientation="P", unit="mm", format="A4")
    pdf.set_margins(PAGE_MARGIN_L, PAGE_MARGIN_T, PAGE_MARGIN_R)
    pdf.set_auto_page_break(auto=True, margin=PAGE_MARGIN_B)
    pdf.setup_fonts()
    pdf.add_page()
    render_md(pdf, markdown_text)
    return pdf


def render_to_bytes(markdown_text: str) -> bytes:
    """Render markdown CV/analysis to PDF bytes. Used by FastAPI /render endpoint."""
    pdf = _build_pdf(markdown_text)
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def md_to_pdf(md_path: str, pdf_path: str | None = None) -> str:
    """Render a markdown file to PDF on disk. Returns output PDF path."""
    if pdf_path is None:
        import os as _os
        pdf_path = _os.path.splitext(md_path)[0] + ".pdf"

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    pdf = _build_pdf(md_text)
    pdf.output(pdf_path)
    return pdf_path
