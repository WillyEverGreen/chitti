"""Publication-grade academic report PDF engine and teacher template augmentation suite.

Provides dual-mode PDF generation:
1. Mode A (build_report_pdf): Compiles publication-grade academic report PDFs from scratch
   with cover/header blocks, student identification, flexible section flowables (headings,
   justified body text, bullet/numbered lists, syntax code blocks, formatted tables,
   captioned processed images), and two-pass 'Page X of Y' page numbering.
2. Mode B (augment_teacher_template, overlay_on_template_page): Augments teacher-provided
   prompt/template PDFs by seamlessly merging continuation solution pages or overlaying
   text at specific coordinates.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image
import pymupdf as fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas

from classroom.config import StudentConfig
from classroom.media_processor import ProcessedImage, calculate_print_dimensions


@dataclass
class PDFBuildResult:
    """Metadata result for a generated or augmented PDF document."""

    output_path: Path
    page_count: int


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas callback for dynamic total page count rendering ('Page X of Y')."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count: int) -> None:
        """Draw running rule line and 'Page X of Y' footer."""
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748B"))

        # Thin footer separator rule
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 45, self._pagesize[0] - 54, 45)

        # Running page number string
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(self._pagesize[0] - 54, 30, page_str)
        self.restoreState()


_FONT_MAP = {
    "helv": "helv",
    "helvetica": "helv",
    "helv-bold": "hebo",
    "helvetica-bold": "hebo",
    "bold": "hebo",
    "hebo": "hebo",
    "helv-italic": "heit",
    "helvetica-italic": "heit",
    "heit": "heit",
    "helv-bolditalic": "hebi",
    "hebi": "hebi",
    "times": "tiro",
    "times-roman": "tiro",
    "times-bold": "tibo",
    "tiro": "tiro",
    "tibo": "tibo",
    "courier": "cour",
    "cour": "cour",
    "courier-bold": "cobo",
    "cobo": "cobo",
}


def _get_report_styles() -> Dict[str, ParagraphStyle]:
    """Generate style dictionary tailored for academic reports."""
    return {
        "ReportInstitution": ParagraphStyle(
            "ReportInstitution",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0F172A"),
        ),
        "ReportDepartment": ParagraphStyle(
            "ReportDepartment",
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475569"),
        ),
        "ReportCourse": ParagraphStyle(
            "ReportCourse",
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#2563EB"),
        ),
        "ReportTitle": ParagraphStyle(
            "ReportTitle",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=21,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0F172A"),
        ),
        "ReportMetaCell": ParagraphStyle(
            "ReportMetaCell",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1E293B"),
        ),
        "ReportHeading": ParagraphStyle(
            "ReportHeading",
            fontName="Helvetica-Bold",
            fontSize=13.5,
            leading=17,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "ReportSubheading": ParagraphStyle(
            "ReportSubheading",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#334155"),
            spaceBefore=8,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "ReportBody": ParagraphStyle(
            "ReportBody",
            fontName="Helvetica",
            fontSize=9.5,
            leading=14.5,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#334155"),
            spaceBefore=2,
            spaceAfter=4,
        ),
        "ReportBullet": ParagraphStyle(
            "ReportBullet",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#334155"),
            leftIndent=16,
            bulletIndent=4,
            spaceBefore=2,
            spaceAfter=2,
        ),
        "ReportNumbered": ParagraphStyle(
            "ReportNumbered",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#334155"),
            leftIndent=18,
            bulletIndent=4,
            spaceBefore=2,
            spaceAfter=2,
        ),
        "ReportCode": ParagraphStyle(
            "ReportCode",
            fontName="Courier",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#0F172A"),
        ),
        "ReportTableCell": ParagraphStyle(
            "ReportTableCell",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1E293B"),
        ),
        "ReportTableHeaderCell": ParagraphStyle(
            "ReportTableHeaderCell",
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.white,
        ),
        "ReportCaption": ParagraphStyle(
            "ReportCaption",
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#64748B"),
        ),
    }


def _create_header_flowables(
    config: Optional[StudentConfig],
    assignment_meta: Dict[str, Any],
    printable_width: float,
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build cover information and academic header block."""
    flowables: List[Any] = []

    # Institution
    institution = config.institution.strip() if config and config.institution else ""
    if institution:
        flowables.append(Paragraph(institution, styles["ReportInstitution"]))
        flowables.append(Spacer(1, 2))

    # Department
    department = config.department.strip() if config and config.department else ""
    if department:
        flowables.append(Paragraph(department, styles["ReportDepartment"]))
        flowables.append(Spacer(1, 4))

    # Decorative divider
    if institution or department:
        flowables.append(
            HRFlowable(
                width="100%",
                thickness=1.5,
                color=colors.HexColor("#2563EB"),
                spaceBefore=4,
                spaceAfter=8,
            )
        )

    # Course
    course = assignment_meta.get("course") or assignment_meta.get("course_name") or ""
    if course:
        flowables.append(Paragraph(str(course), styles["ReportCourse"]))
        flowables.append(Spacer(1, 2))

    # Title
    title = (
        assignment_meta.get("title")
        or assignment_meta.get("assignment_title")
        or "Academic Assignment Report"
    )
    flowables.append(Paragraph(str(title), styles["ReportTitle"]))
    flowables.append(Spacer(1, 8))

    # Metadata Card (2x2 grid)
    student_name = config.student_name.strip() if config and config.student_name else "Student"
    roll_number = config.roll_number.strip() if config and config.roll_number else "N/A"
    date_str = (
        assignment_meta.get("date")
        or assignment_meta.get("due_date")
        or assignment_meta.get("submission_date")
        or datetime.now().strftime("%B %d, %Y")
    )

    meta_table_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student_name}", styles["ReportMetaCell"]),
            Paragraph(f"<b>Roll Number:</b> {roll_number}", styles["ReportMetaCell"]),
        ],
        [
            Paragraph(
                f"<b>Department:</b> {department if department else 'N/A'}",
                styles["ReportMetaCell"],
            ),
            Paragraph(f"<b>Submission Date:</b> {date_str}", styles["ReportMetaCell"]),
        ],
    ]

    col_w = printable_width / 2.0
    meta_table = Table(meta_table_data, colWidths=[col_w, col_w])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    flowables.append(
        KeepTogether(
            [
                meta_table,
                Spacer(1, 10),
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#CBD5E1"),
                    spaceBefore=4,
                    spaceAfter=12,
                ),
            ]
        )
    )

    return flowables


def _create_section_flowables(
    sections: List[Union[Dict[str, Any], str]],
    printable_width: float,
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Convert raw section items into structured ReportLab flowables."""
    flowables: List[Any] = []

    for sec in sections:
        if isinstance(sec, str):
            sec = {"type": "paragraph", "text": sec}
        if not isinstance(sec, dict):
            continue

        sec_type = str(sec.get("type", "paragraph")).lower().strip()

        if sec_type in ("heading", "h1"):
            text = sec.get("text") or sec.get("title") or sec.get("content") or ""
            flowables.append(Paragraph(str(text), styles["ReportHeading"]))
            flowables.append(Spacer(1, 4))

        elif sec_type in ("subheading", "h2"):
            text = sec.get("text") or sec.get("title") or sec.get("content") or ""
            flowables.append(Paragraph(str(text), styles["ReportSubheading"]))
            flowables.append(Spacer(1, 3))

        elif sec_type in ("paragraph", "body", "text"):
            text = sec.get("text") or sec.get("content") or ""
            flowables.append(Paragraph(str(text), styles["ReportBody"]))
            flowables.append(Spacer(1, 4))

        elif sec_type in ("bullet", "bullets", "bullet_list"):
            items = sec.get("items")
            if items is None:
                raw_text = sec.get("text") or sec.get("content") or ""
                items = [s.strip() for s in str(raw_text).split("\n") if s.strip()]
            for item in items:
                flowables.append(Paragraph(str(item), styles["ReportBullet"], bulletText="•"))
            flowables.append(Spacer(1, 4))

        elif sec_type in ("numbered", "numbered_list"):
            items = sec.get("items")
            if items is None:
                raw_text = sec.get("text") or sec.get("content") or ""
                items = [s.strip() for s in str(raw_text).split("\n") if s.strip()]
            for idx, item in enumerate(items, 1):
                flowables.append(
                    Paragraph(str(item), styles["ReportNumbered"], bulletText=f"{idx}.")
                )
            flowables.append(Spacer(1, 4))

        elif sec_type in ("code", "code_block"):
            code_text = sec.get("text") or sec.get("code") or sec.get("content") or ""
            pre = Preformatted(str(code_text), styles["ReportCode"])
            code_table = Table([[pre]], colWidths=[printable_width])
            code_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            flowables.append(KeepTogether([code_table, Spacer(1, 6)]))

        elif sec_type in ("table", "grid"):
            raw_data = sec.get("data") or sec.get("rows") or []
            headers = sec.get("headers")
            if headers:
                table_rows = [headers] + list(raw_data)
                has_header = True
            else:
                table_rows = list(raw_data)
                has_header = False

            if not table_rows:
                continue

            num_cols = max(len(row) for row in table_rows) if table_rows else 1
            formatted_data = []
            for r_idx, row in enumerate(table_rows):
                formatted_row = []
                is_hdr = r_idx == 0 and has_header
                style_to_use = (
                    styles["ReportTableHeaderCell"] if is_hdr else styles["ReportTableCell"]
                )
                for cell in row:
                    formatted_row.append(Paragraph(str(cell), style_to_use))
                while len(formatted_row) < num_cols:
                    formatted_row.append(Paragraph("", style_to_use))
                formatted_data.append(formatted_row)

            user_widths = sec.get("col_widths") or sec.get("widths")
            if user_widths and len(user_widths) == num_cols:
                col_widths = user_widths
            else:
                col_width = printable_width / num_cols
                col_widths = [col_width] * num_cols

            t = Table(formatted_data, colWidths=col_widths)
            table_style = [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
            if has_header:
                table_style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")))
                for row_i in range(1, len(formatted_data)):
                    bg = (
                        colors.HexColor("#F8FAFC")
                        if row_i % 2 == 1
                        else colors.HexColor("#FFFFFF")
                    )
                    table_style.append(("BACKGROUND", (0, row_i), (-1, row_i), bg))
            else:
                for row_i in range(len(formatted_data)):
                    bg = (
                        colors.HexColor("#F8FAFC")
                        if row_i % 2 == 1
                        else colors.HexColor("#FFFFFF")
                    )
                    table_style.append(("BACKGROUND", (0, row_i), (-1, row_i), bg))

            t.setStyle(TableStyle(table_style))
            flowables.append(KeepTogether([t, Spacer(1, 8)]))

        elif sec_type == "image":
            img_item = sec.get("image") or sec.get("path") or sec.get("file")
            caption = sec.get("caption")

            if isinstance(img_item, ProcessedImage):
                img_path = img_item.path
                if not caption:
                    caption = img_item.caption
                w, h = calculate_print_dimensions(
                    img_item, max_pt_width=printable_width, max_pt_height=360.0
                )
            elif img_item is not None:
                img_path = Path(img_item).resolve()
                if not img_path.exists():
                    continue
                with Image.open(img_path) as pil_img:
                    w_px, h_px = pil_img.size
                aspect = (w_px / h_px) if h_px > 0 else 1.0
                w = min(printable_width, float(w_px))
                h = w / aspect
                if h > 360.0:
                    h = 360.0
                    w = h * aspect
            else:
                continue

            rl_img = RLImage(str(img_path), width=w, height=h, hAlign="CENTER")
            img_elements: List[Any] = [rl_img]
            if caption:
                img_elements.append(Spacer(1, 4))
                img_elements.append(
                    Paragraph(f"<i>Figure: {caption}</i>", styles["ReportCaption"])
                )
            img_elements.append(Spacer(1, 8))
            flowables.append(KeepTogether(img_elements))

        elif sec_type in ("page_break", "pagebreak", "break"):
            flowables.append(PageBreak())

        elif sec_type in ("divider", "hr"):
            flowables.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#CBD5E1"),
                    spaceBefore=6,
                    spaceAfter=8,
                )
            )

    return flowables


def build_report_pdf(
    config: StudentConfig,
    assignment_meta: Dict[str, Any],
    sections: List[Union[Dict[str, Any], str]],
    output_path: Union[str, Path],
) -> Path:
    """Compile a publication-grade academic report PDF from scratch.

    Args:
        config: StudentConfig providing student and institutional identity.
        assignment_meta: Metadata dictionary (title, course, date).
        sections: List of section dicts (heading, subheading, paragraph, bullet, numbered,
                  code, image, table) or plain text strings.
        output_path: Destination path for the generated PDF.

    Returns:
        Resolved Path to the created PDF file.

    Raises:
        ValueError: If config is None or sections list is empty.
    """
    if config is None:
        raise ValueError("StudentConfig cannot be None")
    if not sections:
        raise ValueError("Sections cannot be empty")

    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    margin = 54.0  # 0.75 in (54 pt)
    printable_width = A4[0] - (2 * margin)

    styles = _get_report_styles()
    story: List[Any] = []

    # 1. Academic Header / Cover Info Block
    story.extend(_create_header_flowables(config, assignment_meta or {}, printable_width, styles))

    # 2. Section Flowables
    story.extend(_create_section_flowables(sections, printable_width, styles))

    # 3. Document Template Compilation with NumberedCanvas
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )
    doc.build(story, canvasmaker=NumberedCanvas)

    return out_path


def smart_fill_rubric_fields(
    page: Any,
    config: Optional[StudentConfig],
    submission_date: Optional[str] = None,
    performance_date: Optional[str] = None,
) -> bool:
    """Smartly fills student name, roll number, and date directly into rubric fields/lines.

    Detects both inline underline prompts (e.g. 'Name: ______', 'Roll No: ______')
    and formal table cells (e.g. college evaluation rubrics with vertical column dividers).
    Returns True if at least one field was found and filled.
    """
    if not config or not config.student_name:
        return False

    name = config.student_name.strip()
    roll = str(config.roll_number or "").strip()
    sub_date = submission_date or datetime.now().strftime("%d/%m/%Y")
    perf_date = performance_date or sub_date

    # 1. Detect vertical dividing lines to understand table column layout
    v_lines = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r and r.width < 3 and r.height > 15:
            v_lines.append(r.x0)
    v_lines = sorted(list(set(round(x, 1) for x in v_lines)))

    def get_val_x(label_rect: Any) -> float:
        for vx in v_lines:
            if vx > label_rect.x0 and vx >= label_rect.x1 - 5:
                return vx + 6
        return label_rect.x1 + 6

    fields_filled = 0

    # 1. Fill Name
    name_done = False
    for pat in [
        "Name of the Student:",
        "Name of Student:",
        "Student Name:",
        "Name of the Student",
        "Name of Student",
        "Name:",
    ]:
        hits = page.search_for(pat)
        if hits:
            r = hits[0]
            val_x = (
                r.x1 + 4
                if "_" in page.get_text("text", clip=fitz.Rect(r.x1, r.y0 - 2, r.x1 + 160, r.y1 + 2))
                else get_val_x(r)
            )
            page.insert_text(
                fitz.Point(val_x, r.y1 - 1.5),
                name,
                fontsize=10.5,
                fontname="hebo",
                color=(0.08, 0.15, 0.35),
            )
            name_done = True
            fields_filled += 1
            break

    if not name_done:
        # Check for standalone table cell 'Name' (below title header y > 150, left col x < 200)
        for r in page.search_for("Name"):
            if r.y0 > 150 and r.x0 < 200:
                val_x = get_val_x(r)
                page.insert_text(
                    fitz.Point(val_x, r.y1 - 1.5),
                    name,
                    fontsize=10.5,
                    fontname="hebo",
                    color=(0.08, 0.15, 0.35),
                )
                name_done = True
                fields_filled += 1
                break

    # 2. Fill Roll No
    for pat in [
        "Roll No:",
        "Roll Number:",
        "Roll No.",
        "Roll No",
        "URN:",
        "UID:",
        "Registration No:",
    ]:
        hits = page.search_for(pat)
        if hits:
            r = hits[0]
            val_x = (
                r.x1 + 4
                if "_" in page.get_text("text", clip=fitz.Rect(r.x1, r.y0 - 2, r.x1 + 160, r.y1 + 2))
                else get_val_x(r)
            )
            page.insert_text(
                fitz.Point(val_x, r.y1 - 1.5),
                roll,
                fontsize=10.5,
                fontname="hebo",
                color=(0.08, 0.15, 0.35),
            )
            fields_filled += 1
            break

    # 3. Fill Date of Submission
    for pat in [
        "Date of Submission:",
        "Date of Submission",
        "Submission Date:",
        "Date:",
    ]:
        hits = page.search_for(pat)
        if hits:
            r = hits[-1]
            val_x = (
                r.x1 + 4
                if "_" in page.get_text("text", clip=fitz.Rect(r.x1, r.y0 - 2, r.x1 + 160, r.y1 + 2))
                else get_val_x(r)
            )
            page.insert_text(
                fitz.Point(val_x, r.y1 - 1.5),
                sub_date,
                fontsize=10,
                fontname="hebo",
                color=(0.08, 0.15, 0.35),
            )
            fields_filled += 1
            break

    # 4. Fill Date of Performance if present
    for pat in ["Date of Performance:", "Date of Performance"]:
        hits = page.search_for(pat)
        if hits:
            r = hits[0]
            val_x = get_val_x(r)
            page.insert_text(
                fitz.Point(val_x, r.y1 - 1.5),
                perf_date,
                fontsize=10,
                fontname="hebo",
                color=(0.08, 0.15, 0.35),
            )
            fields_filled += 1
            break

    return fields_filled > 0


def augment_teacher_template(
    template_pdf_path: Optional[Union[str, Path]] = None,
    solution_pdf_path: Optional[Union[str, Path]] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    template_path: Optional[Union[str, Path]] = None,
    solution_sections: Optional[List[Any]] = None,
    config: Optional[StudentConfig] = None,
    assignment_meta: Optional[Dict[str, Any]] = None,
    stamp_student_info: bool = True,
) -> Path:
    """Merge continuation solution pages after a teacher-provided prompt/template PDF.

    Args:
        template_pdf_path: Path to the existing teacher template PDF.
        solution_pdf_path: Path to the generated solution PDF.
        output_path: Destination path for the merged PDF.

    Returns:
        Resolved Path to the merged PDF document.

    Raises:
        FileNotFoundError: If template_pdf_path or solution_pdf_path does not exist.
        ValueError: If either PDF file cannot be opened or is corrupted.
    """
    actual_template = template_pdf_path or template_path
    if not actual_template:
        raise ValueError("template_pdf_path or template_path must be provided")

    t_path = Path(actual_template).resolve()
    if not t_path.exists():
        raise FileNotFoundError(f"Template PDF not found: {t_path}")

    if not output_path:
        raise ValueError("output_path must be specified")

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Compile solution sections if passed instead of solution_pdf_path
    temp_sol_file = None
    if solution_sections:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_sol_file = Path(tf.name)
        build_report_pdf(
            config=config or StudentConfig(),
            assignment_meta=assignment_meta or {},
            sections=solution_sections,
            output_path=temp_sol_file,
        )
        actual_solution = temp_sol_file
    else:
        actual_solution = solution_pdf_path

    if not actual_solution:
        raise ValueError("Either solution_pdf_path or solution_sections must be provided")

    s_path = Path(actual_solution).resolve()
    if not s_path.exists():
        raise FileNotFoundError(f"Solution PDF not found: {s_path}")

    t_doc = None
    s_doc = None
    merged_doc = None
    try:
        try:
            t_doc = fitz.open(str(t_path))
        except Exception as exc:
            raise ValueError(f"Failed to open PDF template file '{t_path}': {exc}") from exc

        # Smartly fill student credentials on template page 0 if requested
        if stamp_student_info and config and len(t_doc) > 0:
            p0 = t_doc[0]
            filled = smart_fill_rubric_fields(p0, config)
            if not filled and config.student_name:
                p0.insert_text(
                    fitz.Point(36, 24),
                    f"{config.student_name} | Roll No: {config.roll_number or ''}",
                    fontsize=8.5,
                    fontname="hebo",
                    color=(0.25, 0.3, 0.4),
                )

        try:
            s_doc = fitz.open(str(s_path))
        except Exception as exc:
            raise ValueError(f"Failed to open PDF solution file '{s_path}': {exc}") from exc

        merged_doc = fitz.open()
        merged_doc.insert_pdf(t_doc)
        merged_doc.insert_pdf(s_doc)
        merged_doc.save(str(out_p))
        return out_p
    finally:
        if t_doc:
            t_doc.close()
        if s_doc:
            s_doc.close()
        if merged_doc:
            merged_doc.close()
        if temp_sol_file and temp_sol_file.exists():
            try:
                temp_sol_file.unlink()
            except Exception:
                pass


def overlay_on_template_page(
    template_pdf_path: Union[str, Path],
    page_index: int,
    text_entries: List[Any],
    output_path: Union[str, Path],
) -> Path:
    """Overlay text entries onto designated coordinates of an existing template page.

    Args:
        template_pdf_path: Path to the existing template PDF.
        page_index: Zero-based page index to overlay onto.
        text_entries: List of dicts (with 'text', 'pos'/'point'/'rect', 'fontsize', 'fontname',
                      'color') or tuples ((x, y), text).
        output_path: Destination path for the modified PDF.

    Returns:
        Resolved Path to the output PDF document.

    Raises:
        FileNotFoundError: If template_pdf_path does not exist.
        ValueError: If PDF cannot be opened.
        IndexError: If page_index is out of range.
    """
    t_path = Path(template_pdf_path).resolve()
    if not t_path.exists():
        raise FileNotFoundError(f"Template PDF not found: {t_path}")

    doc = None
    try:
        try:
            doc = fitz.open(str(t_path))
        except Exception as exc:
            raise ValueError(f"Failed to open PDF template file '{t_path}': {exc}") from exc

        num_pages = len(doc)
        if page_index < 0 or page_index >= num_pages:
            raise IndexError(
                f"Page index {page_index} out of range (document has {num_pages} pages)"
            )

        page = doc[page_index]

        for entry in text_entries:
            if isinstance(entry, dict):
                text = str(entry.get("text", ""))
                fontsize = float(entry.get("fontsize", entry.get("font_size", 10.0)))
                raw_font = str(entry.get("fontname", entry.get("font_name", "helv"))).lower()
                fontname = _FONT_MAP.get(raw_font, "helv")
                color = entry.get("color", (0, 0, 0))
                if (
                    isinstance(color, (tuple, list))
                    and len(color) >= 3
                    and any(c > 1.0 for c in color)
                ):
                    color = tuple(c / 255.0 for c in color[:3])

                if "rect" in entry:
                    rect = fitz.Rect(entry["rect"])
                    page.insert_textbox(
                        rect, text, fontsize=fontsize, fontname=fontname, color=color
                    )
                else:
                    x = entry.get("x")
                    y = entry.get("y")
                    pos = (
                        entry.get("pos")
                        or entry.get("point")
                        or ((x, y) if x is not None and y is not None else (50, 50))
                    )
                    page.insert_text(pos, text, fontsize=fontsize, fontname=fontname, color=color)

            elif isinstance(entry, (tuple, list)):
                if len(entry) == 2:
                    pos, text = entry
                    page.insert_text(
                        pos, str(text), fontsize=10.0, fontname="helv", color=(0, 0, 0)
                    )
                elif len(entry) >= 3:
                    if isinstance(entry[0], (int, float)) and isinstance(entry[1], (int, float)):
                        pos = (entry[0], entry[1])
                        text = entry[2]
                        fontsize = float(entry[3]) if len(entry) > 3 else 10.0
                    else:
                        pos = entry[0]
                        text = entry[1]
                        fontsize = float(entry[2])
                    page.insert_text(
                        pos, str(text), fontsize=fontsize, fontname="helv", color=(0, 0, 0)
                    )

        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))
        return out_path
    finally:
        if doc:
            doc.close()


def personalize_reference_pdf(
    source_pdf: Union[str, Path],
    config: StudentConfig,
    output_path: Union[str, Path],
    old_name: Optional[str] = None,
    old_roll: Optional[str] = None,
    stamp_header: bool = True,
) -> Path:
    """Sanitize and personalize a reference assignment PDF with current student credentials.

    Args:
        source_pdf: Path to the reference or template PDF.
        config: StudentConfig with student_name, roll_number, etc.
        output_path: Destination path for personalized PDF.
        old_name: Optional existing author name to search & redact.
        old_roll: Optional existing roll number to search & redact.
        stamp_header: Whether to add a clean academic student banner on page 0 if no old details found.

    Returns:
        Resolved Path to the personalized PDF.
    """
    src = Path(source_pdf).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source PDF not found: {src}")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src))
    try:
        replaced_any = False
        for page in doc:
            page_replacements: List[Tuple[fitz.Rect, str]] = []

            # 1. Find old name
            if old_name:
                for rect in page.search_for(old_name):
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page_replacements.append((rect, config.student_name))

            # 2. Find old roll
            if old_roll:
                for rect in page.search_for(old_roll):
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page_replacements.append((rect, config.roll_number))

            # Apply all redactions first before inserting new text
            if page_replacements:
                page.apply_redactions()
                replaced_any = True
                for rect, new_text in page_replacements:
                    fsize = rect.height * 0.85 if rect.height > 6 else 10.0
                    page.insert_text(
                        (rect.x0, rect.y1 - 1),
                        new_text,
                        fontsize=fsize,
                        fontname="helv",
                        color=(0, 0, 0),
                    )

        # 3. If no specific target strings were replaced and stamp_header is True, smart fill on page 0
        if not replaced_any and stamp_header and len(doc) > 0:
            p0 = doc[0]
            filled = smart_fill_rubric_fields(p0, config)
            if not filled and config.student_name:
                p0.insert_text(
                    fitz.Point(36, 24),
                    f"{config.student_name} | Roll No: {config.roll_number or ''}",
                    fontsize=8.5,
                    fontname="hebo",
                    color=(0.25, 0.3, 0.4),
                )

        doc.save(str(out))
        return out
    finally:
        doc.close()
