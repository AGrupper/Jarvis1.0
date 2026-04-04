"""Morning briefing agent: Gmail + Calendar + Todoist -> Claude -> Notion.

Designed to run daily via cron (Mac) or Task Scheduler (PC).
First run requires interactive OAuth consent (opens browser).
"""

import os
import sys
import logging
import webbrowser
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Google APIs
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Todoist
from todoist_api_python.api import TodoistAPI

# Shared helpers — add agent/ root to path for cross-directory imports
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))
from shared.claude_helper import summarize
from shared.notion_helper import create_briefing_page

# Load .env from agent/ root
load_dotenv(AGENT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Google OAuth scopes — read-only access to Gmail and Calendar
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Claude system prompt for the morning briefing
BRIEFING_SYSTEM_PROMPT = """You are a personal executive assistant. Generate a concise morning briefing.

Structure your response in markdown with these sections (use ## headings exactly as shown):

## Today's Summary
2-3 sentences max. Say whether the day is packed or lighter, mention the main things on the agenda, and call out anything that needs attention (e.g. an important email, a deadline, a conflict). Do NOT list individual calendar events or tasks — those are shown separately. Keep it casual and useful.

## Email Highlights
Key emails that need attention. Skip newsletters and automated notifications unless they contain action items. Use bullet points.

## Today's Tasks
Tasks for today organized by priority. Flag overdue items with [OVERDUE]. Use bullet points.

Be concise and direct. Do not include any other sections."""


# ---------------------------------------------------------------------------
# Google OAuth2
# ---------------------------------------------------------------------------

def get_google_credentials() -> Credentials:
    """Authenticate with Google APIs using OAuth2.

    - Loads existing token.json if available
    - Refreshes expired tokens automatically
    - Falls back to interactive OAuth flow (opens browser) on first run

    Returns:
        Valid Google Credentials object.
    """
    creds_path = AGENT_ROOT / os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    token_path = AGENT_ROOT / os.getenv("GOOGLE_TOKEN_PATH", "token.json")

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials not found at {creds_path}. "
            "Download credentials.json from Google Cloud Console."
        )

    creds = None

    # Try loading saved token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or re-authenticate
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.warning("Token refresh failed (%s). Re-authenticating...", e)
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
        logger.info("OAuth consent completed. Saving token.")

    # Save token for future runs
    token_path.write_text(creds.to_json())
    return creds


# ---------------------------------------------------------------------------
# Data fetching — each function catches its own errors, returns [] on failure
# ---------------------------------------------------------------------------

def fetch_todays_emails(creds: Credentials, max_results: int = 20) -> list[dict]:
    """Fetch today's unread emails from Gmail.

    Returns:
        List of dicts: {'subject', 'sender', 'snippet', 'date'}
    """
    try:
        service = build("gmail", "v1", credentials=creds)
        today_str = date.today().strftime("%Y/%m/%d")
        query = f"is:unread after:{today_str}"

        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        if not messages:
            logger.info("No unread emails found for today.")
            return []

        emails = []
        for msg_stub in messages:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_stub["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "subject": headers.get("Subject", "(no subject)"),
                "sender": headers.get("From", "unknown"),
                "snippet": msg.get("snippet", ""),
                "date": headers.get("Date", ""),
            })

        logger.info("Fetched %d emails.", len(emails))
        return emails

    except HttpError as e:
        logger.error("Gmail API error: %s", e)
        return []


def fetch_todays_events(creds: Credentials) -> list[dict]:
    """Fetch today's calendar events.

    Returns:
        List of dicts: {'summary', 'start', 'end', 'location'}
    """
    try:
        service = build("calendar", "v3", credentials=creds)

        now_utc = datetime.now(timezone.utc)
        start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        raw_events = result.get("items", [])

        events = []
        for ev in raw_events:
            start = ev.get("start", {})
            end = ev.get("end", {})
            events.append({
                "summary": ev.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
                "location": ev.get("location", ""),
            })

        logger.info("Fetched %d calendar events.", len(events))
        return events

    except HttpError as e:
        logger.error("Calendar API error: %s", e)
        return []


def fetch_active_tasks() -> list[dict]:
    """Fetch today's and overdue Todoist tasks.

    Returns:
        List of dicts: {'content', 'priority', 'due', 'project_id'}
    """
    try:
        api = TodoistAPI(os.environ["TODOIST_API_TOKEN"])
        today = date.today()

        tasks = []
        for page in api.get_tasks():
            for task in page:
                if task.due and str(task.due.date) <= today.isoformat():
                    tasks.append({
                        "content": task.content,
                        "priority": task.priority,
                        "due": task.due.string if task.due else None,
                        "project_id": task.project_id,
                    })

        logger.info("Fetched %d tasks for today.", len(tasks))
        return tasks

    except Exception as e:
        logger.error("Todoist API error: %s", e)
        return []


# ---------------------------------------------------------------------------
# Claude summarization
# ---------------------------------------------------------------------------

def generate_briefing(
    emails: list[dict],
    events: list[dict],
    tasks: list[dict],
) -> str:
    """Format raw data and send to Claude for summarization."""

    today = date.today()
    sections = [f"TODAY'S DATE: {today.isoformat()} ({today.strftime('%A')})"]

    # Calendar events (context for the summary — shown via Notion Calendar, not as a section)
    sections.append(f"\n=== TODAY'S CALENDAR ({len(events)}) ===")
    if events:
        for i, ev in enumerate(events, 1):
            loc = f" | {ev['location']}" if ev["location"] else ""
            sections.append(f"{i}. {ev['start']} - {ev['end']} | {ev['summary']}{loc}")
    else:
        sections.append("(none)")

    # Emails
    sections.append(f"\n=== UNREAD EMAILS ({len(emails)}) ===")
    if emails:
        for i, em in enumerate(emails, 1):
            sections.append(
                f"{i}. From: {em['sender']}\n"
                f"   Subject: {em['subject']}\n"
                f"   Preview: {em['snippet']}"
            )
    else:
        sections.append("(none)")

    # Tasks (today + overdue only)
    sections.append(f"\n=== TODAY'S TASKS ({len(tasks)}) ===")
    if tasks:
        for i, t in enumerate(tasks, 1):
            due = f" (due: {t['due']})" if t["due"] else ""
            sections.append(f"{i}. [P{t['priority']}] {t['content']}{due}")
    else:
        sections.append("(none)")

    raw_text = "\n".join(sections)
    logger.info("Sending %d chars to Claude for summarization.", len(raw_text))

    return summarize(
        content=raw_text,
        system_prompt=BRIEFING_SYSTEM_PROMPT,
        max_tokens=1500,
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full morning briefing pipeline."""
    logger.info("=== Starting morning briefing for %s ===", date.today())

    # 1. Authenticate with Google
    try:
        creds = get_google_credentials()
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    # 2. Fetch data from all sources (each fails gracefully)
    emails = fetch_todays_emails(creds)
    events = fetch_todays_events(creds)
    tasks = fetch_active_tasks()

    if not emails and not events and not tasks:
        logger.warning("No data from any source. Skipping briefing.")
        return

    logger.info(
        "Data collected: %d emails, %d events, %d tasks",
        len(emails), len(events), len(tasks),
    )

    # 3. Generate Claude summary
    summary = generate_briefing(emails, events, tasks)
    logger.info("Generated briefing (%d chars).", len(summary))

    # 4. Write to Notion
    page_id = create_briefing_page(briefing_date=date.today(), summary_markdown=summary, events=events)
    logger.info("Notion page created: %s", page_id)

    # 5. Open the briefing page in Notion
    page_url = f"https://notion.so/{page_id.replace('-', '')}"
    webbrowser.open(page_url)
    logger.info("Opened briefing in browser.")

    logger.info("=== Morning briefing complete ===")


if __name__ == "__main__":
    main()
