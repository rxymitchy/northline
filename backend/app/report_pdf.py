from fpdf import FPDF, XPos, YPos

from app.brief import BRAND

GREEN = (21, 128, 61)
INK = (23, 23, 23)
MUTE = (92, 92, 92)
LINE = (228, 228, 224)
PAPER = (247, 247, 245)
HIGH = (154, 52, 18)
MED = (133, 77, 14)
LOW = (63, 98, 18)


def _t(value) -> str:
    text = str(value or "").replace("\r", "").strip()
    return text.encode("latin-1", "replace").decode("latin-1")


def _prio_color(label: str) -> tuple[int, int, int]:
    key = str(label or "").upper()
    if key == "HIGH":
        return HIGH
    if key == "MEDIUM":
        return MED
    if key == "LOW":
        return LOW
    return MUTE


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(auto=True, margin=32)
        self.set_margins(18, 22, 18)
        self.set_title(f"{BRAND} operations snapshot")
        self.set_author(BRAND)

    def header(self):
        # Watermark must not use cell()/multi_cell — those trigger extra page breaks.
        broke = self.auto_page_break
        margin = self.b_margin
        self.set_auto_page_break(False)
        with self.local_context(fill_opacity=0.07, text_color=GREEN):
            self.set_font("Helvetica", "B", 48)
            label = BRAND.upper()
            cx, cy = self.w / 2, self.h / 2
            with self.rotation(32, cx, cy):
                self.text(cx - self.get_string_width(label) / 2, cy, label)
        self.set_fill_color(*GREEN)
        self.rect(0, 0, self.w, 14, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10)
        self.set_xy(18, 4)
        self.cell(70, 6, BRAND.upper())
        self.set_font("Helvetica", "", 8)
        self.set_xy(88, 4)
        self.cell(self.w - 106, 6, "See what's still manual", align="R")
        self.set_text_color(*INK)
        self.set_xy(self.l_margin, 20)
        self.set_auto_page_break(broke, margin=margin)

    def footer(self):
        broke = self.auto_page_break
        margin = self.b_margin
        self.set_auto_page_break(False)
        self.set_y(-16)
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        self.line(18, self.get_y(), self.w - 18, self.get_y())
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTE)
        self.cell(self.epw - 16, 5, f"Prepared by {BRAND}. Public pages and what you submitted only.")
        self.cell(16, 5, str(self.page_no()), align="R")
        self.set_auto_page_break(broke, margin=margin)

    def need(self, height: float):
        if self.get_y() + height > self.page_break_trigger:
            self.add_page()

    def section(self, title: str):
        self.need(28)
        self.ln(3)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*GREEN)
        self.cell(0, 6, _t(title).upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*GREEN)
        self.set_line_width(0.5)
        y = self.get_y()
        self.line(self.l_margin, y, self.l_margin + 26, y)
        self.ln(3)
        self.set_text_color(*INK)

    def body(self, text: str, bold: bool = False, size: int = 11):
        line = _t(text)
        if not line:
            return
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B" if bold else "", size)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.5, line)
        self.ln(0.8)

    def muted(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*MUTE)
        self.multi_cell(0, 5, _t(text))
        self.ln(0.6)
        self.set_text_color(*INK)

    def bullets(self, items: list):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*INK)
        for item in items:
            line = _t(item)
            if not line:
                continue
            self.need(12)
            y = self.get_y()
            self.set_xy(self.l_margin, y)
            self.cell(5, 5.5, "-")
            self.set_xy(self.l_margin + 5, y)
            self.multi_cell(self.epw - 5, 5.5, line)

    def _wrap_height(self, text: str, width: float, line_h: float = 4.2) -> float:
        lines = self.multi_cell(width, line_h, text or " ", dry_run=True, output="LINES")
        return max(line_h + 1.5, len(lines) * line_h + 2)


def build_brief_pdf(brief: dict, name: str, site: str = "") -> bytes:
    diagnosis = brief.get("diagnosis") if isinstance(brief.get("diagnosis"), dict) else {}
    channel = brief.get("channel") if isinstance(brief.get("channel"), dict) else {}
    industry = _t(brief.get("industry") or "")
    overall = _t(diagnosis.get("overall_label") or diagnosis.get("overall") or "Not rated").upper()
    automate = diagnosis.get("automate_first") or {}
    processes = diagnosis.get("processes") or []
    workflow = diagnosis.get("workflow") or []
    evidence = automate.get("evidence") or []
    observed = _t(
        diagnosis.get("summary")
        or "Northline reviewed what you sent and noted how work appears to move."
    )
    site_line = " - ".join(x for x in (_t(site), industry) if x)

    pdf = ReportPDF()
    pdf.add_page()
    pdf.set_xy(pdf.l_margin, pdf.get_y())
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 8, _t(name or "Operations snapshot"))
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTE)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, _t((site_line + " - " if site_line else "") + "operations snapshot"))
    pdf.ln(2)

    pdf.set_fill_color(*PAPER)
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    y_badge = pdf.get_y()
    pdf.rect(pdf.l_margin, y_badge, pdf.epw, 10, "DF")
    pdf.set_xy(pdf.l_margin + 4, y_badge + 2)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTE)
    pdf.cell(58, 6, "Overall manual dependency")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_prio_color(overall))
    pdf.cell(0, 6, overall)
    pdf.set_xy(pdf.l_margin, y_badge + 12)
    pdf.set_text_color(*INK)

    pdf.section("Business operations snapshot")
    pdf.body(observed)

    if processes:
        pdf.ln(1)
        col_w = [36, 50, 22, pdf.epw - 108]
        headers = ["Process", "Current human work", "Priority", "Why it matters"]
        pdf.need(16)
        pdf.set_fill_color(*PAPER)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*MUTE)
        pdf.set_x(pdf.l_margin)
        for i, head in enumerate(headers):
            pdf.cell(col_w[i], 6, head.upper(), border="B", fill=True)
        pdf.ln()
        for row in processes:
            cells = [
                _t(row.get("process")),
                _t(row.get("human_work")),
                _t(row.get("priority")),
                _t(row.get("why")),
            ]
            pdf.set_font("Helvetica", "", 8)
            h = max(pdf._wrap_height(cells[i], col_w[i]) for i in range(4))
            pdf.need(h + 2)
            x0 = pdf.l_margin
            y0 = pdf.get_y()
            broke = pdf.auto_page_break
            margin = pdf.b_margin
            pdf.set_auto_page_break(False)
            for i, cell in enumerate(cells):
                pdf.set_xy(x0, y0 + 1)
                if i == 2:
                    pdf.set_text_color(*_prio_color(cell))
                    pdf.set_font("Helvetica", "B", 8)
                else:
                    pdf.set_text_color(*INK)
                    pdf.set_font("Helvetica", "", 8)
                pdf.multi_cell(col_w[i], 4.2, cell, new_x=XPos.LEFT, new_y=YPos.TOP)
                x0 += col_w[i]
            pdf.set_auto_page_break(broke, margin=margin)
            pdf.set_xy(pdf.l_margin, y0 + h)
            pdf.set_draw_color(*LINE)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + pdf.epw, pdf.get_y())

    pdf.section("What to automate first")
    pdf.body(_t(automate.get("title") or "The first handoff"), bold=True, size=12)
    pdf.body(
        _t(
            automate.get("reason")
            or "Northline did not see a single dominant public bottleneck."
        )
    )
    if evidence:
        pdf.bullets(evidence)

    pdf.section("Suggested workflow")
    steps = [_t(s) for s in workflow if s]
    pdf.body("  ->  ".join(steps) if steps else "Incoming enquiry -> capture -> follow-up -> human handoff when needed")

    if channel and (channel.get("state") or channel.get("missing") or channel.get("explore")):
        pdf.section("Notes on what you sent")
        if channel.get("state"):
            pdf.body(_t(channel.get("state")))
        if channel.get("missing"):
            pdf.muted("What's missing")
            pdf.bullets(channel.get("missing") or [])
        if channel.get("explore"):
            pdf.muted("Could be worth exploring")
            pdf.bullets(channel.get("explore") or [])

    pdf.ln(4)
    pdf.need(16)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*MUTE)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        0,
        5,
        _t(
            diagnosis.get("caveat")
            or "Based on the information provided. Northline does not invent internal processes."
        ),
    )

    return bytes(pdf.output())
