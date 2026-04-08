# End Session

Wrap up the current work session: update CLAUDE.md, commit + push, and generate a session debrief posted to Notion.

## How to detect the project

Infer the project name from the current workspace folder name:
- Strip trailing version numbers: "Jarvis1.0" -> "Jarvis"
- Use as-is for other names

## Steps

### 1. Update CLAUDE.md

Update the "Current Status" section in CLAUDE.md to reflect what was done in this session. Keep the format consistent with existing entries. Add new items under "### Working" and update "### Not Yet Done" as appropriate.

### 2. Commit and push

Stage all changed files (except .env, credentials, tokens). Create a commit with a descriptive message summarizing the session's work. Push to GitHub.

**Important:** "Commit" always means commit + push for this user.

### 3. Generate session debrief

Spawn a **Sonnet subagent** (via the Agent tool with `model: "sonnet"`) with the following prompt:

```
You are a technical project assistant writing a session debrief for the project "{project_name}".

## Step 1: Fetch recent commits

Use the github MCP tools to fetch commits from AGrupper/Jarvis1.0 (or the relevant repo).

To determine the time window: search Notion for the most recent "[{project_name}] Session Debrief" in the Session Debriefs database (URL: https://www.notion.so/33834a332bc2806381a4dd07fe7db184). Use that page's date as the "since" cutoff. If no previous debrief, use the last 48 hours.

If GitHub MCP is not authenticated, use `git log` locally via Bash to get commits since the last debrief date.

If NO commits are found (nothing was pushed), fall back to a conversation-based debrief: summarize what was discussed and accomplished in the current Claude Code session based on the conversation context. Generate the three sections from that context instead.

## Step 2: Generate debrief

Based on the commits and file changes, write:

# What Was Done
Describe specifically what was built, changed, or fixed. Explain why it matters.

# What's Open
What looks unfinished, untested, or likely to need follow-up.

# What's Next
Top 3-5 priorities for the next session.

Use bullet points. Be concise but specific.

## Step 3: Post to Notion

Create a page in the Session Debriefs database:
- Database URL: https://www.notion.so/33834a332bc2806381a4dd07fe7db184
- Data source: collection://33834a33-2bc2-8063-81a4-dd07fe7db184

Properties:
- Name: "[{project_name}] Session Debrief — {YYYY-MM-DD HH:MM}"
- date:Date:start: "{ISO datetime}"
- date:Date:is_datetime: 1
- Type: "session_debrief"
- Status: "completed"
- Project: "{project_name}"

Content (Notion-flavored Markdown):
## What Was Done
{content as bullet points}
---
## What's Open
{content as bullet points}
---
## What's Next
{content as bullet points}

## Step 4: Return result

Return the Notion page URL.
```

### 4. Report to user

Show the Notion page URL for the debrief so they can review it.
