"""Unit tests for the PDF personalization and sanitization engine."""

from pathlib import Path
import pytest
import pymupdf as fitz

from classroom.config import StudentConfig
from classroom.pdf_engine import personalize_reference_pdf


def test_personalize_reference_pdf_redact_and_replace(tmp_path):
    """Verify personalizing a reference assignment by replacing old student credentials."""
    src_pdf = tmp_path / "reference_assignment.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "Assignment 3 - Computer Networks\nSubmitted by: John Doe (Roll: 99999)\nFr. CRCE")
    doc.save(str(src_pdf))
    doc.close()

    config = StudentConfig(
        student_name="Sai Balkawade",
        roll_number="10707",
        department="Computer Engineering",
        institution="Fr. Conceicao Rodrigues College of Engineering",
    )

    out_pdf = tmp_path / "personalized_submission.pdf"
    personalize_reference_pdf(
        source_pdf=src_pdf,
        config=config,
        output_path=out_pdf,
        old_name="John Doe",
        old_roll="99999",
    )

    assert out_pdf.exists()

    # Verify extracted text contains new student details and not old ones
    doc_out = fitz.open(str(out_pdf))
    out_text = doc_out[0].get_text()
    doc_out.close()

    assert "Sai Balkawade" in out_text
    assert "10707" in out_text
    assert "John Doe" not in out_text
    assert "99999" not in out_text


def test_personalize_reference_pdf_header_stamp(tmp_path):
    """Verify header stamping when no specific old author string is provided."""
    src_pdf = tmp_path / "anonymous_lab_sheet.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 200), "Experiment 5: Microprocessor 8086 Assembly.")
    doc.save(str(src_pdf))
    doc.close()

    config = StudentConfig(
        student_name="Sai Balkawade",
        roll_number="10707",
        department="Computer Engineering",
    )

    out_pdf = tmp_path / "stamped_lab_sheet.pdf"
    personalize_reference_pdf(
        source_pdf=src_pdf,
        config=config,
        output_path=out_pdf,
        stamp_header=True,
    )

    assert out_pdf.exists()
    doc_out = fitz.open(str(out_pdf))
    out_text = doc_out[0].get_text()
    doc_out.close()

    assert "Sai Balkawade" in out_text
    assert "10707" in out_text

