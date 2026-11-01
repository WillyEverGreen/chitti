import os
import re
from pathlib import Path

FORBIDDEN_PATTERNS = [
    r"10707",               # Personal roll number
    r"ODcwODczMTkxMjk2",    # Hardcoded base64 course IDs
    r"870873191296",        # Hardcoded raw course IDs
]

LEGACY_SCRIPTS = [
    "submit_all_css.py",
    "submit_all_dwm.py",
    "submit_css_789.py",
    "submit_lab6.py",
    "submit_lab7.py",
    "submit_remaining.py",
    "submit_updated_cn_pdfs.py",
    "finish_all_css.py",
    "reclaim_cn_submissions.py",
    "submit_all_clean.py",
    "submit_all_final.py",
    "test_browse_loc.py",
    "css_notes_generator.py",
]

def get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent

def test_no_hardcoded_user_secrets_in_src():
    root = get_repo_root()
    checked_extensions = (".py", ".json", ".md")
    ignored_dirs = {".git", ".legacy_archive", "tests", "__pycache__", ".superpowers", "docs", "output", ".chrome_isolated", ".browser_profile"}
    
    violations = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs]
        if any(ignored in Path(dirpath).parts for ignored in ignored_dirs):
            continue
        for f in filenames:
            if f.endswith(checked_extensions) and f not in ("credentials.json", "token.json"):
                filepath = Path(dirpath) / f
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                for pattern in FORBIDDEN_PATTERNS:
                    if re.search(pattern, content):
                        violations.append(f"{filepath.relative_to(root)} matched forbidden pattern {pattern}")
    
    assert not violations, "Sanitization violations found:\n" + "\n".join(violations)

def test_no_legacy_scripts_in_root():
    root = get_repo_root()
    found_legacy = [f for f in LEGACY_SCRIPTS if (root / f).exists()]
    assert not found_legacy, f"Legacy personal scripts found in root: {found_legacy}"

def test_gitignore_rules():
    root = get_repo_root()
    gitignore_path = root / ".gitignore"
    assert gitignore_path.exists(), ".gitignore must exist"
    content = gitignore_path.read_text(encoding="utf-8")
    assert ".legacy_archive" in content, ".gitignore must ignore .legacy_archive/"
    assert "output" in content, ".gitignore must ignore output/"
