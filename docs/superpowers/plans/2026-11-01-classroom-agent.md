# Classroom Agent: Universal Student Assistant & Deliverable Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the personal Classroom submission workspace into an open, easy-to-setup academic agent that solves assignments, builds high-fidelity PDFs from scratch or from teacher templates, processes genuine terminal screenshots without synthetic mocks, stages deliverables cleanly in `output/` for student review, and sanitizes all personal data and obsolete scripts.

**Architecture:** A modular Python suite structured into:
1. `classroom/config.py` & `classroom_setup.py`: Zero-friction student setup and profile management.
2. `classroom/media_processor.py`: Media engine for authentic terminal screenshot ingestion, framing, border enhancement, and image optimization (strictly no synthetic fake terminal code mocks).
3. `classroom/pdf_engine.py`: Dual-mode PDF generator (ReportLab for from-scratch structured reports + PyMuPDF/fitz for teacher template continuation and overlays).
4. `classroom/deliverables.py`: Staging manager that organizes assets, generates manifests, and prints interactive review summaries with Classroom links.
5. `classroom_agent.py`: Unified, user-friendly CLI tying together discovery, generation, template merging, staging, and optional verified submission.

**Tech Stack:** Python 3.10+, ReportLab, PyMuPDF (fitz), Pillow (PIL), Rich, Google Classroom API (`google-api-python-client`), Playwright (sync CDP for optional submission), Pytest.

**Spec:** Grounded in user requirements:
- Full E2E pipeline preparing assignment submissions in an `output/` folder and notifying the student for review.
- Support both building PDFs from scratch and building upon/overlaying teacher-provided template PDFs.
- Easily add properly formatted/edited images and authentic screenshots from the user's actual terminal (strictly no fake terminal mocks generated via code).
- Frictionless setup wizard for new students.
- Remove hardcoded personal data, user tokens, and one-off subject scripts.
- Rigorous automated test coverage for each subsystem.

---

## Global Constraints

- **Python Version:** Python 3.10+ compatible.
- **Authentic Media Only:** Never generate synthetic terminal UI cards using code or mock HTML. Real image inputs only.
- **Sanitization:** No personal student roll numbers (e.g., `10707`), hardcoded course IDs, or personal Google tokens in version-controlled files.
- **Safe Staging:** All generated assets and PDFs must be staged under `output/<course_slug>/<assignment_slug>/` without touching existing source files.
- **Platform:** Cross-platform path handling (Windows, macOS, Linux) with UTF-8 stdout enforcement.

---

## Review Focus

1. **Teacher Template PDF Corruption/Incompatibility:** Complex or password-protected/XFA teacher PDFs causing PyMuPDF to crash; must gracefully detect and fallback to appending or report a clear actionable error.
2. **Extreme Image Aspect Ratios:** Very wide terminal screenshots or vertical mobile photos distorting PDF page boundaries; must auto-scale while preserving aspect ratio and fit within printable margins.
3. **Missing or Expired OAuth Tokens:** Student running the agent without setup or after token revocation; must prompt with a single-line setup instruction rather than dumping a stack trace.
4. **Filename / Slug Sanitization:** Course or assignment titles containing illegal Windows path characters (`:`, `?`, `/`, `\`, `*`, `|`, `"`); must safely sanitize folder names.
5. **PDF Overwrite Safety:** Running generation twice for the same assignment must not corrupt open file handles or silently erase past iterations without creating backups.

---

## File Structure

```text
classroom/
  ├── __init__.py
  ├── config.py              # Student profile & path configuration
  ├── media_processor.py     # Real screenshot framing, cropping, and optimization
  ├── pdf_engine.py          # ReportLab generation + PyMuPDF template merging
  ├── deliverables.py        # Staging, metadata manifest, and review notifications
  ├── api_client.py          # Google Classroom & Drive API wrapper
  └── submission_engine.py   # Verified browser CDP submission engine
classroom_setup.py           # Interactive onboarding wizard
classroom_agent.py           # Master CLI application
tests/
  ├── conftest.py
  ├── test_config.py
  ├── test_media_processor.py
  ├── test_pdf_engine.py
  ├── test_deliverables.py
  └── test_cli.py
```

---

## Task Breakdown

### Task 1: Repo Sanitization & Legacy Migration

**Files:**
- Create: `.legacy_archive/README.md`
- Move: `submit_all_css.py`, `submit_all_dwm.py`, `submit_css_789.py`, `submit_lab6.py`, `submit_lab7.py`, `submit_remaining.py`, `submit_updated_cn_pdfs.py`, `finish_all_css.py`, `reclaim_cn_submissions.py`, `submit_all_clean.py`, `submit_all_final.py`, `test_browse_loc.py` -> `.legacy_archive/`
- Modify: `.gitignore`
- Test: `tests/test_sanitization.py`

**Interfaces:**
- Consumes: Existing files in repo root.
- Produces: Clean root workspace containing only universal code; `.legacy_archive` ignored or cleanly separated.

- [ ] **Step 1: Write test for repository sanitization**
```python
# tests/test_sanitization.py
import os
import re

FORBIDDEN_PATTERNS = [
    r"10707",  # Personal roll number
    r"ODcwODczMTkxMjk2",  # Hardcoded base64 course IDs
    r"870873191296",       # Hardcoded raw course IDs
]

def test_no_hardcoded_user_secrets_in_src():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    checked_extensions = (".py", ".json", ".md")
    for dirpath, dirnames, filenames in os.walk(root):
        if any(ignored in dirpath for ignored in [".git", ".legacy_archive", "tests", "__pycache__", ".superpowers"]):
            continue
        for f in filenames:
            if f.endswith(checked_extensions) and f != "credentials.json" and f != "token.json":
                filepath = os.path.join(dirpath, f)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    for pattern in FORBIDDEN_PATTERNS:
                        assert not re.search(pattern, content), f"Forbidden pattern {pattern} found in {f}"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_sanitization.py`
Expected: FAIL due to legacy personal scripts containing roll numbers and course IDs.

- [ ] **Step 3: Move legacy personal scripts into `.legacy_archive/` and update `.gitignore`**
Move personal scripts to `.legacy_archive/` and ensure `.gitignore` excludes user tokens, credentials, and `output/`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_sanitization.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add .
git commit -m "chore: sanitize workspace and archive personal subject scripts"
```

---

### Task 2: Student Configuration & Setup Wizard

**Files:**
- Create: `classroom/config.py`
- Create: `classroom_setup.py`
- Create: `config.template.json`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: Environment variables or `config.json`.
- Produces: `StudentConfig` dataclass:
  - `student_name: str`
  - `roll_number: str`
  - `department: str`
  - `institution: str`
  - `output_dir: Path`
  - `credentials_path: Path`
  - `chrome_debug_port: int`

- [ ] **Step 1: Write test for config validation and serialization**
```python
# tests/test_config.py
from pathlib import Path
from classroom.config import StudentConfig, load_config, save_config

def test_default_config_creation(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg = StudentConfig(
        student_name="Jane Doe",
        roll_number="CS2026-001",
        department="Computer Science",
        institution="Engineering College",
        output_dir=str(tmp_path / "output")
    )
    save_config(cfg, cfg_file)
    assert cfg_file.exists()
    
    loaded = load_config(cfg_file)
    assert loaded.student_name == "Jane Doe"
    assert loaded.roll_number == "CS2026-001"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_config.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'classroom'`.

- [ ] **Step 3: Implement `classroom/config.py` and `classroom_setup.py`**
Implement `StudentConfig` with automatic path resolution, validation, slugification helpers, and interactive wizard CLI in `classroom_setup.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_config.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add classroom/config.py classroom_setup.py config.template.json tests/test_config.py
git commit -m "feat(config): add student configuration manager and setup wizard"
```

---

### Task 3: Authentic Media & Terminal Screenshot Processing Engine

**Files:**
- Create: `classroom/media_processor.py`
- Test: `tests/test_media_processor.py`

**Interfaces:**
- Consumes: Raw image files (PNG/JPG/WEBP) from user disk or genuine terminal captures.
- Produces: `ProcessedImage` object:
  - `path: Path` (saved high-res output image)
  - `width: int`
  - `height: int`
  - `aspect_ratio: float`
  - `caption: str`
  - Functions: `process_terminal_screenshot(src_path, dest_path, caption=None, add_border=True) -> ProcessedImage`
  - `process_diagram(src_path, dest_path, caption=None) -> ProcessedImage`

- [ ] **Step 1: Write test for image cropping, framing, and aspect preservation**
```python
# tests/test_media_processor.py
from PIL import Image
from classroom.media_processor import process_terminal_screenshot, process_diagram

def test_process_terminal_screenshot(tmp_path):
    # Create a dummy raw screenshot image
    raw_img = Image.new("RGB", (800, 600), color=(30, 30, 30))
    raw_path = tmp_path / "terminal_raw.png"
    raw_img.save(raw_path)
    
    out_path = tmp_path / "terminal_clean.png"
    proc = process_terminal_screenshot(raw_path, out_path, caption="Figure 1: Ping Command Output", add_border=True)
    
    assert out_path.exists()
    assert proc.caption == "Figure 1: Ping Command Output"
    assert proc.width > 0
    assert proc.height > 0
    
    # Check that output image has border added
    res_img = Image.open(out_path)
    assert res_img.size[0] >= 800
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_media_processor.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'classroom.media_processor'`.

- [ ] **Step 3: Implement `classroom/media_processor.py`**
Use Pillow to auto-crop whitespace/black padding, apply subtle clean borders (1px slate/gray frame), optional padding, and DPI enhancement (300 DPI metadata) without generating fake synthetic terminal cards.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_media_processor.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add classroom/media_processor.py tests/test_media_processor.py
git commit -m "feat(media): implement authentic terminal screenshot and image processor"
```

---

### Task 4: Dual-Mode PDF Generation Engine (From-Scratch & Template Augmentation)

**Files:**
- Create: `classroom/pdf_engine.py`
- Test: `tests/test_pdf_engine.py`

**Interfaces:**
- Consumes: `StudentConfig`, structured report sections (Title, Objectives, Theory, Code, Media), or teacher's template PDF file path.
- Produces: `PDFBuildResult`:
  - `output_path: Path`
  - `page_count: int`
  - Functions:
    - `build_report_pdf(config: StudentConfig, assignment_meta: dict, sections: list, output_path: Path) -> Path`
    - `augment_teacher_template(template_pdf_path: Path, continuation_pdf_path: Path, output_path: Path) -> Path`
    - `overlay_on_template_page(template_pdf_path: Path, page_num: int, overlays: list, output_path: Path) -> Path`

- [ ] **Step 1: Write test for generating report and merging with teacher template**
```python
# tests/test_pdf_engine.py
import fitz  # PyMuPDF
from classroom.config import StudentConfig
from classroom.pdf_engine import build_report_pdf, augment_teacher_template

def test_build_report_pdf(tmp_path):
    cfg = StudentConfig("Alice Smith", "101", "IT", "Uni", str(tmp_path))
    out_pdf = tmp_path / "report.pdf"
    sections = [
        {"type": "heading", "text": "Experiment 1: Network Topology"},
        {"type": "paragraph", "text": "In this lab we studied star and mesh topologies."},
        {"type": "code", "text": "ping -c 4 192.168.1.1\ntraceroute google.com"},
    ]
    res_path = build_report_pdf(cfg, {"title": "Lab 1"}, sections, out_pdf)
    assert res_path.exists()
    doc = fitz.open(res_path)
    assert len(doc) >= 1
    doc.close()

def test_augment_teacher_template(tmp_path):
    # Create mock teacher PDF
    teacher_pdf = tmp_path / "teacher_prompt.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Teacher Prompt: Complete Experiment 1")
    doc.save(teacher_pdf)
    doc.close()
    
    # Create solution PDF
    cfg = StudentConfig("Alice Smith", "101", "IT", "Uni", str(tmp_path))
    sol_pdf = tmp_path / "sol.pdf"
    build_report_pdf(cfg, {"title": "Solution"}, [{"type": "paragraph", "text": "Solution content"}], sol_pdf)
    
    # Merge
    merged_pdf = tmp_path / "merged_final.pdf"
    augment_teacher_template(teacher_pdf, sol_pdf, merged_pdf)
    assert merged_pdf.exists()
    merged_doc = fitz.open(merged_pdf)
    assert len(merged_doc) == 2  # Teacher prompt (1 page) + Solution (1 page)
    merged_doc.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_pdf_engine.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'classroom.pdf_engine'`.

- [ ] **Step 3: Implement `classroom/pdf_engine.py`**
Combine ReportLab Platypus styles (academic headers, clean typography, code flowables, image blocks with captions) and PyMuPDF PDF merging/overlay capabilities.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_pdf_engine.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add classroom/pdf_engine.py tests/test_pdf_engine.py
git commit -m "feat(pdf): add dual-mode report generation and teacher template augmentation engine"
```

---

### Task 5: Deliverables Manager & Review Notification Staging

**Files:**
- Create: `classroom/deliverables.py`
- Test: `tests/test_deliverables.py`

**Interfaces:**
- Consumes: Course metadata, assignment metadata, final PDF path, processed assets.
- Produces: Staging workspace in `output/<course_slug>/<assignment_slug>/`:
  - `manifest.json` (metadata + file checksums + status)
  - `SUMMARY.md` (student instructions and verification checklist)
  - Console summary card with clickable paths and Classroom web link.
  - Functions: `stage_deliverable(course_name, assignment_title, pdf_path, assets, classroom_url) -> StagedDeliverable`

- [ ] **Step 1: Write test for deliverable staging and manifest generation**
```python
# tests/test_deliverables.py
from classroom.deliverables import stage_deliverable

def test_stage_deliverable(tmp_path):
    dummy_pdf = tmp_path / "sample.pdf"
    dummy_pdf.write_text("%PDF-1.4 dummy", encoding="utf-8")
    
    staged = stage_deliverable(
        output_root=tmp_path / "output",
        course_name="Computer Networks",
        assignment_title="Lab 6 RSA",
        pdf_path=dummy_pdf,
        assets=[],
        classroom_url="https://classroom.google.com/c/123/a/456/details"
    )
    
    assert staged.staged_dir.exists()
    assert (staged.staged_dir / "final_submission.pdf").exists()
    assert (staged.staged_dir / "manifest.json").exists()
    assert (staged.staged_dir / "SUMMARY.md").exists()
    assert staged.classroom_url == "https://classroom.google.com/c/123/a/456/details"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_deliverables.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'classroom.deliverables'`.

- [ ] **Step 3: Implement `classroom/deliverables.py`**
Implement safe staging, slug generation (safe path strings for Windows/Linux), manifest generator with sha256 checksums, markdown summary generator, and Rich console notification banner.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_deliverables.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add classroom/deliverables.py tests/test_deliverables.py
git commit -m "feat(deliverables): add staging manager, manifest generator, and review notifications"
```

---

### Task 6: Master CLI Application & User Experience Integration

**Files:**
- Create: `classroom_agent.py`
- Modify: `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- CLI commands:
  - `python classroom_agent.py setup`
  - `python classroom_agent.py courses`
  - `python classroom_agent.py pending`
  - `python classroom_agent.py build --course <name> --assignment <name> [--template <pdf>]`
  - `python classroom_agent.py review`
  - `python classroom_agent.py submit --course <name> --assignment <name>` (optional explicit submission)

- [ ] **Step 1: Write CLI end-to-end integration test**
```python
# tests/test_cli.py
import subprocess
import sys

def test_cli_help():
    res = subprocess.run([sys.executable, "classroom_agent.py", "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Classroom Agent" in res.stdout
    assert "setup" in res.stdout
    assert "build" in res.stdout
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_cli.py`
Expected: FAIL with file not found.

- [ ] **Step 3: Implement `classroom_agent.py` and update `README.md`**
Create clean CLI using `argparse` and `rich`, cleanly binding together config, media processor, PDF engine, deliverables staging, Classroom API discovery, and optional verified browser turn-in. Update `README.md` with beginner-friendly instructions.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_cli.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add classroom_agent.py README.md tests/test_cli.py
git commit -m "feat(cli): provide unified master classroom agent CLI and documentation"
```

---

### Task 7: Full Test Suite Verification & Pre-Flight Audit

**Files:**
- Test: all tests in `tests/`
- Verify clean working tree and full test pass.

- [ ] **Step 1: Run complete pytest suite**
Run: `pytest -v tests/`
Expected: ALL PASS.

- [ ] **Step 2: Run sanity check on sanitization and documentation**
Verify no leftover personal credentials, personal roll numbers, or broken links.

- [ ] **Step 3: Final Commit**
```bash
git add .
git commit -m "test: verify full suite and complete classroom agent integration"
```
