import asyncio, logging, re, time, html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from .config import C
from .db import DB
from .sources import FEEDS, read_feed, read_truthsocial
from .calendar import update_calendar
from .analysis import Analyzer
from .formatting import render, split

logging.basicConfig(level=getattr(logging,C.LOG,logging.INFO),format='%(asctime)s %(levelname)s %(name)s %(message)s')
log=logging.getLogger('trumpwatch'); router=Router()
db=None; bot=None; analyzer=None; started=time.time()
display_tz=ZoneInfo(C.DISPLAY_TIMEZONE)
def is_admin(m): return not C.ADMINS or (m.from_user and m.from_user.id in C.ADMINS)
def targets(): return [int(C.CHAT)] if C.CHAT else db.users()
def format_rows(rows):
    out=[]
    for src,title,url,pub,cat,score,created in rows:
        stamp=pub or datetime.fromtimestamp(created,display_tz).strftime('%Y-%m-%d %I:%M %p %Z')
        out.append(f'<b>{html.escape(src)} | {html.escape(cat)} | {score}/10</b>\n{html.escape(title)}\n{html.escape(stamp)}\n{html.escape(url or "")}')
    return '\n\n'.join(out)
def format_calendar_table(rows,heading):
    headers=('DATE / TIME','IMPACT','USD EVENT')
    widths=(22,8,54)
    lines=[
        f'{headers[0]:<{widths[0]}} {headers[1]:<{widths[1]}} {headers[2]}',
        f'{"-"*widths[0]} {"-"*widths[1]} {"-"*widths[2]}',
    ]
    for _,title,ts,_,_,score in rows:
        event_time=datetime.fromtimestamp(ts,display_tz).strftime('%a %d %b %I:%M %p %Z')
        impact='HIGH' if score>=9 else 'MEDIUM' if score>=8 else 'LOW'
        event_title=' '.join(title.split())
        event_title=event_title.removeprefix('USD: ')
        event_title=re.sub(r' \((?:high|medium|low|holiday) impact\)$','',event_title,flags=re.IGNORECASE)
        if len(event_title)>widths[2]:
            event_title=event_title[:widths[2]-3]+'...'
        lines.append(f'{event_time:<{widths[0]}} {impact:<{widths[1]}} {event_title}')
    return f'<b>{html.escape(heading)}</b>\n<pre>{html.escape(chr(10).join(lines))}</pre>'
async def send_text(chat,text):
    for chunk in split(text):
        for attempt in range(3):
            try:
                await bot.send_message(chat,chunk,parse_mode=ParseMode.HTML,disable_web_page_preview=True)
                break
            except Exception:
                if attempt==2:
                    raise
                await asyncio.sleep(2**attempt)
@router.message(Command('start'))
async def start(m:Message):
    db.add_user(m.chat.id)
    await m.answer('TrumpWatch Pro is running. Registered this chat. Try /latest, /news, /trump, /upcoming, /today, /explain, /status.')
@router.message(Command('help'))
async def help_cmd(m:Message):
    await m.answer('/start register chat\n/latest last 10 recent items\n/news last 24h US news\n/trump last 24h Trump/White House items\n/upcoming scheduled events\n/today today\'s events\n/explain [last|upcoming] explain latest news or next event\n/status source health\n/sources monitored sources\n/settings config\n/test test delivery\n/pause pause alerts\n/resume resume alerts')
@router.message(Command('status'))
async def status(m:Message):
    rows=db.health_rows(); out=[f'Uptime: {int(time.time()-started)} sec',f'Polling: {C.POLL}s',f'Minimum alert score: {C.ALERT_MIN_SCORE}/10',f'Timezone: {C.DISPLAY_TIMEZONE}',f'News max age: {C.NEWS_MAX_AGE_HOURS}h',f'Pre-alerts: {C.PREALERT_HOURS}h and {C.SECOND_PREALERT_HOURS}h',f'Groq configured: {bool(C.GROQ_KEY and C.AI)}','']
    for source,ok,error in rows:
        out.append(('⚠️ '+source+': '+str(error)[:180]) if error else ('✅ '+source+': '+datetime.fromtimestamp(ok,display_tz).strftime('%Y-%m-%d %I:%M %p %Z') if ok else '… '+source+': waiting'))
    await m.answer('\n'.join(out)[:3900])
@router.message(Command('latest'))
async def latest(m:Message):
    rows=db.latest(10,since_epoch=time.time()-C.NEWS_MAX_AGE_HOURS*3600)
    if not rows:
        return await m.answer('No fresh items found in the configured last 24 hours. Check /status for source errors.')
    await send_text(m.chat.id,format_rows(rows))
@router.message(Command('news'))
async def news(m:Message):
    rows=db.latest(20,since_epoch=time.time()-24*3600)
    if not rows:
        return await m.answer('No news from the last 24 hours is stored yet.')
    await send_text(m.chat.id,format_rows(rows))
@router.message(Command('trump'))
async def trump(m:Message):
    rows=db.latest(20,since_epoch=time.time()-24*3600,category='trump')
    if not rows:
        return await m.answer('No Trump/White House items from the last 24 hours.')
    await send_text(m.chat.id,format_rows(rows))
@router.message(Command('upcoming'))
async def upcoming(m:Message):
    rows=db.upcoming(time.time(),15)
    if not rows: return await m.answer('No future scheduled events loaded. Calendar source may be unavailable; check /status.')
    await send_text(m.chat.id,format_calendar_table(rows,'Upcoming USD economic events'))
@router.message(Command('today'))
async def today(m:Message):
    now=datetime.now(display_tz); end=now+timedelta(days=1)
    rows=[r for r in db.upcoming(now.timestamp(),30) if r[2]<end.timestamp()]
    if not rows: return await m.answer('No scheduled items in the next 24 hours.')
    await send_text(m.chat.id,format_calendar_table(rows,'USD events in the next 24 hours'))
@router.message(Command('explain'))
async def explain(m:Message):
    argument=(m.text or '').partition(' ')[2].strip().lower()
    if argument in ('','last','news'):
        row=db.latest_event()
        if not row:
            return await m.answer('No timestamped news is stored yet to explain.')
        source,title,url,published,content,category,score,published_epoch=row
        event={
            'source':source,
            'title':title,
            'url':url or '',
            'published':published or datetime.fromtimestamp(published_epoch,display_tz).strftime('%Y-%m-%d %I:%M %p %Z'),
            'content':content or '',
            'category':category,
            'score':score,
        }
        heading='Latest news'
    elif argument in ('upcoming','event'):
        row=db.next_scheduled_event(time.time())
        if not row:
            return await m.answer('No upcoming scheduled event is available to explain.')
        title,event_time,source,url,score,content=row
        event={
            'source':source,
            'title':title,
            'url':url or '',
            'published':datetime.fromtimestamp(event_time,display_tz).strftime('%Y-%m-%d %I:%M %p %Z'),
            'content':content or '',
            'category':'economic calendar',
            'score':score,
        }
        heading='Next scheduled event'
    else:
        return await m.answer('Usage: /explain for latest news, or /explain upcoming for the next event.')
    if not analyzer or not C.GROQ_KEY or not C.AI:
        return await m.answer('Groq AI analysis is not enabled. Configure GROQ_API_KEY and AI_ANALYSIS_ENABLED=true.')
    await m.answer(f'<b>{heading}: {html.escape(event["title"])}</b>\nAnalyzing with Groq...')
    explanation=await analyzer.analyze(event)
    if not explanation:
        detail=analyzer.last_error or 'No explanation was returned.'
        return await m.answer(f'Could not generate an explanation: {html.escape(detail)}')
    await send_text(
        m.chat.id,
        '<b>AI explanation (informational, not a trading signal)</b>\n'+html.escape(explanation[:3500]),
    )
@router.message(Command('sources'))
async def sources(m:Message):
    lines=[f'{name}: {url}' for name,url,cat in FEEDS]
    lines.append('Truth Social: '+(C.TS_URL+' (best effort)' if C.TS else 'disabled'))
    lines.append('Forex Factory calendar: '+(C.FF_CALENDAR_URL or 'disabled'))
    await m.answer('\n'.join(lines)[:3900],disable_web_page_preview=True)
@router.message(Command('settings'))
async def settings(m:Message):
    await m.answer(f'AI: {C.AI}\nGroq configured: {bool(C.GROQ_KEY)}\nTruth Social: {C.TS}\nForex Factory calendar: {bool(C.FF_CALENDAR_URL)}\nPolling: {C.POLL}s\nMinimum alert score: {C.ALERT_MIN_SCORE}/10\nTimezone: {C.DISPLAY_TIMEZONE}\nFreshness cutoff: {C.NEWS_MAX_AGE_HOURS}h\nPre-alert: {C.PREALERT_HOURS}h')
@router.message(Command('pause'))
async def pause(m:Message):
    if not is_admin(m): return await m.answer('Admin only.')
    db.pause(m.chat.id); await m.answer('Alerts paused.')
@router.message(Command('resume'))
async def resume(m:Message):
    if not is_admin(m): return await m.answer('Admin only.')
    db.resume(m.chat.id); await m.answer('Alerts resumed.')
@router.message(Command('test'))
async def test(m:Message):
    if not is_admin(m): return await m.answer('Admin only.')
    await m.answer('✅ Test notification delivered.')
async def deliver(event):
    original=render(event,'')
    for chat in targets():
        try: await send_text(chat,original)
        except Exception as exc: log.warning('Telegram send failed: %s',exc)
    if analyzer:
        try: ai=await analyzer.analyze(event)
        except Exception as exc: log.warning('Groq analysis failed: %s',exc); ai=''
        if ai:
            msg='<b>Groq context (AI-generated, not a trading signal)</b>\n'+html.escape(ai[:3000])
            for chat in targets():
                try: await send_text(chat,msg)
                except Exception as exc: log.warning('AI send failed: %s',exc)
def fresh(event):
    ts=event.get('published_epoch')
    if ts is None: return False
    now=time.time()
    return ts<=now+ C.FUTURE_SKEW_MINUTES*60 and ts>=now-C.NEWS_MAX_AGE_HOURS*3600
def alertable(event):
    return fresh(event) and (C.LOW or event['score']>=C.ALERT_MIN_SCORE)
async def monitor(client):
    while True:
        cycle=time.monotonic()
        for name,url,cat in FEEDS:
            try:
                events=await read_feed(client,name,url,cat); db.health(name)
                first=not db.initialized(name)
                for event in events:
                    if db.seen(event['id']): continue
                    # Always store, but only alert if the publication timestamp is fresh.
                    inserted=db.add(event)
                    if first: continue
                    if not inserted or not alertable(event): continue
                    if not db.claim_news_alert(event['title']): continue
                    await deliver(event)
                db.mark_initialized(name)
            except Exception as exc:
                db.health(name,exc); log.warning('Feed failure %s: %s',name,exc)
        if C.TS:
            try:
                events=await read_truthsocial(client,C.TS_URL,C.TS_RSS); db.health('Truth Social')
                first=not db.initialized('Truth Social')
                for event in events:
                    inserted=db.add(event)
                    if first or not inserted or not alertable(event): continue
                    if not db.claim_news_alert(event['title']): continue
                    await deliver(event)
                db.mark_initialized('Truth Social')
            except Exception as exc:
                db.health('Truth Social',exc); log.warning('Truth Social error: %s',exc)
        await asyncio.sleep(max(5,C.POLL-(time.monotonic()-cycle)))
async def calendar_loop(client):
    while True:
        try:
            n=await update_calendar(client,db)
            log.info('Calendar sync: %d scheduled events',n)
        except Exception as exc:
            db.health('Event calendar',exc); log.warning('Calendar sync error: %s',exc)
        await asyncio.sleep(C.SCHEDULE_POLL_SECONDS)
async def reminder_loop():
    while True:
        now=time.time()
        for event_id,title,ts,src,url,importance,r4,r1,revent in db.reminder_candidates(now):
            delta=ts-now
            msg=None; kind=None
            if not r4 and 3.9*3600<=delta<=4.1*3600 and importance>=8:
                msg=f'⏰ <b>HIGH-IMPORTANCE EVENT IN ~4 HOURS</b>\n{html.escape(title)}\nSource: {html.escape(src)}\nTime: {datetime.fromtimestamp(ts,display_tz).strftime("%Y-%m-%d %I:%M %p %Z")}\n{html.escape(url or "")}'
                kind='4'
            elif C.SECOND_PREALERT_HOURS and not r1 and 0.9*3600<=delta<=1.1*3600 and importance>=8:
                msg=f'🚨 <b>HIGH-IMPORTANCE EVENT IN ~1 HOUR</b>\n{html.escape(title)}\n{datetime.fromtimestamp(ts,display_tz).strftime("%Y-%m-%d %I:%M %p %Z")}\n{html.escape(url or "")}'
                kind='1'
            elif not revent and -120<=delta<=0 and importance>=8:
                msg=f'🔴 <b>EVENT TIME</b>\n{html.escape(title)}\n{html.escape(url or "")}'
                kind='event'
            if msg:
                for chat in targets():
                    try: await send_text(chat,msg)
                    except Exception as exc: log.warning('Reminder failed: %s',exc)
                db.mark_reminder(event_id,kind)
        await asyncio.sleep(30)
async def main():
    global db,bot,analyzer
    if not C.TOKEN: raise SystemExit('Missing TELEGRAM_BOT_TOKEN. Configure .env/host variables.')
    db=DB(C.DB); bot=Bot(C.TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp=Dispatcher(); dp.include_router(router)
    headers={'User-Agent':'TrumpWatchPro/2.0 (official RSS monitor)','Accept':'application/rss+xml,application/atom+xml,text/xml,text/html,*/*'}
    async with httpx.AsyncClient(headers=headers,timeout=25,follow_redirects=True) as client:
        analyzer=Analyzer(C.GROQ_KEY,C.GROQ_MODEL,C.AI,client)
        tasks=[asyncio.create_task(monitor(client)),asyncio.create_task(calendar_loop(client)),asyncio.create_task(reminder_loop()),asyncio.create_task(dp.start_polling(bot))]
        try: await asyncio.gather(*tasks)
        finally:
            for task in tasks: task.cancel()
            await bot.session.close()
