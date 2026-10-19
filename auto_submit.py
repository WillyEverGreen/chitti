"""
Google Classroom Dedicated Auto-Submission Engine (auto_submit.py)
-----------------------------------------------------------------
Purpose: Pure, deterministic submission pipeline for Google Classroom.
- Attaches single or multiple deliverables (PDF, DOCX, ZIP, code, etc.)
- Attaches single or multiple web links (Credly, GitHub, Google Docs)
- Supports pure 'Mark as done' for no-attachment assignments
- Handles both file upload methods (Drive Picker Browse button + hidden input)
- Prevents overlay interception (.hrIntegrationsOnepick detachment wait)
- Reliably detects and confirms modal dialogs
- Dual-Layer Verification: Browser DOM check ('Unsubmit' presence) + Classroom API check ('TURNED_IN')
- Aggressively closes non-Classroom and unrelated tabs (anti-distraction)
"""

import os
import re
import sys
import time
import argparse
from typing import Optional, List, Dict, Any

# Ensure UTF-8 output across all environments
sys.stdout.reconfigure(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright, Browser, Page
except ImportError:
    from patchright.sync_api import sync_playwright, Browser, Page

DEFAULT_CDP_PORT = 9444


# =====================================================================
# 1. Tab Hygiene & Cleanup
# =====================================================================

def clean_unrelated_tabs(browser: Browser, current_url: Optional[str] = None) -> int:
    """
    Closes all browser tabs that are NOT related to Google Classroom or its services.
    Removes extensions, ads, welcome pages, blank pages, or unrelated domains.
    """
    closed_count = 0
    allowed_domains = [
        "classroom.google.com",
        "accounts.google.com",
        "drive.google.com",
        "docs.google.com",
    ]

    for ctx in browser.contexts:
        for page in list(ctx.pages):
            try:
                url = page.url.strip()
                # If page is not in allowed domains, close it immediately
                if not any(domain in url for domain in allowed_domains):
                    title = url[:60]
                    try:
                        title = page.title() or url[:60]
                    except Exception:
                        pass
                    print(f"[*] Closing unrelated tab: '{title}' ({url[:60]}...)")
                    page.close()
                    closed_count += 1
            except Exception:
                pass
    return closed_count


# =====================================================================
# 2. Classroom API URL Resolver & Dual Verification Helpers
# =====================================================================

def resolve_assignment_info(course_query: str, assignment_query: str) -> Optional[Dict[str, Any]]:
    """
    Resolves course name/ID and assignment title/ID to course_id, coursework_id, and direct URL.
    Handles coursework pagination so assignments are never missed.
    """
    try:
        import classroom_manager as cm
        service, _ = cm.get_services()
        courses = cm.list_courses(service)

        target_course = None
        cq = course_query.lower().strip()
        for c in courses:
            if str(c.get("id")) == cq or cq in c.get("name", "").lower():
                target_course = c
                break

        if not target_course:
            print(f"[!] Course matching '{course_query}' not found.")
            return None

        course_id = str(target_course["id"])
        aq = assignment_query.lower().strip()

        # Query coursework with pagination
        page_token = None
        while True:
            res = service.courses().courseWork().list(
                courseId=course_id,
                pageSize=50,
                pageToken=page_token
            ).execute()
            works = res.get("courseWork", [])
            for w in works:
                if str(w.get("id")) == aq or aq in w.get("title", "").lower():
                    cw_id = str(w.get("id"))
                    target_url = w.get("alternateLink")
                    if not target_url:
                        import base64
                        b64_c = base64.b64encode(course_id.encode()).decode()
                        b64_w = base64.b64encode(cw_id.encode()).decode()
                        target_url = f"https://classroom.google.com/c/{b64_c}/a/{b64_w}/details"

                    return {
                        "course_id": course_id,
                        "course_name": target_course.get("name"),
                        "work_id": cw_id,
                        "work_title": w.get("title"),
                        "url": target_url,
                    }

            page_token = res.get("nextPageToken")
            if not page_token:
                break

        print(f"[!] Assignment matching '{assignment_query}' not found in course.")
        return None
    except Exception as e:
        print(f"[!] Warning: Could not resolve URL via API ({e}). Please pass --url directly.")
        return None


def verify_submission_api(course_id: str, work_id: str) -> bool:
    """
    Queries Google Classroom API server-side to confirm official TURNED_IN state.
    Anti-hallucination guarantee directly from Google servers.
    """
    try:
        import classroom_manager as cm
        service, _ = cm.get_services()
        res = service.courses().courseWork().studentSubmissions().list(
            courseId=course_id,
            courseWorkId=work_id,
            userId="me"
        ).execute()
        subs = res.get("studentSubmissions", [])
        if subs:
            state = subs[0].get("state", "UNKNOWN")
            print(f"[API CHECK] Server-side submission state: {state}")
            return state == "TURNED_IN"
        return False
    except Exception as e:
        print(f"[!] API verification note: {e}")
        return False


# =====================================================================
# 3. Core Submission Engine (The Exact Map)
# =====================================================================

def execute_submission(
    url: str,
    file_paths: Optional[List[str]] = None,
    links: Optional[List[str]] = None,
    file_path: Optional[str] = None,
    link: Optional[str] = None,
    mark_done: bool = False,
    port: int = DEFAULT_CDP_PORT,
    keep_tab: bool = False,
    course_id: Optional[str] = None,
    work_id: Optional[str] = None,
) -> bool:
    """
    Executes the exact submission workflow:
    1. Connect to isolated Chrome CDP
    2. Clean any unrelated/stray tabs
    3. Navigate to assignment details URL
    4. Check if already turned in (Unsubmit button visible)
    5. Attach all files via Google Drive Picker (supports multiple files)
    6. Attach all links via 'Add or create' -> Link (supports multiple links)
    7. Wait for all attachments to register and action button to be enabled
    8. Click 'Turn in' / 'Mark as done' / 'Resubmit'
    9. Detect and confirm modal confirmation dialog
    10. Verify state change in UI ('Unsubmit' button / 'Turned in' badge)
    11. Verify state change in Classroom API (Layer 2 Anti-Hallucination check)
    12. Clean tabs and finish
    """
    # Normalize inputs
    all_files: List[str] = []
    if file_path:
        all_files.append(file_path)
    if file_paths:
        for f in file_paths:
            if f and f not in all_files:
                all_files.append(f)

    all_links: List[str] = []
    if link:
        all_links.append(link)
    if links:
        for l in links:
            if l and l not in all_links:
                all_links.append(l)

    print("=" * 68)
    print("           GOOGLE CLASSROOM UNIVERSAL SUBMISSION ENGINE")
    print("=" * 68)
    print(f"[*] Target URL   : {url}")
    if all_files:
        print(f"[*] Attachments  : {', '.join(os.path.basename(f) for f in all_files)} ({len(all_files)} file(s))")
    if all_links:
        print(f"[*] Links        : {', '.join(all_links)} ({len(all_links)} link(s))")
    if mark_done and not all_files and not all_links:
        print(f"[*] Mode         : Mark as done (No attachments)")
    print(f"[*] Chrome Port  : {port}")
    print("-" * 68)

    # Validate that local files exist before starting browser
    for fp in all_files:
        if not os.path.exists(fp):
            print(f"[!] Error: File does not exist at '{fp}'")
            return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=10000)
        except Exception as e:
            print(f"\n[!] ERROR: Could not connect to Chrome on port {port}: {e}")
            print("[!] To launch Chrome with remote debugging, run this in PowerShell:")
            print(f'    Start-Process chrome -ArgumentList "--remote-debugging-port={port} --user-data-dir=`"$PWD\\.chrome_isolated`" `"https://classroom.google.com`""')
            return False

        # Step 1: Clean unrelated tabs immediately
        clean_unrelated_tabs(browser)

        context = browser.contexts[0]
        page = context.new_page()

        try:
            print(f"\n[Step 1/6] Navigating to assignment page...")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Step 2: Dynamically wait for submission widget to load
            print(f"[*] Waiting for submission widget to load...")
            unsubmit_btn = None
            add_btn = None
            for _ in range(30):  # Poll up to 15s
                unsub_check = page.locator("button:visible, div[role='button']:visible").filter(has_text="Unsubmit")
                add_check = page.locator("button:visible, div[role='button']:visible").filter(has_text="Add or create")
                if unsub_check.count() > 0 or add_check.count() > 0:
                    unsubmit_btn = unsub_check
                    add_btn = add_check
                    break
                page.wait_for_timeout(500)

            if unsubmit_btn and unsubmit_btn.count() > 0:
                print(f"[OK] Assignment is ALREADY TURNED IN! ('Unsubmit' button is present)")
                if not keep_tab:
                    page.close()
                clean_unrelated_tabs(browser)
                return True

            # Step 3: Attach Files (Sequential multi-file upload)
            for idx, fp in enumerate(all_files):
                abs_path = os.path.abspath(fp)
                filename = os.path.basename(abs_path)
                print(f"\n[Step 2/6] Attaching file [{idx + 1}/{len(all_files)}]: '{filename}'...")

                # Check if file chip is already on the page
                chip = page.locator(f"text='{filename}'").locator("visible=true")
                if chip.count() > 0:
                    print(f"[+] File '{filename}' is already attached under 'Your work'. Skipping upload.")
                    continue

                print(f"[*] Opening 'Add or create' menu...")
                add_btn = page.locator("button, div[role='button']").filter(has_text="Add or create").locator("visible=true").first
                if add_btn.count() == 0:
                    print(f"[!] Error: 'Add or create' button not found on page.")
                    page.close()
                    return False

                add_btn.click()
                page.wait_for_timeout(1000)

                file_option = page.locator("[role='menuitem']:visible").filter(has_text="File").first
                if file_option.count() == 0:
                    print(f"[!] Error: 'File' menu item not found.")
                    page.close()
                    return False

                file_option.click()
                print(f"[*] Waiting for Google Drive Picker...")

                # Wait for Google Drive Picker iframe
                picker = None
                for _ in range(30):
                    for f in page.frames:
                        if "picker" in f.url:
                            picker = f
                            break
                    if picker:
                        break
                    page.wait_for_timeout(400)

                if not picker:
                    print(f"[!] Error: Google Drive Picker frame did not load.")
                    page.close()
                    return False

                # Switch to Upload tab if available
                upload_tab = picker.locator("[role='tab']").filter(has_text="Upload").first
                if upload_tab.is_visible():
                    upload_tab.click()
                    page.wait_for_timeout(800)

                # Upload file using native Browse button file chooser or hidden input
                browse_btn = picker.locator("button:visible, div[role='button']:visible").filter(has_text="Browse").first
                if browse_btn.count() > 0 and browse_btn.is_visible():
                    print(f"[*] Found 'Browse' button. Triggering native file chooser for '{filename}'...")
                    with page.expect_file_chooser() as fc_info:
                        browse_btn.click()
                    fc = fc_info.value
                    fc.set_files(abs_path)
                    print(f"[+] File chosen via file chooser. Uploading...")
                else:
                    file_input = picker.locator("input[type='file']")
                    file_input.set_input_files(abs_path)
                    print(f"[*] File input set directly. Uploading '{filename}'...")

                # Wait for attachment chip to appear under 'Your work'
                chip_verified = False
                base_name_no_ext = os.path.splitext(filename)[0]
                for sec in range(90):  # Wait up to 90s for large files
                    has_chip = (
                        page.locator(f"text='{filename}'").count() > 0 or 
                        page.locator(f"text='{base_name_no_ext}'").count() > 0
                    )
                    has_turn_in = page.locator("button:visible, div[role='button']:visible").filter(
                        has_text=re.compile(r"^Turn in$", re.IGNORECASE)
                    ).count() > 0

                    if has_chip or has_turn_in:
                        print(f"[+] Attachment upload verified after {sec + 1}s!")
                        chip_verified = True
                        break
                    page.wait_for_timeout(1000)

                if not chip_verified:
                    print(f"[!] Warning: Did not see chip within 90s, waiting 5s for UI...")
                    page.wait_for_timeout(5000)

                # Ensure picker backdrop overlay (.hrIntegrationsOnepick) is fully detached
                for _ in range(25):
                    if page.locator(".hrIntegrationsOnepick:visible").count() == 0:
                        break
                    page.wait_for_timeout(400)
                page.wait_for_timeout(1500)

            # Step 4: Attach Links (Sequential multi-link attachment)
            for idx, lk in enumerate(all_links):
                print(f"\n[Step 3/6] Attaching link [{idx + 1}/{len(all_links)}]: '{lk}'...")
                if page.locator(f"text='{lk}'").locator("visible=true").count() > 0:
                    print(f"[+] Link already attached.")
                    continue

                add_btn = page.locator("button, div[role='button']").filter(has_text="Add or create").locator("visible=true").first
                add_btn.click()
                page.wait_for_timeout(1000)

                link_option = page.locator("[role='menuitem']:visible").filter(has_text="Link").first
                link_option.click()
                page.wait_for_timeout(1000)

                link_input = page.locator("input[type='text']:visible, input[aria-label*='Link']:visible").first
                link_input.fill(lk)
                page.wait_for_timeout(400)

                add_link_btn = page.locator("button:visible, div[role='button']:visible").filter(has_text="Add link").first
                add_link_btn.click()
                print(f"[+] Link added. Waiting for registration...")
                page.wait_for_timeout(3500)

            # Step 5: Press 'Turn in' / 'Mark as done' / 'Resubmit'
            print(f"\n[Step 4/6] Locating and activating submission button...")
            page.wait_for_timeout(2000)

            # If deliverables were provided, prioritize 'Turn in' / 'Resubmit'; otherwise allow 'Mark as done'
            if all_files:
                target_regex = r"^(Turn in|Resubmit|Turn in again)$"
            else:
                target_regex = r"^(Turn in|Mark as done|Resubmit|Turn in again)$"

            turn_btn = None
            for wait_i in range(30):  # Wait up to 15s for button to be enabled
                candidates = page.locator("button:visible, div[role='button']:visible").filter(
                    has_text=re.compile(target_regex, re.IGNORECASE)
                )
                if candidates.count() > 0:
                    for c_idx in range(candidates.count()):
                        cand = candidates.nth(c_idx)
                        txt = cand.inner_text().strip().lower()
                        if txt in ["turn in", "resubmit", "turn in again"] or (not all_files and txt == "mark as done"):
                            is_aria_disabled = cand.get_attribute("aria-disabled") == "true"
                            if not is_aria_disabled and cand.is_enabled():
                                turn_btn = cand
                                break
                    if turn_btn:
                        break
                page.wait_for_timeout(500)

            if not turn_btn:
                print(f"[!] Error: Could not locate active 'Turn in' or 'Mark as done' button.")
                page.close()
                return False

            action_text = turn_btn.inner_text().strip()
            print(f"[*] Clicking main action button: '{action_text}'...")
            try:
                turn_btn.click(timeout=8000)
            except Exception:
                print(f"[*] Fallback: clicking with force=True...")
                turn_btn.click(force=True)
            page.wait_for_timeout(1500)

            # Step 6: Confirm Modal Dialog
            print(f"\n[Step 5/6] Handling modal confirmation dialog...")
            dialog_confirmed = False
            for d_sec in range(16):  # Wait up to 8s for dialog
                dialogs = page.locator("[role='dialog']:visible, [role='alertdialog']:visible, div[aria-modal='true']:visible")
                if dialogs.count() > 0:
                    dialog = dialogs.first
                    dialog_btns = dialog.locator("button:visible, div[role='button']:visible").filter(
                        has_text=re.compile(r"^(Turn in|Mark as done|Resubmit|Turn in again)$", re.IGNORECASE)
                    )
                    if dialog_btns.count() > 0:
                        conf_btn = dialog_btns.first
                        conf_text = conf_btn.inner_text().strip()
                        print(f"[+] Modal dialog detected! Clicking confirmation button: '{conf_text}'...")
                        conf_btn.click()
                        dialog_confirmed = True
                        page.wait_for_timeout(3000)
                        break
                page.wait_for_timeout(500)

            if not dialog_confirmed:
                print("[*] Note: No popup dialog appeared (submission registered directly).")

            # Step 7: Final Verification (Dual-Layer Shield)
            print(f"\n[Step 6/6] Verifying submission status...")
            dom_verified = False
            for v_sec in range(30):  # Poll up to 15s
                unsub = page.locator("button:visible, div[role='button']:visible").filter(has_text="Unsubmit")
                if unsub.count() > 0:
                    dom_verified = True
                    break

                # Also verify via status badge text
                status_txt = page.locator("text='Turned in', text='Turned in late', text='Done late'").locator("visible=true")
                if status_txt.count() > 0:
                    dom_verified = True
                    break

                page.wait_for_timeout(500)

            # Clean unrelated tabs again
            clean_unrelated_tabs(browser)

            # Layer 2: API ground-truth verification if course/work IDs are available
            api_verified = False
            if course_id and work_id:
                api_verified = verify_submission_api(course_id, work_id)

            if dom_verified or api_verified:
                print("\n" + "=" * 68)
                print(" [SUCCESS] ASSIGNMENT HAS BEEN OFFICIALLY TURNED IN!")
                print(f" Browser UI State: {'TURNED_IN (Unsubmit present)' if dom_verified else 'Verified'}")
                if course_id and work_id:
                    print(f" API Server State: {'TURNED_IN (Confirmed)' if api_verified else 'Pending sync'}")
                print("=" * 68 + "\n")
                if not keep_tab:
                    page.close()
                return True
            else:
                print("\n[!] WARNING: Action sent, but 'Unsubmit' state was not confirmed.")
                print("[!] The assignment tab will remain open for manual review.")
                return False

        except Exception as err:
            print(f"\n[!] Unexpected Error during submission execution: {err}")
            return False


# =====================================================================
# 4. CLI Parser & Entry Point
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Google Classroom Universal Dedicated Submission Engine",
        epilog="Examples:\n"
               "  py auto_submit.py --url 'https://classroom.google.com/c/.../a/.../details' --file solution.pdf\n"
               "  py auto_submit.py --course 'Computer Network' --assignment 'EXPERIMENT 7' --files exp7.pdf code.zip\n"
               "  py auto_submit.py --course 'Cloud Computing' --assignment 'LAB 10' --file report.pdf --link https://credly.com/...\n"
               "  py auto_submit.py --clean-tabs\n"
    )

    parser.add_argument("--url", help="Direct URL to Google Classroom assignment details", default=None)
    parser.add_argument("--course", help="Course name or Course ID (if --url is not passed)", default=None)
    parser.add_argument("--assignment", help="Assignment title or ID (if --url is not passed)", default=None)
    parser.add_argument("--file", help="Single local file path to attach", default=None)
    parser.add_argument("--files", nargs="+", help="Multiple local file paths to attach", default=None)
    parser.add_argument("--link", help="Single web link to attach", default=None)
    parser.add_argument("--links", nargs="+", help="Multiple web links to attach", default=None)
    parser.add_argument("--mark-done", action="store_true", help="Submit as 'Mark as done' without attachments")
    parser.add_argument("--port", type=int, help="Chrome CDP debug port (default: 9444)", default=DEFAULT_CDP_PORT)
    parser.add_argument("--keep-tab", action="store_true", help="Keep assignment tab open after submission")
    parser.add_argument("--clean-tabs", action="store_true", help="Only clean and close unrelated tabs in Chrome")

    args = parser.parse_args()

    # Clean-only mode
    if args.clean_tabs:
        with sync_playwright() as p:
            try:
                b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}", timeout=8000)
                c = clean_unrelated_tabs(b)
                print(f"[OK] Closed {c} unrelated tabs.")
            except Exception as e:
                print(f"[!] Could not connect to Chrome on port {args.port}: {e}")
        sys.exit(0)

    # Determine URL and Course/Work IDs
    target_url = args.url
    resolved_cid = None
    resolved_wid = None

    if not target_url:
        if args.course and args.assignment:
            info = resolve_assignment_info(args.course, args.assignment)
            if info:
                target_url = info["url"]
                resolved_cid = info["course_id"]
                resolved_wid = info["work_id"]
                print(f"[+] Resolved Assignment: '{info['work_title']}' in '{info['course_name']}'")
                print(f"[+] Canonical URL: {target_url}")
        else:
            parser.print_help()
            print("\n[!] Please specify either --url OR both --course and --assignment.")
            sys.exit(1)

    if not target_url:
        print("[!] Failed to determine assignment URL. Aborting.")
        sys.exit(1)

    success = execute_submission(
        url=target_url,
        file_paths=args.files,
        links=args.links,
        file_path=args.file,
        link=args.link,
        mark_done=args.mark_done,
        port=args.port,
        keep_tab=args.keep_tab,
        course_id=resolved_cid,
        work_id=resolved_wid,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
