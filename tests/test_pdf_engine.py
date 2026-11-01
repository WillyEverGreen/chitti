"""Unit tests for Classroom dual-mode PDF generation engine."""

from pathlib import Path
import pytest
from PIL import Image
import pymupdf as fitz

from classroom.config import StudentConfig
from classroom.media_processor import ProcessedImage
from classroom.pdf_engine import (
    build_report_pdf,
    augment_teacher_template,
    overlay_on_template_page,
    NumberedCanvas,
)


@pytest.fixture
def sample_config(tmp_path: Path) -> StudentConfig:
    """Fixture providing a standard StudentConfig profile."""
    return StudentConfig(
        student_name="Alice Smith",
        roll_number="CS2024-001",
        department="Department of Computer Science & Engineering",
        institution="Apex Institute of Technology",
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Fixture creating a dummy test image on disk."""
    img_path = tmp_path / "test_diagram.png"
    img = Image.new("RGB", (400, 250), color=(37, 99, 235))
    img.save(img_path)
    return img_path


def test_build_report_pdf_all_sections(tmp_path: Path, sample_config: StudentConfig, sample_image: Path):
    """Test generating a publication-grade report with all supported section flowables."""
    out_pdf = tmp_path / "comprehensive_report.pdf"
    assignment_meta = {
        "title": "Lab 4: Distributed Routing Protocols",
        "course": "CS-401 Advanced Computer Networks",
        "date": "November 1, 2026",
    }

    processed_img = ProcessedImage(
        path=sample_image,
        width=400,
        height=250,
        aspect_ratio=400 / 250,
        caption="OSPF Convergence State Diagram",
    )

    sections = [
        {"type": "heading", "text": "1. Introduction & Objectives"},
        {
            "type": "paragraph",
            "text": "The primary objective of this laboratory exercise is to configure and evaluate OSPF and BGP routing algorithms in a simulated mesh topology.",
        },
        {"type": "subheading", "text": "1.1 Key Requirements"},
        {
            "type": "bullet",
            "items": [
                "Establish shortest path convergence under 50ms",
                "Prevent routing loops using split horizon with poison reverse",
                "Verify link failure failover behavior",
            ],
        },
        {"type": "subheading", "text": "1.2 Steps Executed"},
        {
            "type": "numbered",
            "items": [
                "Initialize router interfaces with designated IPv4 subnets.",
                "Broadcast link state advertisements across Area 0.",
                "Inject link failure and capture traceroute output.",
            ],
        },
        {"type": "heading", "text": "2. Router Configuration Script"},
        {
            "type": "code",
            "text": "router ospf 1\n network 10.0.0.0 0.255.255.255 area 0\n neighbor 10.0.0.2 priority 10\n exit",
        },
        {"type": "heading", "text": "3. Convergence Performance Metrics"},
        {
            "type": "table",
            "headers": ["Metric", "Baseline", "Observed", "Status"],
            "data": [
                ["Link Down Detection", "5 ms", "4.2 ms", "PASSED"],
                ["Convergence Time", "50 ms", "38.6 ms", "PASSED"],
                ["Packet Loss Ratio", "< 0.1%", "0.02%", "PASSED"],
            ],
        },
        {"type": "heading", "text": "4. Topology Diagram"},
        {
            "type": "image",
            "image": processed_img,
            "caption": "OSPF Convergence State Diagram",
        },
    ]

    result_path = build_report_pdf(
        config=sample_config,
        assignment_meta=assignment_meta,
        sections=sections,
        output_path=out_pdf,
    )

    assert result_path.exists()
    assert result_path == out_pdf.resolve()

    # Verify PDF structure using PyMuPDF
    doc = fitz.open(result_path)
    assert len(doc) >= 1

    extracted_text = ""
    for page in doc:
        extracted_text += page.get_text() + "\n"
    doc.close()

    # Verify Cover block / Header Info
    assert "Apex Institute of Technology" in extracted_text
    assert "Department of Computer Science & Engineering" in extracted_text
    assert "Alice Smith" in extracted_text
    assert "CS2024-001" in extracted_text
    assert "CS-401 Advanced Computer Networks" in extracted_text
    assert "Lab 4: Distributed Routing Protocols" in extracted_text
    assert "November 1, 2026" in extracted_text

    # Verify Section Content
    assert "1. Introduction & Objectives" in extracted_text
    assert "mesh topology" in extracted_text
    assert "Establish shortest path convergence under 50ms" in extracted_text
    assert "router ospf 1" in extracted_text
    assert "Convergence Time" in extracted_text
    assert "OSPF Convergence State Diagram" in extracted_text

    # Verify NumberedCanvas page numbering pattern ("Page X of Y")
    assert "Page 1 of" in extracted_text


def test_build_report_pdf_multipage_page_numbering(tmp_path: Path, sample_config: StudentConfig):
    """Test that multi-page documents generate accurate 'Page X of Y' numbering on each page."""
    out_pdf = tmp_path / "long_report.pdf"
    assignment_meta = {"title": "Multi-page Long Form Lab Report"}

    # Generate enough paragraphs to span multiple pages
    long_paragraphs = [
        {
            "type": "paragraph",
            "text": f"Section {i}: Academic body paragraph detailing in-depth theoretical analysis and simulation telemetry data for routing node {i}. "
            * 8,
        }
        for i in range(25)
    ]

    result_path = build_report_pdf(sample_config, assignment_meta, long_paragraphs, out_pdf)
    assert result_path.exists()

    doc = fitz.open(result_path)
    total_pages = len(doc)
    assert total_pages >= 2

    # Verify each page has its respective "Page N of <total_pages>"
    for idx, page in enumerate(doc):
        page_text = page.get_text()
        expected_page_str = f"Page {idx + 1} of {total_pages}"
        assert expected_page_str in page_text, f"Expected '{expected_page_str}' in page {idx + 1}"
    doc.close()


def test_build_report_pdf_raw_image_path(tmp_path: Path, sample_config: StudentConfig, sample_image: Path):
    """Test building report with image provided as raw Path/str."""
    out_pdf = tmp_path / "raw_image_report.pdf"
    sections = [
        {"type": "heading", "text": "Raw Image Attachment"},
        {
            "type": "image",
            "path": sample_image,
            "caption": "Screenshot of Ping Telemetry",
        },
    ]

    result_path = build_report_pdf(sample_config, {"title": "Raw Image Test"}, sections, out_pdf)
    assert result_path.exists()

    doc = fitz.open(result_path)
    extracted = doc[0].get_text()
    assert "Raw Image Attachment" in extracted
    assert "Screenshot of Ping Telemetry" in extracted
    doc.close()


def test_build_report_pdf_empty_sections_raises(tmp_path: Path, sample_config: StudentConfig):
    """Test that empty or None sections list raises ValueError."""
    with pytest.raises(ValueError, match="Sections cannot be empty"):
        build_report_pdf(sample_config, {"title": "Test"}, [], tmp_path / "fail.pdf")

    with pytest.raises(ValueError, match="Sections cannot be empty"):
        build_report_pdf(sample_config, {"title": "Test"}, None, tmp_path / "fail.pdf")


def test_augment_teacher_template(tmp_path: Path, sample_config: StudentConfig):
    """Test merging a multi-page teacher template with a generated solution PDF."""
    teacher_pdf = tmp_path / "teacher_manual.pdf"
    # Create 2-page teacher PDF
    t_doc = fitz.open()
    p1 = t_doc.new_page()
    p1.insert_text((72, 72), "Teacher Lab Manual - Question 1: Implement Dijkstra", fontsize=14)
    p2 = t_doc.new_page()
    p2.insert_text((72, 72), "Teacher Lab Manual - Question 2: Implement Bellman-Ford", fontsize=14)
    t_doc.save(teacher_pdf)
    t_doc.close()

    # Create solution PDF
    sol_pdf = tmp_path / "solution.pdf"
    sol_sections = [
        {"type": "heading", "text": "Dijkstra and Bellman-Ford Implementation"},
        {"type": "paragraph", "text": "Here is the verified shortest-path routing algorithm implementation."},
        {"type": "code", "text": "def dijkstra(graph, start):\n    pass"},
    ]
    build_report_pdf(sample_config, {"title": "Solutions"}, sol_sections, sol_pdf)

    # Merge
    merged_pdf = tmp_path / "final_submission.pdf"
    result_path = augment_teacher_template(teacher_pdf, sol_pdf, merged_pdf)

    assert result_path.exists()
    assert result_path == merged_pdf.resolve()

    # Verify merged document
    m_doc = fitz.open(result_path)
    assert len(m_doc) >= 3  # 2 teacher pages + at least 1 solution page
    assert "Question 1: Implement Dijkstra" in m_doc[0].get_text()
    assert "Question 2: Implement Bellman-Ford" in m_doc[1].get_text()
    assert "Dijkstra and Bellman-Ford Implementation" in m_doc[2].get_text()
    m_doc.close()


def test_augment_teacher_template_with_solution_sections(tmp_path: Path, sample_config: StudentConfig):
    """Test augmenting teacher template by passing solution_sections directly (auto-compilation)."""
    teacher_pdf = tmp_path / "rubric_sheet.pdf"
    t_doc = fitz.open()
    p1 = t_doc.new_page()
    p1.insert_text((72, 72), "Teacher Rubric & Grading Criteria", fontsize=14)
    t_doc.save(teacher_pdf)
    t_doc.close()

    sol_sections = [
        {"type": "heading", "text": "Laboratory Findings & Code"},
        {"type": "paragraph", "text": "Detailed execution summary and test results."},
        {"type": "code", "text": "print('Convergence verified')"},
    ]
    out_pdf = tmp_path / "augmented_with_sections.pdf"

    result_path = augment_teacher_template(
        template_path=teacher_pdf,
        output_path=out_pdf,
        solution_sections=sol_sections,
        config=sample_config,
        assignment_meta={"course": "Algorithms", "title": "Lab 5"},
    )

    assert result_path.exists()
    doc = fitz.open(result_path)
    assert len(doc) >= 2
    assert "Teacher Rubric & Grading Criteria" in doc[0].get_text()
    assert "Laboratory Findings & Code" in doc[1].get_text()
    doc.close()


def test_overlay_on_template_page(tmp_path: Path):
    """Test overlaying student metadata and answers onto a designated page of a teacher template."""
    template_pdf = tmp_path / "exam_sheet.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # Standard A4
    page.insert_text((72, 72), "EXAM COVER SHEET", fontsize=16)
    page.insert_text((72, 120), "Student Name: ____________________", fontsize=11)
    page.insert_text((72, 150), "Roll Number:  ____________________", fontsize=11)
    doc.save(template_pdf)
    doc.close()

    output_pdf = tmp_path / "filled_exam_sheet.pdf"
    overlays = [
        {"text": "Alice Smith", "pos": (160, 120), "fontsize": 11, "fontname": "helv-bold"},
        {"text": "CS2024-001", "x": 160, "y": 150, "fontsize": 11},
        ((72, 220), "Score / Remarks: Verified Completed"),
    ]

    res_path = overlay_on_template_page(template_pdf, page_index=0, text_entries=overlays, output_path=output_pdf)
    assert res_path.exists()

    res_doc = fitz.open(res_path)
    assert len(res_doc) == 1
    page_text = res_doc[0].get_text()
    assert "EXAM COVER SHEET" in page_text
    assert "Alice Smith" in page_text
    assert "CS2024-001" in page_text
    assert "Verified Completed" in page_text
    res_doc.close()


def test_overlay_on_template_page_out_of_bounds(tmp_path: Path):
    """Test overlaying on an invalid page index raises IndexError."""
    template_pdf = tmp_path / "one_page.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(template_pdf)
    doc.close()

    out_pdf = tmp_path / "out.pdf"
    with pytest.raises(IndexError, match="Page index 5 out of range"):
        overlay_on_template_page(template_pdf, page_index=5, text_entries=[{"text": "Hi", "pos": (10, 10)}], output_path=out_pdf)


def test_error_handling_invalid_paths(tmp_path: Path):
    """Test that missing template or solution PDF paths raise FileNotFoundError."""
    missing_template = tmp_path / "nonexistent_teacher.pdf"
    valid_pdf = tmp_path / "valid.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(valid_pdf)
    doc.close()

    with pytest.raises(FileNotFoundError, match="Template PDF not found"):
        augment_teacher_template(missing_template, valid_pdf, tmp_path / "out.pdf")

    with pytest.raises(FileNotFoundError, match="Solution PDF not found"):
        augment_teacher_template(valid_pdf, missing_template, tmp_path / "out.pdf")

    with pytest.raises(FileNotFoundError, match="Template PDF not found"):
        overlay_on_template_page(missing_template, 0, [], tmp_path / "out.pdf")


def test_error_handling_corrupt_pdf(tmp_path: Path):
    """Test that corrupt PDF files raise ValueError."""
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\nCorrupted content without PDF structures\nEOF")

    valid_pdf = tmp_path / "valid.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(valid_pdf)
    doc.close()

    with pytest.raises(ValueError, match="Failed to open PDF"):
        augment_teacher_template(corrupt_pdf, valid_pdf, tmp_path / "out.pdf")

    with pytest.raises(ValueError, match="Failed to open PDF"):
        augment_teacher_template(valid_pdf, corrupt_pdf, tmp_path / "out.pdf")

    with pytest.raises(ValueError, match="Failed to open PDF"):
        overlay_on_template_page(corrupt_pdf, 0, [], tmp_path / "out.pdf")


def test_build_report_pdf_none_config_raises(tmp_path: Path):
    """Test that passing None for StudentConfig raises ValueError."""
    with pytest.raises(ValueError, match="StudentConfig cannot be None"):
        build_report_pdf(None, {"title": "Test"}, [{"type": "paragraph", "text": "Hi"}], tmp_path / "out.pdf")


def test_init_exports():
    """Verify that classroom package properly exports all Task 4 interfaces."""
    import classroom

    assert hasattr(classroom, "build_report_pdf")
    assert hasattr(classroom, "augment_teacher_template")
    assert hasattr(classroom, "overlay_on_template_page")
    assert hasattr(classroom, "NumberedCanvas")
    assert hasattr(classroom, "PDFBuildResult")


def test_overlay_textbox_and_colors(tmp_path: Path):
    """Test overlaying using rect boundaries and RGB 0-255 color scaling."""
    template_pdf = tmp_path / "rect_template.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(template_pdf)
    doc.close()

    out_pdf = tmp_path / "rect_overlay_out.pdf"
    entries = [
        {
            "rect": (50, 50, 300, 150),
            "text": "Multi-line commentary inserted within a bounding rectangle.",
            "fontsize": 10,
            "fontname": "courier",
            "color": (255, 0, 0),  # Red in 0-255 format
        },
        # (x, y, text, fontsize) format
        (50, 200, "Footer annotation", 8),
    ]

    res = overlay_on_template_page(template_pdf, 0, entries, out_pdf)
    assert res.exists()

    res_doc = fitz.open(res)
    text = res_doc[0].get_text()
    assert "Multi-line commentary" in text
    assert "Footer annotation" in text
    res_doc.close()

