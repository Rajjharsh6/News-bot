# TrumpWatch Pro v2

Telegram bot for fresh Trump/White House alerts, US macro/geopolitical news, and upcoming scheduled event reminders.

## New in v2
- News freshness cutoff: 24 hours by default (`NEWS_MAX_AGE_HOURS`).
- RSS entries without a reliable published timestamp are stored but not treated as breaking/new. Fresh `/latest` filters by publication time, not database insertion time.
- `/latest`, `/news`, `/trump`, `/upcoming`, `/today`, `/explain`, `/status`, `/sources`, `/settings`, `/pause`, `/resume`, `/test`.
- Upcoming BLS selected releases plus official Federal Reserve FOMC decision calendar.
- Forex Factory weekly economic calendar feed (public JSON endpoint; no login or scraping of its calendar page).
- Optional external ICS calendar via `ECONOMIC_CALENDAR_ICS_URL`.
- High-importance event reminders at about 4 hours and 1 hour before, plus event-time alert.
- Source timestamp and original URL included in alert.
- SQLite deduplication and first-run history suppression.

## Setup
1. Create Telegram bot using BotFather.
2. Copy `.env.example` to `.env`.
3. Fill `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`, `TELEGRAM_CHAT_ID`, and optional `GROQ_API_KEY` from GroqCloud.
4. Install: `pip install -r requirements.txt`.
5. Start: `python -m trumpwatch`.
6. Telegram: send `/start`, then `/test`.

## Commands
- `/latest`: last 10 stored items from freshness window
- `/news`: items published within the last 24 hours
- `/trump`: Trump/White House items from the last 24 hours
- `/upcoming`: future scheduled events
- `/today`: events within the next 24 hours
- `/explain`: use Groq to explain the latest timestamped news item
- `/explain upcoming`: use Groq to explain the next scheduled event
- `/status`: source health, poll interval, alert window
- `/sources`: source URLs
- `/settings`: current config
- `/pause`, `/resume`: pause/resume alerts for this chat

## Alert and AI settings
- Groq AI analysis is optional. Set `GROQ_API_KEY` and `GROQ_MODEL`; the default model is `llama-3.3-70b-versatile`. Remove the old Gemini variables from your private `.env`.
- `/explain` responses are brief Hinglish (Hindi in Latin script), limited to 3 short bullets.
- News sources are polled every 30 seconds by default (`POLL_INTERVAL_SECONDS`; minimum 30 seconds). Calendar refresh remains separate at `SCHEDULE_POLL_SECONDS` (15 minutes by default).
- Forex Factory calendar alerts and `/upcoming`/`/today` output include USD events only. Scheduled events are sent in a compact table formatted for Telegram.
- Alerts default to importance score 7/10 or higher (`ALERT_MIN_SCORE`). Set `SEND_LOW_PRIORITY=true` to receive all fresh items.
- News headlines are deduplicated across sources for 24 hours. Telegram delivery retries failed message chunks up to three times.
- Display times default to India Standard Time (`Asia/Kolkata`, UTC+05:30) in 12-hour format. `DISPLAY_TIMEZONE` controls displayed times and floating ICS times; ICS events with `TZID` are converted to the configured display timezone.

## Important limitations
- RSS source timestamps are not perfectly consistent; stale/undated RSS items are deliberately not sent as fresh alerts.
- Truth Social integration first tries unauthenticated public account/status endpoints for post timestamps, then falls back to public profile HTML. Either may be blocked or change. If `/status` reports HTTP 403, configure an authorized, compliant timestamped feed in `TRUTHSOCIAL_RSS_URL`; no access-control bypass is attempted. Undated HTML-scraped posts are not sent as real-time alerts.
- BLS schedule scraping may be affected by site layout changes. An ICS calendar feed is recommended for broader economic event coverage. This version uses BLS selected releases as its built-in calendar source.
- Forex Factory events come from `https://nfs.faireconomy.media/ff_calendar_thisweek.json`. It is a public, undocumented feed and may change or become unavailable; the bot reports sync errors in `/status`. Configure `FOREX_FACTORY_CALENDAR_URL` to override it, or leave it blank to disable. Calendar sync runs every `SCHEDULE_POLL_SECONDS` (15 minutes by default). High-impact events use the existing `/upcoming`, `/today`, and reminder features.
- Reminder timing depends on the host staying awake and source/calendar schedule accuracy. Use a persistent worker, not a sleeping serverless service.
- Groq output is AI-generated context and may be inaccurate. This is news monitoring, not investment advice or a trading signal.
