#!/usr/bin/env python3
"""Interactive Onboarding and Configuration Wizard for Classroom Agent.

Initializes or updates `student_config.json` with student profile information,
credentials paths, and output settings.
"""

import argparse
import os
from pathlib import Path
import sys
from typing import Optional, List

from classroom.config import (
    StudentConfig,
    load_config,
    save_config,
    get_default_config_path,
)


def prompt_value(prompt: str, default: str = "", required: bool = False) -> str:
    """Prompt the user for an input string, with default value fallback."""
    suffix = f" [{default}]" if default else ""
    full_prompt = f"{prompt}{suffix}: "

    while True:
        try:
            val = input(full_prompt).strip()
        except EOFError:
            val = ""

        if not val and default:
            return default
        if not val and required:
            print("  This field cannot be empty. Please enter a value.")
            continue
        return val


def run_setup(argv: Optional[List[str]] = None) -> int:
    """Run the setup wizard with the provided CLI arguments or sys.argv."""
    parser = argparse.ArgumentParser(
        description="Classroom Agent Student Setup Wizard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompting (uses CLI args and defaults only)",
    )
    parser.add_argument("-n", "--name", default="", help="Student Full Name")
    parser.add_argument("-r", "--roll", default="", help="Roll / Registration Number")
    parser.add_argument("-d", "--dept", default="", help="Department / Major")
    parser.add_argument("-i", "--institution", default="", help="College or University Name")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory for generated deliverables")
    parser.add_argument("-c", "--credentials", default="credentials.json", help="Path to Google credentials.json")
    parser.add_argument("-t", "--token", default="token.json", help="Path to Google OAuth token.json")
    parser.add_argument("-p", "--port", type=int, default=9444, help="Chrome Remote Debugging port")
    parser.add_argument("--config-path", default=None, help="Target path for student_config.json")

    args = parser.parse_args(argv)

    target_config_path = Path(args.config_path).expanduser().resolve() if args.config_path else get_default_config_path()

    # Load existing config if available to pre-fill defaults
    existing_cfg = StudentConfig()
    if target_config_path.exists():
        try:
            existing_cfg = load_config(target_config_path)
        except Exception:
            pass

    # Check whether we should run interactively
    if args.non_interactive:
        is_interactive = False
    elif any([args.name, args.roll, args.dept, args.institution]):
        is_interactive = False
    else:
        is_interactive = True

    print("==========================================================")
    print("      Classroom Agent - Student Setup & Configuration     ")
    print("==========================================================")

    if is_interactive:
        print("Please provide your academic profile details for assignment headers.\n")
        name = prompt_value("Student Full Name", default=args.name or existing_cfg.student_name, required=True)
        roll = prompt_value("Roll / Registration Number", default=args.roll or existing_cfg.roll_number, required=True)
        dept = prompt_value("Department / Branch", default=args.dept or existing_cfg.department)
        institution = prompt_value("College / University", default=args.institution or existing_cfg.institution)
        out_dir = prompt_value("Deliverables Output Directory", default=args.output_dir or existing_cfg.output_dir)
        creds_path = prompt_value("Google credentials.json Path", default=args.credentials or existing_cfg.credentials_path)
        token_path = existing_cfg.token_path or args.token
        port = existing_cfg.chrome_debug_port or args.port
    else:
        name = args.name or existing_cfg.student_name
        roll = args.roll or existing_cfg.roll_number
        dept = args.dept or existing_cfg.department
        institution = args.institution or existing_cfg.institution
        out_dir = args.output_dir or existing_cfg.output_dir
        creds_path = args.credentials or existing_cfg.credentials_path
        token_path = args.token or existing_cfg.token_path
        port = args.port or existing_cfg.chrome_debug_port

    config = StudentConfig(
        student_name=name,
        roll_number=roll,
        department=dept,
        institution=institution,
        output_dir=out_dir,
        credentials_path=creds_path,
        token_path=token_path,
        chrome_debug_port=port,
    )

    saved_path = save_config(config, target_config_path)
    print(f"\nConfiguration saved to {saved_path}")

    # Check for credentials presence
    check_creds = Path(creds_path)
    if not check_creds.is_absolute():
        check_creds = Path.cwd() / check_creds

    if not check_creds.exists():
        print(f"\n[Warning] Google credentials file '{creds_path}' was not found at {check_creds}.")
        print("  To sync coursework directly from Google Classroom:")
        print("  1. Download OAuth 2.0 Client credentials from Google Cloud Console.")
        print(f"  2. Save it as '{creds_path}'.")
        print("  (Note: You can still compile PDFs and stage deliverables offline without credentials.)")
    else:
        print(f"[OK] Google credentials file verified at {check_creds}")

    print("\nSetup completed successfully!\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_setup())
