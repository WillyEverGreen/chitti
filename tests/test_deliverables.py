"""Unit tests for Classroom deliverables staging manager and requirement auditor."""

from pathlib import Path
import json
import pymupdf as fitz
from rich.console import Console

from classroom.deliverables import (
    RequirementItem,
    RequirementAudit,
    StagedDeliverable,
    audit_assignment_requirements,
    stage_deliverable,
    print_completion_card,
)


def test_stage_deliverable_basic(tmp_path: Path):
    """Verify basic deliverable staging creates directory hierarchy, PDF, manifest, and summary."""
    dummy_pdf = tmp_path / "sample.pdf"
    dummy_pdf.write_text("%PDF-1.4 dummy", encoding="utf-8")

    staged = stage_deliverable(
        output_root=tmp_path / "output",
        course_name="Computer Networks",
        assignment_title="Lab 6 RSA",
        pdf_path=dummy_pdf,
        assets=[],
        classroom_url="https://classroom.google.com/c/123/a/456/details",
    )

    assert staged.staged_dir.exists()
    assert staged.staged_dir == tmp_path / "output" / "computer_networks" / "lab_6_rsa"
    assert staged.pdf_path == staged.staged_dir / "final_submission.pdf"
    assert staged.pdf_path.exists()
    assert staged.manifest_path == staged.staged_dir / "manifest.json"
    assert staged.manifest_path.exists()
    assert staged.summary_path == staged.staged_dir / "SUMMARY.md"
    assert staged.summary_path.exists()
    assert staged.classroom_url == "https://classroom.google.com/c/123/a/456/details"
    assert staged.course_name == "Computer Networks"
    assert staged.assignment_title == "Lab 6 RSA"


def test_stage_deliverable_with_assets_and_checksums(tmp_path: Path):
    """Verify assets are staged and manifest contains correct sha256 checksums."""
    dummy_pdf = tmp_path / "report.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 sample binary content for checksum")

    asset1 = tmp_path / "terminal.png"
    asset1.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes1")

    asset2 = tmp_path / "output.log"
    asset2.write_text("Execution completed successfully with 0 errors.", encoding="utf-8")

    staged = stage_deliverable(
        output_root=tmp_path / "output",
        course_name="Operating Systems",
        assignment_title="Process Scheduling",
        pdf_path=dummy_pdf,
        assets=[asset1, asset2],
        classroom_url="https://classroom.google.com/c/789/a/101/details",
    )

    staged_assets_dir = staged.staged_dir / "assets"
    assert staged_assets_dir.exists()
    assert (staged_assets_dir / "terminal.png").exists()
    assert (staged_assets_dir / "output.log").exists()

    with open(staged.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["course_name"] == "Operating Systems"
    assert manifest["assignment_title"] == "Process Scheduling"
    assert manifest["classroom_url"] == "https://classroom.google.com/c/789/a/101/details"
    assert "submission_pdf" in manifest["deliverables"]
    assert manifest["deliverables"]["submission_pdf"]["filename"] == "final_submission.pdf"
    assert len(manifest["deliverables"]["submission_pdf"]["sha256"]) == 64
    assert len(manifest["deliverables"]["assets"]) == 2

    # Check sha256 checksums match files
    import hashlib

    expected_pdf_sha = hashlib.sha256(b"%PDF-1.4 sample binary content for checksum").hexdigest()
    assert manifest["deliverables"]["submission_pdf"]["sha256"] == expected_pdf_sha
    assert manifest["checksums"]["final_submission.pdf"] == expected_pdf_sha

    expected_asset_sha = hashlib.sha256(b"\x89PNG\r\n\x1a\nfakeimagebytes1").hexdigest()
    assert manifest["checksums"]["assets/terminal.png"] == expected_asset_sha


def test_stage_deliverable_with_real_pdf_page_count(tmp_path: Path):
    """Verify PyMuPDF page count is accurately reflected in StagedDeliverable."""
    real_pdf_path = tmp_path / "multipage.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page(width=595, height=842)
    doc.save(str(real_pdf_path))
    doc.close()

    staged = stage_deliverable(
        output_root=tmp_path / "output",
        course_name="Database Management",
        assignment_title="B-Trees",
        pdf_path=real_pdf_path,
        assets=[],
    )

    assert staged.page_count == 3
    with open(staged.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["page_count"] == 3


def test_stage_deliverable_missing_pdf_raises_file_not_found(tmp_path: Path):
    """Verify FileNotFoundError is raised if pdf_path does not exist."""
    import pytest

    missing_pdf = tmp_path / "non_existent.pdf"
    with pytest.raises(FileNotFoundError, match="PDF deliverable not found"):
        stage_deliverable(
            output_root=tmp_path / "output",
            course_name="Course A",
            assignment_title="Task A",
            pdf_path=missing_pdf,
            assets=[],
        )


def test_stage_deliverable_missing_asset_raises_file_not_found(tmp_path: Path):
    """Verify FileNotFoundError is raised if an asset path does not exist."""
    import pytest

    pdf = tmp_path / "dummy.pdf"
    pdf.write_text("%PDF-1.4", encoding="utf-8")
    missing_asset = tmp_path / "non_existent_asset.png"

    with pytest.raises(FileNotFoundError, match="Asset file not found"):
        stage_deliverable(
            output_root=tmp_path / "output",
            course_name="Course A",
            assignment_title="Task A",
            pdf_path=pdf,
            assets=[missing_asset],
        )


def test_audit_pure_automated_assignment():
    """Verify algorithms, calculations, code, and theoretical prompts are classified as automated."""
    prompt = (
        "1. Implement RSA key generation and encryption in Python.\n"
        "2. Calculate modular exponentiation for p=61, q=53, e=17.\n"
        "3. Provide theoretical explanation of why Euler's totient function is used."
    )

    audit = audit_assignment_requirements(prompt)

    assert audit.is_complete is True
    assert len(audit.automated_tasks) == 3
    assert len(audit.student_action_items) == 0
    assert len(audit.blockers) == 0
    assert all(item.status == "automated" for item in audit.automated_tasks)


def test_audit_hardware_blocker():
    """Verify physical hardware, lab equipment, and sensor tasks are flagged as blockers."""
    prompt = (
        "1. Write a Python script to parse serial telemetry data.\n"
        "2. Connect the Raspberry Pi GPIO pins to the breadboard and measure waveforms with an oscilloscope.\n"
        "3. Solder the ESP32 header pins."
    )

    audit = audit_assignment_requirements(prompt)

    assert audit.is_complete is False
    assert len(audit.automated_tasks) == 1
    assert len(audit.blockers) == 2
    assert all(b.status == "blocked" for b in audit.blockers)
    for b in audit.blockers:
        assert b.reason is not None
        assert any(k in b.reason.lower() for k in ["hardware", "physical", "equipment", "breadboard", "sensor"])


def test_audit_missing_attachment_blocker():
    """Verify prompts referencing attachments fail when files are missing, and pass when attached."""
    prompt = (
        "Download the attached dataset `network_traffic.pcap` and analyze the TCP handshake timings. "
        "Calculate the average packet delay."
    )

    # When no attached files are provided
    audit_missing = audit_assignment_requirements(prompt, attached_files=[])
    assert audit_missing.is_complete is False
    assert len(audit_missing.blockers) >= 1
    assert any("network_traffic.pcap" in b.description or "attachment" in b.reason.lower() for b in audit_missing.blockers)

    # When the attached file is provided
    audit_present = audit_assignment_requirements(prompt, attached_files=["network_traffic.pcap"])
    assert len(audit_present.blockers) == 0
    assert audit_present.is_complete is True


def test_audit_student_action_items():
    """Verify handwritten signatures and local machine/network execution require student input."""
    prompt = (
        "1. Solve the subnetting problem for CIDR 192.168.1.0/26.\n"
        "2. Run traceroute on your local machine and capture the screenshot with your personal shell prompt.\n"
        "3. Sign the academic integrity pledge at the bottom by hand."
    )

    audit = audit_assignment_requirements(prompt)

    assert audit.is_complete is False
    assert len(audit.automated_tasks) == 1
    assert len(audit.student_action_items) == 2
    assert all(a.status == "needs_student_input" for a in audit.student_action_items)


def test_summary_markdown_and_manifest_with_audit(tmp_path: Path):
    """Verify SUMMARY.md and manifest.json correctly render audit checklist items."""
    dummy_pdf = tmp_path / "solution.pdf"
    dummy_pdf.write_text("%PDF-1.4 sample", encoding="utf-8")

    prompt = (
        "1. Write Python code for merge sort.\n"
        "2. Sign the honor statement by hand."
    )
    audit = audit_assignment_requirements(prompt)

    staged = stage_deliverable(
        output_root=tmp_path / "output",
        course_name="Algorithms",
        assignment_title="Sorting Lab",
        pdf_path=dummy_pdf,
        assets=[],
        classroom_url="https://classroom.google.com/c/555/a/666/details",
        audit=audit,
    )

    summary_content = staged.summary_path.read_text(encoding="utf-8")
    assert "Algorithms" in summary_content
    assert "Sorting Lab" in summary_content
    assert "https://classroom.google.com/c/555/a/666/details" in summary_content
    assert "- [x]" in summary_content  # Automated task completed
    assert "- [ ]" in summary_content  # Student action item pending
    assert "final_submission.pdf" in summary_content

    with open(staged.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["status"] == "needs_student_action"
    assert manifest["audit"]["is_complete"] is False
    assert len(manifest["audit"]["automated_tasks"]) == 1
    assert len(manifest["audit"]["student_action_items"]) == 1


def test_print_completion_card():
    """Verify terminal completion card formats paths, URLs, and status without error."""
    deliverable = StagedDeliverable(
        course_name="Computer Networks",
        assignment_title="Lab 6 RSA",
        staged_dir=Path("/workspace/output/computer_networks/lab_6_rsa"),
        pdf_path=Path("/workspace/output/computer_networks/lab_6_rsa/final_submission.pdf"),
        manifest_path=Path("/workspace/output/computer_networks/lab_6_rsa/manifest.json"),
        summary_path=Path("/workspace/output/computer_networks/lab_6_rsa/SUMMARY.md"),
        classroom_url="https://classroom.google.com/c/123/a/456/details",
        page_count=5,
        audit=RequirementAudit(
            automated_tasks=[RequirementItem(description="RSA Algorithm", status="automated")],
            student_action_items=[],
            blockers=[],
            is_complete=True,
        ),
    )

    console = Console(record=True, width=100)
    print_completion_card(deliverable, console=console)
    output = console.export_text()

    assert "Computer Networks" in output
    assert "Lab 6 RSA" in output
    assert "final_submission.pdf" in output
    assert "https://classroom.google.com/c/123/a/456/details" in output


def test_audit_empty_and_whitespace_prompt():
    """Verify empty or whitespace prompts return empty audit cleanly without error."""
    audit_empty = audit_assignment_requirements("")
    assert audit_empty.is_complete is True
    assert len(audit_empty.automated_tasks) == 0

    audit_ws = audit_assignment_requirements("   \n\t  ")
    assert audit_ws.is_complete is True
    assert len(audit_ws.automated_tasks) == 0


def test_audit_unspecified_missing_attachment():
    """Verify generic mentions of attached files without extension flag blocker if unattached."""
    prompt = "Refer to the attached dataset to perform exploratory data analysis."
    audit = audit_assignment_requirements(prompt, attached_files=[])
    assert audit.is_complete is False
    assert len(audit.blockers) >= 1
    assert "attachment" in audit.blockers[0].reason.lower()


def test_dataclasses_to_dict_serialization():
    """Verify to_dict methods serialize dataclasses accurately."""
    item = RequirementItem(description="Test item", status="automated", reason=None)
    item_dict = item.to_dict()
    assert item_dict == {"description": "Test item", "status": "automated", "reason": None}

    audit = RequirementAudit(automated_tasks=[item], student_action_items=[], blockers=[], is_complete=True)
    audit_dict = audit.to_dict()
    assert audit_dict["is_complete"] is True
    assert len(audit_dict["automated_tasks"]) == 1

    staged = StagedDeliverable(
        course_name="Course A",
        assignment_title="Assign 1",
        staged_dir=Path("/tmp/out"),
        pdf_path=Path("/tmp/out/final_submission.pdf"),
        manifest_path=Path("/tmp/out/manifest.json"),
        summary_path=Path("/tmp/out/SUMMARY.md"),
        classroom_url=None,
        page_count=2,
        audit=audit,
    )
    staged_dict = staged.to_dict()
    assert staged_dict["course_name"] == "Course A"
    assert staged_dict["page_count"] == 2
    assert staged_dict["audit"]["is_complete"] is True


def test_stage_deliverable_directory_inputs_raise_value_error(tmp_path: Path):
    """Verify passing a directory path as PDF or asset raises ValueError."""
    import pytest

    dir_as_pdf = tmp_path / "not_a_file"
    dir_as_pdf.mkdir()

    with pytest.raises(ValueError, match="must be a file"):
        stage_deliverable(
            output_root=tmp_path / "output",
            course_name="Course X",
            assignment_title="Task Y",
            pdf_path=dir_as_pdf,
            assets=[],
        )

    valid_pdf = tmp_path / "valid.pdf"
    valid_pdf.write_text("%PDF-1.4", encoding="utf-8")
    dir_as_asset = tmp_path / "dir_asset"
    dir_as_asset.mkdir()

    with pytest.raises(ValueError, match="must be a file"):
        stage_deliverable(
            output_root=tmp_path / "output",
            course_name="Course X",
            assignment_title="Task Y",
            pdf_path=valid_pdf,
            assets=[dir_as_asset],
        )


def test_print_completion_card_blocker_and_action_variations():
    """Verify completion card renders different alert levels for blockers and action items."""
    # Blocker card
    blocked_deliverable = StagedDeliverable(
        course_name="Hardware Lab",
        assignment_title="FPGA Design",
        staged_dir=Path("/workspace/output/hardware_lab/fpga"),
        pdf_path=Path("/workspace/output/hardware_lab/fpga/final_submission.pdf"),
        manifest_path=Path("/workspace/output/hardware_lab/fpga/manifest.json"),
        summary_path=Path("/workspace/output/hardware_lab/fpga/SUMMARY.md"),
        classroom_url=None,
        page_count=1,
        audit=RequirementAudit(
            automated_tasks=[],
            student_action_items=[],
            blockers=[RequirementItem(description="Connect FPGA board", status="blocked", reason="Hardware required")],
            is_complete=False,
        ),
    )
    console_blocker = Console(record=True, width=100)
    print_completion_card(blocked_deliverable, console=console_blocker)
    output_blocker = console_blocker.export_text()
    assert "ASSIGNMENT BLOCKED" in output_blocker
    assert "1 blockers" in output_blocker

    # Action required card
    action_deliverable = StagedDeliverable(
        course_name="Ethics",
        assignment_title="Essay",
        staged_dir=Path("/workspace/output/ethics/essay"),
        pdf_path=Path("/workspace/output/ethics/essay/final_submission.pdf"),
        manifest_path=Path("/workspace/output/ethics/essay/manifest.json"),
        summary_path=Path("/workspace/output/ethics/essay/SUMMARY.md"),
        classroom_url="https://classroom.google.com/c/321/a/654/details",
        page_count=2,
        audit=RequirementAudit(
            automated_tasks=[RequirementItem(description="Write essay", status="automated")],
            student_action_items=[RequirementItem(description="Sign pledge", status="needs_student_input", reason="Signature")],
            blockers=[],
            is_complete=False,
        ),
    )
    console_action = Console(record=True, width=100)
    print_completion_card(action_deliverable, console=console_action)
    output_action = console_action.export_text()
    assert "STUDENT REVIEW REQUIRED" in output_action
    assert "1 student actions" in output_action

