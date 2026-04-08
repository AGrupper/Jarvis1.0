# Start Session

Detect the current project and generate a "here's where you left off" summary, posted to Notion.

## How to detect the project

Infer the project name from the current workspace folder name:
- Strip trailing version numbers: "Jarvis1.0" -> "Jarvis"
- Use as-is for other names: "Math homework" -> "Math homework"

## Instructions

Spawn a **Sonnet subagent** (via the Agent tool with `model: "sonnet"`) with the following prompt. The subagent does all the work — you just relay the result.

### Subagent prompt

```
You are a development assistant generating a "here's where you left off" session start summary for the project "{project_name}".

## Step 1: Fetch last session debrief from Notion

Search Notion for the most recent page in the Session Debriefs database (URL: https://www.notion.so/33834a332bc2806381a4dd07fe7db184) that matches the project "{project_name}".

Use notion-search with query "[{project_name}] Session Debrief" to find it. Fetch the page content.

If no debrief found, note "No previous session debrief found for {project_name}."

## Step 2: Fetch recent GitHub activity

Use the github MCP tools to fetch from the repo AGrupper/Jarvis1.0 (or the relevant repo for this project):
- Recent commits (last 48 hours)
- Open PRs
- Open issues assigned to the user

If GitHub MCP is not authenticated, skip this step and note it.

## Step 3: Generate summary

Write a concise summary with these sections:

# Last Session Recap
What was accomplished and what was left open.

# Recent GitHub Activity
Key commits, open PRs, and issues that need attention.

# Suggested Priorities
Top 3-5 things to focus on this session, in order of importance.

Be direct and actionable.

## Step 4: Post to Notion

Create a page in the Session Start database:
- Database URL: https://www.notion.so/33834a332bc28032b70de04777e86133
- Data source: collection://33834a33-2bc2-8032-b70d-e04777e86133

Properties:
- Name: "[{project_name}] Session Start — {YYYY-MM-DD HH:MM}"
- date:Date:start: "{ISO datetime}"
- date:Date:is_datetime: 1
- Project: "{project_name}"

Content (Notion-flavored Markdown):
<callout icon="🔄" color="blue_bg">
	{Last Session Recap content}
</callout>
---
## 🐙 GitHub Activity
{GitHub activity content as bullet points}
---
## 🎯 Suggested Priorities
{Priority list as bullet points}

## Step 5: Return result

Return the Notion page URL so the user can open it.
```
