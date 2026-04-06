"""Notion helper functions for reading and writing agent pages."""

import os
import logging
from datetime import date, datetime

from notion_client import Client, APIResponseError
from notion_client.helpers import iterate_paginated_api

logger = logging.getLogger(__name__)


def get_client() -> Client:
    """Return a Notion client using NOTION_TOKEN from env."""
    return Client(auth=os.environ["NOTION_TOKEN"])


# ---------------------------------------------------------------------------
# Briefing pages (PersonalHQ writes)
# ---------------------------------------------------------------------------

def create_briefing_page(
    briefing_date: date,
    summary_markdown: str,
    events: list[dict] | None = None,
    database_id: str | None = None,
) -> str:
    """Create a daily briefing page in the Notion briefing database.

    Returns:
        The created page's ID.
    """
    db_id = database_id or os.environ["NOTION_BRIEFING_DB_ID"]
    notion = get_client()

    title = f"Daily Briefing \u2014 {briefing_date.isoformat()}"
    blocks = _build_briefing_blocks(summary_markdown, briefing_date=briefing_date, events=events)

    page = notion.pages.create(
        parent={"database_id": db_id},
        properties={
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": briefing_date.isoformat()}},
            "Type": {"select": {"name": "morning_briefing"}},
        },
        children=blocks,
    )
    logger.info("Created briefing page: %s", page["id"])
    return page["id"]


# ---------------------------------------------------------------------------
# Session start pages (WorkHorse writes)
# ---------------------------------------------------------------------------

def create_session_start_page(
    summary_markdown: str,
    project: str | None = None,
    database_id: str | None = None,
) -> str:
    """Create a session start page in the Notion session start database.

    Returns:
        The created page's ID.
    """
    db_id = database_id or os.environ["NOTION_SESSION_START_DB_ID"]
    notion = get_client()

    now = datetime.now()
    title = f"Session Start — {now.strftime('%Y-%m-%d %H:%M')}"
    if project:
        title = f"[{project}] {title}"

    blocks = _build_session_start_blocks(summary_markdown)

    # Ensure required properties exist in the database
    _ensure_database_property(db_id, "Date", "date")
    if project:
        _ensure_database_property(db_id, "Project", "select")

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Date": {"date": {"start": now.isoformat()}},
    }
    if project:
        properties["Project"] = {"select": {"name": project}}

    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties,
        children=blocks,
    )
    logger.info("Created session start page: %s", page["id"])
    return page["id"]


# ---------------------------------------------------------------------------
# Session debrief pages (WorkHorse writes & reads)
# ---------------------------------------------------------------------------

def get_latest_session_debrief(
    project: str | None = None,
    database_id: str | None = None,
) -> dict | None:
    """Fetch the most recent session debrief from Notion.

    Args:
        project: If provided, only return debriefs matching this project.

    Returns:
        Dict with 'title', 'date', 'project', 'content' keys, or None if empty.
    """
    db_id = database_id or os.environ["NOTION_SESSION_DB_ID"]
    notion = get_client()

    kwargs = {
        "sorts": [{"property": "Date", "direction": "descending"}],
        "page_size": 1,
    }
    if project:
        kwargs["filter"] = {
            "property": "Project",
            "select": {"equals": project},
        }

    try:
        results = _query_database(notion, db_id, **kwargs)
    except (APIResponseError, Exception) as e:
        logger.error("Failed to query session debrief DB: %s", e)
        return None

    pages = results.get("results", [])
    if not pages:
        return None

    page = pages[0]
    props = page["properties"]

    title_parts = props.get("Name", {}).get("title", [])
    title = title_parts[0]["plain_text"] if title_parts else "Untitled"

    date_prop = props.get("Date", {}).get("date")
    debrief_date = date_prop["start"] if date_prop else None

    project_prop = props.get("Project", {}).get("select")
    project_name = project_prop["name"] if project_prop else None

    content = _get_page_content_as_text(page["id"])

    return {"title": title, "date": debrief_date, "project": project_name, "content": content}


def write_session_debrief(
    what_done: str,
    whats_open: str,
    whats_next: str,
    project: str | None = None,
    session_time: datetime | None = None,
    database_id: str | None = None,
) -> str:
    """Write a structured session debrief page to Notion.

    Returns:
        The created page's ID.
    """
    db_id = database_id or os.environ["NOTION_SESSION_DB_ID"]
    notion = get_client()

    # Ensure required properties exist in the database
    _ensure_database_property(db_id, "Status", "select")
    if project:
        _ensure_database_property(db_id, "Project", "select")

    now = session_time or datetime.now()
    title = f"Session Debrief — {now.strftime('%Y-%m-%d %H:%M')}"
    if project:
        title = f"[{project}] {title}"

    body_md = (
        f"# What Was Done\n{what_done}\n\n"
        f"# What's Open\n{whats_open}\n\n"
        f"# What's Next\n{whats_next}"
    )
    blocks = _markdown_to_notion_blocks(body_md)

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Date": {"date": {"start": now.isoformat()}},
        "Type": {"select": {"name": "session_debrief"}},
        "Status": {"select": {"name": "completed"}},
    }
    if project:
        properties["Project"] = {"select": {"name": project}}

    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties,
        children=blocks,
    )
    logger.info("Created session debrief page: %s", page["id"])
    return page["id"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_briefing_blocks(
    summary_markdown: str,
    briefing_date: date | None = None,
    events: list[dict] | None = None,
) -> list[dict]:
    """Build rich Notion blocks for the daily briefing page.

    Parses Claude's markdown into sections and formats them with callouts,
    dividers, emoji headings, and a formatted calendar schedule.
    """
    sections = _split_into_sections(summary_markdown)
    blocks = []

    # Summary section → callout block
    for name in list(sections.keys()):
        if "summary" in name.lower():
            blocks.append({
                "callout": {
                    "rich_text": _chunk_rich_text(sections.pop(name).strip()),
                    "icon": {"emoji": "☀️"},
                    "color": "yellow_background",
                }
            })
            blocks.append({"divider": {}})
            break

    # Body section (readiness) → if present, insert between summary and calendar
    for name in list(sections.keys()):
        if "body" in name.lower():
            blocks.append({"heading_2": {"rich_text": _chunk_rich_text(f"💪 {name}")}})
            blocks.extend(_markdown_to_notion_blocks(sections.pop(name)))
            blocks.append({"divider": {}})
            break

    # Calendar section with formatted events
    blocks.append({"heading_2": {"rich_text": _chunk_rich_text("📅 Today's Schedule")}})
    if events:
        for ev in events:
            time_str = _format_event_time(ev["start"], ev["end"])
            text = f"{time_str}  —  {ev['summary']}"
            if ev.get("location"):
                text += f"  📍 {ev['location']}"
            blocks.append(_rich_text_block("bulleted_list_item", text))
    else:
        blocks.append(_rich_text_block("paragraph", "No events today."))
    blocks.append({"divider": {}})

    # Remaining sections with emoji headings
    section_icons = {"email": "📧", "task": "✅", "body": "💪"}
    for name, content in sections.items():
        icon = ""
        for key, emoji in section_icons.items():
            if key in name.lower():
                icon = f"{emoji} "
                break
        blocks.append({"heading_2": {"rich_text": _chunk_rich_text(f"{icon}{name}")}})
        blocks.extend(_markdown_to_notion_blocks(content))
        blocks.append({"divider": {}})

    # Remove trailing divider
    if blocks and "divider" in blocks[-1]:
        blocks.pop()

    return blocks


def _build_session_start_blocks(summary_markdown: str) -> list[dict]:
    """Build rich Notion blocks for the session start page."""
    sections = _split_into_sections(summary_markdown)
    blocks = []

    section_icons = {"recap": "🔄", "github": "🐙", "priorities": "🎯"}

    for name, content in sections.items():
        # First section (recap) → callout
        if not blocks and "recap" in name.lower():
            blocks.append({
                "callout": {
                    "rich_text": _chunk_rich_text(content.strip()),
                    "icon": {"emoji": "🔄"},
                    "color": "blue_background",
                }
            })
            blocks.append({"divider": {}})
            continue

        icon = ""
        for key, emoji in section_icons.items():
            if key in name.lower():
                icon = f"{emoji} "
                break
        blocks.append({"heading_2": {"rich_text": _chunk_rich_text(f"{icon}{name}")}})
        blocks.extend(_markdown_to_notion_blocks(content))
        blocks.append({"divider": {}})

    if blocks and "divider" in blocks[-1]:
        blocks.pop()

    return blocks


def _split_into_sections(markdown: str) -> dict[str, str]:
    """Split markdown into sections by ## (or #) headers. Preserves order."""
    sections = {}
    current_name = None
    current_lines = []

    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines)
            current_name = stripped[3:].strip()
            current_lines = []
        elif stripped.startswith("# ") and current_name is None:
            current_name = stripped[2:].strip()
            current_lines = []
        else:
            if current_name is not None:
                current_lines.append(line)

    if current_name is not None:
        sections[current_name] = "\n".join(current_lines)

    return sections


def _ensure_database_property(database_id: str, prop_name: str, prop_type: str) -> None:
    """Ensure a property exists in a Notion database (no-op if it already exists)."""
    import httpx
    resp = httpx.patch(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        json={"properties": {prop_name: {prop_type: {}}}},
    )
    resp.raise_for_status()


def _format_event_time(start_str: str, end_str: str) -> str:
    """Format event start/end times for display (e.g. '9:00 AM – 10:30 AM')."""
    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        fmt = lambda dt: f"{dt.hour % 12 or 12}:{dt.strftime('%M')} {'AM' if dt.hour < 12 else 'PM'}"
        return f"{fmt(start)} – {fmt(end)}"
    except (ValueError, TypeError):
        return "All day"


def _query_database(notion: Client, database_id: str, **kwargs) -> dict:
    """Query a Notion database, working around notion-client v3 API changes.

    Uses httpx directly since v3 removed databases.query() and
    data_sources.query() doesn't support regular database IDs.
    """
    import httpx

    body = {}
    if "sorts" in kwargs:
        body["sorts"] = kwargs["sorts"]
    if "page_size" in kwargs:
        body["page_size"] = kwargs["page_size"]
    if "filter" in kwargs:
        body["filter"] = kwargs["filter"]

    resp = httpx.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        json=body,
    )
    resp.raise_for_status()
    return resp.json()


def _markdown_to_notion_blocks(markdown: str) -> list[dict]:
    """Convert simple markdown to Notion block objects.

    Supports: # heading_1, ## heading_2, ### heading_3, - bullets, plain text.
    Chunks text at 2000 chars (Notion's per-element limit).
    """
    blocks = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("### "):
            blocks.append(_heading_block("heading_3", stripped[4:]))
        elif stripped.startswith("## "):
            blocks.append(_heading_block("heading_2", stripped[3:]))
        elif stripped.startswith("# "):
            blocks.append(_heading_block("heading_1", stripped[2:]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(_rich_text_block("bulleted_list_item", stripped[2:]))
        else:
            blocks.append(_rich_text_block("paragraph", stripped))

    return blocks


def _heading_block(level: str, text: str) -> dict:
    return {level: {"rich_text": _chunk_rich_text(text)}}


def _rich_text_block(block_type: str, text: str) -> dict:
    return {block_type: {"rich_text": _chunk_rich_text(text)}}


def _chunk_rich_text(text: str, limit: int = 2000) -> list[dict]:
    """Split text into rich_text elements, each within Notion's char limit."""
    chunks = []
    for i in range(0, len(text), limit):
        chunks.append({"type": "text", "text": {"content": text[i : i + limit]}})
    return chunks


def _get_page_content_as_text(page_id: str) -> str:
    """Read all blocks from a Notion page and return as plain text."""
    notion = get_client()
    lines = []

    for block in iterate_paginated_api(
        notion.blocks.children.list, block_id=page_id
    ):
        block_type = block.get("type", "")
        data = block.get(block_type, {})
        rich_text = data.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text)
        if text:
            lines.append(text)

    return "\n".join(lines)
