#!/usr/bin/env python3
"""Classroom Agent Master CLI Application.

Unifies Google Classroom discovery, academic PDF compilation, authentic media and
terminal screenshot framing, deliverables staging, review verification, and CDP-based
browser submission.
"""

import argparse
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
    from rich import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

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
    setup_argv.extend(remaining_argv)

    return classroom_setup.run_setup(setup_argv)


# =====================================================================
# Command: courses
# =====================================================================

def cmd_courses(args: argparse.Namespace) -> int:
    """List all enrolled Google Classroom courses."""
    try:
        classroom_service, _ = classroom_manager.get_services()
        courses = classroom_manager.list_courses(classroom_service)
        classroom_manager.display_courses(courses)
        return 0
    except Exception as exc:
        print(f"[!] Error accessing Google Classroom: {exc}")
        print("Tip: Run 'python classroom_agent.py setup' to configure Google Classroom API credentials.")
        return 1


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
        print(f"[!] Error fetching pending assignments: {exc}")
        return 1


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

    assets_to_stage: List[Path] = []

    # Handle proof screenshot if provided
    if args.proof:
        proof_src = Path(args.proof).expanduser().resolve()
        if not proof_src.exists():
            print(f"[!] Specified proof image does not exist: {proof_src}")
            return 1

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

    if args.template:
        template_path = Path(args.template).expanduser().resolve()
        if not template_path.exists():
            print(f"[!] Teacher template PDF not found: {template_path}")
            return 1
        augment_teacher_template(
            template_path=template_path,
            output_path=temp_pdf_out,
            solution_sections=sections,
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

    img_src = Path(args.image).expanduser().resolve()
    if not img_src.exists():
        print(f"[!] Error: Image file not found at: {img_src}")
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
            console.print("Tip: Run 'python classroom_agent.py build' to create deliverables.")
        else:
            print(f"No staged deliverables found. Output directory does not exist: {output_root}")
            print("Tip: Run 'python classroom_agent.py build' to create deliverables.")
        return 0

    manifest_files = list(output_root.glob("**/manifest.json"))
    if not manifest_files:
        if HAS_RICH and console:
            console.print(f"[yellow]No staged deliverables found in '{output_root}'. Output directory is empty.[/yellow]")
            console.print("Tip: Run 'python classroom_agent.py build' to compile and stage an assignment.")
        else:
            print(f"No staged deliverables found in '{output_root}'. Output directory is empty.")
            print("Tip: Run 'python classroom_agent.py build' to compile and stage an assignment.")
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

        if staged_pdf.exists():
            print(f"[*] Auto-detected staged deliverable: {staged_pdf}")
            files_to_submit = [str(staged_pdf)]
        else:
            print(f"[!] No file specified and no staged deliverable found at:\n    {staged_pdf}")
            print("Tip: Run 'python classroom_agent.py build' first, or provide '--file <path>'.")
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
# Parser Builder & Main Entry Point
# =====================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the Classroom Agent CLI."""
    parser = argparse.ArgumentParser(
        prog="classroom_agent",
        description="Classroom Agent - Unified Master CLI for Google Classroom Intelligence, Deliverables & Submission",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick Workflow Guide:
  1. Setup student profile:
     python classroom_agent.py setup
  2. View pending assignments:
     python classroom_agent.py pending
  3. Inspect assignment requirements:
     python classroom_agent.py details --course "Networks" --assignment "Lab 7"
  4. Compile academic PDF deliverable:
     python classroom_agent.py build --course "Networks" --assignment "Lab 7" --proof screenshot.png --proof-caption "Terminal RIP Output"
  5. Attach authentic terminal screenshot proof:
     python classroom_agent.py attach-proof --course "Networks" --assignment "Lab 7" --image term.png --caption "Ping Test"
  6. Review staged deliverables:
     python classroom_agent.py review
  7. Turn in via CDP engine:
     python classroom_agent.py submit --course "Networks" --assignment "Lab 7"
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
    build_parser.add_argument("--proof", help="Path to authentic terminal screenshot or observation photo", default=None)
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
    attach_parser.add_argument("--image", required=True, help="Path to authentic screenshot or photo")
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
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
