"""Unit tests for the Coursework Workspace & Academic Study Engine (classroom/workspace.py)."""

from pathlib import Path
import pytest
import pymupdf as fitz

from classroom.config import StudentConfig
from classroom.workspace import (
    CourseWorkspace,
    get_course_workspace,
    extract_pdf_text,
    save_study_notes,
)


def test_course_workspace_paths(tmp_path):
    """Verify CourseWorkspace creates isolated, structured per-course directories."""
    output_root = tmp_path / "coursework_root"
    ws = get_course_workspace(output_root, "Computer Networks Lab")

    assert ws.course_slug == "computer_networks_lab"
    assert ws.root_dir == output_root / "computer_networks_lab"
    assert ws.assignments_dir == output_root / "computer_networks_lab" / "assignments"
    assert ws.materials_dir == output_root / "computer_networks_lab" / "materials"
    assert ws.notes_dir == output_root / "computer_networks_lab" / "notes"

    # Verify directories exist on disk
    assert ws.root_dir.is_dir()
    assert ws.assignments_dir.is_dir()
    assert ws.materials_dir.is_dir()
    assert ws.notes_dir.is_dir()

    # Test assignment subfolder resolution
    assign_dir = ws.get_assignment_dir("Experiment 7 - Socket Programming")
    assert assign_dir == ws.assignments_dir / "experiment_7_socket_programming"
    assert assign_dir.is_dir()

    # Test topic notes subfolder resolution
    notes_topic_dir = ws.get_notes_dir("TCP Three-Way Handshake")
    assert notes_topic_dir == ws.notes_dir / "tcp_three_way_handshake"
    assert notes_topic_dir.is_dir()


def test_extract_pdf_text(tmp_path):
    """Verify PDF text extraction using PyMuPDF."""
    test_pdf = tmp_path / "test_teacher_prompt.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "Experiment 4: Operating System Scheduling Algorithms\nObjective: Implement Round Robin and SJF in C++.")
    doc.save(str(test_pdf))
    doc.close()

    # Extract text without file export
    extracted = extract_pdf_text(test_pdf)
    assert "Experiment 4" in extracted
    assert "Round Robin" in extracted

    # Extract text with file export
    export_txt = tmp_path / "extracted_prompt.txt"
    extracted_2 = extract_pdf_text(test_pdf, output_txt_path=export_txt)
    assert export_txt.exists()
    assert export_txt.read_text(encoding="utf-8") == extracted_2


def test_extract_pdf_text_file_not_found():
    """Verify FileNotFoundError is raised for non-existent PDF."""
    with pytest.raises(FileNotFoundError):
        extract_pdf_text("nonexistent_file.pdf")


def test_save_study_notes(tmp_path):
    """Verify study notes generation creates structured markdown and compiled PDF."""
    output_root = tmp_path / "output"
    ws = get_course_workspace(output_root, "Operating Systems")
    config = StudentConfig(
        student_name="Sai Balkawade",
        roll_number="10707",
        department="Computer Engineering",
        institution="Fr. CRCE",
    )

    theory_text = (
        "Round Robin (RR) is a preemptive CPU scheduling algorithm where each process "
        "is assigned a fixed time slice or quantum. It ensures fairness among processes."
    )
    formula_text = "Turnaround Time = Completion Time - Arrival Time\nWaiting Time = Turnaround Time - Burst Time"
    viva = [
        {"question": "What is starvation in SJF?", "answer": "Long processes wait indefinitely if short jobs arrive continuously."},
        {"question": "What happens if quantum is too large in RR?", "answer": "It degenerates into First-Come First-Served (FCFS)."},
    ]

    result = save_study_notes(
        workspace=ws,
        config=config,
        topic="CPU Scheduling - Round Robin",
        theory=theory_text,
        formulas=formula_text,
        viva_questions=viva,
        compile_pdf=True,
    )

    md_path = result["markdown"]
    pdf_path = result["pdf"]

    assert md_path.exists()
    assert pdf_path.exists()

    md_content = md_path.read_text(encoding="utf-8")
    assert "Sai Balkawade" in md_content
    assert "10707" in md_content
    assert "CPU Scheduling - Round Robin" in md_content
    assert "Round Robin (RR) is a preemptive" in md_content
    assert "What is starvation in SJF?" in md_content

    # Verify PDF is valid PyMuPDF document
    doc = fitz.open(str(pdf_path))
    assert len(doc) >= 1
    doc.close()


def test_download_drive_file_mock(tmp_path, monkeypatch):
    """Verify download_drive_file streams chunks to local destination."""
    from unittest.mock import MagicMock
    from classroom.workspace import download_drive_file

    mock_drive = MagicMock()
    mock_request = MagicMock()
    mock_drive.files().get_media.return_value = mock_request

    # Mock MediaIoBaseDownload
    mock_downloader_cls = MagicMock()
    mock_downloader_instance = MagicMock()
    mock_downloader_instance.next_chunk.side_effect = [(MagicMock(), False), (MagicMock(), True)]
    mock_downloader_cls.return_value = mock_downloader_instance

    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", mock_downloader_cls)

    dest = tmp_path / "downloads" / "test_manual.pdf"
    res = download_drive_file(mock_drive, "file_12345", dest)

    assert res == dest
    mock_drive.files().get_media.assert_called_once_with(fileId="file_12345", supportsAllDrives=True)
