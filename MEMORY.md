# MEMORY — Jarvis Collaboration Preferences

This file holds Jarvis-specific collaboration context that Claude should load every session. It lives in the repo (not in Claude Code's user-wide memory) so it travels across machines — open this project on the MacBook and the same context loads.

User-wide preferences (secrets handling, commit conventions, machine setup) live in Claude Code's auto-memory system and apply to all projects. Only Jarvis-specific guidance belongs here.

---

## Project overview

Jarvis 1.0 is a personal AI agent system spanning two machines (MacBook + PC) with Notion as shared brain. Automated daily briefings + structured work session tracking across devices.

**How to apply:** All code lives in `agent/`. Maintain the graceful degradation pattern — data fetch failures should not kill the pipeline. Notion SDK v3 has workarounds: use `_query_database()` and `_ensure_database_property()` in `notion_helper.py`, not the SDK's built-in methods. (Full architectural detail is in CLAUDE.md — this entry exists so future sessions know the *shape* of the project at a glance.)

---

## Daily briefing design & workflow

**Voice spec canonical location:** [agent/personalhq/summary_voice.md](agent/personalhq/summary_voice.md). Edit there when tuning the summary's voice/tone. This entry keeps only non-voice guidance (layout, task behavior, weather infra, iteration workflow).

### Page layout
Layout: Summary callout → Body (Garmin readiness, only if data available) → Calendar (formatted event list) → Email Highlights → Today's Tasks. NO "Priority Actions" or "Quick Notes" sections.

**Why:** User finds those sections redundant — a good summary already covers both. Prefers concise, at-a-glance pages. Body section added 2026-04-06 for Garmin sleep/HRV/readiness interpretation.

**How to apply:** Don't re-add cut sections even if they'd seem useful. The briefing is tuned for glanceability, not completeness. Body section is conditional — only present when Garmin data is available (graceful degradation if Garmin is offline).

### Today's Tasks section
- Only today's + overdue Todoist tasks (never all active).
- Tasks are pre-tagged `[OVERDUE]` or `[TODAY]` in the prompt input — Claude must preserve those tags verbatim and not add `[OVERDUE]` to `[TODAY]` items.
- Overdue = `task.due.date < today` strictly (carried over from prior day).

**Why:** User's Todoist dates mean "planning to work on today," not hard deadlines. Showing all active tasks would flood the page; only today+overdue keeps it actionable.

### Weather system
- Uses Open-Meteo (no API key) via `fetch_weather()` in `morning_briefing.py`.
- `WEATHER_LOCATION` in .env (must use spaces not hyphens — "Tel Aviv" not "Tel-Aviv", geocoder rejects hyphens).
- Returns `{location, feel, wind}` — `feel` is sky+temp phrase from `_sky_and_temp()`, `wind` from `_wind_feel()` or None.
- User wants descriptive feel, not short asides — give weather enough words to paint a picture.

**How to apply:** When debugging weather, check geocoder hyphen rule first. When adding weather-dependent phrasings, keep them prose-y.

### Iteration loop
User reviews briefings via Notion page comments. Fetch them via `notion-get-comments` MCP tool. He's direct and will tell you when voice is off. Iterate the voice spec ([summary_voice.md](agent/personalhq/summary_voice.md)); re-run the briefing; check the new Notion page for comments.

**How to apply:** After running the briefing, proactively offer to fetch Notion comments from the last page. When voice feedback comes in, update `summary_voice.md` (add to examples, anti-examples, or iteration log) — don't edit the Python prompt.
