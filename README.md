# 🤖 Chitti: The Super-Intelligent Classroom Agent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?style=flat&logo=python&logoColor=white" alt="Python Versions">
  <img src="https://img.shields.io/badge/Tests-96%20Passed%20(100%25)-success.svg?style=flat&logo=pytest&logoColor=white" alt="Test Status">
  <img src="https://img.shields.io/badge/Google%20OAuth-Desktop%20App%20Verified-4285F4.svg?style=flat&logo=google&logoColor=white" alt="OAuth Verified">
  <img src="https://img.shields.io/badge/PDF%20Engine-ReportLab%20%2B%20PyMuPDF-FF6F00.svg?style=flat" alt="PDF Engine">
  <img src="https://img.shields.io/badge/Security-Sanitized%20%26%20Zero--Leak-brightgreen.svg?style=flat&logo=security" alt="Security Verified">
</p>

> *"Speed 1 terahertz, memory 1 zettabyte."*  
> **Chitti** is an autonomous, production-grade academic agent engineered to assist engineering and university students with coursework, lab assignments, study notes, and Google Classroom submissions. It parses teacher prompts, inspects grading rubrics, writes clean academic reports across **3 distinct completion strategies**, embeds authentic terminal execution proofs, organizes per-subject workspaces, and handles verified 1-click browser turn-ins with zero hallucination.

---

## 📑 Table of Contents
- [✨ Key Capabilities](#-key-capabilities)
- [⚡ 1-Minute Quick Setup & OAuth Guide](#-1-minute-quick-setup--oauth-guide)
- [📂 Per-Course Isolated Workspace Architecture](#-per-course-isolated-workspace-architecture)
- [🎯 The 3 Assignment Completion Strategies](#-the-3-assignment-completion-strategies)
  - [Strategy A: Build From Scratch (Code + Theory + Proofs)](#strategy-a-build-from-scratch-code--theory--proofs)
  - [Strategy B: Teacher Rubric / Template Augmentation](#strategy-b-teacher-rubric--template-augmentation)
  - [Strategy C: Personalize / Sanitize Reference Assignment](#strategy-c-personalize--sanitize-reference-assignment)
- [📚 High-Agency Study Notes & Materials Sync](#-high-agency-study-notes--materials-sync)
- [💻 Complete CLI Command Reference](#-complete-cli-command-reference)
- [🛡️ Dual-Layer Verification Protocol](#️-dual-layer-verification-protocol)
- [🧪 Running the Test Suite](#-running-the-test-suite)

---

## ✨ Key Capabilities

- **Zero-Distraction Academic Dashboard (`chitti status`)**: Live tracking of urgent/overdue coursework, staged deliverables, and generated study notes in a single view.
- **Publication-Grade PDF Compilation**: ReportLab Platypus engine with running headers, student metadata tables, two-pass `Page X of Y` canvas numbering, syntax-highlighted code blocks, and bordered figure framing.
- **Authentic Terminal Screenshots Only**: Ingests real terminal execution screenshots, observation photos, or circuit captures with auto-cropping and clean borders. Strictly prohibits synthetic or mock ASCII cards.
- **3 Flexible Completion Strategies**: From scratch, augmenting a teacher's rubric cover page, or redacting and personalizing classmate/senior reference PDFs.
- **Clean Workspace Discipline**: Everything generated resides in `output/<course_slug>/` (`assignments/`, `materials/`, `notes/`). The root repository stays 100% clean.
- **Study Notes Generator (`chitti notes`)**: Produces structured Markdown revision sheets and companion publication PDFs for quick exam prep.
- **Materials Catalog (`chitti materials`)**: Extracts teacher-shared Drive attachments, syllabi, and links into a local `materials_catalog.md` with direct 1-click browser URLs.
- **Dual-Layer Turn-In Verification (`chitti submit`)**: CDP Playwright upload + official Google Classroom API server-side verification (`state == 'TURNED_IN'`).

---

## ⚡ 1-Minute Quick Setup & OAuth Guide

### 1. Install Dependencies
```bash
git clone https://github.com/your-username/chitti.git
cd chitti
pip install -r requirements.txt
playwright install chromium
```

### 2. Google Cloud OAuth Setup (Desktop Application)
Google restricts local OAuth tokens for Web applications with `Error 400: redirect_uri_mismatch` and hides the Advanced bypass link. Chitti requires a **Desktop app** credential:

1. Open [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
2. Click **+ Create credentials** -> **OAuth client ID**.
3. Select Application type: **Desktop app** (NOT Web application). Name it `Chitti`.
4. Click **Create**, then click **DOWNLOAD JSON**.
5. Save it to your `Downloads` folder (or copy it to the project directory as `credentials.json`).

### 3. Run Chitti's Setup Wizard
```bash
python chitti.py setup
```
Chitti will:
- Auto-detect and import the desktop credential from `~/Downloads`.
- Prompt you for your academic profile (Name, Roll Number, Department, Institution).
- Save configuration to `student_config.json` (strictly `.gitignore`'d).

*(For automated / headless setup:)*
```bash
python chitti.py setup --non-interactive \
  --name "Alex Doe" \
  --roll "CS-2026-042" \
  --dept "Computer Engineering" \
  --institution "Apex Institute of Technology"
```

---

## 📂 Per-Course Isolated Workspace Architecture

All student deliverables, study notes, and downloaded course materials are strictly isolated per subject under `output/`:

```text
output/
├── computer_network/
│   ├── assignments/
│   │   └── self_learning_topic/
│   │       ├── final_submission.pdf     <-- 100% audited submission deliverable
│   │       ├── manifest.json            <-- SHA-256 integrity checksums
│   │       ├── SUMMARY.md               <-- Requirements checklist
│   │       └── assets/                  <-- Framed screenshots, scripts, data
│   ├── materials/
│   │   ├── materials_catalog.md         <-- Index of teacher drive files & web links
│   │   └── lab_manuals/
│   └── notes/
│       └── tcp_handshake/
│           ├── notes.md                 <-- Markdown study revision guide
│           └── notes.pdf                <-- Beautiful PDF cheat sheet
└── cryptography/
    ├── assignments/
    │   └── non_tech_lab_2_hash_integrity/
    ├── materials/
    └── notes/
```

---

## 🎯 The 3 Assignment Completion Strategies

### Strategy A: Build From Scratch (Code + Theory + Proofs)
Compile a full academic laboratory report from raw code, theory notes, and terminal screenshots:

```bash
# 1. Compile report with embedded source code, theory, and authentic screenshot
python chitti.py build \
  --course "Cryptography" \
  --assignment "Lab 2 - Hash Integrity" \
  --theory "output/cryptography/assignments/hash_integrity/theory.md" \
  --code "output/cryptography/assignments/hash_integrity/verify_hash.py" \
  --proof "output/cryptography/assignments/hash_integrity/terminal_execution.png" \
  --proof-caption "Figure 1: Authentic Terminal Verification of Hash Digest Avalanche & HMAC-SHA256"
```
**Output:** A 3-page publication-grade PDF containing college header, student metadata box, theoretical formulation, monospace syntax code block, and auto-bordered terminal screenshot with figure caption.

---

### Strategy B: Teacher Rubric / Template Augmentation
When instructors provide a rubric cover sheet or lab manual template PDF, Chitti stamps student details onto Page 0 and seamlessly appends continuation solution pages:

```bash
python chitti.py build \
  --course "Cryptography" \
  --assignment "Lab 3 - RSA Encryption" \
  --template "output/cryptography/materials/teacher_rubric_template.pdf" \
  --mode template \
  --code "solution_rsa.py" \
  --proof "rsa_terminal.png"
```
**Output:** The original rubric sheet as Page 1 with student metadata stamped into the rubric boxes, followed by subsequent solution pages with matching margins and two-pass page numbers.

---

### Strategy C: Personalize / Sanitize Reference Assignment
When utilizing a reference PDF from a classmate or senior, Chitti redacts the original student's credentials and stamps the current student's identity while preserving all charts, mathematical equations, and body text:

```bash
python chitti.py build \
  --course "Cryptography" \
  --assignment "Lab 4 - Digital Signatures" \
  --template "reference_report.pdf" \
  --mode personalize \
  --old-name "John Doe" \
  --old-roll "9999"
```
**Output:** Complete redaction of previous author info and clean overlay of current student name, roll number, and department.

---

## 📚 High-Agency Study Notes & Materials Sync

### 1. Generate Instant Exam Study Notes & PDF Sheets
Generate quick revision sheets for challenging engineering concepts:

```bash
python chitti.py notes \
  --course "Cryptography" \
  --topic "Diffie-Hellman Key Exchange & Man-in-the-Middle Attack" \
  --theory "Diffie-Hellman enables two parties to negotiate a shared secret over an insecure medium using modular exponentiation..." \
  --formulas "Key Equation: K = (B^a) mod p = (A^b) mod p"
```
*Creates both `notes.md` and a clean `notes.pdf` in `output/<course>/notes/<topic>/`.*

List all study notes across courses:
```bash
python chitti.py notes --list
```

### 2. Sync Course Materials & Drive Resources
```bash
python chitti.py materials --course "COMPUTER NETWORK"
```
Downloads available PDFs and compiles a structured `materials_catalog.md` linking every syllabus file, rubric document, and docx with direct web URLs for 1-click browser access.

---

## 💻 Complete CLI Command Reference

| Command | Syntax | Description |
|---|---|---|
| `status` | `python chitti.py status` | Comprehensive academic dashboard with pending tasks, staged PDFs, and study notes. |
| `setup` | `python chitti.py setup` | Interactive student profile configuration wizard with OAuth credential auto-import. |
| `courses` | `python chitti.py courses` | List all enrolled Google Classroom courses with IDs and section details. |
| `pending` | `python chitti.py pending [--course "..."]` | Scan pending and overdue assignments across all courses. |
| `details` | `python chitti.py details --course "..." --assignment "..."` | Inspect assignment prompt, max points, due dates, and rubrics. |
| `build` | `python chitti.py build --course "..." --assignment "..." [flags]` | Compile academic PDF via Strategy A, B, or C and stage in `output/`. |
| `attach-proof` | `python chitti.py attach-proof --course "..." --assignment "..." --image "..."` | Attach and frame additional terminal screenshot into staged report. |
| `notes` | `python chitti.py notes --course "..." --topic "..." [--theory "..."]` | Generate revision markdown notes and companion PDF cheat sheet. |
| `materials` | `python chitti.py materials --course "..."` | Download course materials and generate `materials_catalog.md`. |
| `review` | `python chitti.py review [--course "..."]` | Review staged deliverables, page counts, and automated audit status. |
| `submit` | `python chitti.py submit --course "..." --assignment "..."` | Execute 100% verified Playwright CDP turn-in and check Classroom API server state. |

---

## 🛡️ Dual-Layer Verification Protocol

Chitti rejects the "fire-and-forget" approach to AI automation. Submissions undergo a rigorous dual-layer audit:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DUAL-LAYER VERIFICATION PROTOCOL                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 1: Real Browser DOM Verification (Playwright CDP Engine)              │
│    - Detects presence of interactive 'Unsubmit' button                      │
│    - Detects 'Turned in' / 'Turned in late' status badges                   │
│    - Confirms dismissal of modal dialogs & detach of Drive Picker overlays  │
│                                                                             │
│  Layer 2: Google Classroom API Server-Side Verification                     │
│    - Directly queries courses.courseWork.studentSubmissions endpoint        │
│    - Confirms authoritative Google server state: state == 'TURNED_IN'       │
│    - Verifies exact Google Drive attachment IDs & URLs                      │
│    - Provides 100% mathematical certainty (0% hallucination risk)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧪 Running the Test Suite

Chitti is tested with a comprehensive suite covering sanitization, CLI dispatch, ReportLab canvas flowables, PyMuPDF redaction/augmentation, media processing, and Google API error recovery:

```bash
# Run all unit and integration tests (96 tests)
pytest -v

# Run sanitization and leak prevention checks
pytest -v tests/test_sanitization.py
```

### Git Sanitization Guarantee
- Zero personal roll numbers or student credentials are tracked in source code.
- `credentials.json`, `token.json`, `student_config.json`, and `output/` are strictly ignored by `.gitignore`.

---

<p align="center">
  <b>Built with precision for students by students. 🤖</b>
</p>
