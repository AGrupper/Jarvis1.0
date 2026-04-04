"""Session debrief agent: collect notes + auto-detect activity -> structured Notion page.

Run manually at the end of a work session:
    cd agent && python workhorse/session_debrief.py
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from github import Github, Auth

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))
from shared.claude_helper import summarize
from shared.notion_helper import write_session_debrief

load_dotenv(AGENT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEBRIEF_PROMPT = """You are a technical project assistant writing a session debrief. Synthesize the user's notes with any auto-detected activity (commits, files changed) into a clear, insightful debrief.

For each section:
- **What Was Done**: Combine the user's high-level description with specific technical details from commits and files changed. Be specific about what was built, fixed, or changed and why it matters.
- **What's Open**: Reflect what the user said is open, and if the code changes suggest anything unfinished or untested, mention it.
- **What's Next**: Keep the user's stated priorities and add smart suggestions based on the work done (e.g. "commit before continuing", "test the new flow end-to-end").

Keep the three section structure with these exact headers: # What Was Done, # What's Open, # What's Next. Use bullet points. Be concise but thorough. If there's no GitHub activity, just work with the user's notes."""


def auto_detect_activity() -> str:
    """Fetch today's GitHub commits with file-level details across configured repos."""
    token = os.environ.get("GITHUB_TOKEN")
    repos_str = os.getenv("GITHUB_REPOS", "")
    if not token or not repos_str:
        return ""

    g = Github(auth=Auth.Token(token))
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    lines = []

    for repo_name in repos_str.split(","):
        repo_name = repo_name.strip()
        if not repo_name:
            continue
        try:
            repo = g.get_repo(repo_name)
            commits = list(repo.get_commits(since=since)[:10])
            if commits:
                lines.append(f"\n{repo_name}:")
                for c in commits:
                    # Full commit message
                    lines.append(f"  Commit {c.sha[:7]}: {c.commit.message}")
                    # Files changed
                    try:
                        for f in c.files[:15]:
                            lines.append(f"    {f.status}: {f.filename} (+{f.additions}/-{f.deletions})")
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Error fetching %s: %s", repo_name, e)

    return "\n".join(lines)


def collect_session_notes() -> tuple[str, str, str, str]:
    """Interactively collect session debrief notes from the user."""
    print("\n=== Session Debrief ===\n")

    project = input("What project/topic is this session about? ").strip()

    # Show auto-detected activity as context
    activity = auto_detect_activity()
    if activity:
        print("\nDetected today's GitHub activity:")
        print(activity)
        print()

    print("Answer the following (press Enter twice to finish each section):\n")

    what_done = _multiline_input("What did you accomplish this session?")
    whats_open = _multiline_input("What's still open or blocked?")
    whats_next = _multiline_input("What should you tackle next session?")

    # Prepend auto-detected activity to what_done
    if activity:
        what_done = f"Auto-detected commits:\n{activity}\n\nManual notes:\n{what_done}"

    return what_done, whats_open, whats_next, project


def _multiline_input(prompt: str) -> str:
    """Read multiple lines until user enters a blank line."""
    print(f"{prompt}")
    print("(Enter a blank line to finish)")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    """Collect session notes and write debrief to Notion."""
    what_done, whats_open, whats_next, project = collect_session_notes()

    if not what_done and not whats_open and not whats_next:
        print("Nothing entered. Skipping debrief.")
        return

    # Optionally clean up notes with Claude
    try:
        raw = f"# What Was Done\n{what_done}\n\n# What's Open\n{whats_open}\n\n# What's Next\n{whats_next}"
        cleaned = summarize(content=raw, system_prompt=DEBRIEF_PROMPT, max_tokens=1500)

        # Parse cleaned output back into sections
        sections = {"done": what_done, "open": whats_open, "next": whats_next}
        current = None
        for line in cleaned.split("\n"):
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

        what_done = sections["done"].strip() or what_done
        whats_open = sections["open"].strip() or whats_open
        whats_next = sections["next"].strip() or whats_next
    except Exception as e:
        logger.warning("Claude cleanup failed (%s). Using raw notes.", e)

    # Write to Notion
    page_id = write_session_debrief(what_done, whats_open, whats_next, project=project or None)

    print(f"\nDebrief saved to Notion (page: {page_id})")
    logger.info("=== Session debrief complete ===")


if __name__ == "__main__":
    main()
