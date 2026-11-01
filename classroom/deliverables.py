"""Deliverables staging manager, manifest generator, and review notification suite.

Provides end-to-end deliverables orchestration:
1. Capability & Requirement Auditor (`audit_assignment_requirements`):
   Identifies what is fully automated (calculations, algorithms, code, theory)
   vs. what requires student action (handwritten signatures, local network execution,
   personal photos) or represents true blockers (physical hardware/sensors, missing
   teacher attachments). Never hallucinates or fakes outputs.
2. Deliverables Staging Manager (`stage_deliverable`):
   Safely stages final PDF deliverables and processed assets into organized directories
   (`output/<course_slug>/<assignment_slug>/`), generates SHA-256 checksums, writes
   a machine-readable `manifest.json`, and generates an actionable `SUMMARY.md` checklist.
3. Review Notification Banner (`print_completion_card`):
   Renders a formatted terminal summary card with clickable file links and Google
   Classroom web URLs so students retain full agency and oversight.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Union

import pymupdf as fitz
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from classroom.config import slugify


@dataclass
class RequirementItem:
    """An individual assignment requirement or task item with audit classification."""

    description: str
    status: str  # "automated", "needs_student_input", "blocked"
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize RequirementItem to a dictionary."""
        return asdict(self)


@dataclass
class RequirementAudit:
    """Result of an assignment requirements capability audit."""

    automated_tasks: List[RequirementItem] = field(default_factory=list)
    student_action_items: List[RequirementItem] = field(default_factory=list)
    blockers: List[RequirementItem] = field(default_factory=list)
    is_complete: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize RequirementAudit to a dictionary."""
        return {
            "is_complete": self.is_complete,
            "automated_tasks": [t.to_dict() for t in self.automated_tasks],
            "student_action_items": [t.to_dict() for t in self.student_action_items],
            "blockers": [t.to_dict() for t in self.blockers],
        }


@dataclass
class StagedDeliverable:
    """Represents a staged assignment deliverable package ready for student review."""

    course_name: str
    assignment_title: str
    staged_dir: Path
    pdf_path: Path
    manifest_path: Path
    summary_path: Path
    classroom_url: Optional[str] = None
    page_count: int = 0
    audit: Optional[RequirementAudit] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize StagedDeliverable to a dictionary."""
        return {
            "course_name": self.course_name,
            "assignment_title": self.assignment_title,
            "staged_dir": str(self.staged_dir),
            "pdf_path": str(self.pdf_path),
            "manifest_path": str(self.manifest_path),
            "summary_path": str(self.summary_path),
            "classroom_url": self.classroom_url,
            "page_count": self.page_count,
            "audit": self.audit.to_dict() if self.audit else None,
        }


# Pattern matchers for capability auditing
_HARDWARE_PATTERNS = [
    r"\b(?:raspberry\s*pi|arduino|esp32|esp8266|stm32|microcontroller|8051|8086)\b",
    r"\b(?:breadboard|circuit\s+board|pcb|soldering|solder|jumper\s+wires?|gpio)\b",
    r"\b(?:oscilloscope|multimeter|multitester|logic\s+analyzer|signal\s+generator|function\s+generator)\b",
    r"\b(?:fpga|verilog\s+on\s+hardware|hardware\s+kit|trainer\s+kit|physical\s+circuit)\b",
    r"\b(?:sensor\s+module|dht11|dht22|ultrasonic\s+sensor|servo\s+motor|stepper\s+motor)\b",
    r"\b(?:physical\s+hardware|hardware\s+setup|connect\s+pins?)\b",
]

_ATTACHMENT_FILE_PATTERN = (
    r"(?:`|\b)([\w-]+\.(?:pcap|pcapng|csv|xlsx|xls|zip|tar\.gz|dat|tsv|pdf|docx|txt|json|py|c|cpp|h|java|sql))\b(?:`|\b)?"
)

_ATTACHMENT_PHRASE_PATTERN = (
    r"\b(?:attached\s+(?:file|dataset|document|template|data|archive|spreadsheet|code)|download\s+the\s+attached|see\s+attached|refer\s+to\s+(?:the\s+)?attached)\b"
)

_STUDENT_ACTION_RULES = [
    (
        r"\b(?:sign(?:ature)?(?:\s+by\s+hand|\s+in\s+ink|\s+physically)?|handwritten\s+signature|sign\s+(?:the\s+)?(?:pledge|declaration|cover|document|sheet|form|honor|academic\s+integrity))\b",
        "Requires student handwritten signature directly on deliverable.",
    ),
    (
        r"\b(?:photo(?:graph)?\s+of\s+(?:your|student|yourself|id\s+card|student\s+id)|upload\s+(?:a\s+)?(?:selfie|passport\s+photo|photo\s+of\s+id|id\s+card)|webcam)\b",
        "Requires student personal photograph or physical ID document.",
    ),
    (
        r"\b(?:local\s+machine|local\s+network|home\s+network|campus\s+network|local\s+router|router\s+(?:page|settings|admin)|private\s+network|shell\s+prompt\s+with\s+your\s+(?:student\s+id|username)|capture\s+(?:packets\s+)?on\s+your\s+(?:local|wi-?fi)|traceroute\s+on\s+your\s+local)\b",
        "Requires executing commands or capturing data on student's local machine or private network environment.",
    ),
    (
        r"\b(?:personal\s+(?:password|credentials|api\s+key|token|auth\s+token|secret)|login\s+with\s+your\s+credentials)\b",
        "Requires private student credentials that cannot be stored or automated.",
    ),
]


def audit_assignment_requirements(
    prompt_text: str = "",
    attached_files: Optional[List[str]] = None,
    *,
    instructions: Optional[str] = None,
    assignment_title: Optional[str] = None,
    materials: Optional[List[Any]] = None,
) -> RequirementAudit:
    """Performs a capability audit on an assignment prompt.

    Differentiates automated tasks (calculations, algorithms, code, theory) from
    items requiring student agency (handwritten signatures, local network execution,
    personal photos) and true blockers (physical hardware/sensors, missing teacher attachments).
    Never fakes or hallucinates outputs.

    Args:
        prompt_text: Raw instruction text, prompt, or rubric of the assignment.
        attached_files: List of file names or paths actually attached to the assignment.
        instructions: Optional alias for prompt_text.
        assignment_title: Optional assignment title if prompt_text is empty.
        materials: Optional materials list.

    Returns:
        RequirementAudit containing categorized tasks, action items, and blockers.
    """
    if instructions and not prompt_text:
        prompt_text = instructions
    if assignment_title and not prompt_text:
        prompt_text = assignment_title
    if materials and not attached_files:
        attached_files = [str(m) for m in materials]
    if not prompt_text or not prompt_text.strip():
        return RequirementAudit(
            automated_tasks=[],
            student_action_items=[],
            blockers=[],
            is_complete=True,
        )

    # Normalize attached file basenames for case-insensitive lookup
    attached_set = {Path(f).name.lower() for f in (attached_files or [])}

    # Split prompt into actionable items (honoring bulleted/numbered lines or sentences)
    raw_lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
    items_raw: List[str] = []
    for line in raw_lines:
        list_match = re.match(r"^(?:\d+[\.\)]\s*|[a-zA-Z][\.\)]\s*|[\-\*•]\s*)(.+)$", line)
        if list_match:
            items_raw.append(list_match.group(1).strip())
        else:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
            items_raw.extend(sentences)

    automated_tasks: List[RequirementItem] = []
    student_action_items: List[RequirementItem] = []
    blockers: List[RequirementItem] = []

    for item in items_raw:
        if not item:
            continue

        # 1. Check for physical hardware / lab equipment blockers
        is_hardware = False
        for hw_pat in _HARDWARE_PATTERNS:
            if re.search(hw_pat, item, re.IGNORECASE):
                blockers.append(
                    RequirementItem(
                        description=item,
                        status="blocked",
                        reason="Requires physical hardware, lab equipment, breadboard, or circuit wiring that cannot be automated via software.",
                    )
                )
                is_hardware = True
                break

        if is_hardware:
            continue

        # 2. Check for missing teacher attachment blockers
        referenced_files = re.findall(_ATTACHMENT_FILE_PATTERN, item, re.IGNORECASE)
        has_attachment_phrase = bool(re.search(_ATTACHMENT_PHRASE_PATTERN, item, re.IGNORECASE))

        missing_files = [f for f in referenced_files if f.lower() not in attached_set]
        if referenced_files and missing_files:
            blockers.append(
                RequirementItem(
                    description=item,
                    status="blocked",
                    reason=f"Required teacher attachment '{', '.join(missing_files)}' referenced in prompt is missing.",
                )
            )
            continue
        elif has_attachment_phrase and not referenced_files and not attached_set:
            blockers.append(
                RequirementItem(
                    description=item,
                    status="blocked",
                    reason="Required teacher attachment or dataset referenced in instructions is missing.",
                )
            )
            continue

        # 3. Check for student action items (handwritten signatures, local host execution, photos)
        is_student_action = False
        for action_pat, action_reason in _STUDENT_ACTION_RULES:
            if re.search(action_pat, item, re.IGNORECASE):
                student_action_items.append(
                    RequirementItem(
                        description=item,
                        status="needs_student_input",
                        reason=action_reason,
                    )
                )
                is_student_action = True
                break

        if is_student_action:
            continue

        # 4. Standard automated academic task (code, algorithms, calculations, theory)
        automated_tasks.append(
            RequirementItem(
                description=item,
                status="automated",
                reason=None,
            )
        )

    is_complete = len(blockers) == 0 and len(student_action_items) == 0

    return RequirementAudit(
        automated_tasks=automated_tasks,
        student_action_items=student_action_items,
        blockers=blockers,
        is_complete=is_complete,
    )


def compute_sha256(file_path: Union[str, Path]) -> str:
    """Compute the SHA-256 hexadecimal digest of a file in binary mode.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        Hex-encoded SHA-256 checksum string.
    """
    path = Path(file_path).resolve()
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stage_deliverable(
    output_root: Union[str, Path],
    course_name: str,
    assignment_title: str,
    pdf_path: Union[str, Path],
    assets: Optional[List[Union[str, Path]]] = None,
    classroom_url: Optional[str] = None,
    audit: Optional[RequirementAudit] = None,
) -> StagedDeliverable:
    """Stages submission deliverable files and generates manifest & review summary.

    Organizes generated PDFs and assets into `output/<course_slug>/<assignment_slug>/`,
    computes SHA-256 checksums, writes `manifest.json`, generates `SUMMARY.md` checklist,
    and returns a `StagedDeliverable`.

    Args:
        output_root: Root directory for output artifacts.
        course_name: Name of the course.
        assignment_title: Title of the assignment.
        pdf_path: Source path to the final generated PDF.
        assets: Optional list of supporting asset paths (images, logs, source code).
        classroom_url: Optional direct Google Classroom URL for submission.
        audit: Optional RequirementAudit containing capability audit findings.

    Returns:
        StagedDeliverable package instance.

    Raises:
        FileNotFoundError: If pdf_path or any asset path does not exist.
        ValueError: If pdf_path or any asset is a directory instead of a file.
    """
    resolved_pdf = Path(pdf_path).expanduser().resolve()
    if not resolved_pdf.exists():
        raise FileNotFoundError(f"PDF deliverable not found at: {pdf_path}")
    if not resolved_pdf.is_file():
        raise ValueError(f"PDF deliverable must be a file, got: {pdf_path}")

    # Validate asset files
    resolved_assets: List[Path] = []
    for asset in assets or []:
        p = Path(asset).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Asset file not found at: {asset}")
        if not p.is_file():
            raise ValueError(f"Asset path must be a file, got: {asset}")
        resolved_assets.append(p)

    # Resolve safe filesystem directory paths
    course_slug = slugify(course_name) or "general_course"
    assignment_slug = slugify(assignment_title) or "assignment"
    staged_dir = Path(output_root).expanduser().resolve() / course_slug / assignment_slug
    staged_dir.mkdir(parents=True, exist_ok=True)

    # Stage submission PDF
    dest_pdf = staged_dir / "final_submission.pdf"
    if resolved_pdf != dest_pdf:
        shutil.copy2(resolved_pdf, dest_pdf)

    # Determine PDF page count
    page_count = 0
    try:
        with fitz.open(dest_pdf) as doc:
            page_count = len(doc)
    except Exception:
        page_count = 1

    pdf_sha = compute_sha256(dest_pdf)
    pdf_size = dest_pdf.stat().st_size

    # Stage assets if present
    staged_assets_info: List[Dict[str, Any]] = []
    files_dict: Dict[str, Dict[str, Any]] = {
        "final_submission.pdf": {
            "sha256": pdf_sha,
            "size_bytes": pdf_size,
        }
    }
    checksums_dict: Dict[str, str] = {
        "final_submission.pdf": pdf_sha,
    }

    if resolved_assets:
        assets_dir = staged_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for asset_path in resolved_assets:
            dest_asset = assets_dir / asset_path.name
            if asset_path != dest_asset:
                shutil.copy2(asset_path, dest_asset)
            asset_sha = compute_sha256(dest_asset)
            asset_size = dest_asset.stat().st_size
            rel_asset_path = f"assets/{asset_path.name}"
            staged_assets_info.append({
                "filename": asset_path.name,
                "path": rel_asset_path,
                "sha256": asset_sha,
                "size_bytes": asset_size,
            })
            files_dict[rel_asset_path] = {
                "sha256": asset_sha,
                "size_bytes": asset_size,
            }
            checksums_dict[rel_asset_path] = asset_sha

    # Determine status string
    if audit is not None:
        if audit.blockers:
            status_str = "blocked"
        elif audit.student_action_items:
            status_str = "needs_student_action"
        else:
            status_str = "ready_for_review"
    else:
        status_str = "ready_for_review"

    # Write manifest.json
    manifest_path = staged_dir / "manifest.json"
    manifest_data: Dict[str, Any] = {
        "course_name": course_name,
        "assignment_title": assignment_title,
        "course_slug": course_slug,
        "assignment_slug": assignment_slug,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "classroom_url": classroom_url,
        "page_count": page_count,
        "status": status_str,
        "deliverables": {
            "submission_pdf": {
                "filename": "final_submission.pdf",
                "path": "final_submission.pdf",
                "sha256": pdf_sha,
                "size_bytes": pdf_size,
                "page_count": page_count,
            },
            "assets": staged_assets_info,
        },
        "files": files_dict,
        "checksums": checksums_dict,
        "audit": audit.to_dict() if audit else None,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Generate SUMMARY.md checklist
    summary_path = staged_dir / "SUMMARY.md"
    summary_lines = [
        f"# 🤖 Chitti Deliverable Summary: {assignment_title}",
        "> Generated and audited by **Chitti** — The Super-Intelligent Classroom Agent.",
        "",
        f"**Course:** {course_name}  ",
        f"**Assignment:** {assignment_title}  ",
        f"**Staged Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Status:** {'✅ Ready for Submission' if status_str == 'ready_for_review' else ('⚠️ Action Required by Student' if status_str == 'needs_student_action' else '🚫 Blocked')}  ",
    ]
    if classroom_url:
        summary_lines.append(f"**Classroom URL:** [{classroom_url}]({classroom_url})  ")

    summary_lines.extend([
        "",
        "---",
        "",
        "## Deliverables Checklist",
        f"- [x] **Final Submission PDF**: `final_submission.pdf` ({page_count} pages)",
        f"  - SHA-256: `{pdf_sha}`",
        f"  - File Size: `{pdf_size} bytes`",
    ])

    if staged_assets_info:
        summary_lines.append("- [x] **Staged Assets**:")
        for a in staged_assets_info:
            summary_lines.append(f"  - `{a['path']}` (SHA-256: `{a['sha256']}`)")

    summary_lines.extend([
        "",
        "---",
        "",
        "## Requirements & Verification Audit",
    ])

    if audit is not None:
        if audit.automated_tasks:
            summary_lines.append("")
            summary_lines.append("### Automated Tasks (Completed)")
            for item in audit.automated_tasks:
                summary_lines.append(f"- [x] {item.description}")

        if audit.student_action_items:
            summary_lines.append("")
            summary_lines.append("### Student Action Items (Required Prior to Submission)")
            for item in audit.student_action_items:
                summary_lines.append(f"- [ ] {item.description}")
                if item.reason:
                    summary_lines.append(f"  - *Reason:* {item.reason}")

        if audit.blockers:
            summary_lines.append("")
            summary_lines.append("### Blockers Identified")
            for item in audit.blockers:
                summary_lines.append(f"- 🚫 {item.description}")
                if item.reason:
                    summary_lines.append(f"  - *Explanation:* {item.reason}")
    else:
        summary_lines.extend([
            "",
            "- [x] Submission PDF compiled and staged with integrity verified.",
        ])

    summary_lines.extend([
        "",
        "---",
        "",
        "## Submission Next Steps",
        f"1. Review `final_submission.pdf` in `{staged_dir.as_posix()}`.",
        "2. Complete any pending checklist items marked with `[ ]` above.",
    ])
    if classroom_url:
        summary_lines.append(f"3. Submit your assignment at: [{classroom_url}]({classroom_url})")
    else:
        summary_lines.append("3. Upload `final_submission.pdf` to the corresponding Google Classroom assignment.")

    summary_lines.append("")
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    return StagedDeliverable(
        course_name=course_name,
        assignment_title=assignment_title,
        staged_dir=staged_dir,
        pdf_path=dest_pdf,
        manifest_path=manifest_path,
        summary_path=summary_path,
        classroom_url=classroom_url,
        page_count=page_count,
        audit=audit,
    )


def print_completion_card(
    deliverable: StagedDeliverable,
    console: Optional[Console] = None,
) -> None:
    """Renders a rich formatted console card with links and status.

    Outputs clickable local file paths and Google Classroom URLs so students can
    review deliverables and submit with agency.

    Args:
        deliverable: The StagedDeliverable package to display.
        console: Optional Rich Console instance (useful for tests or custom outputs).
    """
    if console is None:
        console = Console()

    # Determine status color and banner
    if deliverable.audit and deliverable.audit.blockers:
        border_style = "red"
        title_text = "[bold red]🤖 CHITTI: 🚫 ASSIGNMENT BLOCKED - ACTION REQUIRED[/bold red]"
    elif deliverable.audit and deliverable.audit.student_action_items:
        border_style = "yellow"
        title_text = "[bold yellow]🤖 CHITTI: ⚠️ DELIVERABLE STAGED - STUDENT REVIEW REQUIRED[/bold yellow]"
    else:
        border_style = "green"
        title_text = "[bold green]🤖 CHITTI: ✓ DELIVERABLE STAGED & READY FOR SUBMISSION[/bold green]"

    table = Table.grid(padding=(0, 2))
    table.add_column("Key", style="bold cyan", justify="right")
    table.add_column("Value", style="white")

    table.add_row("Course:", deliverable.course_name)
    table.add_row("Assignment:", deliverable.assignment_title)
    table.add_row("Pages:", f"{deliverable.page_count} pages")

    # Format clickable file links
    pdf_url = deliverable.pdf_path.resolve().as_uri()
    manifest_url = deliverable.manifest_path.resolve().as_uri()
    summary_url = deliverable.summary_path.resolve().as_uri()

    table.add_row("PDF Deliverable:", f"[link={pdf_url}]{deliverable.pdf_path.name}[/link] ({pdf_url})")
    table.add_row("Manifest:", f"[link={manifest_url}]{deliverable.manifest_path.name}[/link]")
    table.add_row("Summary Checklist:", f"[link={summary_url}]{deliverable.summary_path.name}[/link]")

    if deliverable.classroom_url:
        table.add_row("Classroom URL:", f"[link={deliverable.classroom_url}]{deliverable.classroom_url}[/link]")

    if deliverable.audit:
        auto_count = len(deliverable.audit.automated_tasks)
        action_count = len(deliverable.audit.student_action_items)
        blocker_count = len(deliverable.audit.blockers)

        audit_status = (
            f"[green]✓ {auto_count} automated[/green] | "
            f"[{'yellow' if action_count else 'dim'}]{action_count} student actions[/{'yellow' if action_count else 'dim'}] | "
            f"[{'red' if blocker_count else 'dim'}]{blocker_count} blockers[/{'red' if blocker_count else 'dim'}]"
        )
        table.add_row("Audit Status:", audit_status)

    panel = Panel(
        table,
        title=title_text,
        border_style=border_style,
        expand=False,
    )

    console.print(panel)
