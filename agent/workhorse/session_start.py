"""Session start agent: loads last debrief + GitHub activity -> "where you left off" summary.

Run manually at the start of a work session:
    cd agent && python workhorse/session_start.py
"""

import os
import sys
import subprocess
import logging
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from github import Github, Auth

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))
from shared.claude_helper import summarize
from shared.notion_helper import get_latest_session_debrief, create_session_start_page

load_dotenv(AGENT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SESSION_START_PROMPT = """You are a development assistant. Based on the last session debrief and recent GitHub activity, generate a concise "here's where you left off" summary.

Structure your response:
# Last Session Recap
What was accomplished and what was left open.

# Recent GitHub Activity
Key commits, open PRs, and issues that need attention.

# Suggested Priorities
Top 3-5 things to focus on this session, in order of importance.

Be direct and actionable."""


def fetch_github_activity(repos: list[str], since_hours: int = 48) -> str:
    """Fetch recent commits, open PRs, and assigned issues from configured repos."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN not set. Skipping GitHub activity.")
        return ""

    g = Github(auth=Auth.Token(token))
    username = g.get_user().login
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    sections = []

    for repo_name in repos:
        try:
            repo = g.get_repo(repo_name.strip())
            parts = [f"\n## {repo_name}"]

            # Recent commits
            commits = list(repo.get_commits(since=since)[:5])
            if commits:
                parts.append("### Recent Commits")
                for c in commits:
                    short_msg = c.commit.message.split("\n")[0]
                    parts.append(f"- {c.sha[:7]} {short_msg}")

            # Open PRs
            prs = list(repo.get_pulls(state="open")[:5])
            if prs:
                parts.append("### Open PRs")
                for pr in prs:
                    parts.append(f"- #{pr.number} {pr.title}")

            # Issues assigned to user
            issues = list(repo.get_issues(assignee=username, state="open")[:5])
            if issues:
                parts.append("### My Open Issues")
                for issue in issues:
                    if not issue.pull_request:
                        parts.append(f"- #{issue.number} {issue.title}")

            sections.append("\n".join(parts))
        except Exception as e:
            logger.error("Error fetching %s: %s", repo_name, e)

    return "\n".join(sections)


def main() -> None:
    """Load last debrief + GitHub activity, generate session start summary."""
    logger.info("=== Session Start ===")

    # Auto-sync from GitHub before starting session
    repo_root = AGENT_ROOT.parent
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            logger.info("git pull: %s", result.stdout.strip())
        if result.returncode != 0:
            logger.warning("git pull failed: %s", result.stderr.strip())
    except Exception as e:
        logger.warning("git pull skipped: %s", e)

    # 1. Ask what the user is working on today
    project = input("What are you working on today? ").strip() or None
    if project:
        logger.info("Project context: %s", project)

    # 2. Load last session debrief from Notion (filtered by project if given)
    debrief = get_latest_session_debrief(project=project)
    debrief_text = ""
    if debrief:
        debrief_text = (
            f"LAST SESSION: {debrief['title']} ({debrief['date']})\n"
            f"{debrief['content']}"
        )
        logger.info("Loaded last debrief: %s", debrief["title"])
    else:
        debrief_text = f"No previous session debrief found{f' for {project}' if project else ''}."
        logger.info("No previous session debrief.")

    # 3. Fetch GitHub activity
    repos = os.getenv("GITHUB_REPOS", "").split(",")
    repos = [r.strip() for r in repos if r.strip()]
    github_text = fetch_github_activity(repos) if repos else "No repos configured."

    # 4. Generate summary via Claude
    raw = f"{debrief_text}\n\n=== GITHUB ACTIVITY ===\n{github_text}"
    summary = summarize(content=raw, system_prompt=SESSION_START_PROMPT, max_tokens=1200)

    # 5. Write to Notion and open
    page_id = create_session_start_page(summary, project=project)
    page_url = f"https://notion.so/{page_id.replace('-', '')}"
    webbrowser.open(page_url)
    logger.info("Opened session start in browser.")

    logger.info("=== Session start complete ===")


if __name__ == "__main__":
    main()
