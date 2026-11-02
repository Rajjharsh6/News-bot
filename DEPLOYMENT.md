# Deployment

## Generic bot host
- Runtime: Python 3.12
- Install/build command: `pip install -r requirements.txt`
- Start command: `python -m trumpwatch`
- Add environment variables from `.env.example` in the host dashboard.
- For optional AI context, set `GROQ_API_KEY` and `GROQ_MODEL`; delete the obsolete Gemini variables from your private environment.
- The Forex Factory weekly calendar feed is enabled by default. Override `FOREX_FACTORY_CALENDAR_URL` with a supported feed URL or set it blank to disable.
- Select an always-on worker/service. A sleeping web service is unsuitable.
- Attach persistent storage and set `DATABASE_PATH` to the persistent volume.

## Docker
```bash
cp .env.example .env
# Fill .env values, then:
docker compose up -d --build
docker compose logs -f
```

## Secure setup
- Never commit `.env` or post tokens publicly.
- Set `TELEGRAM_ADMIN_IDS` to your Telegram numeric user ID.
- Use a private bot/group.
- Rotate exposed tokens.

## First-run behavior
Existing RSS entries are stored without alerts on first scan, to avoid dumping feed history. New posts are sent after the source is initialized. This means old articles aren't replayed.

## Troubleshooting
- `/status`: source health/errors.
- `/test`: Telegram connectivity.
- Check host logs for feed failures, HTTP status, rate limits, and parsing errors.
- Telegram sends retry up to three times. If delivery still fails, inspect host logs and check that `TELEGRAM_CHAT_ID` or `/start` registration is correct.
- Keep the database on persistent storage.

## Limitations
- RSS/public-web polling can lag source publication.
- Truth Social public endpoints and HTML may be blocked or change. If `/status` reports HTTP 403, use an authorized, compliant timestamped feed in `TRUTHSOCIAL_RSS_URL`. No access-control bypass is attempted.
- A bot cannot alert before a monitored source publishes content.
- AI market context from Groq is informational and not a trade recommendation.
