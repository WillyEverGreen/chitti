"""Unit tests for the Classroom Agent Master CLI (classroom_agent.py)."""

import argparse
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import classroom_agent
from classroom.config import StudentConfig, save_config
from classroom.deliverables import RequirementAudit, RequirementItem, stage_deliverable


def test_main_parser_help(capsys):
    """Test that main parser displays help with all core subcommands."""
    parser = classroom_agent.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "setup" in captured.out
    assert "courses" in captured.out
    assert "pending" in captured.out
    assert "details" in captured.out
    assert "build" in captured.out
    assert "attach-proof" in captured.out
    assert "review" in captured.out
    assert "submit" in captured.out
    assert "notes" in captured.out
    assert "materials" in captured.out
    assert "status" in captured.out


@pytest.mark.parametrize(
    "subcommand",
    ["setup", "courses", "pending", "details", "build", "attach-proof", "review", "submit", "notes", "materials", "status"],
)
def test_subcommand_helps(subcommand, capsys):
    """Verify each subcommand provides standard --help output."""
    parser = classroom_agent.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([subcommand, "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower() or "options" in captured.out.lower()


def test_no_args_displays_help(capsys):
    """Running without arguments should exit with 0 or print help message."""
    ret = classroom_agent.main([])
    captured = capsys.readouterr()
    assert ret == 0 or ret == 2 or "usage:" in captured.out.lower() or "Classroom Agent" in captured.out


def test_setup_command_dispatch():
    """Verify setup command delegates to classroom_setup."""
    with patch("classroom_setup.run_setup", return_value=0) as mock_setup:
        ret = classroom_agent.main(["setup", "--non-interactive", "--name", "Test Student", "--roll", "12345"])
        assert ret == 0
        mock_setup.assert_called_once()
        args = mock_setup.call_args[0][0]
        assert "--non-interactive" in args
        assert "Test Student" in args
        assert "12345" in args


def test_courses_command_dispatch(capsys):
    """Verify courses command lists enrolled courses."""
    fake_courses = [
        {"id": "101", "name": "Computer Networks Lab", "section": "A", "enrollmentCode": "abc"},
        {"id": "102", "name": "Compiler Design", "section": "B", "enrollmentCode": "def"},
    ]
    with patch("classroom_manager.get_services") as mock_services:
        mock_classroom = MagicMock()
        mock_drive = MagicMock()
        mock_services.return_value = (mock_classroom, mock_drive)
        with patch("classroom_manager.list_courses", return_value=fake_courses):
            with patch("classroom_manager.display_courses") as mock_display:
                ret = classroom_agent.main(["courses"])
                assert ret == 0
                mock_display.assert_called_once_with(fake_courses)


def test_pending_command_dispatch():
    """Verify pending command lists pending coursework."""
    fake_pending = [
        {
            "course_id": "101",
            "course_name": "Computer Networks Lab",
            "work_id": "w1",
            "title": "EXPERIMENT 7",
            "description": "Implement RIP routing",
            "due_formatted": "2026-11-05 23:59 UTC",
            "is_overdue": False,
            "state": "NEW",
        }
    ]
    with patch("classroom_manager.get_services") as mock_services:
        mock_services.return_value = (MagicMock(), MagicMock())
        with patch("classroom_master.find_course", return_value={"id": "101", "name": "Networks"}):
            with patch("classroom_manager.get_pending_assignments", return_value=fake_pending) as mock_pending:
                with patch("classroom_manager.display_pending") as mock_display:
                    ret = classroom_agent.main(["pending", "--course", "Networks", "--ignore", "HMI"])
                    assert ret == 0
                    mock_display.assert_called_once_with(fake_pending)


def test_details_command_dispatch():
    """Verify details command looks up course and assignment details."""
    with patch("classroom_manager.get_services") as mock_services:
        mock_services.return_value = (MagicMock(), MagicMock())
        with patch("classroom_master.find_course", return_value={"id": "c1", "name": "Networks"}) as mock_course:
            with patch(
                "classroom_master.find_coursework",
                return_value={"id": "w1", "title": "Lab 7", "description": "Routing protocols"},
            ) as mock_cw:
                with patch("classroom_manager.get_assignment_details") as mock_details:
                    mock_details.return_value = {
                        "courseWork": {"id": "w1", "title": "Lab 7", "description": "Routing protocols"},
                        "submission": {"state": "NEW"},
                    }
                    ret = classroom_agent.main(["details", "--course", "Networks", "--assignment", "Lab 7"])
                    assert ret == 0
                    mock_course.assert_called_once()
                    mock_cw.assert_called_once()


def test_build_command_with_proof(tmp_path):
    """Verify build compiles PDF deliverable, processes proof screenshot, and stages deliverable."""
    # Create dummy proof screenshot
    proof_img = tmp_path / "terminal.png"
    img = Image.new("RGB", (640, 480), color=(30, 30, 30))
    img.save(proof_img)

    config = StudentConfig(
        student_name="Alice Smith",
        roll_number="CS-001",
        department="Computer Science",
        institution="Apex University",
        output_dir=str(tmp_path / "output"),
    )
    cfg_file = tmp_path / "student_config.json"
    save_config(config, cfg_file)

    with patch("classroom_agent.get_default_config_path", return_value=cfg_file):
        with patch("classroom_manager.get_services", side_effect=RuntimeError("Offline")):
            with patch("classroom_agent.print_completion_card") as mock_card:
                ret = classroom_agent.main([
                    "build",
                    "--course",
                    "Computer Networks",
                    "--assignment",
                    "Experiment 7",
                    "--proof",
                    str(proof_img),
                    "--proof-caption",
                    "RIP Routing Simulation Terminal Output",
                    "--config-path",
                    str(cfg_file),
                ])
                assert ret == 0
                mock_card.assert_called_once()

    staged_dir = tmp_path / "output" / "computer_networks" / "experiment_7"
    assert staged_dir.exists()
    assert (staged_dir / "final_submission.pdf").exists()
    assert (staged_dir / "manifest.json").exists()
    assert (staged_dir / "SUMMARY.md").exists()


def test_attach_proof_command(tmp_path):
    """Verify attach-proof adds screenshot proof to staged deliverable and re-renders PDF."""
    proof_img = tmp_path / "ping_result.png"
    img = Image.new("RGB", (800, 600), color=(20, 20, 20))
    img.save(proof_img)

    config = StudentConfig(
        student_name="Bob Jones",
        roll_number="CS-002",
        output_dir=str(tmp_path / "output"),
    )
    cfg_file = tmp_path / "student_config.json"
    save_config(config, cfg_file)

    # First, build a base deliverable
    with patch("classroom_agent.get_default_config_path", return_value=cfg_file):
        with patch("classroom_manager.get_services", side_effect=RuntimeError("Offline")):
            ret_build = classroom_agent.main([
                "build",
                "--course",
                "Cloud Computing",
                "--assignment",
                "Lab 10",
                "--config-path",
                str(cfg_file),
            ])
            assert ret_build == 0

            # Now attach a proof
            with patch("classroom_agent.print_completion_card") as mock_card:
                ret_attach = classroom_agent.main([
                    "attach-proof",
                    "--course",
                    "Cloud Computing",
                    "--assignment",
                    "Lab 10",
                    "--image",
                    str(proof_img),
                    "--caption",
                    "Ping and Traceroute Verification",
                    "--config-path",
                    str(cfg_file),
                ])
                assert ret_attach == 0
                mock_card.assert_called_once()

    staged_dir = tmp_path / "output" / "cloud_computing" / "lab_10"
    manifest_data = (staged_dir / "manifest.json").read_text(encoding="utf-8")
    assert "final_submission.pdf" in manifest_data
    assert "ping_result" in manifest_data


def test_review_command_empty(tmp_path, capsys):
    """Review command reports when output directory is empty."""
    config = StudentConfig(output_dir=str(tmp_path / "empty_output"))
    cfg_file = tmp_path / "student_config.json"
    save_config(config, cfg_file)

    with patch("classroom_agent.get_default_config_path", return_value=cfg_file):
        ret = classroom_agent.main(["review", "--config-path", str(cfg_file)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "no staged deliverables" in captured.out.lower() or "empty" in captured.out.lower()


def test_review_command_with_deliverables(tmp_path, capsys):
    """Review command displays staged deliverables and requirement audits."""
    output_dir = tmp_path / "output"
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy")

    audit = RequirementAudit(
        automated_tasks=[RequirementItem(description="Calculate subnets", status="automated")],
        student_action_items=[RequirementItem(description="Sign document", status="needs_student_input", reason="Signature required")],
        is_complete=False,
    )

    stage_deliverable(
        output_root=output_dir,
        course_name="Operating Systems",
        assignment_title="Lab 3",
        pdf_path=dummy_pdf,
        classroom_url="https://classroom.google.com/c/123/a/456",
        audit=audit,
    )

    config = StudentConfig(output_dir=str(output_dir))
    cfg_file = tmp_path / "student_config.json"
    save_config(config, cfg_file)

    with patch("classroom_agent.get_default_config_path", return_value=cfg_file):
        ret = classroom_agent.main(["review", "--config-path", str(cfg_file)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Operating" in captured.out
        assert "Lab 3" in captured.out


def test_submit_command_auto_detect_staged(tmp_path):
    """Submit command auto-detects staged PDF in output directory if file not specified."""
    output_dir = tmp_path / "output"
    staged_course_dir = output_dir / "cyber_security" / "assignment_1"
    staged_course_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = staged_course_dir / "final_submission.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")

    config = StudentConfig(output_dir=str(output_dir))
    cfg_file = tmp_path / "student_config.json"
    save_config(config, cfg_file)

    with patch("classroom_agent.get_default_config_path", return_value=cfg_file):
        with patch("auto_submit.execute_submission", return_value=True) as mock_exec:
            ret = classroom_agent.main([
                "submit",
                "--course",
                "Cyber Security",
                "--assignment",
                "Assignment 1",
                "--config-path",
                str(cfg_file),
            ])
            assert ret == 0
            mock_exec.assert_called_once()
            call_kwargs = mock_exec.call_args[1]
            assert call_kwargs.get("files") == [str(pdf_file)]


def test_handle_classroom_error_branches(capsys):
    """Test all diagnostic branches of handle_classroom_error."""
    from classroom_agent import handle_classroom_error

    # Missing credentials
    ret = handle_classroom_error(FileNotFoundError("credentials.json not found"))
    assert ret == 1
    assert "Google Credentials Needed" in capsys.readouterr().out

    # Classroom API disabled
    ret = handle_classroom_error(Exception("Google Classroom API has not been used or it is disabled"))
    assert ret == 1
    out = capsys.readouterr().out
    assert "classroom.googleapis.com" in out

    # Drive API disabled
    ret = handle_classroom_error(Exception("Google Drive API has not been used or it is disabled"))
    assert ret == 1
    out = capsys.readouterr().out
    assert "drive.googleapis.com" in out

    # Access denied / test user
    ret = handle_classroom_error(Exception("Error 403: access_denied - not authorized"))
    assert ret == 1
    out = capsys.readouterr().out
    assert "Test User" in out

    # College admin policy
    ret = handle_classroom_error(Exception("admin_policy_enforced error"))
    assert ret == 1
    out = capsys.readouterr().out
    assert "College Organization Policy" in out


def test_notes_command_dispatch(tmp_path):
    """Test notes subcommand creates notes.md and notes.pdf in course workspace."""
    out_dir = tmp_path / "notes_output"
    cfg = StudentConfig(output_dir=str(out_dir))
    cfg_file = tmp_path / "cfg.json"
    save_config(cfg, cfg_file)

    ret = classroom_agent.main([
        "notes",
        "--course", "Computer Networks",
        "--topic", "TCP Three-Way Handshake",
        "--theory", "SYN, SYN-ACK, ACK establishes reliable transmission.",
        "--formulas", "RTT = 2 * Propagation Delay",
        "--config-path", str(cfg_file),
    ])
    assert ret == 0

    expected_md = out_dir / "computer_networks" / "notes" / "tcp_three_way_handshake" / "notes.md"
    expected_pdf = out_dir / "computer_networks" / "notes" / "tcp_three_way_handshake" / "notes.pdf"
    assert expected_md.exists()
    assert expected_pdf.exists()
    assert "SYN, SYN-ACK, ACK" in expected_md.read_text(encoding="utf-8")


def test_materials_command_local_pdf(tmp_path):
    """Test materials subcommand with local PDF extracts text into course workspace."""
    import pymupdf as fitz
    out_dir = tmp_path / "mat_output"
    cfg = StudentConfig(output_dir=str(out_dir))
    cfg_file = tmp_path / "cfg.json"
    save_config(cfg, cfg_file)

    sample_pdf = tmp_path / "lab_instructions.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Important: Complete all Wireshark captures before Monday.")
    doc.save(str(sample_pdf))
    doc.close()

    ret = classroom_agent.main([
        "materials",
        "--course", "Computer Networks",
        "--file", str(sample_pdf),
        "--config-path", str(cfg_file),
    ])
    assert ret == 0

    expected_txt = out_dir / "computer_networks" / "materials" / "lab_instructions_extracted.txt"
    assert expected_txt.exists()
    assert "Wireshark" in expected_txt.read_text(encoding="utf-8")


def test_status_command_dispatch(tmp_path):
    """Test status subcommand displays unified dashboard."""
    out_dir = tmp_path / "dashboard_output"
    cfg = StudentConfig(
        student_name="Sai Balkawade",
        roll_number="10707",
        department="Computer Engineering",
        institution="Fr. CRCE",
        output_dir=str(out_dir),
    )
    cfg_file = tmp_path / "cfg.json"
    save_config(cfg, cfg_file)

    ret = classroom_agent.main([
        "status",
        "--config-path", str(cfg_file),
    ])
    assert ret == 0


def test_build_personalize_mode(tmp_path):
    """Test build command with --mode personalize redacts old student details."""
    import pymupdf as fitz
    out_dir = tmp_path / "out_pers"
    cfg = StudentConfig(
        student_name="Sai Balkawade",
        roll_number="10707",
        output_dir=str(out_dir),
    )
    cfg_file = tmp_path / "cfg.json"
    save_config(cfg, cfg_file)

    ref_pdf = tmp_path / "senior_assignment.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Lab 2: Process Scheduling\nAuthor: Bob Vance (Roll: 88888)")
    doc.save(str(ref_pdf))
    doc.close()

    ret = classroom_agent.main([
        "build",
        "--course", "Operating Systems",
        "--assignment", "Lab 2",
        "--template", str(ref_pdf),
        "--mode", "personalize",
        "--old-name", "Bob Vance",
        "--old-roll", "88888",
        "--config-path", str(cfg_file),
    ])
    assert ret == 0

    staged_pdf = out_dir / "operating_systems" / "lab_2" / "final_submission.pdf"
    assert staged_pdf.exists()

    doc_out = fitz.open(str(staged_pdf))
    text = doc_out[0].get_text()
    doc_out.close()
    assert "Sai Balkawade" in text
    assert "10707" in text
    assert "Bob Vance" not in text


def test_build_with_code_theory_and_sections(tmp_path):
    """Test build command with --code, --theory, and --sections-file flags."""
    import json
    import pymupdf as fitz
    out_dir = tmp_path / "out_rich"
    cfg = StudentConfig(
        student_name="Test Student",
        roll_number="99901",
        output_dir=str(out_dir),
    )
    cfg_file = tmp_path / "cfg.json"
    save_config(cfg, cfg_file)

    code_file = tmp_path / "solution.py"
    code_file.write_text("def solve():\n    return 42\n", encoding="utf-8")

    theory_file = tmp_path / "theory.txt"
    theory_file.write_text("Theoretical analysis of time complexity O(N log N).", encoding="utf-8")

    sections_file = tmp_path / "custom_sections.json"
    sections_file.write_text(json.dumps([
        {"type": "heading", "text": "Custom Lab Section"},
        {"type": "paragraph", "text": "This paragraph was loaded from JSON sections file."},
    ]), encoding="utf-8")

    ret = classroom_agent.main([
        "build",
        "--course", "Data Structures",
        "--assignment", "Lab 1",
        "--code", str(code_file),
        "--theory", str(theory_file),
        "--sections-file", str(sections_file),
        "--config-path", str(cfg_file),
    ])
    assert ret == 0

    staged_pdf = out_dir / "data_structures" / "lab_1" / "final_submission.pdf"
    assert staged_pdf.exists()

    doc = fitz.open(str(staged_pdf))
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    assert "Custom Lab Section" in full_text
    assert "Theoretical analysis of time complexity" in full_text
    assert "def solve():" in full_text
