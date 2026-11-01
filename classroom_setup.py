#!/usr/bin/env python3
"""Interactive Onboarding and Configuration Wizard for Chitti 🤖.

Initializes or updates `student_config.json` with student profile information,
credentials paths, and output settings.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Optional, List
import webbrowser

from classroom.config import (
    StudentConfig,
    load_config,
    save_config,
    get_default_config_path,
)


def create_credentials_json(
    dest_path: Path,
    client_id: str,
    client_secret: str,
    project_id: str = "chitti-classroom",
) -> None:
    """Create a standard Google OAuth Desktop app credentials.json file."""
    data = {
        "installed": {
            "client_id": client_id.strip(),
            "project_id": project_id.strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret.strip(),
            "redirect_uris": ["http://localhost"],
        }
    }
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def prompt_value(prompt: str, default: str = "", required: bool = False) -> str:
    """Prompt the user for an input string, with default value fallback."""
    suffix = f" [{default}]" if default else ""
    full_prompt = f"{prompt}{suffix}: "

    while True:
        try:
            val = input(full_prompt).strip()
        except (EOFError, StopIteration):
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
        description="Chitti 🤖 Student Setup Wizard",
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
    parser.add_argument("--client-id", default="", help="Google OAuth Client ID to auto-generate credentials.json")
    parser.add_argument("--client-secret", default="", help="Google OAuth Client Secret to auto-generate credentials.json")
    parser.add_argument("--open-browser", action="store_true", help="Open Google Cloud Console in browser")

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
    elif any([args.name, args.roll, args.dept, args.institution, args.client_id]):
        is_interactive = False
    else:
        is_interactive = True

    print("==========================================================")
    print("        🤖 Chitti - Student Setup & Configuration         ")
    print("==========================================================")

    if is_interactive:
        if existing_cfg.is_configured():
            print(f"[+] Found existing academic profile for {existing_cfg.student_name} ({existing_cfg.roll_number})!")
            print(f"    • Name:        {existing_cfg.student_name}")
            print(f"    • Roll Number: {existing_cfg.roll_number}")
            print(f"    • Department:  {existing_cfg.department}")
            print(f"    • Institution: {existing_cfg.institution}")
            print(f"    • Output Dir:  {existing_cfg.output_dir}\n")
            keep = prompt_value("Keep these profile details? (Y/n)", default="y")
            if keep.lower().startswith("y"):
                name = existing_cfg.student_name
                roll = existing_cfg.roll_number
                dept = existing_cfg.department
                institution = existing_cfg.institution
                out_dir = existing_cfg.output_dir
                creds_path = existing_cfg.credentials_path
                token_path = existing_cfg.token_path
                port = existing_cfg.chrome_debug_port
            else:
                name = prompt_value("Student Full Name", default=existing_cfg.student_name, required=True)
                roll = prompt_value("Roll / Registration Number", default=existing_cfg.roll_number, required=True)
                dept = prompt_value("Department / Branch", default=existing_cfg.department)
                institution = prompt_value("College / University", default=existing_cfg.institution)
                out_dir = prompt_value("Deliverables Output Directory", default=existing_cfg.output_dir)
                creds_path = prompt_value("Google credentials.json Path", default=existing_cfg.credentials_path)
                token_path = existing_cfg.token_path or args.token
                port = existing_cfg.chrome_debug_port or args.port
        else:
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

    # Auto-generate credentials if client-id and secret passed
    if args.client_id and args.client_secret:
        create_credentials_json(check_creds, args.client_id, args.client_secret)
        print(f"[OK] Google credentials file created automatically at {check_creds}")

    if not check_creds.exists():
        if args.open_browser:
            print("[*] Opening Google Cloud Console in your default browser...")
            webbrowser.open("https://console.cloud.google.com/apis/credentials")

        if is_interactive:
            print("\n" + "=" * 58)
            print("     Google Classroom Credentials Helper (Super Easy)     ")
            print("=" * 58)
            print("Chitti needs your Google OAuth credentials to sync with Google Classroom.")
            print("\nChoose an option:")
            print("  [1] Paste Client ID and Client Secret (I'll generate credentials.json)")
            print("  [2] Open Google Cloud Console in browser")
            print("  [3] Skip for now (continue offline)")
            choice = prompt_value("Select an option (1/2/3)", default="3")
            if choice == "1":
                cid = prompt_value("Google Client ID (e.g. *.apps.googleusercontent.com)", required=True)
                csec = prompt_value("Google Client Secret (e.g. GOCSPX-*)", required=True)
                if cid and csec:
                    create_credentials_json(check_creds, cid, csec)
                    print(f"\n[OK] Successfully created and verified {check_creds}!")
            elif choice == "2":
                print("[*] Opening Google Cloud Console in your browser...")
                webbrowser.open("https://console.cloud.google.com/apis/credentials")
                print("Steps in browser:")
                print("  1. Click 'Create Credentials' -> 'OAuth client ID'")
                print("  2. Select Application type: 'Desktop App' -> Name: 'Chitti'")
                print("  3. Download JSON and save as 'credentials.json' here.")
        else:
            print(f"\n[Warning] Google credentials file '{creds_path}' was not found at {check_creds}.")
            print("  To sync coursework directly from Google Classroom:")
            print("  1. Download OAuth 2.0 Client credentials from Google Cloud Console.")
            print(f"  2. Save it as '{creds_path}'.")
            print("  (Tip: You can pass --client-id and --client-secret to auto-create credentials.json)")
    else:
        print(f"[OK] Google credentials file verified at {check_creds}")

    print("\nSetup completed successfully!\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_setup())
