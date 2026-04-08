# Jarvis 1.0 — Personal AI Agent System

## Project Overview
Personal AI agent system using Claude Code workflows + MCP tools with Notion as the shared brain. No Python scripts — everything runs via `.md` workflow files and Claude Code skills.

- **Morning briefing** — scheduled via RemoteTrigger (cloud, daily 9 AM Israel time). Fetches Gmail, Calendar, Weather, writes to Notion.
- **Session start/debrief** — Claude Code skills (`/start-session`, `/end-session`). Run interactively in any Claude Code session.

**Collaboration context:** see [MEMORY.md](MEMORY.md) for briefing design preferences, iteration workflow, and other Jarvis-specific context Claude should know about.

## Architecture

### How it works (no Python)
All logic lives in `.md` workflow files that instruct Claude agents what to do. Data is fetched via MCP tools (Gmail, Google Calendar, Notion) and WebFetch (weather API). Results are posted to Notion via the Notion MCP.

### Scheduling
- **Morning briefing**: RemoteTrigger `trig_01BsVkCiat4WG2UKTis8kw3p` — runs daily at 6:00 AM UTC (9:00 AM Israel). Cloud-based, Mac doesn't need to be on.
- **Session start/debrief**: Invoked manually via `/start-session` and `/end-session` Claude Code slash commands.
- Manage triggers at: https://claude.ai/code/scheduled

### Billing
- **Automated tasks** (morning briefing via RemoteTrigger): Billed against API account (pay-per-use). Does NOT consume subscription tokens.
- **Interactive tasks** (session start/debrief): Run inside existing Claude Code sessions via Sonnet subagent — minimal incremental cost.

### Model Selection
| Workflow | Model | Why |
|---|---|---|
| Morning briefing (RemoteTrigger) | **Sonnet 4.6** | Creative writing with voice spec + tool calling |
| Session start | **Sonnet** (via subagent) | Structured summary |
| Session debrief | **Sonnet** (via subagent) | Structured summary |

### Cross-Machine Sync
All `.md` workflow files and skills live in the repo. `git push/pull` syncs between Mac and PC. Slash commands are symlinked from `skills/` to `~/.claude/commands/`.

## Project Structure
```
Jarvis1.0/
├── CLAUDE.md                         # This file
├── .gitignore
├── workflows/
│   └── morning-briefing/
│       ├── 1-fetch-data.md           # Instructions: fetch Gmail, Calendar, Weather
│       ├── 2-write-briefing.md       # Instructions: write summary + post to Notion
│       └── summary_voice.md          # Voice spec for briefing summary section
├── skills/
│   ├── start-session.md              # Claude Code skill: fetch last debrief + GitHub, write to Notion
│   └── end-session.md                # Claude Code skill: update CLAUDE.md, commit, write debrief to Notion
└── agent/
    ├── .env                          # API keys (NEVER commit)
    └── .env.example                  # Template listing all required keys
```

**Symlinks (one-time setup per machine):**
```bash
ln -sf /path/to/Jarvis1.0/skills/start-session.md ~/.claude/commands/start-session.md
ln -sf /path/to/Jarvis1.0/skills/end-session.md ~/.claude/commands/end-session.md
```

## Environment Variables
The `agent/.env` file still holds API keys for any future local tooling. See `agent/.env.example` for the full list of variables. The `.md` workflows don't use these — they access services via MCP tools connected to the Claude AI account.

## MCP Connections

### Connected (via Claude AI account)
| Service | MCP Server | Used by |
|---|---|---|
| Gmail | `gmail.mcp.claude.com` | Morning briefing |
| Google Calendar | `gcal.mcp.claude.com` | Morning briefing |
| Notion | `mcp.notion.com` | Morning briefing, session start, session debrief |

### Not yet connected
| Service | Status | Notes |
|---|---|---|
| Todoist | No MCP server available | Tasks section omitted from briefing. WebFetch can't pass auth headers. |
| Garmin | No MCP server available | Body section omitted from briefing. Complex auth (Cloudflare). |
| GitHub | MCP needs OAuth | Run `/mcp` in Claude Code to authenticate. Skills fall back to `git log` locally. |

### Weather
Open-Meteo API via WebFetch (no API key, no MCP needed). Hardcoded to Tel Aviv in workflow.

## Notion Database Schemas

### Daily Briefings DB
- **URL:** `https://www.notion.so/33834a332bc280748168c864704afede`
- **Data source:** `collection://33834a33-2bc2-803c-9ada-000b8d9df901`

| Property | Type | Notes |
|---|---|---|
| Name | title | Format: `Daily Briefing — YYYY-MM-DD` |
| Date | date | |
| Type | select | Always `morning_briefing` |

### Session Starts DB
- **URL:** `https://www.notion.so/33834a332bc28032b70de04777e86133`

| Property | Type | Notes |
|---|---|---|
| Name | title | Format: `[Project] Session Start — YYYY-MM-DD HH:MM` |
| Date | date | |
| Project | select | e.g. "Jarvis", "Math homework" |

### Session Debriefs DB
- **URL:** `https://www.notion.so/33834a332bc2806381a4dd07fe7db184`

| Property | Type | Notes |
|---|---|---|
| Name | title | Format: `[Project] Session Debrief — YYYY-MM-DD HH:MM` |
| Date | date | |
| Type | select | Always `session_debrief` |
| Status | select | Always `completed` |
| Project | select | e.g. "Jarvis", "Math homework" |

## Briefing Page Layout
The morning briefing Notion page uses this structure:
1. **☀️ Summary callout** (yellow) — greeting + one flowing sentence about the day (see [summary_voice.md](workflows/morning-briefing/summary_voice.md))
2. **💪 Body** (if Garmin data available) — sleep, HRV, resting HR interpreted with training recommendations
3. **📅 Today's Schedule** — formatted event list with times (e.g. `9:00 AM – 10:00 AM — Meeting`)
4. **📧 Email Highlights** — bullet points of actionable emails
5. **✅ Today's Tasks** — today's + overdue tasks

Session start page:
1. **🔄 Recap callout** (blue) — last session summary
2. **🐙 GitHub Activity** — recent commits, PRs, issues
3. **🎯 Suggested Priorities** — what to focus on

## Session Project Tagging
Session debriefs are tagged with a "Project" select property (e.g. "Jarvis", "Math homework"). Session start filters to the most recent debrief for that project. Project is auto-detected from the workspace folder name (e.g. "Jarvis1.0" -> "Jarvis").

## Voice Spec
The morning briefing summary voice spec lives in [workflows/morning-briefing/summary_voice.md](workflows/morning-briefing/summary_voice.md). Edit that file when tuning voice. Key rules:
- Greeting + ONE flowing sentence
- Weather woven as an aside, em-dash pivot into the day
- Warm, understated, casual — like a friend, not a productivity app
- No corporate filler, no numeric temperatures

## Current Status (updated 2026-04-08, session 5 — migration complete)

### Working
- **Migration to .md workflows (2026-04-08)** — replaced ~1,400 lines of Python with `.md` workflow files + MCP tools. No Python dependencies. All old scripts deleted (preserved in git history).
- **RemoteTrigger for morning briefing** — `trig_01BsVkCiat4WG2UKTis8kw3p`, daily 6 AM UTC (9 AM Israel). Connected: Gmail, Calendar, Notion MCP. Uses Sonnet 4.6.
- **`/start-session` skill** — detects project from workspace, spawns Sonnet subagent to fetch last debrief + GitHub activity, posts to Notion.
- **`/end-session` skill** — updates CLAUDE.md, commits + pushes, spawns Sonnet subagent to generate debrief from commits, posts to Notion.
- **Voice spec** — externalized in `summary_voice.md`, unchanged from Python era.
- **Weather** — Open-Meteo via WebFetch, feel phrases only (no numeric temps).
- **Notion databases** — all three databases (briefings, session starts, session debriefs) connected and working.

### Not Yet Done
- **RemoteTrigger verification** — manually fired 2026-04-08 but Notion page did not appear. Debug in next session. First scheduled run is 2026-04-09 9 AM Israel.
- **Todoist integration** — no MCP server available. Tasks section shows placeholder. Spec preserved in `1-fetch-data.md` for when a server becomes available.
- **Garmin integration** — no MCP server available. Body section omitted. Spec preserved in `1-fetch-data.md`.
- **GitHub MCP auth** — needs manual OAuth via `/mcp` in Claude Code. Skills fall back to `git log` without it.
- **Apple Shortcuts wake trigger** — trigger briefing when Sleep Focus turns off. Not yet set up (current: fixed 9 AM cron).
- **PC symlinks** — `~/.claude/commands/` symlinks need one-time setup on PC after pulling.
- Gmail query tuning — may return 0 unread (verify after first working RemoteTrigger run)
- Claude occasionally slips corporate filler words despite voice spec

### Iteration workflow
User reviews briefings via Notion page comments. Fetch via `notion-get-comments` MCP tool and iterate the prompt in the workflow `.md` files or the RemoteTrigger prompt.

## Known Issues / Gotchas
- RemoteTrigger runs in Anthropic's cloud — no access to local files, local env vars, or local services.
- GitHub repo: `AGrupper/Jarvis1.0`
- `agent/.env` still exists locally for any future local tooling. Not used by workflows (they use MCP tools directly).
- Old Python scripts are preserved in git history if needed for reference.
