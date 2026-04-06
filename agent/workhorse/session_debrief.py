"""Session debrief agent: auto-summarize commits since last debrief -> Notion page.

Runs automatically at the end of a work session (no user input required):
    cd agent && python workhorse/session_debrief.py

Reads commits from GitHub since the last session debrief, sends them to Claude,
and writes a structured debrief to Notion. Exit code 2 means no commits found
(the /end-session skill uses this to fall back to a conversation-based debrief).
"""

import argparse
import json
import os
import re
import sys
import logging
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from github import Github, Auth

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))
from shared.claude_helper import summarize
from shared.notion_helper import get_latest_session_debrief, write_session_debrief

load_dotenv(AGENT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEBRIEF_PROMPT = """You are a technical project assistant writing a session debrief based solely on git commits and file changes.

For each section:
- **What Was Done**: Describe specifically what was built, changed, or fixed based on the commit messages and files touched. Explain why it matters where you can infer it.
- **What's Open**: Based on the commits and file changes, identify what looks unfinished, untested, or likely to need follow-up.
- **What's Next**: Suggest the top 3-5 priorities for the next session based on what was done and what appears open.

Use these exact headers: # What Was Done, # What's Open, # What's Next. Use bullet points. Be concise but specific."""


def _derive_project_from_repos() -> str | None:
    """Derive a project name from the GITHUB_REPOS env var as a fallback."""
    repos_str = os.getenv("GITHUB_REPOS", "")
    if not repos_str:
        return None
    first_repo = repos_str.split(",")[0].strip()
    repo_name = first_repo.split("/")[-1] if "/" in first_repo else first_repo
    # Strip trailing version numbers/dots (e.g. "Jarvis1.0" -> "Jarvis")
    return re.sub(r"[\d.]+$", "", repo_name).strip() or repo_name


def auto_detect_activity(since: datetime) -> str:
    """Fetch GitHub commits with file-level details since the given datetime."""
    token = os.environ.get("GITHUB_TOKEN")
    repos_str = os.getenv("GITHUB_REPOS", "")
    if not token or not repos_str:
        return ""

    g = Github(auth=Auth.Token(token))
    lines = []

    for repo_name in repos_str.split(","):
        repo_name = repo_name.strip()
        if not repo_name:
            continue
        try:
            repo = g.get_repo(repo_name)
            commits = list(repo.get_commits(since=since)[:20])
            if commits:
                lines.append(f"\n{repo_name} (since {since.strftime('%Y-%m-%d %H:%M UTC')}):")
                for c in commits:
                    lines.append(f"  Commit {c.sha[:7]}: {c.commit.message}")
                    try:
                        for f in c.files[:15]:
                            lines.append(f"    {f.status}: {f.filename} (+{f.additions}/-{f.deletions})")
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Error fetching %s: %s", repo_name, e)

    return "\n".join(lines)


def _parse_sections(text: str, fallback_done: str = "") -> tuple[str, str, str]:
    """Parse Claude's response into (done, open, next) sections."""
    sections = {"done": fallback_done, "open": "", "next": ""}
    current = None
    for line in text.split("\n"):
        lower = line.strip().lower()
        if "what was done" in lower:
            current = "done"
            sections["done"] = ""
        elif "what's open" in lower or "whats open" in lower:
            current = "open"
            sections["open"] = ""
        elif "what's next" in lower or "whats next" in lower:
            current = "next"
            sections["next"] = ""
        elif current:
            sections[current] += line + "\n"
    return (
        sections["done"].strip() or fallback_done,
        sections["open"].strip(),
        sections["next"].strip(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None, help="Project name override (auto-detected if omitted)")
    parser.add_argument("--from-json", default=None, help="Path to JSON with pre-written debrief content (skips commit fetch)")
    args, _ = parser.parse_known_args()

    # ── Mode 2: pre-written content from Claude Code (no-commit fallback) ──
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        what_done = data.get("done", "")
        whats_open = data.get("open", "")
        whats_next = data.get("next", "")
        project = args.project or data.get("project") or None
        logger.info("=== Session Debrief (from conversation summary) ===")
    else:
        # ── Mode 1: auto from GitHub commits ──
        logger.info("=== Session Debrief ===")

        project = args.project or _derive_project_from_repos()
        if project:
            logger.info("Project: %s", project)

        # Determine time window: since last session debrief (fallback: 48h ago)
        last_debrief = get_latest_session_debrief(project=project)
        if last_debrief and last_debrief.get("date"):
            since = datetime.fromisoformat(last_debrief["date"]).replace(
                tzinfo=timezone.utc
            )
            logger.info("Fetching commits since last debrief: %s", last_debrief["date"])
        else:
            since = datetime.now(timezone.utc) - timedelta(hours=48)
            logger.info("No previous debrief found. Fetching last 48 hours of commits.")

        activity = auto_detect_activity(since)
        if not activity:
            print("NO_COMMITS")
            logger.info("No commits found since last debrief. Exiting with code 2.")
            sys.exit(2)

        logger.info("Generating debrief from commits via Claude...")
        cleaned = summarize(content=activity, system_prompt=DEBRIEF_PROMPT, max_tokens=1500)
        what_done, whats_open, whats_next = _parse_sections(cleaned, fallback_done=activity)

    # ── Write to Notion and open in browser ──
    page_id = write_session_debrief(what_done, whats_open, whats_next, project=project)
    page_url = f"https://notion.so/{page_id.replace('-', '')}"
    webbrowser.open(page_url)
    print(f"\nDebrief saved to Notion (page: {page_id})")
    logger.info("=== Session debrief complete ===")


if __name__ == "__main__":
    main()
