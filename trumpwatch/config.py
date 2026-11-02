import os
from dotenv import load_dotenv
load_dotenv()

def boolean(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ('1','true','yes','on')

def int_list(name):
    return {int(v.strip()) for v in os.getenv(name,'').split(',') if v.strip().isdigit()}

class C:
    TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    ADMINS=int_list('TELEGRAM_ADMIN_IDS')
    CHAT=os.getenv('TELEGRAM_CHAT_ID','').strip()
    GROQ_KEY=os.getenv('GROQ_API_KEY','').strip()
    GROQ_MODEL=os.getenv('GROQ_MODEL','llama-3.3-70b-versatile').strip()
    AI=boolean('AI_ANALYSIS_ENABLED',True)
    POLL=max(30,int(os.getenv('POLL_INTERVAL_SECONDS','30')))
    ALERT_MIN_SCORE=max(1,min(10,int(os.getenv('ALERT_MIN_SCORE','7'))))
    NEWS_MAX_AGE_HOURS=max(1,int(os.getenv('NEWS_MAX_AGE_HOURS','24')))
    FUTURE_SKEW_MINUTES=max(0,int(os.getenv('FUTURE_SKEW_MINUTES','10')))
    TS=boolean('TRUTHSOCIAL_ENABLED',False)
    TS_URL=os.getenv('TRUTHSOCIAL_PROFILE_URL','https://truthsocial.com/@realDonaldTrump')
    TS_RSS=os.getenv('TRUTHSOCIAL_RSS_URL','').strip()
    DB=os.getenv('DATABASE_PATH','./data/trumpwatch.sqlite3')
    LOG=os.getenv('LOG_LEVEL','INFO').upper()
    LOW=boolean('SEND_LOW_PRIORITY',False)
    PREALERT_HOURS=max(1,int(os.getenv('PREALERT_HOURS','4')))
    SECOND_PREALERT_HOURS=max(0,int(os.getenv('SECOND_PREALERT_HOURS','1')))
    SCHEDULE_POLL_SECONDS=max(60,int(os.getenv('SCHEDULE_POLL_SECONDS','900')))
    # Optional public ICS calendar URL for events. Use an official/licensed source.
    ICS_URL=os.getenv('ECONOMIC_CALENDAR_ICS_URL','').strip()
    FF_CALENDAR_URL=os.getenv(
        'FOREX_FACTORY_CALENDAR_URL',
        'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
    ).strip()
    DISPLAY_TIMEZONE=os.getenv('DISPLAY_TIMEZONE','Asia/Kolkata').strip() or 'Asia/Kolkata'
