# 🎓 Google Classroom Universal Automation Suite

A production-grade, zero-distraction CLI and automation suite designed for pairing with AI agents to inspect, manage, track, and execute 100% verified submissions to **any** course in Google Classroom without hallucination.

---

## 🏛️ Architecture & Anti-Hallucination Protocol

Agents commonly hallucinate during web submissions due to ambiguous UI states, unconfirmed modals, or intercepted pointer events. This suite eliminates hallucinations through a **Dual-Layer Verification Protocol**:

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

## 🗺️ The Exact Map of Submission Execution

Every submission strictly executes this deterministic 10-step map:

```text
1. [TAB HYGIENE]       Connect to Chrome (port 9444) -> Terminate all non-Classroom tabs.
2. [NAVIGATION]        Open assignment details URL (canonical alternateLink).
3. [STATE CHECK]       Wait for 'Your work' widget -> If 'Unsubmit' is visible, exit (Already Turned In).
4. [FILE ATTACHMENT]   Click '+ Add or create' -> 'File' -> Switch to 'Upload' tab in Google Drive Picker iframe.
                       Trigger native file chooser via 'Browse' button OR inject into hidden file input.
                       Wait for upload chip to appear in 'Your work' (up to 90s).
                       Wait for .hrIntegrationsOnepick backdrop overlay to detach.
5. [LINK ATTACHMENT]   Click '+ Add or create' -> 'Link' -> Input URL -> Click 'Add link'.
6. [ACTION BUTTON]     Wait for 'Turn in' / 'Mark as done' / 'Resubmit' to become enabled. Click it.
7. [MODAL CONFIRM]     Wait for confirmation modal dialog ([role='dialog']) -> Click modal 'Turn in' button.
8. [DOM VERIFICATION]  Poll until 'Unsubmit' button and 'Turned in' badge are confirmed.
9. [API VERIFICATION]  Query Google Classroom API to verify studentSubmissions.state == 'TURNED_IN'.
10. [CLEANUP]          Close assignment tab and terminate any newly opened unrelated tabs.
```

---

## 🚀 Quick Setup Guide

### 1. Google Cloud OAuth Credentials
1. Place your Google Cloud OAuth client credentials JSON in this directory as:
   ```
   d:\temp\Classroom\credentials.json
   ```
2. Required Scopes:
   - `classroom.courses.readonly`
   - `classroom.coursework.me`
   - `classroom.student-submissions.me.readonly`
   - `drive.file`

### 2. Isolated Chrome Session (Port 9444)
Launch your isolated Chrome browser instance on debug port `9444`:
```powershell
Start-Process chrome -ArgumentList "--remote-debugging-port=9444 --user-data-dir=`"$PWD\.chrome_isolated`" `"https://classroom.google.com`""
```
*(Port 9444 ensures complete isolation from any background terminal jobs running on port 9222).*

---

## 🛠️ Unified Master CLI: `classroom_master.py`

The primary interface combining API intelligence with browser execution:

### 1. List All Active Courses
```powershell
py classroom_master.py courses
```

### 2. Scan Pending Coursework (Ultra-Fast Batch Engine)
Scans all courses using batch submission queries (`courseWorkId='-'`) in ~5 seconds, automatically ignoring HMI (Human Machine Interaction):
```powershell
py classroom_master.py pending
```
To scan a specific course:
```powershell
py classroom_master.py pending --course "Computer Network"
```

### 3. View Assignment Details & Prompts
```powershell
py classroom_master.py details --course "Network" --assignment "EXPERIMENT 7"
```

### 4. Verify Server Submission State (Zero Browser Overhead)
Checks the official Google Classroom API ground-truth status and attachments:
```powershell
py classroom_master.py verify --course "Network" --assignment "EXPERIMENT 6"
```

### 5. Universal Automated Submission
Submit deliverables to **any** course in your Classroom:

```powershell
# Single File Deliverable (PDF, DOCX, ZIP, PY, etc.):
py classroom_master.py submit --course "Network" --assignment "EXPERIMENT 7" --file "CN_Exp07.pdf"

# Multiple Files (e.g., Code + Report):
py classroom_master.py submit --course "Cryptography" --assignment "Lab 8" --files "report.pdf" "code.zip"

# File + Web Link (e.g., Report + Credly Badge / GitHub Repo):
py classroom_master.py submit --course "Cloud Computing" --assignment "LAB 10" --file "report.pdf" --link "https://www.credly.com/..."

# No Attachments ('Mark as done'):
py classroom_master.py submit --course "Network" --assignment "SURVEY 1" --mark-done
```

---

## 🎯 Dedicated Submission Engine: `auto_submit.py`

Laser-focused submission engine with strict tab hygiene:

```powershell
# Direct URL submission:
py auto_submit.py --url "https://classroom.google.com/c/.../a/.../details" --file "deliverable.pdf"

# Multi-file direct URL submission:
py auto_submit.py --url "https://classroom.google.com/c/.../a/.../details" --files "doc.pdf" "source.zip"

# Tab hygiene (close all non-Classroom tabs):
py auto_submit.py --clean-tabs
```

---

## 📁 Repository Directory Structure

```text
d:\temp\Classroom\
├── auto_submit.py          # Dedicated browser submission engine (Playwright CDP)
├── classroom_master.py     # Master CLI for discovery, inspection, submission & verify
├── classroom_manager.py    # Google Classroom & Drive API client library
├── credentials.json        # Google Cloud OAuth client secrets
├── token.json              # Cached OAuth user tokens
├── requirements.txt        # Python package dependencies
├── .gitignore              # Repository exclusion rules
├── README.md               # Architecture and documentation
└── deliverables/           # Final verified submitted deliverables
    ├── CN_EXPERIMENT_4.pdf
    ├── CN_Expt_No_5.pdf
    ├── CN_Expt_No_6.pdf
    ├── DWM_EXPT4.pdf
    ├── CCL_Assignment09_Report.pdf
    ├── CCL_Lab06_Report.pdf
    ├── CCL_Lab07_Report.pdf
    ├── CCL_Lab08_Report.pdf
    └── CCL_Lab10_Report.pdf
```

---

## 🛡️ Anti-Hallucination Commitments & Standards
- Never reports a submission as complete until verified via browser DOM (`Unsubmit` button) and confirmed via Google Classroom API (`state: TURNED_IN`).
- Automatically handles both hidden file inputs and Google Drive Picker's visible `Browse` button using Playwright's `expect_file_chooser()`.
- Automatically enforces overlay detachment (`.hrIntegrationsOnepick`) before clicking submission buttons.
- Tab hygiene prevents distraction by closing any non-Classroom tabs across the session.
