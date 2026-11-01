# 🤖 Chitti: The Super-Intelligent Classroom Agent

> *"Speed 1 terahertz, memory 1 zettabyte."*  
> The ultimate, zero-distraction AI agent designed to help students master and complete coursework end-to-end: understanding teacher prompts, generating publication-grade PDFs (from scratch or augmenting teacher templates), framing authentic terminal execution screenshots, staging deliverables in `output/` for student review, and executing 100% verified submissions without hallucination.

---

## ⚡ 1-Minute Quick Setup

Getting Chitti running is completely frictionless:

### 1. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Run Chitti's Setup Wizard
```bash
python chitti.py setup
```
Chitti will prompt you for your name, roll number, department, and institution, and check that your Google Cloud `credentials.json` is ready.

*(You can also configure silently via CLI flags:)*
```bash
python chitti.py setup --non-interactive --name "Jane Doe" --roll "CS-2026-042" --dept "Computer Science" --institution "Apex Institute of Technology"
```

---

## 🚀 Core Workflows

### 1. Discover Pending Coursework
Quickly scan all your active enrolled courses and view upcoming assignments:
```bash
# List all active courses
python chitti.py courses

# Scan pending assignments across all courses
python chitti.py pending

# Scan a specific course
python chitti.py pending --course "Computer Networks"
```

---

### 2. Inspect Assignment Details & Capability Audit
Perform a deep analysis of teacher requirements:
```bash
python chitti.py details --course "Computer Networks" --assignment "Experiment 7"
```
Chitti inspects:
- Official teacher instructions, deadlines, and attached rubrics.
- **Brutally Honest Capability Audit**: Classifies what is 100% automatable (code, algorithms, theory, calculations) vs. what requires physical student agency (e.g. physical breadboard wiring, local Wi-Fi packet captures, personal student signatures) so you never submit fake data.

---

### 3. Generate Reports & Augment Teacher Templates
Compile a publication-grade assignment report:

#### Mode A: Build From Scratch
```bash
python chitti.py build --course "Computer Networks" --assignment "Experiment 7"
```

#### Mode B: Build Upon Teacher's Template PDF
If your instructor provided a template PDF (e.g., question paper or lab sheet):
```bash
python chitti.py build --course "Computer Networks" --assignment "Experiment 7" --template "templates/lab7_prompt.pdf"
```
Chitti seamlessly appends your formatted solution pages after the teacher's prompt with unified styling and running page numbering (`Page X of Y`).

---

### 4. Easily Attach Terminal Screenshots & Proofs
Embed authentic terminal outputs or experimental screenshots with automatic margin cropping, clean border framing, and numbered figure captions:

```bash
# Attach proof during report compilation
python chitti.py build --course "Computer Networks" --assignment "Experiment 7" \
  --proof "screenshots/rip_routing_output.png" \
  --proof-caption "RIP Routing Table Convergence Terminal Output"

# Or attach proofs to an already staged deliverable
python chitti.py attach-proof --course "Computer Networks" --assignment "Experiment 7" \
  --image "screenshots/traceroute.png" \
  --caption "Traceroute Verification to Gateway"
```
> **Constraint Enforced:** Chitti strictly ingests authentic terminal screenshots and observations—never fake synthetic terminal UI mocks.

---

### 5. Review Staged Deliverables in `output/`
Inspect your ready-to-submit deliverables:
```bash
python chitti.py review
```
This prints an interactive console summary with:
- Clickable `file:///` local links to your compiled PDF.
- `manifest.json` with SHA-256 integrity checksums.
- `SUMMARY.md` checklist detailing completed items and any required student action items.
- Direct link to the Google Classroom assignment webpage.

---

### 6. Verified Classroom Turn-In (Optional)
When you've reviewed your deliverables and are ready to turn them in:
```bash
python chitti.py submit --course "Computer Networks" --assignment "Experiment 7"
```
Chitti launches an isolated Playwright browser, uploads `output/<course>/<assignment>/final_submission.pdf`, confirms the Google Classroom submission modal, and mathematically verifies `state == 'TURNED_IN'` via the official Google Classroom API.

---

## 🏛️ Architecture & Verification Protocol

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

## 🧪 Running Automated Tests
```bash
pytest -v
```
All subsystems (sanitization, configuration, authentic media framing, dual-mode PDF compilation, staging, and Chitti CLI interface) are covered by automated unit tests.
