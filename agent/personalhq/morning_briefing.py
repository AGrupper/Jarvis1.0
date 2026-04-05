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
from urllib.request import urlopen
from urllib.parse import urlencode
import json

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
BRIEFING_SYSTEM_PROMPT = """You are Amit's friendly personal assistant. You talk like a real friend giving a quick rundown — warm, casual, human — not a corporate briefing tool.

Structure your response in markdown with these sections. You MUST start your response with the literal line `## Today's Summary` — this heading is required for downstream parsing. Same for the other section headings below. Do not skip, rename, or merge headings.

## Today's Summary
On the line directly after the heading, open with a time-of-day-aware greeting by name: "Good morning, Amit." / "Afternoon, Amit." / "Evening, Amit." (The input tells you the current time of day.)

Then ONE flowing sentence that weaves together the weather feel (if provided) and the day's shape. Weather leads as an aside right after the greeting, then pivot into the day. That's it — one smooth sentence, not two.

Reference example from Amit (match this voice — simple, warm, low on detail):
> "Good morning, Amit. Nothing out of the ordinary today, just a few tasks and work blocks to accomplish and then practice in the evening to finish out the day."

DO:
- Keep it tight: greeting + one flowing sentence that ties weather + day together. Example shape: "Good morning, Amit. Mild and partly cloudy out there with a light breeze — nothing out of the ordinary today, just a few work blocks and training in the evening."
- Use abstract groupings: "a few tasks", "work blocks", "some study time", "training in the evening".
- Use natural vibe-check phrasing like "nothing out of the ordinary", "pretty chill day", "busy but nothing wild", "easy one today".
- If weather info is provided, weave it into the flowing sentence as a descriptive aside right after the greeting. Use the sky/temperature feel AND the wind if present, in natural language — don't truncate. Example: "Mild and partly cloudy out there with a light breeze — [day description follows]". No numbers, no temperatures — just the feel.

DON'T:
- Don't use words like: "structured", "deliberate", "packed", "productive", "balanced", "mix of", "variety of", "solid day", "well-rounded". These are corporate filler.
- Don't name specific calendar events or activities unless ONE is genuinely worth flagging (a real deadline, a conflict, something requiring prep). If nothing stands out, stay abstract.
- Don't describe Todoist tasks as "due today" — Amit's Todoist dates = what he plans to work on today, not hard deadlines. Say "planning to tackle" / "knocking out" / "on the list".
- Don't list the schedule. Calendar and tasks are shown separately.

## Email Highlights
Key emails that need attention. Skip newsletters and automated notifications unless they contain action items. Use bullet points.

## Today's Tasks
Tasks organized by priority. The input marks each task with [OVERDUE] or [TODAY]. Preserve the [OVERDUE] tag in your output for those items. Do NOT add [OVERDUE] to tasks marked [TODAY]. Use bullet points.

Be warm but concise. Do not include any other sections."""


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


def _sky_and_temp(code: int, high_c: float) -> str:
    """Sky + temperature description from WMO code and daily high. No numbers."""
    # Precipitation / storms — code dominates
    if code in (95, 96, 99):
        return "thunderstorms rolling through"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow and cold"
    if code in (66, 67):
        return "freezing rain"
    if code in (51, 53, 55):
        return "light drizzle"
    if code in (61, 63, 65, 80, 81, 82):
        temp_word = "warm" if high_c >= 20 else "cool" if high_c >= 12 else "cold"
        heavy = code in (65, 82)
        return f"{'heavy rain' if heavy else 'rainy'} and {temp_word}"
    if code in (45, 48):
        return "foggy"

    # Cloudy / overcast (code 3) and partly cloudy (2)
    if code == 3:
        if high_c >= 22:
            return "warm but overcast"
        if high_c >= 12:
            return "mild and grey"
        return "cold and overcast"
    if code == 2:
        if high_c >= 24:
            return "warm with some clouds"
        if high_c >= 18:
            return "mild and partly cloudy"
        if high_c >= 12:
            return "cool and partly cloudy"
        return "cold and partly cloudy"

    # Clear / mostly clear (codes 0, 1)
    if high_c >= 30:
        return "hot and sunny"
    if high_c >= 24:
        return "warm and sunny"
    if high_c >= 18:
        return "mild and clear"
    if high_c >= 12:
        return "cool and clear"
    return "cold and crisp"


def _wind_feel(wind_kmh: float) -> str | None:
    """Natural-language wind descriptor. None if barely any wind."""
    if wind_kmh < 10:
        return None
    if wind_kmh < 20:
        return "light breeze"
    if wind_kmh < 35:
        return "breezy"
    if wind_kmh < 50:
        return "windy"
    return "very windy"


def fetch_weather() -> dict | None:
    """Fetch today's weather feel for WEATHER_LOCATION via Open-Meteo (no API key).

    Returns:
        Dict: {'location', 'feel'} or None. `feel` is a short natural-language
        phrase like "nice and warm" or "cold and rainy" — no numbers.
    """
    location = os.getenv("WEATHER_LOCATION")
    if not location:
        return None

    try:
        # Geocode
        geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
            {"name": location, "count": 1, "format": "json"}
        )
        with urlopen(geo_url, timeout=10) as r:
            geo = json.loads(r.read())
        results = geo.get("results") or []
        if not results:
            logger.warning("Weather: no geocoding result for %r.", location)
            return None
        lat, lon = results[0]["latitude"], results[0]["longitude"]
        resolved_name = results[0].get("name", location)

        # Forecast
        fc_url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,weather_code,wind_speed_10m_max",
            "timezone": "auto",
            "forecast_days": 1,
        })
        with urlopen(fc_url, timeout=10) as r:
            fc = json.loads(r.read())

        daily = fc.get("daily", {})
        code = int((daily.get("weather_code") or [0])[0])
        high_c = float((daily.get("temperature_2m_max") or [15])[0])
        wind_kmh = float((daily.get("wind_speed_10m_max") or [0])[0])

        feel = _sky_and_temp(code, high_c)
        wind = _wind_feel(wind_kmh)

        weather = {"location": resolved_name, "feel": feel, "wind": wind}
        log_wind = f", {wind}" if wind else ""
        logger.info("Weather: %s, %s%s.", resolved_name, feel, log_wind)
        return weather

    except Exception as e:
        logger.error("Weather fetch failed: %s", e)
        return None


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
                        "is_overdue": str(task.due.date) < today.isoformat(),
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
    weather: dict | None = None,
) -> str:
    """Format raw data and send to Claude for summarization."""

    today = date.today()
    now = datetime.now()
    hour = now.hour
    if hour < 12:
        time_of_day = "morning"
    elif hour < 17:
        time_of_day = "afternoon"
    else:
        time_of_day = "evening"
    sections = [
        f"TODAY'S DATE: {today.isoformat()} ({today.strftime('%A')})",
        f"CURRENT TIME: {now.strftime('%H:%M')} ({time_of_day})",
    ]

    if weather:
        wind_line = f"\nWind: {weather['wind']}." if weather.get("wind") else ""
        sections.append(
            f"\n=== WEATHER ===\n"
            f"Location: {weather['location']}\n"
            f"Sky and temperature: {weather['feel']}.{wind_line}"
        )

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
            tag = "[OVERDUE]" if t.get("is_overdue") else "[TODAY]"
            sections.append(f"{i}. {tag} [P{t['priority']}] {t['content']}{due}")
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
    weather = fetch_weather()

    if not emails and not events and not tasks:
        logger.warning("No data from any source. Skipping briefing.")
        return

    logger.info(
        "Data collected: %d emails, %d events, %d tasks, weather=%s",
        len(emails), len(events), len(tasks), "yes" if weather else "no",
    )

    # 3. Generate Claude summary
    summary = generate_briefing(emails, events, tasks, weather=weather)
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
