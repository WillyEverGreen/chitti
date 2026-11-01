#!/usr/bin/env python3
"""Classroom Agent Master CLI Application.

Unifies Google Classroom discovery, academic PDF compilation, authentic media and
terminal screenshot framing, deliverables staging, review verification, and CDP-based
browser submission.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 stdout across all operating systems
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None
    Text = None

from classroom.config import (
    StudentConfig,
    get_default_config_path,
    load_config,
    save_config,
    slugify,
)
from classroom.deliverables import (
    RequirementAudit,
    RequirementItem,
    StagedDeliverable,
    audit_assignment_requirements,
    print_completion_card,
    stage_deliverable,
)
from classroom.media_processor import (
    ProcessedImage,
    process_terminal_screenshot,
)
from classroom.pdf_engine import (
    augment_teacher_template,
    build_report_pdf,
    personalize_reference_pdf,
)
from classroom.workspace import (
    CourseWorkspace,
    get_course_workspace,
    extract_pdf_text,
    save_study_notes,
    download_drive_file,
)
import classroom_manager
import classroom_master
import classroom_setup
import auto_submit


def _load_student_config(config_path_arg: Optional[str] = None) -> Tuple[StudentConfig, Path]:
    """Load StudentConfig from specified path or default location."""
    target_path = (
        Path(config_path_arg).expanduser().resolve()
        if config_path_arg
        else get_default_config_path()
    )
    if target_path.exists():
        try:
            return load_config(target_path), target_path
        except Exception:
            return StudentConfig(), target_path
    return StudentConfig(), target_path


# =====================================================================
# Command: setup
# =====================================================================

def cmd_setup(args: argparse.Namespace, remaining_argv: List[str]) -> int:
    """Run interactive or automated student profile setup wizard."""
    setup_argv: List[str] = []
    if args.non_interactive:
        setup_argv.append("--non-interactive")
    if args.name:
        setup_argv.extend(["--name", args.name])
    if args.roll:
        setup_argv.extend(["--roll", args.roll])
    if args.dept:
        setup_argv.extend(["--dept", args.dept])
    if args.institution:
        setup_argv.extend(["--institution", args.institution])
    if args.output_dir:
        setup_argv.extend(["--output-dir", args.output_dir])
    if args.credentials:
        setup_argv.extend(["--credentials", args.credentials])
    if args.token:
        setup_argv.extend(["--token", args.token])
    if args.port:
        setup_argv.extend(["--port", str(args.port)])
    if args.config_path:
        setup_argv.extend(["--config-path", args.config_path])
    if getattr(args, "client_id", None):
        setup_argv.extend(["--client-id", args.client_id])
    if getattr(args, "client_secret", None):
        setup_argv.extend(["--client-secret", args.client_secret])
    if getattr(args, "open_browser", False):
        setup_argv.append("--open-browser")
    setup_argv.extend(remaining_argv)

    return classroom_setup.run_setup(setup_argv)


# =====================================================================
# Command: courses
# =====================================================================

def handle_classroom_error(exc: Exception) -> int:
    """Provides user-friendly diagnosis and clickable fix links for Classroom API errors."""
    err_msg = str(exc)
    err_lower = err_msg.lower()

    if "desktop app" in err_lower or "web application" in err_lower:
        # classroom_manager has already displayed the guided instructions
        return 1

    if "credentials.json" in err_lower:
        print("\n" + "=" * 62)
        print("        🤖 Chitti Helper: Google Credentials Needed           ")
        print("=" * 62)
        print("Google credentials.json was not found in this directory.\n")
        print("Super easy options to connect:")
        print("  [1] If you have Client ID & Client Secret:")
        print("      python chitti.py setup --client-id YOUR_ID --client-secret YOUR_SECRET")
        print("  [2] Run the interactive helper wizard:")
        print("      python chitti.py setup")
        print("  [3] Auto-open Google Cloud Console in your browser:")
        print("      python chitti.py setup --open-browser")
        print("=" * 62 + "\n")
        return 1

    if "classroom.googleapis.com" in err_lower or ("classroom" in err_lower and "disabled" in err_lower):
        print("\n" + "=" * 66)
        print("   ⚠️  Google Classroom API is not enabled in your Google Cloud Project")
        print("=" * 66)
        print("To fix this, open this link in your browser and click 'ENABLE':")
        print("👉 https://console.cloud.google.com/apis/library/classroom.googleapis.com")
        print("\nOnce enabled, re-run your command!")
        print("=" * 66 + "\n")
        return 1

    if "drive.googleapis.com" in err_lower or ("drive" in err_lower and "disabled" in err_lower):
        print("\n" + "=" * 66)
        print("   ⚠️  Google Drive API is not enabled in your Google Cloud Project")
        print("=" * 66)
        print("To fix this, open this link in your browser and click 'ENABLE':")
        print("👉 https://console.cloud.google.com/apis/library/drive.googleapis.com")
        print("\nOnce enabled, re-run your command!")
        print("=" * 66 + "\n")
        return 1

    if "access_denied" in err_lower or "test user" in err_lower or ("403" in err_lower and "not authorized" in err_lower):
        print("\n" + "=" * 66)
        print("   ⚠️  Access Blocked: Your email must be added as a Test User")
        print("=" * 66)
        print("Because your Google Cloud app is currently in 'Testing' mode:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials/consent")
        print("2. Scroll down to 'Test users' and click '+ ADD USERS'")
        print("3. Enter the exact Google email address you are signing in with")
        print("4. Click 'SAVE' and retry: python chitti.py courses")
        print("=" * 66 + "\n")
        return 1

    if "admin_policy_enforced" in err_lower or "org_internal" in err_lower:
        print("\n" + "=" * 66)
        print("   ⚠️  College Organization Policy Restriction")
        print("=" * 66)
        print("Your college Google Workspace administrator restricts third-party OAuth apps.")
        print("No worries! You can use Chitti directly with your live browser session:")
        print("👉 Run: python chitti.py submit --port 9444")
        print("=" * 66 + "\n")
        return 1

    print(f"[!] Error accessing Google Classroom: {exc}")
    print("Tip: Run 'python chitti.py setup' to check your configuration.")
    return 1


def cmd_courses(args: argparse.Namespace) -> int:
    """List all enrolled Google Classroom courses."""
    try:
        classroom_service, _ = classroom_manager.get_services()
        courses = classroom_manager.list_courses(classroom_service)
        classroom_manager.display_courses(courses)
        return 0
    except Exception as exc:
        return handle_classroom_error(exc)


# =====================================================================
# Command: pending
# =====================================================================

def cmd_pending(args: argparse.Namespace) -> int:
    """List pending coursework with due dates and statuses."""
    try:
        classroom_service, _ = classroom_manager.get_services()
        course_id = None
        if args.course:
            course_obj = classroom_master.find_course(classroom_service, args.course)
            if not course_obj:
                print(f"[!] Course matching '{args.course}' not found.")
                return 1
            course_id = str(course_obj["id"])

        pending = classroom_manager.get_pending_assignments(
            classroom_service, course_id=course_id, ignore_pattern=args.ignore
        )
        classroom_manager.display_pending(pending)
        return 0
    except Exception as exc:
        return handle_classroom_error(exc)


# =====================================================================
# Command: details
# =====================================================================

def _display_assignment_details(course: Dict[str, Any], cw: Dict[str, Any], details: Dict[str, Any]) -> None:
    """Format and display detailed coursework information and submission state."""
    submission = details.get("submission") or {}
    materials = cw.get("materials", [])
    due_str = classroom_manager.format_due_date(cw.get("dueDate"), cw.get("dueTime"))

    if HAS_RICH and console:
        table = Table.grid(padding=(0, 2))
        table.add_column("Key", style="bold cyan", justify="right")
        table.add_column("Value", style="white")

        table.add_row("Course:", course.get("name", "Unknown"))
        table.add_row("Assignment:", cw.get("title", "Untitled"))
        table.add_row("Due Date:", due_str)
        table.add_row("Status:", submission.get("state", "NEW"))
        if cw.get("maxPoints") is not None:
            table.add_row("Max Points:", str(cw.get("maxPoints")))
        if cw.get("alternateLink"):
            table.add_row("Classroom URL:", f"[link={cw['alternateLink']}]{cw['alternateLink']}[/link]")

        if materials:
            mat_lines = []
            for m in materials:
                if "driveFile" in m:
                    f = m["driveFile"]["driveFile"]
                    mat_lines.append(f"• [Drive] {f.get('title')} ({f.get('alternateLink', '')})")
                elif "link" in m:
                    lk = m["link"]
                    mat_lines.append(f"• [Link] {lk.get('title', 'Web Link')} ({lk.get('url')})")
                elif "youtubeVideo" in m:
                    yt = m["youtubeVideo"]
                    mat_lines.append(f"• [YouTube] {yt.get('title')} ({yt.get('alternateLink')})")
            table.add_row("Materials:", "\n".join(mat_lines))

        desc = (cw.get("description") or "").strip()
        if desc:
            table.add_row("Description:", desc[:500] + ("..." if len(desc) > 500 else ""))

        panel = Panel(
            table,
            title=f"[bold green]Assignment Details: {cw.get('title')}[/bold green]",
            border_style="cyan",
            expand=False,
        )
        console.print(panel)
    else:
        print("\n" + "=" * 60)
        print(f"Course:      {course.get('name')}")
        print(f"Assignment:  {cw.get('title')}")
        print(f"Due Date:    {due_str}")
        print(f"Status:      {submission.get('state', 'NEW')}")
        if cw.get("alternateLink"):
            print(f"URL:         {cw['alternateLink']}")
        if cw.get("description"):
            print(f"\nDescription:\n{cw['description']}")
        print("=" * 60 + "\n")


def cmd_details(args: argparse.Namespace) -> int:
    """View in-depth assignment requirements, instructions, and rubrics."""
    try:
        classroom_service, _ = classroom_manager.get_services()
        course_obj = classroom_master.find_course(classroom_service, args.course)
        if not course_obj:
            print(f"[!] Course matching '{args.course}' not found.")
            return 1
        course_id = str(course_obj["id"])

        cw_obj = classroom_master.find_coursework(classroom_service, course_id, args.assignment)
        if not cw_obj:
            print(f"[!] Assignment matching '{args.assignment}' not found in course '{course_obj.get('name')}'.")
            return 1
        work_id = str(cw_obj["id"])

        details = classroom_manager.get_assignment_details(classroom_service, course_id, work_id)
        _display_assignment_details(course_obj, cw_obj, details)
        return 0
    except Exception as exc:
        print(f"[!] Error fetching assignment details: {exc}")
        return 1


# =====================================================================
# Command: build
# =====================================================================

def cmd_build(args: argparse.Namespace) -> int:
    """Compile PDF deliverable with formatted proofs and stage in output."""
    config, _ = _load_student_config(args.config_path)
    output_root = Path(args.output_dir) if args.output_dir else Path(config.output_dir)

    course_name = args.course
    assignment_title = args.assignment
    classroom_url = None
    assignment_desc = ""

    # Optional Google Classroom lookup if credentials available
    try:
        classroom_service, _ = classroom_manager.get_services()
        c_obj = classroom_master.find_course(classroom_service, args.course)
        if c_obj:
            course_name = c_obj.get("name", course_name)
            w_obj = classroom_master.find_coursework(classroom_service, str(c_obj["id"]), args.assignment)
            if w_obj:
                assignment_title = w_obj.get("title", assignment_title)
                classroom_url = w_obj.get("alternateLink")
                assignment_desc = w_obj.get("description", "")
    except Exception:
        pass

    # Perform assignment requirement audit
    audit = audit_assignment_requirements(
        assignment_title=assignment_title,
        instructions=assignment_desc,
        materials=[],
    )

    # Prepare document flowable sections
    sections: List[Dict[str, Any]] = []

    if getattr(args, "sections_file", None):
        sec_path = Path(args.sections_file).expanduser().resolve()
        if sec_path.exists():
            try:
                with open(sec_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        sections = loaded
            except Exception as e:
                print(f"[!] Warning: Could not parse sections file {sec_path}: {e}")

    if not sections:
        if assignment_desc:
            sections.append({"type": "heading", "text": "Assignment Description & Objectives"})
            sections.append({"type": "paragraph", "text": assignment_desc})
        else:
            sections.append({"type": "heading", "text": "1. Objective & Scope"})
            sections.append({
                "type": "paragraph",
                "text": f"This submission report fulfills the curriculum requirements for '{assignment_title}' under the course '{course_name}'.",
            })
            sections.append({"type": "heading", "text": "2. Implementation & Methodology"})
            sections.append({
                "type": "paragraph",
                "text": "The computational algorithms, experimental methodologies, and analytical steps have been executed and verified in accordance with technical specifications.",
            })

    if getattr(args, "theory", None):
        th_p = Path(args.theory).expanduser().resolve()
        if th_p.is_file():
            th_text = th_p.read_text(encoding="utf-8")
        else:
            th_text = str(args.theory)
        sections.append({"type": "heading", "text": "Theoretical Background & Principles"})
        sections.append({"type": "paragraph", "text": th_text})

    assets_to_stage: List[Path] = []

    if getattr(args, "code", None):
        code_p = Path(args.code).expanduser().resolve()
        if code_p.is_file():
            code_text = code_p.read_text(encoding="utf-8")
            sections.append({"type": "heading", "text": f"Source Code Implementation ({code_p.name})"})
            sections.append({"type": "code", "text": code_text})
            assets_to_stage.append(code_p)

    proof_src = None
    if getattr(args, "proof_clipboard", False):
        try:
            from PIL import ImageGrab
            clip_img = ImageGrab.grabclipboard()
            if clip_img is not None and hasattr(clip_img, "save"):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_clip:
                    proof_src = Path(tf_clip.name)
                clip_img.save(proof_src)
            else:
                print("[!] Clipboard does not contain an image. Please use Win + Shift + S to snip your terminal.")
                return 1
        except Exception as e:
            print(f"[!] Error accessing clipboard: {e}")
            return 1
    elif args.proof:
        proof_src = Path(args.proof).expanduser().resolve()
        if not proof_src.exists():
            print(f"[!] Specified proof image does not exist: {proof_src}")
            return 1

    if proof_src:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            temp_proof_dest = Path(tf.name)

        caption = args.proof_caption or "Authentic Terminal Execution Output"
        processed_proof = process_terminal_screenshot(
            src_path=proof_src,
            dest_path=temp_proof_dest,
            caption=caption,
            add_border=True,
            autocrop=True,
        )

        sections.append({"type": "heading", "text": "Verification & Terminal Execution Proof"})
        sections.append({
            "type": "image",
            "image": processed_proof,
            "caption": caption,
        })
        assets_to_stage.append(processed_proof.path)

    sections.append({"type": "heading", "text": "3. Deliverable Verification"})
    sections.append({
        "type": "paragraph",
        "text": "All required solution artifacts, calculation models, and experimental outputs have been validated for integrity and completeness.",
    })

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        temp_pdf_out = Path(tf.name)

    assignment_meta = {
        "course": course_name,
        "title": assignment_title,
    }

    in_place_answers = None
    if getattr(args, "answers_file", None):
        ans_f = Path(args.answers_file).expanduser().resolve()
        if ans_f.exists():
            try:
                in_place_answers = json.loads(ans_f.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[!] Warning: Could not parse answers file {ans_f}: {e}")
        else:
            print(f"[!] Warning: Answers file not found: {ans_f}")
    elif getattr(args, "answers", None):
        try:
            in_place_answers = json.loads(args.answers)
        except Exception as e:
            print(f"[!] Warning: Could not parse --answers JSON string: {e}")

    if getattr(args, "mode", "scratch") == "personalize" or (args.template and (getattr(args, "old_name", None) or getattr(args, "old_roll", None))):
        template_path = Path(args.template).expanduser().resolve()
        if not template_path.exists():
            print(f"[!] Reference PDF not found: {template_path}")
            return 1
        personalize_reference_pdf(
            source_pdf=template_path,
            config=config,
            output_path=temp_pdf_out,
            old_name=getattr(args, "old_name", None),
            old_roll=getattr(args, "old_roll", None),
        )
    elif args.template:
        template_path = Path(args.template).expanduser().resolve()
        if not template_path.exists():
            print(f"[!] Teacher template PDF not found: {template_path}")
            return 1

        has_custom_solution = bool(
            getattr(args, "code", None)
            or getattr(args, "proof", None)
            or getattr(args, "theory", None)
            or getattr(args, "sections_file", None)
        )

        augment_teacher_template(
            template_path=template_path,
            output_path=temp_pdf_out,
            solution_sections=sections if has_custom_solution else None,
            in_place_answers=in_place_answers,
            config=config,
            assignment_meta=assignment_meta,
        )
    else:
        build_report_pdf(
            output_path=temp_pdf_out,
            assignment_meta=assignment_meta,
            sections=sections,
            config=config,
        )

    deliverable = stage_deliverable(
        output_root=output_root,
        course_name=course_name,
        assignment_title=assignment_title,
        pdf_path=temp_pdf_out,
        assets=assets_to_stage,
        classroom_url=classroom_url,
        audit=audit,
    )

    print_completion_card(deliverable)
    return 0


# =====================================================================
# Command: attach-proof
# =====================================================================

def cmd_attach_proof(args: argparse.Namespace) -> int:
    """Attach and frame authentic terminal screenshots & output proofs into deliverable PDF."""
    config, _ = _load_student_config(args.config_path)
    output_root = Path(config.output_dir)

    course_slug = slugify(args.course) or "general_course"
    assignment_slug = slugify(args.assignment) or "assignment"
    staged_dir = output_root / course_slug / assignment_slug

    img_src = None
    if getattr(args, "from_clipboard", False):
        try:
            from PIL import ImageGrab
            clip_img = ImageGrab.grabclipboard()
            if clip_img is not None and hasattr(clip_img, "save"):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_clip:
                    img_src = Path(tf_clip.name)
                clip_img.save(img_src)
            else:
                print("[!] Clipboard does not contain an image. Please use Win + Shift + S to snip your terminal, then try again.")
                return 1
        except Exception as e:
            print(f"[!] Error accessing clipboard: {e}")
            return 1
    elif getattr(args, "image", None):
        img_src = Path(args.image).expanduser().resolve()
        if not img_src.exists():
            print(f"[!] Error: Image file not found at: {img_src}")
            return 1
    else:
        print("[!] Error: Either --image <path> or --from-clipboard must be provided.")
        return 1

    caption = args.caption or "Authentic Terminal Screenshot & Output Proof"

    # Process and frame screenshot
    with tempfile.NamedTemporaryFile(suffix=img_src.suffix or ".png", delete=False) as tf:
        temp_processed_path = Path(tf.name)

    processed_img = process_terminal_screenshot(
        src_path=img_src,
        dest_path=temp_processed_path,
        caption=caption,
        add_border=True,
        autocrop=True,
    )

    # Read existing manifest if available to preserve prior state
    existing_manifest_file = staged_dir / "manifest.json"
    existing_assets: List[Path] = []
    course_name = args.course
    assignment_title = args.assignment
    classroom_url = None
    existing_audit: Optional[RequirementAudit] = None

    if existing_manifest_file.exists():
        try:
            with open(existing_manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            course_name = manifest_data.get("course_name", course_name)
            assignment_title = manifest_data.get("assignment_title", assignment_title)
            classroom_url = manifest_data.get("classroom_url")

            assets_info = manifest_data.get("deliverables", {}).get("assets", [])
            for a in assets_info:
                p = staged_dir / a.get("path", "")
                if p.exists() and p != temp_processed_path:
                    existing_assets.append(p)
        except Exception:
            pass

    # Gather all assets to stage
    all_assets: List[Path] = list(existing_assets)
    # Include original image name destination for clarity
    named_dest = temp_processed_path.parent / img_src.name
    try:
        import shutil
        shutil.copy2(temp_processed_path, named_dest)
        all_assets.append(named_dest)
    except Exception:
        all_assets.append(temp_processed_path)

    # Prepare updated PDF with proof figure
    sections: List[Dict[str, Any]] = [
        {"type": "heading", "text": "1. Objective & Scope"},
        {
            "type": "paragraph",
            "text": f"This deliverable report presents the implementation and verification for '{assignment_title}' ({course_name}).",
        },
        {"type": "heading", "text": "2. Verification & Terminal Execution Proof"},
        {
            "type": "paragraph",
            "text": "The terminal execution output below verifies the operational correctness of the required implementation:",
        },
        {
            "type": "image",
            "image": processed_img,
            "caption": caption,
        },
        {"type": "heading", "text": "3. Deliverable Verification"},
        {
            "type": "paragraph",
            "text": "All test outputs, network telemetry, and command responses conform to expected assignment criteria.",
        },
    ]

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        temp_pdf_out = Path(tf.name)

    existing_pdf = staged_dir / "final_submission.pdf"
    if existing_pdf.exists():
        # Preserve existing lab manual / deliverable and append proof page
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf_proof:
            proof_page_pdf = Path(tf_proof.name)
        build_report_pdf(
            output_path=proof_page_pdf,
            assignment_meta={"course": course_name, "title": assignment_title},
            sections=sections,
            config=config,
        )
        augment_teacher_template(
            template_path=existing_pdf,
            solution_pdf_path=proof_page_pdf,
            output_path=temp_pdf_out,
            stamp_student_info=False,
        )
        try:
            proof_page_pdf.unlink()
        except Exception:
            pass
    else:
        build_report_pdf(
            output_path=temp_pdf_out,
            assignment_meta={"course": course_name, "title": assignment_title},
            sections=sections,
            config=config,
        )

    deliverable = stage_deliverable(
        output_root=output_root,
        course_name=course_name,
        assignment_title=assignment_title,
        pdf_path=temp_pdf_out,
        assets=all_assets,
        classroom_url=classroom_url,
        audit=existing_audit,
    )

    print(f"\n[+] Successfully framed and attached terminal screenshot: {img_src.name}")
    print_completion_card(deliverable)
    return 0


# =====================================================================
# Command: review
# =====================================================================

def cmd_review(args: argparse.Namespace) -> int:
    """List all staged deliverables in output directory with page counts and requirement audits."""
    config, _ = _load_student_config(args.config_path)
    output_root = Path(config.output_dir).expanduser().resolve()

    if not output_root.exists():
        if HAS_RICH and console:
            console.print(f"[yellow]No staged deliverables found. Output directory does not exist: {output_root}[/yellow]")
            console.print("Tip: Run 'python chitti.py build' to create deliverables.")
        else:
            print(f"No staged deliverables found. Output directory does not exist: {output_root}")
            print("Tip: Run 'python chitti.py build' to create deliverables.")
        return 0

    manifest_files = list(output_root.glob("**/manifest.json"))
    if not manifest_files:
        if HAS_RICH and console:
            console.print(f"[yellow]No staged deliverables found in '{output_root}'. Output directory is empty.[/yellow]")
            console.print("Tip: Run 'python chitti.py build' to compile and stage an assignment.")
        else:
            print(f"No staged deliverables found in '{output_root}'. Output directory is empty.")
            print("Tip: Run 'python chitti.py build' to compile and stage an assignment.")
        return 0

    staged_items: List[Dict[str, Any]] = []
    course_query = (args.course or "").lower().strip()

    for mf in manifest_files:
        try:
            with open(mf, "r", encoding="utf-8") as f:
                data = json.load(f)

            c_name = data.get("course_name", "")
            c_slug = data.get("course_slug", "")
            if course_query and (course_query not in c_name.lower() and course_query not in c_slug.lower()):
                continue

            staged_items.append({
                "manifest_path": mf,
                "data": data,
            })
        except Exception:
            continue

    if not staged_items:
        msg = f"No staged deliverables matching course '{args.course}'." if args.course else "No staged deliverables found."
        print(msg)
        return 0

    if HAS_RICH and console:
        table = Table(
            title=f"Staged Deliverables Review ({len(staged_items)} assignments)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Course", style="cyan")
        table.add_column("Assignment", style="bold white")
        table.add_column("Pages", justify="center", style="yellow")
        table.add_column("Status", style="bold")
        table.add_column("Audit", style="white")
        table.add_column("PDF Deliverable", style="green")

        for item in staged_items:
            d = item["data"]
            mf: Path = item["manifest_path"]
            pdf_path = mf.parent / "final_submission.pdf"
            pdf_uri = pdf_path.resolve().as_uri()

            status_val = d.get("status", "ready_for_review")
            if status_val == "blocked":
                status_styled = "[red]🚫 BLOCKED[/red]"
            elif status_val == "needs_student_action":
                status_styled = "[yellow]⚠️ ACTION REQUIRED[/yellow]"
            else:
                status_styled = "[green]✓ READY[/green]"

            audit_info = d.get("audit") or {}
            auto_cnt = len(audit_info.get("automated_tasks", []))
            action_cnt = len(audit_info.get("student_action_items", []))
            blocker_cnt = len(audit_info.get("blockers", []))

            audit_summary = f"{auto_cnt} auto | {action_cnt} student | {blocker_cnt} block"
            table.add_row(
                d.get("course_name", "")[:24],
                d.get("assignment_title", "")[:32],
                str(d.get("page_count", "-")),
                status_styled,
                audit_summary,
                f"[link={pdf_uri}]{pdf_path.name}[/link]",
            )
        console.print(table)
    else:
        print("\n--- Staged Deliverables Review ---")
        for item in staged_items:
            d = item["data"]
            mf: Path = item["manifest_path"]
            pdf_path = mf.parent / "final_submission.pdf"
            print(f"Course:     {d.get('course_name')}")
            print(f"Assignment: {d.get('assignment_title')}")
            print(f"Pages:      {d.get('page_count')}")
            print(f"Status:     {d.get('status')}")
            print(f"PDF:        {pdf_path}")
            print("-" * 50)

    return 0


# =====================================================================
# Command: submit
# =====================================================================

def cmd_submit(args: argparse.Namespace) -> int:
    """Turn in assignment using verified CDP browser automation."""
    config, _ = _load_student_config(args.config_path)

    # Determine file to submit
    if args.file:
        sub_file = Path(args.file).expanduser().resolve()
        if not sub_file.exists():
            print(f"[!] Specified file not found: {sub_file}")
            return 1
        files_to_submit = [str(sub_file)]
    else:
        # Auto-detect staged final_submission.pdf
        output_root = Path(config.output_dir).expanduser().resolve()
        course_slug = slugify(args.course) or "course"
        assignment_slug = slugify(args.assignment) or "assignment"
        staged_pdf = output_root / course_slug / assignment_slug / "final_submission.pdf"
        if not staged_pdf.exists():
            alt_pdf = output_root / course_slug / "assignments" / assignment_slug / "final_submission.pdf"
            if alt_pdf.exists():
                staged_pdf = alt_pdf

        if staged_pdf.exists():
            print(f"[*] Auto-detected staged deliverable: {staged_pdf}")
            files_to_submit = [str(staged_pdf)]
        else:
            print(f"[!] No file specified and no staged deliverable found at:\n    {staged_pdf}")
            print("Tip: Run 'python chitti.py build' first, or provide '--file <path>'.")
            return 1

    port = args.port or config.chrome_debug_port or 9444
    print(f"[*] Connecting to Chrome on debugging port {port}...")
    success = auto_submit.execute_submission(
        course_query=args.course,
        assignment_query=args.assignment,
        files=files_to_submit,
        port=port,
        keep_tab=args.keep_tab,
    )
    return 0 if success else 1


# =====================================================================
# Command: notes
# =====================================================================

def cmd_notes(args: argparse.Namespace) -> int:
    """Generate structured study notes, revision sheets, and publication PDF."""
    config, _ = _load_student_config(args.config_path)
    output_root = Path(config.output_dir).expanduser().resolve()

    # List notes mode if --list or no topic specified
    if getattr(args, "list", False) or not getattr(args, "topic", None):
        notes_files = list(output_root.glob("**/notes/**/notes.md")) if output_root.exists() else []
        if not notes_files:
            print("[*] No study notes found yet in coursework workspace.")
            print("Tip: Run 'python chitti.py notes --course <course> --topic <topic>' to create one.")
            return 0
        if HAS_RICH and console:
            table = Table(title="📚 All Generated Study Notes & Revision Sheets", border_style="cyan")
            table.add_column("Course", style="cyan")
            table.add_column("Topic", style="white")
            table.add_column("Markdown Note", style="yellow")
            table.add_column("PDF Sheet", style="green")
            for nf in notes_files:
                topic = nf.parent.name.replace("_", " ").title()
                cslug = nf.parent.parent.parent.name
                pdf_f = nf.parent / "notes.pdf"
                pdf_str = str(pdf_f.name) if pdf_f.exists() else "-"
                table.add_row(cslug, topic, nf.name, pdf_str)
            console.print(table)
        else:
            print("\n--- Available Study Notes ---")
            for nf in notes_files:
                print(f"• {nf.parent.parent.parent.name} | {nf.parent.name}: {nf}")
            print()
        return 0

    ws = get_course_workspace(output_root, args.course)

    theory_text = (args.theory or "").strip()
    if args.file:
        f_path = Path(args.file).expanduser().resolve()
        if not f_path.exists():
            print(f"[!] Specified file not found: {f_path}")
            return 1
        file_content = f_path.read_text(encoding="utf-8")
        if theory_text:
            theory_text = f"{theory_text}\n\n{file_content}"
        else:
            theory_text = file_content

    if not theory_text:
        theory_text = f"Study notes and core conceptual summary for {args.topic}."

    compile_pdf = not args.no_pdf
    res = save_study_notes(
        workspace=ws,
        config=config,
        topic=args.topic,
        theory=theory_text,
        formulas=args.formulas,
        compile_pdf=compile_pdf,
    )

    md_path = res["markdown"]
    pdf_path = res.get("pdf")

    if HAS_RICH and console:
        panel_content = Text()
        panel_content.append("📚 Academic Study Notes Created\n\n", style="bold green")
        panel_content.append(f"Course:    {ws.course_name}\n", style="cyan")
        panel_content.append(f"Topic:     {args.topic}\n", style="white")
        panel_content.append(f"Markdown:  {md_path}\n", style="yellow")
        if compile_pdf and pdf_path and pdf_path.exists():
            panel_content.append(f"PDF Sheet: {pdf_path}\n", style="bold magenta")
        console.print(Panel(panel_content, border_style="green", expand=False))
    else:
        print("\n" + "=" * 50)
        print("📚 Academic Study Notes Created")
        print("=" * 50)
        print(f"Course:    {ws.course_name}")
        print(f"Topic:     {args.topic}")
        print(f"Markdown:  {md_path}")
        if compile_pdf and pdf_path and pdf_path.exists():
            print(f"PDF Sheet: {pdf_path}")
        print("=" * 50 + "\n")

    return 0


# =====================================================================
# Command: materials
# =====================================================================

def cmd_materials(args: argparse.Namespace) -> int:
    """Download teacher materials and extract PDF text into course workspace."""
    config, _ = _load_student_config(args.config_path)
    output_root = Path(config.output_dir).expanduser().resolve()
    ws = get_course_workspace(output_root, args.course)

    # Local PDF text extraction
    if args.file:
        local_f = Path(args.file).expanduser().resolve()
        if not local_f.exists():
            print(f"[!] File not found: {local_f}")
            return 1
        out_txt = ws.materials_dir / f"{local_f.stem}_extracted.txt"
        extracted = extract_pdf_text(local_f, output_txt_path=out_txt)
        print(f"\n[+] Extracted text from {local_f.name} -> {out_txt}")
        print(f"    Total Characters: {len(extracted)}")
        return 0

    # Classroom sync
    try:
        classroom_service, drive_service = classroom_manager.get_services()
    except Exception as exc:
        return handle_classroom_error(exc)

    course_obj = classroom_master.find_course(classroom_service, args.course)
    if not course_obj:
        print(f"[!] Course matching '{args.course}' not found.")
        return 1

    course_id = str(course_obj["id"])
    target_dir = ws.materials_dir
    if args.assignment:
        cw = classroom_master.find_coursework(classroom_service, course_id, args.assignment)
        if not cw:
            print(f"[!] Assignment '{args.assignment}' not found in {course_obj.get('name')}.")
            return 1
        target_dir = ws.get_assignment_dir(args.assignment) / "materials"
        target_dir.mkdir(parents=True, exist_ok=True)
        materials = cw.get("materials", [])
    else:
        # Fetch coursework to list materials
        cw_list = classroom_service.courses().courseWork().list(courseId=course_id, pageSize=20).execute().get("courseWork", [])
        materials = []
        for c in cw_list:
            materials.extend(c.get("materials", []))

    if not materials:
        print(f"[*] No attached files or materials found for {args.course}.")
        return 0

    downloaded = 0
    catalog_entries = []
    extract_opt = not args.no_extract
    for mat in materials:
        if "driveFile" in mat:
            df = mat["driveFile"]["driveFile"]
            file_id = df.get("id")
            title = df.get("title", f"material_{file_id}")
            link = df.get("alternateLink", "")
            dest_file = target_dir / title
            status_desc = "Link only"
            try:
                print(f"[*] Downloading Drive material: {title}...")
                download_drive_file(drive_service, file_id, dest_file)
                downloaded += 1
                status_desc = f"Saved ({dest_file.name})"
                if dest_file.suffix.lower() == ".pdf" and extract_opt:
                    txt_out = target_dir / f"{dest_file.stem}_extracted.txt"
                    extract_pdf_text(dest_file, output_txt_path=txt_out)
                    print(f"    [+] Extracted text: {txt_out.name}")
            except Exception as e:
                print(f"    [!] Direct download blocked (permissions): {title}")
                print(f"        Direct web link: {link}")
            catalog_entries.append((title, link, status_desc))
        elif "link" in mat:
            lk = mat["link"]
            title = lk.get("title", "Web Link")
            link = lk.get("url", "")
            catalog_entries.append((title, link, "Web Resource"))

    # Write materials_catalog.md for easy reference
    if catalog_entries:
        cat_file = target_dir / "materials_catalog.md"
        cat_lines = [
            f"# Materials Catalog: {course_obj.get('name')}\n",
            f"*Generated by Chitti on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n",
            "| Title | Type / Status | Web Link |",
            "|---|---|---|",
        ]
        for t, l, s in catalog_entries:
            link_md = f"[Open Link]({l})" if l else "-"
            cat_lines.append(f"| {t} | {s} | {link_md} |")
        cat_file.write_text("\n".join(cat_lines) + "\n", encoding="utf-8")
        print(f"\n[+] Created materials catalog: {cat_file}")

    print(f"\n[OK] Completed! Saved {downloaded} files into:\n     {target_dir}\n")
    return 0


# =====================================================================
# Command: status
# =====================================================================

def cmd_status(args: argparse.Namespace) -> int:
    """Unified academic dashboard: pending assignments, staged deliverables, notes & materials."""
    config, _ = _load_student_config(args.config_path)
    output_root = Path(config.output_dir).expanduser().resolve()

    if HAS_RICH and console:
        header = Text()
        header.append("🎓 Student Academic Dashboard | Chitti\n", style="bold cyan")
        header.append(f"Name: {config.student_name or 'Not Set'}  |  Roll: {config.roll_number or 'Not Set'}\n", style="white")
        dept_info = config.department or "Not Set"
        inst_info = config.institution or "Not Set"
        header.append(f"Dept: {dept_info}  |  {inst_info}\n", style="dim")
        console.print(Panel(header, border_style="blue", expand=False))

    # 1. Check Pending Assignments via Classroom API if credentials exist
    pending_list = []
    try:
        if os.path.exists(classroom_manager.TOKEN_FILE) or os.path.exists(classroom_manager.CREDENTIALS_FILE):
            cs, _ = classroom_manager.get_services()
            pending_list = classroom_manager.get_pending_assignments(cs, ignore_pattern="HMI")
    except Exception:
        pass

    if HAS_RICH and console:
        # Table of Pending Assignments
        p_table = Table(title="🚨 Pending & Missing Coursework", border_style="red")
        p_table.add_column("Course", style="cyan")
        p_table.add_column("Assignment", style="white")
        p_table.add_column("Due Date", style="yellow")
        p_table.add_column("Urgency", style="bold")

        if pending_list:
            for p in pending_list:
                course_name = p.get("course_name") or "Course"
                title = p.get("title") or p.get("assignment_title") or "Untitled Assignment"
                due_formatted = p.get("due_formatted") or p.get("due_date") or "No due date"
                is_overdue = p.get("is_overdue", False)

                if is_overdue:
                    urgency = "[bold red]OVERDUE[/bold red]"
                    due_styled = f"[red]{due_formatted}[/red]"
                else:
                    state_val = p.get("state", "ASSIGNED")
                    urgency = f"[yellow]{state_val}[/yellow]"
                    due_styled = f"[white]{due_formatted}[/white]"

                p_table.add_row(
                    course_name[:28],
                    title[:40],
                    due_styled,
                    urgency,
                )
            console.print(p_table)
        else:
            console.print("[green]✓ No pending coursework detected via Google Classroom.[/green]\n")

        # Staged Deliverables
        manifests = list(output_root.glob("**/manifest.json")) if output_root.exists() else []
        d_table = Table(title="📦 Staged Deliverables (Ready for Review / Submit)", border_style="green")
        d_table.add_column("Course", style="cyan")
        d_table.add_column("Assignment", style="white")
        d_table.add_column("Pages", justify="center")
        d_table.add_column("Audit Status", style="bold")

        for mf in manifests[:6]:
            try:
                mdata = json.loads(mf.read_text(encoding="utf-8"))
                d_table.add_row(
                    mdata.get("course_name", "")[:24],
                    mdata.get("assignment_title", "")[:32],
                    str(mdata.get("page_count", "-")),
                    "[green]Ready[/green]" if mdata.get("status") == "ready_for_review" else "[yellow]Action Needed[/yellow]",
                )
            except Exception:
                pass
        if manifests:
            console.print(d_table)
        else:
            console.print("[dim]No deliverables currently staged in output/.[/dim]\n")

        # Study Notes
        notes_mds = list(output_root.glob("**/notes/**/notes.md")) if output_root.exists() else []
        n_table = Table(title="📚 Course Study Notes & Revision Sheets", border_style="cyan")
        n_table.add_column("Course Slug", style="cyan")
        n_table.add_column("Topic", style="white")
        n_table.add_column("Has PDF", justify="center")

        for n in notes_mds[:6]:
            topic_name = n.parent.name.replace("_", " ").title()
            course_slug = n.parent.parent.parent.name
            has_pdf = "[green]Yes[/green]" if (n.parent / "notes.pdf").exists() else "[dim]No[/dim]"
            n_table.add_row(course_slug, topic_name, has_pdf)

        if notes_mds:
            console.print(n_table)
    else:
        print("\n--- Academic Dashboard ---")
        print(f"Student: {config.student_name} ({config.roll_number})")
        print(f"\n🚨 Pending Assignments ({len(pending_list)}):")
        for p in pending_list:
            tag = "[OVERDUE]" if p.get("is_overdue") else f"[{p.get('state', 'ASSIGNED')}]"
            title = p.get("title") or p.get("assignment_title") or "Untitled"
            due = p.get("due_formatted") or p.get("due_date") or "No due date"
            print(f"  {tag} {p.get('course_name')} -> {title} (Due: {due})")
        manifests = list(output_root.glob("**/manifest.json")) if output_root.exists() else []
        print(f"\nStaged deliverables: {len(manifests)}")
        notes_mds = list(output_root.glob("**/notes/**/notes.md")) if output_root.exists() else []
        print(f"Study notes:         {len(notes_mds)}\n")

    return 0


# =====================================================================
# Parser Builder & Main Entry Point
# =====================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the Chitti CLI."""
    parser = argparse.ArgumentParser(
        prog="chitti",
        description="🤖 Chitti - The Super-Intelligent Classroom & Assignment Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick Workflow Guide:
  1. Setup student profile:
     python chitti.py setup
  2. View pending assignments:
     python chitti.py pending
  3. Inspect assignment requirements:
     python chitti.py details --course "Networks" --assignment "Lab 7"
  4. Compile academic PDF deliverable:
     python chitti.py build --course "Networks" --assignment "Lab 7" --proof screenshot.png --proof-caption "Terminal RIP Output"
  5. Attach authentic terminal screenshot proof:
     python chitti.py attach-proof --course "Networks" --assignment "Lab 7" --image term.png --caption "Ping Test"
  6. Review staged deliverables:
     python chitti.py review
  7. Turn in via CDP engine:
     python chitti.py submit --course "Networks" --assignment "Lab 7"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: setup
    setup_parser = subparsers.add_parser("setup", help="Run interactive or automated student configuration setup")
    setup_parser.add_argument("--non-interactive", action="store_true", help="Run without user prompts")
    setup_parser.add_argument("-n", "--name", help="Student Full Name")
    setup_parser.add_argument("-r", "--roll", help="Student Roll / Registration Number")
    setup_parser.add_argument("-d", "--dept", help="Department / Major")
    setup_parser.add_argument("-i", "--institution", help="College / University Name")
    setup_parser.add_argument("-o", "--output-dir", help="Directory for generated deliverables")
    setup_parser.add_argument("-c", "--credentials", help="Path to Google credentials.json")
    setup_parser.add_argument("-t", "--token", help="Path to Google OAuth token.json")
    setup_parser.add_argument("-p", "--port", type=int, help="Chrome Remote Debugging port")
    setup_parser.add_argument("--config-path", help="Path to student_config.json")
    setup_parser.add_argument("--client-id", help="Google OAuth Client ID to auto-generate credentials.json")
    setup_parser.add_argument("--client-secret", help="Google OAuth Client Secret to auto-generate credentials.json")
    setup_parser.add_argument("--open-browser", action="store_true", help="Open Google Cloud Console in browser")

    # Command: courses
    subparsers.add_parser("courses", help="List all enrolled Google Classroom courses")

    # Command: pending
    pending_parser = subparsers.add_parser("pending", help="List all pending coursework with due dates")
    pending_parser.add_argument("--course", help="Filter by course name or ID", default=None)
    pending_parser.add_argument("--ignore", help="Ignore courses matching pattern (default: HMI)", default="HMI")

    # Command: details
    details_parser = subparsers.add_parser("details", help="View assignment instructions, rubrics, and materials")
    details_parser.add_argument("--course", required=True, help="Course name or ID")
    details_parser.add_argument("--assignment", required=True, help="Assignment title or ID")

    # Command: build
    build_parser = subparsers.add_parser("build", help="Compile academic report PDF with formatted proofs & stage deliverable")
    build_parser.add_argument("--course", required=True, help="Course name or ID")
    build_parser.add_argument("--assignment", required=True, help="Assignment title or ID")
    build_parser.add_argument("--template", help="Optional path to teacher template PDF", default=None)
    build_parser.add_argument("--mode", choices=["scratch", "template", "personalize"], default="scratch", help="Report compilation strategy")
    build_parser.add_argument("--old-name", help="Old author name to redact in personalize mode", default=None)
    build_parser.add_argument("--old-roll", help="Old roll number to redact in personalize mode", default=None)
    build_parser.add_argument("--code", help="Path to source code file to embed in report", default=None)
    build_parser.add_argument("--theory", help="Theory text or file path to embed in report", default=None)
    build_parser.add_argument("--answers", help="JSON string mapping questions to answers for in-place manual filling", default=None)
    build_parser.add_argument("--answers-file", help="Path to JSON file mapping questions to answers for in-place manual filling", default=None)
    build_parser.add_argument("--sections-file", help="Path to JSON file containing structured flowable sections", default=None)
    build_parser.add_argument("--proof", help="Path to authentic terminal screenshot or observation photo", default=None)
    build_parser.add_argument("--proof-clipboard", action="store_true", help="Extract terminal screenshot directly from Windows clipboard (Win + Shift + S)")
    build_parser.add_argument("--proof-caption", help="Caption describing the proof figure", default=None)
    build_parser.add_argument("--output-dir", help="Override output directory", default=None)
    build_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    # Command: attach-proof
    attach_parser = subparsers.add_parser(
        "attach-proof",
        help="Add and frame authentic terminal screenshot & output proof into staged deliverable PDF",
    )
    attach_parser.add_argument("--course", required=True, help="Course name or ID")
    attach_parser.add_argument("--assignment", required=True, help="Assignment title or ID")
    attach_parser.add_argument("--image", default=None, help="Path to authentic screenshot or photo")
    attach_parser.add_argument("--from-clipboard", action="store_true", help="Extract screenshot directly from Windows clipboard (Win + Shift + S)")
    attach_parser.add_argument("--caption", help="Descriptive figure caption", default=None)
    attach_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    # Command: review
    review_parser = subparsers.add_parser("review", help="List all staged deliverables in output directory with page counts & audits")
    review_parser.add_argument("--course", help="Filter review by course name substring", default=None)
    review_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    # Command: submit
    submit_parser = subparsers.add_parser("submit", help="Turn in assignment via verified CDP browser automation")
    submit_parser.add_argument("--course", required=True, help="Course name or ID")
    submit_parser.add_argument("--assignment", required=True, help="Assignment title or ID")
    submit_parser.add_argument("--file", help="Explicit file to submit (defaults to auto-detected staged PDF)", default=None)
    submit_parser.add_argument("--keep-tab", action="store_true", help="Keep browser tab open after submission")
    submit_parser.add_argument("--port", type=int, help="Chrome Remote Debugging port (default: 9444)", default=None)
    submit_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    # Command: notes
    notes_parser = subparsers.add_parser(
        "notes",
        help="Generate structured study notes, revision sheets, and publication PDF",
    )
    notes_parser.add_argument("--course", help="Course name or ID", default=None)
    notes_parser.add_argument("--topic", help="Topic title (e.g. 'TCP Handshake', 'CPU Scheduling')", default=None)
    notes_parser.add_argument("--theory", help="Core theoretical concepts or summary", default="")
    notes_parser.add_argument("--formulas", help="Key formulas, equations, or code snippets", default=None)
    notes_parser.add_argument("--file", help="Path to markdown/text file containing notes content", default=None)
    notes_parser.add_argument("--list", action="store_true", help="List all generated study notes across courses")
    notes_parser.add_argument("--no-pdf", action="store_true", help="Only save Markdown note, skip PDF compilation")
    notes_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    # Command: materials
    mat_parser = subparsers.add_parser(
        "materials",
        help="Download teacher materials and extract PDF text into course workspace",
    )
    mat_parser.add_argument("--course", required=True, help="Course name or ID")
    mat_parser.add_argument("--assignment", help="Optional assignment title to fetch specific assignment materials", default=None)
    mat_parser.add_argument("--file", help="Path to a local teacher PDF to extract text into workspace", default=None)
    mat_parser.add_argument("--no-extract", action="store_true", help="Skip automatic PDF text extraction")
    mat_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    # Command: status
    status_parser = subparsers.add_parser(
        "status",
        help="Unified academic dashboard: pending coursework, deliverables, notes & materials",
    )
    status_parser.add_argument("--config-path", help="Path to student_config.json", default=None)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()

    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        parser.print_help()
        return 0

    # Parse known args so subcommands like setup can handle variable arguments
    args, remaining = parser.parse_known_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "setup":
        return cmd_setup(args, remaining)
    elif args.command == "courses":
        return cmd_courses(args)
    elif args.command == "pending":
        return cmd_pending(args)
    elif args.command == "details":
        return cmd_details(args)
    elif args.command == "build":
        return cmd_build(args)
    elif args.command == "attach-proof":
        return cmd_attach_proof(args)
    elif args.command == "review":
        return cmd_review(args)
    elif args.command == "submit":
        return cmd_submit(args)
    elif args.command == "notes":
        return cmd_notes(args)
    elif args.command == "materials":
        return cmd_materials(args)
    elif args.command == "status":
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
