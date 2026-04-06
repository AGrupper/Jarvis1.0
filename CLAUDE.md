# Jarvis 1.0 — Personal AI Agent System

## Project Overview
Two-machine personal AI agent system with Notion as the shared brain.

- **PersonalHQ** (MacBook) — morning briefing via launchd (5:30 AM, fires on wake)
- **WorkHorse** (PC) — manual session start/debrief scripts (both write to Notion + auto-open)

**Collaboration context:** see [MEMORY.md](MEMORY.md) for briefing design preferences, iteration workflow, and other Jarvis-specific context Claude should know about.

## Machine Ownership

| Directory | Machine | What it does |
|---|---|---|
| `agent/personalhq/` | **MacBook only** | Morning briefing (Gmail + Calendar + Todoist + Garmin + Weather -> Claude -> Notion). Triggered by launchd at 5:30 AM (fires on wake if Mac was asleep). |
| `agent/workhorse/` | **PC only** | Session start + debrief (GitHub + last debrief -> Claude -> Notion). Run manually from terminal. |
| `agent/shared/` | **Both** | Common code: `claude_helper.py`, `notion_helper.py`. Changes here affect both machines. |

**Requirements per machine:**
- Mac: `pip install -r agent/requirements-mac.txt`
- PC: `pip install -r agent/requirements-pc.txt`
- `agent/requirements.txt` is the union of all deps (kept for backwards compat)

**Do not** run `personalhq/` scripts on the PC or `workhorse/` scripts on the Mac — they depend on machine-specific APIs and credentials.

## Tech Stack
- Python 3.13 (primary on PC), 3.11+ compatible
- Claude API (`claude-haiku-4-5-20251001`) via `anthropic` SDK
- Notion via `notion-client` v3.0.0
- Gmail + Google Calendar via `google-api-python-client` (OAuth2 Desktop flow) — Mac only
- Todoist via `todoist-api-python` v4.0.0
- Garmin Connect via `garminconnect` (unofficial, sleep/HRV/RHR/body battery) — Mac only
- GitHub via `PyGithub` — PC only
- Open-Meteo weather API (no key required) — Mac only
- Secrets via `.env` + `python-dotenv`

## Project Structure
```
agent/
├── personalhq/                    # MacBook only
│   ├── morning_briefing.py        # Gmail + Calendar + Todoist + Garmin -> Claude -> Notion
│   ├── garmin_helper.py           # Garmin Connect auth + sleep/HRV/RHR/body battery fetch
│   └── summary_voice.md           # Voice spec for briefing summary section
├── workhorse/                     # PC only
│   ├── session_start.py           # Last debrief + GitHub -> Claude -> Notion (project-filtered)
│   └── session_debrief.py         # Interactive input + GitHub -> Claude -> Notion (project-tagged)
├── shared/                        # Both machines
│   ├── claude_helper.py           # Thin wrapper: summarize() function
│   └── notion_helper.py           # All Notion read/write operations
├── run_briefing.sh                # Wrapper for launchd/Shortcuts (Mac only)
├── garmin_tokens/                  # Garmin session cache (gitignored)
├── .env                           # Real secrets (NEVER commit)
├── .env.example                   # Template listing all required keys
├── .gitignore
├── credentials.json               # Google OAuth client secret (NEVER commit)
├── token.json                     # Auto-generated Google OAuth token (NEVER commit)
├── requirements.txt               # All deps (union)
├── requirements-base.txt          # Shared deps (both machines)
├── requirements-mac.txt           # Mac-only deps (includes base)
└── requirements-pc.txt            # PC-only deps (includes base)
```

## Key Design Decisions

### Imports
No `__init__.py` files. Scripts use `sys.path.insert(0, AGENT_ROOT)` to import from `shared/`. This is intentional for cron robustness.

### Notion SDK v3 Workaround
`notion-client` v3.0.0 removed `databases.query()` and `data_sources.query()` doesn't work with regular database IDs. We use custom helpers in `notion_helper.py` that call the REST API directly with `Notion-Version: 2022-06-28`:
- `_query_database()` — POST to `/databases/{id}/query`
- `_ensure_database_property()` — PATCH to `/databases/{id}` to add missing properties (Date, Project, Status, etc.) automatically before page creation

### Todoist v4 Pagination & Filtering
`api.get_tasks()` returns `Iterator[list[Task]]`, not a flat list. Must flatten with nested loop.
The v4 client does NOT support a `filter` parameter — filtering (e.g. today's tasks only) must be done client-side by comparing `task.due.date` (which is a `datetime.date` object, not a string — use `str()` to compare with ISO date strings).

### Session Project Tagging
Session debriefs are tagged with a "Project" select property (e.g. "Jarvis", "Math homework"). Session start asks "What are you working on today?" and filters to the most recent debrief for that project. This allows context switching between unrelated work streams.

### Error Handling
- Data fetching (Gmail, Calendar, Todoist, GitHub): catches errors, returns empty list, pipeline continues
- Claude API + Notion writes: errors are fatal (re-raised)

### Google OAuth
- First run is interactive (opens browser). After that, `token.json` is reused.
- If Google Cloud app is in "testing" mode, tokens expire after 7 days.
- User's Gmail must be added as a test user in Google Cloud Console > OAuth consent screen.

## Running the Scripts

```bash
# Morning briefing (runs full pipeline, auto-opens Notion page)
cd agent && python personalhq/morning_briefing.py

# Session start (asks project, writes to Notion, auto-opens page)
cd agent && python workhorse/session_start.py

# Session debrief (asks project + 3 prompts, writes to Notion)
cd agent && python workhorse/session_debrief.py
```

## Environment Variables (.env)
| Variable | Service | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API | Must have credits on console.anthropic.com |
| `NOTION_TOKEN` | Notion | Starts with `ntn_` or `secret_` |
| `NOTION_BRIEFING_DB_ID` | Notion | 32-char ID from database URL |
| `NOTION_SESSION_DB_ID` | Notion | 32-char ID from database URL (session debriefs) |
| `NOTION_SESSION_START_DB_ID` | Notion | 32-char ID from database URL (session starts) |
| `TODOIST_API_TOKEN` | Todoist | From Settings > Integrations > Developer |
| `GITHUB_TOKEN` | GitHub | Personal access token |
| `GITHUB_REPOS` | GitHub | Format: `owner/repo1,owner/repo2` |
| `GOOGLE_CREDENTIALS_PATH` | Google | Default: `credentials.json` (Mac only) |
| `GOOGLE_TOKEN_PATH` | Google | Default: `token.json` (Mac only) |
| `WEATHER_LOCATION` | Open-Meteo | City name, e.g. `Tel Aviv` (Mac only) |
| `GARMIN_EMAIL` | Garmin Connect | Garmin account email (Mac only) |
| `GARMIN_PASSWORD` | Garmin Connect | Garmin account password (Mac only) |

## Notion Database Schemas

### Daily Briefings DB
| Property | Type |
|---|---|
| Name | title |
| Date | date |
| Type | select |

### Session Starts DB
| Property | Type | Notes |
|---|---|---|
| Name | title | Format: `[Project] Session Start — YYYY-MM-DD HH:MM` |
| Date | date | Auto-created by `_ensure_database_property()` |
| Project | select | Auto-created; e.g. "Jarvis", "Math homework" |

### Session Debriefs DB
| Property | Type | Notes |
|---|---|---|
| Name | title | Format: `[Project] Session Debrief — YYYY-MM-DD HH:MM` |
| Date | date | |
| Type | select | Always "session_debrief" |
| Status | select | Auto-created; always "completed" |
| Project | select | Auto-created; e.g. "Jarvis", "Math homework" |

All databases must have the Jarvis1.0 integration connected (database `...` menu > Connections). Missing properties (Date, Project, Status) are auto-created via the Notion API on first use.

## Current Status (updated 2026-04-06)

### Working
- morning_briefing.py — fully tested, redesigned Notion page (callout summary, formatted calendar schedule, emoji headings, dividers), auto-opens in browser on TTY / notification only on launchd
- **Summary voice spec externalized (2026-04-05)** — voice rules now live in [agent/personalhq/summary_voice.md](agent/personalhq/summary_voice.md) as prose + annotated examples + anti-examples, loaded at runtime and injected into `BRIEFING_SYSTEM_PROMPT`. Edit that file (not the Python prompt) when tuning voice. Structural/parsing requirements (required headings, `[OVERDUE]`/`[TODAY]` tag preservation) stay in `BRIEFING_SYSTEM_PROMPT` in [morning_briefing.py](agent/personalhq/morning_briefing.py) next to the parser. Approved example: *"Good morning, Amit. Mild and partly cloudy out there with a light breeze — you've got a solid day lined up with deep work, a session at Machon Weizmann..."*
- **Weather integration (2026-04-05)** — Open-Meteo (no API key). `WEATHER_LOCATION` env var (use spaces not hyphens). Returns feel phrases (sky+temp+wind) with NO numeric temperatures
- **Task tagging (2026-04-05)** — tasks pre-tagged `[OVERDUE]`/`[TODAY]` in the prompt input; overdue strictly means `due.date < today`
- **Garmin integration implemented (2026-04-06)** — `garmin_helper.py` written, wired into `morning_briefing.py`, Notion `_build_briefing_blocks()` updated for Body section. All code verified (syntax OK). End-to-end test passed WITHOUT Garmin (graceful degradation confirmed — briefing runs fine, Body section simply absent). launchd job loaded and confirmed registered (`com.jarvis.briefing`, fires at 5:30 AM / on wake). `run_briefing.sh` wrapper with 60-min dedup lock in place.
- **Garmin auth NOT yet validated (2026-04-06)** — Hit Garmin's Cloudflare 429 rate limit during initial auth testing (~8 attempts across test runs). Code is correct; needs one successful auth to cache tokens in `agent/garmin_tokens/`. Rate limit clears in ~30-60 min. **Next step: run `python personalhq/garmin_helper.py` from terminal once rate limit is clear (wait at least 30 min since last attempt). If it prompts for MFA code, enter it — tokens cache and this never happens again.**
- session_start.py — writes to Notion Session Start DB with project filtering, auto-opens in browser
- session_debrief.py — writes to Notion with project tagging, Claude synthesizes user notes + GitHub commit details into insightful debrief
- Project-based context switching — debrief tagged with project name, session start filters by project to pull relevant history
- Google OAuth — token.json saved, no browser popup needed on subsequent runs
- All APIs authenticated and confirmed working (Claude, Notion, Gmail, Calendar, Todoist, GitHub, Open-Meteo)

### Not Yet Done
- **Garmin auth first-time validation** — run `python personalhq/garmin_helper.py` from terminal (at least 30-60 min after last attempt, ~10:45 AM on 2026-04-06). Enter MFA code if prompted. Then run full briefing to verify Body section in Notion.
- Automate session debrief so it doesn't require running from terminal
- No unit tests yet
- Gmail query tuning — returned 0 unread during testing (verify on a day with actual unread mail)
- Claude occasionally slips corporate filler words despite voice spec — user has tolerated it but keep an eye on it

### Iteration workflow
User reviews briefings via Notion page comments. Fetch via `notion-get-comments` MCP tool after each run and iterate the prompt based on feedback.

## Quick Verification
```bash
# Test that all APIs are connected (from agent/ directory):
python -c "from dotenv import load_dotenv; load_dotenv('.env'); import os; print('Anthropic:', 'OK' if os.environ.get('ANTHROPIC_API_KEY') else 'MISSING'); print('Notion:', 'OK' if os.environ.get('NOTION_TOKEN') else 'MISSING'); print('Todoist:', 'OK' if os.environ.get('TODOIST_API_TOKEN') else 'MISSING'); print('GitHub:', 'OK' if os.environ.get('GITHUB_TOKEN') else 'MISSING')"

# Full morning briefing test:
cd agent && python personalhq/morning_briefing.py

# Session start test:
cd agent && python workhorse/session_start.py
```

## Briefing Page Layout
The morning briefing Notion page uses a structured layout built by `_build_briefing_blocks()`:
1. **☀️ Summary callout** (yellow) — greeting + one flowing sentence about the day
2. **💪 Body** (if Garmin data available) — sleep, HRV, resting HR interpreted with training recommendations
3. **📅 Today's Schedule** — formatted event list with times (e.g. `9:00 AM – 10:00 AM — Meeting`)
4. **📧 Email Highlights** — bullet points of actionable emails
5. **✅ Today's Tasks** — today's + overdue Todoist tasks only

The session start page uses `_build_session_start_blocks()`:
1. **🔄 Recap callout** (blue) — last session summary
2. **🐙 GitHub Activity** — recent commits, PRs, issues
3. **🎯 Suggested Priorities** — what to focus on

## Known Issues / Gotchas
- PC has Python 3.12 AND 3.13 installed. Use `python -m pip install` (not bare `pip`) to target the right version.
- `file_cache` warnings from `googleapiclient.discovery_cache` are harmless — ignore them.
- Todoist `task.due.date` is a `datetime.date` object, not a string. Must use `str()` for comparison.
- GitHub repo `AGrupper/Jarvis1.0` — first commit pushed 2026-04-04. GitHub fetch errors should no longer occur.
