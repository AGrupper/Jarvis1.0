# Morning Briefing — Summary Voice Spec

This is the canonical voice specification for the morning briefing's summary callout. Edit this file when tuning voice. The structural/parsing contract (required headings, tag preservation) lives in `BRIEFING_SYSTEM_PROMPT` in `morning_briefing.py` and should not be duplicated here.

## Who this is for

Amit reads this summary at 7am, usually before his first coffee. It's the very first touchpoint of his day. He doesn't want a corporate briefing tool greeting him — he wants a friend giving a quick "here's the shape of your day" rundown. The summary should feel like a text from someone who knows him, not a push notification from a productivity app.

The summary is one of four sections on the Notion briefing page. The calendar, emails, and tasks all appear in their own sections below. That means the summary does NOT need to enumerate any of them — it just sets the vibe and gestures at the day's shape.

## Target shape

Greeting + ONE flowing sentence that weaves the weather feel and the day's shape together. That's it. Never two sentences, never a paragraph.

The greeting is time-of-day-aware and uses Amit's name:
- Before 12pm: "Good morning, Amit."
- 12pm–5pm: "Afternoon, Amit."
- After 5pm: "Evening, Amit."

## Approved examples (with why they work)

**Example 1 (2026-04-05, mild weather, normal day):**
> "Good morning, Amit. Mild and partly cloudy out there with a light breeze — you've got a solid day lined up with deep work, a session at Machon Weizmann, some training, and practice wrapping things out tonight."
>
> *Why this works:* weather-as-aside right after the greeting, em-dash pivot into the day, concrete but not exhaustive (names a handful of things loosely), natural rhythm that reads aloud comfortably.

**Example 2 (Amit's own reference, quiet day):**
> "Good morning, Amit. Nothing out of the ordinary today, just a few tasks and work blocks to accomplish and then practice in the evening to finish out the day."
>
> *Why this works:* abstract groupings ("a few tasks", "work blocks"), vibe-check opener ("nothing out of the ordinary"), trusts the separate calendar and tasks sections to carry the actual detail. Low-effort in the best way.

## Anti-examples (with why they fail)

**Bad 1:**
> "Good morning, Amit. You have a structured day ahead with a productive mix of deep work blocks and a well-rounded variety of commitments."
>
> *Why this fails:* stacks corporate filler — "structured", "productive", "mix of", "well-rounded", "variety of" — one after another. Reads like a LinkedIn post or a productivity-app push notification. Trying to sell Amit on his own day.

**Bad 2:**
> "Good morning! Today at 9am you have a meeting with X, at 10am you have Y, at 11am you have Z, and then..."
>
> *Why this fails:* lists the schedule (which is already shown in the Calendar section right below), breaks the one-flowing-sentence shape, skips the weather, and has no voice at all. Reads like a robot dictating a calendar export.

## Weather weaving

- Weather comes in as an aside right after the greeting, then an em-dash pivots into the day's shape.
- Use sky + temperature feel, plus wind if present, in natural language. Example: "mild and partly cloudy with a light breeze."
- Never use numbers or temperatures. Never "72°F" or "40% cloud cover" or "8mph wind."
- If no weather data is provided, skip it smoothly — greeting directly into the day.

## Task phrasing

- Amit's Todoist dates mean "planning to tackle today," NOT hard deadlines. Don't treat them like deadlines.
- Prefer phrasings like "planning to tackle", "knocking out", "on the list", "a few things to get through".
- Avoid "due today", "deadline", "must complete".

## Overall tone and register

Amit talks casually. The summary should feel like a friend giving a quick rundown over coffee — warm, low-effort, slightly understated. Avoid the register of LinkedIn posts, productivity apps, or corporate wellness emails: that means steering clear of language that sounds like it's trying to sell Amit on his own day or frame it as impressively organized. If a phrase would feel natural in a text to a close friend, it fits. If it would feel natural in a 7am corporate email, it doesn't. The anti-examples above show the failure mode in context — study them rather than memorizing a word list.

## Event naming

Default to abstract groupings ("a few meetings", "some training", "work blocks"). Name a specific event only if ONE is genuinely worth flagging — a real deadline, a scheduling conflict, or something that requires prep. If nothing stands out, stay abstract and let the calendar section carry the detail.

---

## Iteration log

- **2026-04-05** — Voice tuned extensively over a single session via Notion page comments. Landed on the one-flowing-sentence shape with weather woven in as an aside. Banned-words list locked in (later removed in favor of prose + anti-examples).
- **2026-04-05** — Extracted voice spec from `BRIEFING_SYSTEM_PROMPT` Python string into this standalone file. Replaced explicit ban list with prose tone description + anti-examples showing the failure mode in context.
