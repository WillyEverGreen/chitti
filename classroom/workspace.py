"""Coursework Workspace Manager & Academic Study Engine (classroom/workspace.py).

Provides clean workspace isolation and all-rounder academic capabilities:
1. Isolated Course Workspace (`CourseWorkspace`, `get_course_workspace`):
   Organizes all coursework strictly into dedicated, per-course directories under
   `output/<course_slug>/`:
     • `assignments/<assignment_slug>/`: Final PDFs, checksum manifests, review checklists, and assets.
     • `materials/`: Downloaded teacher assignment sheets, syllabus, reference PDFs, and manuals.
     • `notes/<topic_slug>/`: Revision notes, formula cheatsheets, and viva question banks.
   Keeps the root project codebase 100% clean and free of build artifacts.
2. PDF Text Extraction (`extract_pdf_text`):
   Extracts readable text from teacher assignment PDFs using PyMuPDF (fitz) so
   students and agents can inspect instructions without manual copy-pasting.
3. Study Notes & Viva Engine (`save_study_notes`):
   Builds comprehensive academic notes in Markdown and compiles publication-grade
   PDF study sheets with academic headers and page numbering.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pymupdf as fitz

from classroom.config import StudentConfig, slugify
from classroom.pdf_engine import build_report_pdf


@dataclass
class CourseWorkspace:
    """Encapsulates isolated, per-subject workspace directories for a course."""

    course_name: str
    course_slug: str
    root_dir: Path
    assignments_dir: Path
    materials_dir: Path
    notes_dir: Path

    def get_assignment_dir(self, assignment_title: str) -> Path:
        """Returns and ensures the directory for a specific assignment."""
        assign_slug = slugify(assignment_title) or "assignment"
        target = self.assignments_dir / assign_slug
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_notes_dir(self, topic_name: str) -> Path:
        """Returns and ensures the directory for a specific study topic."""
        topic_slug = slugify(topic_name) or "general_notes"
        target = self.notes_dir / topic_slug
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_materials_dir(self) -> Path:
        """Returns and ensures the general materials directory for the course."""
        self.materials_dir.mkdir(parents=True, exist_ok=True)
        return self.materials_dir


def get_course_workspace(
    output_root: Union[str, Path],
    course_name: str,
) -> CourseWorkspace:
    """Creates and returns an isolated CourseWorkspace under the configured output directory.

    Structure:
      <output_root>/<course_slug>/
        ├── assignments/
        ├── materials/
        └── notes/
    """
    root = Path(output_root).expanduser().resolve()
    c_slug = slugify(course_name) or "general_course"
    course_root = root / c_slug

    assign_dir = course_root / "assignments"
    mat_dir = course_root / "materials"
    notes_dir = course_root / "notes"

    for d in (course_root, assign_dir, mat_dir, notes_dir):
        d.mkdir(parents=True, exist_ok=True)

    return CourseWorkspace(
        course_name=course_name,
        course_slug=c_slug,
        root_dir=course_root,
        assignments_dir=assign_dir,
        materials_dir=mat_dir,
        notes_dir=notes_dir,
    )


def extract_pdf_text(
    pdf_path: Union[str, Path],
    output_txt_path: Optional[Union[str, Path]] = None,
) -> str:
    """Extracts raw text content from a PDF document using PyMuPDF.

    Args:
        pdf_path: Path to the target PDF file.
        output_txt_path: Optional path to save the extracted text.

    Returns:
        Extracted text string across all document pages.

    Raises:
        FileNotFoundError: If pdf_path does not exist on disk.
    """
    resolved = Path(pdf_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(str(resolved))
    page_texts: List[str] = []
    for idx, page in enumerate(doc):
        text = page.get_text("text") or ""
        page_texts.append(f"--- Page {idx + 1} ---\n{text.strip()}")
    doc.close()

    full_text = "\n\n".join(page_texts).strip()

    if output_txt_path:
        out_p = Path(output_txt_path).expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(full_text, encoding="utf-8")

    return full_text


def save_study_notes(
    workspace: CourseWorkspace,
    config: StudentConfig,
    topic: str,
    theory: str,
    formulas: Optional[str] = None,
    viva_questions: Optional[List[Dict[str, str]]] = None,
    references: Optional[List[str]] = None,
    compile_pdf: bool = True,
) -> Dict[str, Path]:
    """Generates structured markdown notes and compiles a publication-grade PDF study sheet.

    Saves into:
      output/<course_slug>/notes/<topic_slug>/
        ├── notes.md
        └── notes.pdf
    """
    topic_dir = workspace.get_notes_dir(topic)
    md_file = topic_dir / "notes.md"
    pdf_file = topic_dir / "notes.pdf"

    # 1. Format Markdown
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_lines: List[str] = [
        f"# {topic}",
        f"**Course:** {workspace.course_name}  ",
        f"**Student:** {config.student_name} ({config.roll_number})  ",
        f"**Department:** {config.department} | {config.institution}  ",
        f"**Date:** {now_str}  \n",
        "---",
        "\n## 1. Core Theory & Key Concepts\n",
        theory.strip(),
    ]

    if formulas and formulas.strip():
        md_lines.extend([
            "\n## 2. Key Formulas & Equations\n",
            formulas.strip(),
        ])

    if viva_questions:
        md_lines.append("\n## 3. Viva & Exam Revision Questions\n")
        for idx, v in enumerate(viva_questions, start=1):
            q = v.get("question", "")
            a = v.get("answer", "")
            md_lines.append(f"**Q{idx}. {q}**  \n*Ans:* {a}\n")

    if references:
        md_lines.append("\n## 4. References & Study Materials\n")
        for ref in references:
            md_lines.append(f"- {ref}")

    md_content = "\n".join(md_lines) + "\n"
    md_file.write_text(md_content, encoding="utf-8")

    # 2. Compile Publication PDF if requested
    if compile_pdf:
        pdf_sections: List[Dict[str, Any]] = [
            {"type": "heading", "text": "1. Core Theory & Key Concepts"},
            {"type": "paragraph", "text": theory.strip()},
        ]
        if formulas and formulas.strip():
            pdf_sections.extend([
                {"type": "heading", "text": "2. Key Formulas & Equations"},
                {"type": "code", "code": formulas.strip(), "language": "text"},
            ])
        if viva_questions:
            pdf_sections.append({"type": "heading", "text": "3. Viva & Exam Prep Questions"})
            for idx, v in enumerate(viva_questions, start=1):
                pdf_sections.append({
                    "type": "paragraph",
                    "text": f"<b>Q{idx}. {v.get('question', '')}</b><br/><i>Ans:</i> {v.get('answer', '')}",
                })

        build_report_pdf(
            output_path=pdf_file,
            assignment_meta={"course": workspace.course_name, "title": f"Study Notes: {topic}"},
            sections=pdf_sections,
            config=config,
        )

    return {"markdown": md_file, "pdf": pdf_file}


def download_drive_file(
    drive_service: Any,
    file_id: str,
    dest_path: Union[str, Path],
) -> Path:
    """Download a Google Drive file by ID using drive_service and MediaIoBaseDownload."""
    from googleapiclient.http import MediaIoBaseDownload

    target = Path(dest_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
        with io.FileIO(target, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
    except Exception:
        if target.exists() and target.stat().st_size == 0:
            try:
                target.unlink()
            except OSError:
                pass
        raise

    return target

