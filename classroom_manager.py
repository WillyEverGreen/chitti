"""
Google Classroom Submission Manager CLI & Library
Empowers you and your agent to inspect, track, and manage assignments and submissions.
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.me',
    'https://www.googleapis.com/auth/classroom.student-submissions.me.readonly',
    'https://www.googleapis.com/auth/drive.file'
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')


def get_credentials() -> Credentials:
    """Authenticates the user and returns OAuth2 credentials."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[!] Error refreshing token: {e}")
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_FILE}' not found!\n"
                    "Please download your OAuth client ID credentials from Google Cloud Console "
                    "and place the JSON file as 'credentials.json' in this folder."
                )
            print("\n" + "=" * 64)
            print("        🔑 Chitti: One-Time Google Classroom Authorization      ")
            print("=" * 64)
            print("Your credentials.json is loaded! A browser window will now open.")
            print("Sign in with your Google / College account to authorize Chitti.")
            print("\n💡 Important Tips:")
            print("  • If Google shows 'Google hasn't verified this app':")
            print("    Click 'Advanced' -> Click 'Go to Chitti (unsafe)' -> 'Continue'")
            print("  • Check all permission boxes so Chitti can read coursework & sync.")
            print("=" * 64 + "\n")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            print("\n[OK] Authorization successful! Token saved to token.json.\n")

        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return creds


def get_services():
    """Initializes Classroom and Drive API services."""
    creds = get_credentials()
    classroom_service = build('classroom', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return classroom_service, drive_service


def list_courses(classroom_service) -> List[Dict[str, Any]]:
    """Fetches all active courses where the user is a student or teacher."""
    courses = []
    page_token = None
    while True:
        results = classroom_service.courses().list(
            pageSize=50,
            courseStates=['ACTIVE'],
            pageToken=page_token
        ).execute()
        courses.extend(results.get('courses', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return courses


def format_due_date(due_date_dict: Optional[Dict[str, int]], due_time_dict: Optional[Dict[str, int]]) -> str:
    """Formats Google Classroom due date and time into a readable string."""
    if not due_date_dict:
        return "No Due Date"
    year = due_date_dict.get('year')
    month = due_date_dict.get('month')
    day = due_date_dict.get('day')
    hour = due_time_dict.get('hours', 23) if due_time_dict else 23
    minute = due_time_dict.get('minutes', 59) if due_time_dict else 59
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} UTC"


def is_past_due(due_date_dict: Optional[Dict[str, int]], due_time_dict: Optional[Dict[str, int]]) -> bool:
    """Checks if a due date is in the past."""
    if not due_date_dict:
        return False
    year = due_date_dict.get('year')
    month = due_date_dict.get('month')
    day = due_date_dict.get('day')
    hour = due_time_dict.get('hours', 23) if due_time_dict else 23
    minute = due_time_dict.get('minutes', 59) if due_time_dict else 59
    try:
        due_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > due_dt
    except Exception:
        return False


def get_student_submission(classroom_service, course_id: str, coursework_id: str) -> Optional[Dict[str, Any]]:
    """Gets the student's submission for a given coursework."""
    try:
        results = classroom_service.courses().courseWork().studentSubmissions().list(
            courseId=course_id,
            courseWorkId=coursework_id,
            userId='me'
        ).execute()
        submissions = results.get('studentSubmissions', [])
        return submissions[0] if submissions else None
    except HttpError as e:
        return None


def get_pending_assignments(
    classroom_service, 
    course_id: Optional[str] = None,
    ignore_pattern: Optional[str] = "HMI"
) -> List[Dict[str, Any]]:
    """
    Retrieves all pending (unsubmitted / reclaimed) coursework across all or specified courses.
    Uses batch studentSubmissions query (courseWorkId='-') for maximum speed (~2s across all courses).
    """
    if course_id:
        course_obj = classroom_service.courses().get(id=course_id).execute()
        courses = [course_obj]
    else:
        courses = list_courses(classroom_service)

    pending_list = []

    for course in courses:
        c_id = str(course['id'])
        c_name = course.get('name', 'Untitled Course')

        # Early filter out ignored courses (e.g. HMI / Human Machine Interaction)
        if ignore_pattern:
            ig = ignore_pattern.lower().strip()
            c_lower = c_name.lower()
            if ig in c_lower or (ig == "hmi" and "human machine" in c_lower):
                continue

        # 1. Fetch all student submissions for this course in a single batch query
        sub_map = {}
        sub_page_token = None
        while True:
            try:
                sub_res = classroom_service.courses().courseWork().studentSubmissions().list(
                    courseId=c_id,
                    courseWorkId='-',
                    userId='me',
                    pageSize=100,
                    pageToken=sub_page_token
                ).execute()
                for s in sub_res.get('studentSubmissions', []):
                    w_id = str(s.get('courseWorkId'))
                    sub_map[w_id] = s
                sub_page_token = sub_res.get('nextPageToken')
                if not sub_page_token:
                    break
            except Exception:
                break

        # 2. Fetch published coursework with pagination
        cw_page_token = None
        while True:
            try:
                cw_results = classroom_service.courses().courseWork().list(
                    courseId=c_id,
                    pageSize=50,
                    courseWorkStates=['PUBLISHED'],
                    pageToken=cw_page_token
                ).execute()
            except HttpError:
                break

            course_work_items = cw_results.get('courseWork', [])
            for cw in course_work_items:
                cw_id = str(cw['id'])
                submission = sub_map.get(cw_id)
                state = submission.get('state', 'UNKNOWN') if submission else 'NEW'

                # States: 'NEW', 'CREATED', 'RECLAIMED_BY_STUDENT', 'RETURNED' indicate pending submission
                if state in ['NEW', 'CREATED', 'RECLAIMED_BY_STUDENT', 'RETURNED']:
                    # Exclude already graded returned items
                    if state == 'RETURNED' and submission.get('assignedGrade') is not None:
                        continue

                    due_date = cw.get('dueDate')
                    due_time = cw.get('dueTime')
                    overdue = is_past_due(due_date, due_time)

                    pending_list.append({
                        'course_id': c_id,
                        'course_name': c_name,
                        'work_id': cw_id,
                        'title': cw.get('title', 'Untitled Assignment'),
                        'description': cw.get('description', ''),
                        'due_formatted': format_due_date(due_date, due_time),
                        'is_overdue': overdue,
                        'state': state,
                        'submission_id': submission.get('id') if submission else None,
                        'alternate_link': cw.get('alternateLink', '')
                    })

            cw_page_token = cw_results.get('nextPageToken')
            if not cw_page_token:
                break

    # Sort pending items: overdue first, then by due date
    return pending_list



def get_assignment_details(classroom_service, course_id: str, coursework_id: str) -> Dict[str, Any]:
    """Fetches in-depth information about an assignment and the user's submission."""
    cw = classroom_service.courses().courseWork().get(
        courseId=course_id,
        id=coursework_id
    ).execute()

    submission = get_student_submission(classroom_service, course_id, coursework_id)

    return {
        'courseWork': cw,
        'submission': submission
    }


def attach_link(classroom_service, course_id: str, coursework_id: str, url: str) -> Dict[str, Any]:
    """Attaches an external link (URL) to the student submission."""
    submission = get_student_submission(classroom_service, course_id, coursework_id)
    if not submission:
        raise ValueError(f"Could not find student submission for coursework {coursework_id}")

    sub_id = submission['id']
    body = {
        'addAttachments': [
            {'link': {'url': url}}
        ]
    }
    return classroom_service.courses().courseWork().studentSubmissions().modifyAttachments(
        courseId=course_id,
        courseWorkId=coursework_id,
        id=sub_id,
        body=body
    ).execute()


def upload_and_attach_file(classroom_service, drive_service, course_id: str, coursework_id: str, filepath: str) -> Dict[str, Any]:
    """Uploads a local file to Google Drive and attaches it to the student submission."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File '{filepath}' not found.")

    filename = os.path.basename(filepath)
    print(f"[*] Uploading '{filename}' to Google Drive...")

    file_metadata = {'name': filename}
    media = MediaFileUpload(filepath, resumable=True)
    drive_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name'
    ).execute()
    file_id = drive_file.get('id')
    print(f"[+] File uploaded to Google Drive with ID: {file_id}")

    submission = get_student_submission(classroom_service, course_id, coursework_id)
    if not submission:
        raise ValueError(f"Could not find student submission for coursework {coursework_id}")

    sub_id = submission['id']
    body = {
        'addAttachments': [
            {'driveFile': {'id': file_id}}
        ]
    }
    return classroom_service.courses().courseWork().studentSubmissions().modifyAttachments(
        courseId=course_id,
        courseWorkId=coursework_id,
        id=sub_id,
        body=body
    ).execute()


def turn_in_assignment(classroom_service, course_id: str, coursework_id: str) -> Dict[str, Any]:
    """Submits / turns in the assignment."""
    submission = get_student_submission(classroom_service, course_id, coursework_id)
    if not submission:
        raise ValueError(f"Could not find student submission for coursework {coursework_id}")

    sub_id = submission['id']
    return classroom_service.courses().courseWork().studentSubmissions().turnIn(
        courseId=course_id,
        courseWorkId=coursework_id,
        id=sub_id,
        body={}
    ).execute()


def reclaim_assignment(classroom_service, course_id: str, coursework_id: str) -> Dict[str, Any]:
    """Reclaims / un-submits the assignment to modify attachments."""
    submission = get_student_submission(classroom_service, course_id, coursework_id)
    if not submission:
        raise ValueError(f"Could not find student submission for coursework {coursework_id}")

    sub_id = submission['id']
    return classroom_service.courses().courseWork().studentSubmissions().reclaim(
        courseId=course_id,
        courseWorkId=coursework_id,
        id=sub_id,
        body={}
    ).execute()


# ==========================================
# CLI Display Helpers
# ==========================================

def display_courses(courses: List[Dict[str, Any]]):
    if HAS_RICH:
        table = Table(title="Enrolled Google Classroom Courses", show_header=True, header_style="bold magenta")
        table.add_column("Course ID", style="cyan", no_wrap=True)
        table.add_column("Course Name", style="bold green")
        table.add_column("Section / Room", style="yellow")
        table.add_column("Enrollment Code", style="dim")

        for c in courses:
            table.add_row(
                str(c.get('id')),
                c.get('name', ''),
                c.get('section', '') or c.get('room', '-'),
                c.get('enrollmentCode', '-')
            )
        console.print(table)
    else:
        print("\n--- Enrolled Google Classroom Courses ---")
        for c in courses:
            print(f"ID: {c.get('id')} | Name: {c.get('name')} | Section: {c.get('section', '-')}")


def display_pending(pending: List[Dict[str, Any]]):
    if not pending:
        if HAS_RICH:
            console.print("[bold green]No pending assignments found! All caught up![/bold green]")
        else:
            print("No pending assignments found! All caught up!")
        return

    if HAS_RICH:
        table = Table(title=f"Pending Assignments ({len(pending)} tasks)", show_header=True, header_style="bold cyan")
        table.add_column("Course", style="cyan")
        table.add_column("Assignment Title", style="bold white")
        table.add_column("Due Date", style="yellow")
        table.add_column("Status", style="magenta")
        table.add_column("Course ID", style="dim")
        table.add_column("Work ID", style="dim")

        for item in pending:
            status = item['state']
            if item['is_overdue']:
                status_styled = "[bold red]OVERDUE[/bold red]"
                due_styled = f"[red]{item['due_formatted']}[/red]"
            else:
                status_styled = f"[green]{status}[/green]"
                due_styled = f"[yellow]{item['due_formatted']}[/yellow]"

            table.add_row(
                item['course_name'][:25],
                item['title'][:40],
                due_styled,
                status_styled,
                str(item['course_id']),
                str(item['work_id'])
            )
        console.print(table)
    else:
        print(f"\n--- Pending Assignments ({len(pending)} tasks) ---")
        for item in pending:
            tag = "[OVERDUE]" if item['is_overdue'] else f"[{item['state']}]"
            print(f"{tag} {item['course_name']} -> {item['title']}")
            print(f"    Due: {item['due_formatted']} | CourseID: {item['course_id']} | WorkID: {item['work_id']}")


def display_details(details: Dict[str, Any]):
    cw = details.get('courseWork', {})
    sub = details.get('submission', {})

    title = cw.get('title', 'Untitled')
    desc = cw.get('description', 'No description provided.')
    link = cw.get('alternateLink', '')
    max_points = cw.get('maxPoints', 'N/A')
    due = format_due_date(cw.get('dueDate'), cw.get('dueTime'))
    state = sub.get('state', 'Unknown') if sub else 'Not Started'

    attachments = []
    if sub and 'assignmentSubmission' in sub:
        atts = sub['assignmentSubmission'].get('attachments', [])
        for a in atts:
            if 'driveFile' in a:
                attachments.append(f"Drive: {a['driveFile'].get('title')} ({a['driveFile'].get('alternateLink')})")
            elif 'link' in a:
                attachments.append(f"Link: {a['link'].get('url')}")

    materials = []
    for m in cw.get('materials', []):
        if 'driveFile' in m:
            materials.append(f"Drive File: {m['driveFile'].get('driveFile', {}).get('title')} ({m['driveFile'].get('driveFile', {}).get('alternateLink')})")
        elif 'link' in m:
            materials.append(f"Link: {m['link'].get('title', 'Link')} ({m['link'].get('url')})")
        elif 'youtubeVideo' in m:
            materials.append(f"YouTube: {m['youtubeVideo'].get('title')} ({m['youtubeVideo'].get('alternateLink')})")

    if HAS_RICH:
        content = (
            f"[bold cyan]Assignment:[/bold cyan] {title}\n"
            f"[bold cyan]Points:[/bold cyan] {max_points} | [bold cyan]Due:[/bold cyan] {due}\n"
            f"[bold cyan]Status:[/bold cyan] {state}\n"
            f"[bold cyan]Classroom Link:[/bold cyan] {link}\n\n"
            f"[bold yellow]Description:[/bold yellow]\n{desc}\n\n"
        )
        if materials:
            content += "[bold yellow]Attached Course Materials:[/bold yellow]\n" + "\n".join(f"- {m}" for m in materials) + "\n\n"
        if attachments:
            content += "[bold yellow]Your Current Attachments:[/bold yellow]\n" + "\n".join(f"- {a}" for a in attachments)
        else:
            content += "[dim]No attachments submitted yet.[/dim]"

        console.print(Panel(content, title=f"Assignment Details: {title}", expand=False))
    else:
        print(f"\n==========================================")
        print(f"Assignment: {title}")
        print(f"Points: {max_points} | Due: {due} | Status: {state}")
        print(f"Link: {link}")
        print(f"\nDescription:\n{desc}\n")
        if materials:
            print("Materials:")
            for m in materials:
                print(f" - {m}")
        if attachments:
            print("\nYour Current Attachments:")
            for a in attachments:
                print(f" - {a}")
        print(f"==========================================\n")


# ==========================================
# Main Entry Point
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Google Classroom Submission Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: auth
    subparsers.add_parser("auth", help="Verify or execute Google OAuth login")

    # Command: courses
    subparsers.add_parser("courses", help="List all enrolled active courses")

    # Command: pending
    pending_parser = subparsers.add_parser("pending", help="List all pending/unsubmitted assignments")
    pending_parser.add_argument("--course-id", help="Filter pending assignments by Course ID", default=None)

    # Command: details
    details_parser = subparsers.add_parser("details", help="View assignment instructions and submission status")
    details_parser.add_argument("--course-id", required=True, help="Course ID")
    details_parser.add_argument("--work-id", required=True, help="CourseWork ID")

    # Command: attach-link
    link_parser = subparsers.add_parser("attach-link", help="Attach a web link to a submission")
    link_parser.add_argument("--course-id", required=True, help="Course ID")
    link_parser.add_argument("--work-id", required=True, help="CourseWork ID")
    link_parser.add_argument("--url", required=True, help="URL to attach")

    # Command: attach-file
    file_parser = subparsers.add_parser("attach-file", help="Upload a local file to Drive and attach to submission")
    file_parser.add_argument("--course-id", required=True, help="Course ID")
    file_parser.add_argument("--work-id", required=True, help="CourseWork ID")
    file_parser.add_argument("--file", required=True, help="Local file path")

    # Command: turn-in
    turnin_parser = subparsers.add_parser("turn-in", help="Turn in an assignment")
    turnin_parser.add_argument("--course-id", required=True, help="Course ID")
    turnin_parser.add_argument("--work-id", required=True, help="CourseWork ID")

    # Command: reclaim
    reclaim_parser = subparsers.add_parser("reclaim", help="Unsubmit / reclaim an assignment")
    reclaim_parser.add_argument("--course-id", required=True, help="Course ID")
    reclaim_parser.add_argument("--work-id", required=True, help="CourseWork ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        classroom_service, drive_service = get_services()
    except FileNotFoundError as fnf:
        print(f"\n[!] Error: {fnf}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Authentication / Setup Error: {e}")
        sys.exit(1)

    if args.command == "auth":
        print("[+] Authentication successful and token saved!")
    elif args.command == "courses":
        courses = list_courses(classroom_service)
        display_courses(courses)
    elif args.command == "pending":
        print("[*] Fetching assignments and checking submission statuses...")
        pending = get_pending_assignments(classroom_service, course_id=args.course_id)
        display_pending(pending)
    elif args.command == "details":
        details = get_assignment_details(classroom_service, args.course_id, args.work_id)
        display_details(details)
    elif args.command == "attach-link":
        attach_link(classroom_service, args.course_id, args.work_id, args.url)
        print(f"[+] Successfully attached link: {args.url}")
    elif args.command == "attach-file":
        upload_and_attach_file(classroom_service, drive_service, args.course_id, args.work_id, args.file)
        print(f"[+] Successfully uploaded and attached file: {args.file}")
    elif args.command == "turn-in":
        turn_in_assignment(classroom_service, args.course_id, args.work_id)
        print(f"[+] Assignment successfully turned in!")
    elif args.command == "reclaim":
        reclaim_assignment(classroom_service, args.course_id, args.work_id)
        print(f"[+] Assignment reclaimed (unsubmitted) successfully.")


if __name__ == '__main__':
    main()
