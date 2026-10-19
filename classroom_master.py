"""
Classroom Master Automation Engine (classroom_master.py)
--------------------------------------------------------
Universal Google Classroom management, discovery, and 100% automated submissions.
Works seamlessly across any course in your Google Classroom.
"""

import os
import re
import sys
import time
import argparse
from typing import Optional, List, Dict, Any

# Ensure UTF-8 stdout across all platforms
sys.stdout.reconfigure(encoding="utf-8")

import classroom_manager as cm
from auto_submit import execute_submission, clean_unrelated_tabs

CHROME_DEBUG_PORT = 9444


# ==========================================
# Google Classroom API Intelligence Helpers
# ==========================================

def find_course(classroom_service, query: str) -> Optional[Dict[str, Any]]:
    """Finds a course by exact ID or case-insensitive name substring."""
    courses = cm.list_courses(classroom_service)
    query_lower = query.lower().strip()

    # 1. Exact ID match
    for c in courses:
        if str(c.get("id")) == query_lower:
            return c

    # 2. Name substring match
    for c in courses:
        if query_lower in c.get("name", "").lower():
            return c

    return None


def find_coursework(classroom_service, course_id: str, query: str) -> Optional[Dict[str, Any]]:
    """Finds coursework by exact ID or case-insensitive title substring with pagination."""
    query_lower = query.lower().strip()
    page_token = None

    while True:
        results = classroom_service.courses().courseWork().list(
            courseId=course_id,
            pageSize=50,
            pageToken=page_token
        ).execute()

        for w in results.get("courseWork", []):
            if str(w.get("id")) == query_lower or query_lower in w.get("title", "").lower():
                return w

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return None


# ==========================================
# Main CLI Entry Point
# ==========================================

def main():
    parser = argparse.ArgumentParser(
        description="Classroom Master Automation Engine - Universal Google Classroom Management & Submissions",
        epilog="Examples:\n"
               "  py classroom_master.py courses\n"
               "  py classroom_master.py pending\n"
               "  py classroom_master.py details --course 'Network' --assignment 'EXPERIMENT 7'\n"
               "  py classroom_master.py verify --course 'Network' --assignment 'EXPERIMENT 6'\n"
               "  py classroom_master.py submit --course 'Network' --assignment 'EXPERIMENT 7' --file 'report.pdf'\n"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: courses
    subparsers.add_parser("courses", help="List all enrolled active courses")

    # Command: pending
    pending_parser = subparsers.add_parser("pending", help="List all pending/unsubmitted assignments")
    pending_parser.add_argument("--course", help="Filter by course name or ID", default=None)
    pending_parser.add_argument("--ignore", help="Ignore courses matching this name (default: HMI)", default="HMI")

    # Command: details
    details_parser = subparsers.add_parser("details", help="View assignment instructions, materials, and rubrics")
    details_parser.add_argument("--course", required=True, help="Course name or ID")
    details_parser.add_argument("--assignment", required=True, help="Assignment title or ID")

    # Command: verify
    verify_parser = subparsers.add_parser("verify", help="Check official server submission status via Classroom API")
    verify_parser.add_argument("--course", required=True, help="Course name or ID")
    verify_parser.add_argument("--assignment", required=True, help="Assignment title or ID")

    # Command: submit
    submit_parser = subparsers.add_parser("submit", help="Submit any assignment in any course")
    submit_parser.add_argument("--url", help="Direct Google Classroom assignment URL", default=None)
    submit_parser.add_argument("--course", help="Course name or ID (if URL not provided)", default=None)
    submit_parser.add_argument("--assignment", help="Assignment title or ID (if URL not provided)", default=None)
    submit_parser.add_argument("--file", help="Single local file path to attach", default=None)
    submit_parser.add_argument("--files", nargs="+", help="Multiple local file paths to attach", default=None)
    submit_parser.add_argument("--link", help="Single web link to attach (Credly, GitHub, etc.)", default=None)
    submit_parser.add_argument("--links", nargs="+", help="Multiple web links to attach", default=None)
    submit_parser.add_argument("--mark-done", action="store_true", help="Submit as 'Mark as done' without attachments")
    submit_parser.add_argument("--port", type=int, help="Chrome debug port (default: 9444)", default=CHROME_DEBUG_PORT)
    submit_parser.add_argument("--keep-tab", action="store_true", help="Keep assignment tab open after submission")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        classroom_service, _ = cm.get_services()
    except Exception as e:
        print(f"[!] Authentication Error: {e}")
        sys.exit(1)

    if args.command == "courses":
        courses = cm.list_courses(classroom_service)
        cm.display_courses(courses)

    elif args.command == "pending":
        course_id = None
        if args.course:
            matched_course = find_course(classroom_service, args.course)
            if not matched_course:
                print(f"[!] Could not find course matching '{args.course}'")
                sys.exit(1)
            course_id = str(matched_course["id"])
            print(f"[*] Filtering for course: {matched_course['name']} ({course_id})")

        print(f"[*] Fetching pending assignments (ignoring '{args.ignore}' courses)..." if args.ignore else "[*] Fetching pending assignments...")
        pending = cm.get_pending_assignments(classroom_service, course_id=course_id, ignore_pattern=args.ignore)
        cm.display_pending(pending)

    elif args.command == "details":
        matched_course = find_course(classroom_service, args.course)
        if not matched_course:
            print(f"[!] Could not find course matching '{args.course}'")
            sys.exit(1)
        c_id = str(matched_course["id"])

        matched_cw = find_coursework(classroom_service, c_id, args.assignment)
        if not matched_cw:
            print(f"[!] Could not find assignment matching '{args.assignment}' in {matched_course['name']}")
            sys.exit(1)
        w_id = str(matched_cw["id"])

        details = cm.get_assignment_details(classroom_service, c_id, w_id)
        cm.display_details(details)

    elif args.command == "verify":
        matched_course = find_course(classroom_service, args.course)
        if not matched_course:
            print(f"[!] Could not find course matching '{args.course}'")
            sys.exit(1)
        c_id = str(matched_course["id"])

        matched_cw = find_coursework(classroom_service, c_id, args.assignment)
        if not matched_cw:
            print(f"[!] Could not find assignment matching '{args.assignment}' in {matched_course['name']}")
            sys.exit(1)
        w_id = str(matched_cw["id"])

        details = cm.get_assignment_details(classroom_service, c_id, w_id)
        sub = details.get("submission", {})
        state = sub.get("state", "UNKNOWN") if sub else "NOT_STARTED"

        print("=" * 65)
        print(f"Course     : {matched_course['name']} (ID: {c_id})")
        print(f"Assignment : {matched_cw['title']} (ID: {w_id})")
        print(f"Status     : {state}")
        print(f"Due Date   : {cm.format_due_date(matched_cw.get('dueDate'), matched_cw.get('dueTime'))}")
        print(f"Link       : {matched_cw.get('alternateLink')}")

        atts = sub.get("assignmentSubmission", {}).get("attachments", []) if sub else []
        if atts:
            print("\nSubmitted Attachments:")
            for a in atts:
                if "driveFile" in a:
                    print(f" - [Drive] {a['driveFile'].get('title')} ({a['driveFile'].get('alternateLink')})")
                elif "link" in a:
                    print(f" - [Link]  {a['link'].get('url')}")
        else:
            print("\nSubmitted Attachments: None")
        print("=" * 65)

    elif args.command == "submit":
        target_url = args.url
        c_id = None
        w_id = None

        if not target_url:
            if not args.course or not args.assignment:
                print("[!] Error: Either --url OR both (--course and --assignment) must be provided.")
                sys.exit(1)

            matched_course = find_course(classroom_service, args.course)
            if not matched_course:
                print(f"[!] Could not find course matching '{args.course}'")
                sys.exit(1)
            c_id = str(matched_course["id"])

            matched_cw = find_coursework(classroom_service, c_id, args.assignment)
            if not matched_cw:
                print(f"[!] Could not find assignment matching '{args.assignment}' in {matched_course['name']}")
                sys.exit(1)
            w_id = str(matched_cw["id"])

            target_url = matched_cw.get("alternateLink")
            print(f"[*] Resolved assignment '{matched_cw['title']}' in course '{matched_course['name']}'")
            print(f"[*] Canonical URL: {target_url}")

        success = execute_submission(
            url=target_url,
            file_paths=args.files,
            links=args.links,
            file_path=args.file,
            link=args.link,
            mark_done=args.mark_done,
            port=args.port,
            keep_tab=args.keep_tab,
            course_id=c_id,
            work_id=w_id,
        )

        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
