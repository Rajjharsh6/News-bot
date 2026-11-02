import hashlib, json, logging, re, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from bs4 import BeautifulSoup
from .config import C

# BLS calendar is authoritative for selected US labor/inflation releases.
BLS_SCHEDULE='https://www.bls.gov/schedule/2026/11_sched_list.htm'
HIGH_IMPACT_WORDS=('employment situation','consumer price index','producer price index','jolts','fomc','federal funds','gdp','pce','personal income and outlays','retail sales','nonfarm payroll','jobless claims')
FOREX_FACTORY_URL='https://nfs.faireconomy.media/ff_calendar_thisweek.json'
log=logging.getLogger(__name__)
def importance(title):
    t=title.lower()
    return 10 if any(x in t for x in HIGH_IMPACT_WORDS) else 6

def parse_ics_datetime(value,timezone_name=None):
    value=value.strip()
    if value.endswith('Z'):
        return datetime.strptime(value,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    if 'T' not in value:
        dt=datetime.strptime(value,'%Y%m%d')
    else:
        try:
            dt=datetime.strptime(value,'%Y%m%dT%H%M%S')
        except ValueError:
            dt=datetime.strptime(value,'%Y%m%dT%H%M')
    return dt.replace(tzinfo=ZoneInfo(timezone_name or C.DISPLAY_TIMEZONE))

async def fetch_bls_calendar(client):
    # The BLS URL changes by month/year. This endpoint intentionally stays
    # simple; operators can also provide an ICS calendar URL in environment.
    now=datetime.now(timezone.utc)
    urls=[f'https://www.bls.gov/schedule/{now.year}/{now.month:02d}_sched_list.htm']
    if now.month==12: urls.append(f'https://www.bls.gov/schedule/{now.year+1}/01_sched_list.htm')
    else: urls.append(f'https://www.bls.gov/schedule/{now.year}/{now.month+1:02d}_sched_list.htm')
    results=[]
    for url in urls:
        try:
            r=await client.get(url); r.raise_for_status()
            soup=BeautifulSoup(r.text,'html.parser')
            text=soup.get_text(' ',strip=True)
            # Example calendar line: Tuesday, November 3, 2026 10:00 AM JOLTS...
            pattern=r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(.+?)(?=(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}|NOTE:|$)'
            for m in re.finditer(pattern,text):
                date_s,time_s,title=m.group(2),m.group(3),m.group(4).strip()
                try:
                    dt=datetime.strptime(date_s+' '+time_s,'%B %d, %Y %I:%M %p')
                    # BLS calendar timestamps are US Eastern. Handle DST by using zoneinfo.
                    from zoneinfo import ZoneInfo
                    dt=dt.replace(tzinfo=ZoneInfo('America/New_York'))
                    ts=dt.timestamp()
                except Exception: continue
                if ts>time.time():
                    title=re.sub(r'\s+',' ',title)[:200]
                    ident=hashlib.sha256((url+date_s+time_s+title).encode()).hexdigest()
                    results.append({'id':ident,'title':title,'event_time':ts,'source':'BLS official schedule','url':url,'importance':importance(title)})
        except Exception:
            continue
    return results
async def fetch_ics(client,url):
    if not url: return []
    r=await client.get(url); r.raise_for_status()
    data=r.text
    lines=data.replace('\r\n','\n').replace('\r','\n').split('\n')
    unfolded=[]
    for line in lines:
        if line.startswith((' ','\\t')) and unfolded: unfolded[-1]+=line[1:]
        else: unfolded.append(line)
    events=[]; current={}
    for line in unfolded:
        if line=='BEGIN:VEVENT': current={}
        elif line=='END:VEVENT':
            start_line=next((key+':'+value for key,value in current.items() if key.startswith('DTSTART')), '')
            try:
                if not start_line:
                    raise ValueError('Missing DTSTART property')
                property_name,value=start_line.split(':',1)
                params={}
                for param in property_name.split(';')[1:]:
                    if '=' in param:
                        key,param_value=param.split('=',1)
                        params[key.upper()]=param_value.strip('"')
                dt=parse_ics_datetime(value,params.get('TZID'))
                ts=dt.timestamp()
                if ts>time.time():
                    title=current.get('SUMMARY','Scheduled event')
                    title=re.sub(r'\\([nN,;\\])',lambda m:{'n':'\n','N':'\n',',':',',';':';','\\':'\\'}[m.group(1)],title)
                    ident=hashlib.sha256((start_line+title).encode()).hexdigest()
                    events.append({'id':ident,'title':title,'event_time':ts,'source':'Calendar ICS','url':url,'importance':importance(title),'content':''})
            except (ValueError,ZoneInfoNotFoundError) as exc:
                log.warning('Skipping ICS event with invalid start time: %s',exc)
        elif ':' in line:
            key,val=line.split(':',1); current[key]=val
    return events

def parse_forex_factory_events(payload,now_epoch=None):
    entries=json.loads(payload)
    if not isinstance(entries,list):
        raise ValueError('Forex Factory calendar response must be a JSON array.')
    now=time.time() if now_epoch is None else now_epoch
    impact_scores={'high':10,'medium':8,'low':5,'holiday':3}
    events=[]
    for item in entries:
        if not isinstance(item,dict):
            continue
        title=re.sub(r'\s+',' ',str(item.get('title') or '').strip())
        country=re.sub(r'\s+',' ',str(item.get('country') or '').strip()).upper()
        if country!='USD':
            continue
        date=str(item.get('date') or '').strip()
        if not title or not date:
            continue
        try:
            event_time=datetime.fromisoformat(date.replace('Z','+00:00'))
            if event_time.tzinfo is None:
                continue
            ts=event_time.timestamp()
        except ValueError:
            continue
        if ts<=now:
            continue
        impact=re.sub(r'\s+',' ',str(item.get('impact') or '').strip())
        impact_key=impact.lower()
        label=f'{country}: {title}' if country else title
        if impact:
            label+=f' ({impact} impact)'
        details=[]
        for key in ('actual','forecast','previous'):
            value=str(item.get(key) or '').strip()
            if value:
                details.append(f'{key.title()}: {value}')
        identity='|'.join((date,country,title))
        events.append({
            'id':hashlib.sha256(identity.encode('utf-8','ignore')).hexdigest(),
            'title':label[:250],
            'event_time':ts,
            'source':'Forex Factory economic calendar',
            'url':'https://www.forexfactory.com/calendar',
            'importance':impact_scores.get(impact_key,3),
            'content':'; '.join(details),
        })
    return events

async def fetch_forex_factory_calendar(client,url=FOREX_FACTORY_URL):
    if not url:
        return []
    response=await client.get(url)
    response.raise_for_status()
    return parse_forex_factory_events(response.text)
async def fetch_fomc_calendar(client):
    """Parse future FOMC statement dates from the Fed's official calendar page.
    Statement time is conventionally 2:00 PM Eastern on the final meeting day;
    schedule changes are possible, so link the official calendar in alerts.
    """
    url='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
    try:
        r=await client.get(url); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        text=soup.get_text(' ',strip=True)
        from zoneinfo import ZoneInfo
        current_year=datetime.now(timezone.utc).year
        events=[]
        # Page headings look like "2026 FOMC Meetings"; date ranges appear beneath.
        year_pat=r'(20\\d{2})\\s+FOMC Meetings'
        year_matches=list(re.finditer(year_pat,text))
        month_names='January February March April May June July August September October November December'.split()
        for i,ym in enumerate(year_matches):
            year=int(ym.group(1))
            if year<current_year: continue
            end=year_matches[i+1].start() if i+1<len(year_matches) else len(text)
            block=text[ym.end():end]
            # month followed by meeting day range e.g. December 8-9 or March 17-18*
            for m in re.finditer(r'('+'|'.join(month_names)+r')\\s+(\\d{1,2})\\s*[-–]\\s*(\\d{1,2})\\*?',block):
                month,day1,day2=m.group(1),int(m.group(2)),int(m.group(3))
                try:
                    dt=datetime.strptime(f'{year} {month} {day2} 14:00','%Y %B %d %H:%M').replace(tzinfo=ZoneInfo('America/New_York'))
                    ts=dt.timestamp()
                    if ts<=time.time(): continue
                    title=f'FOMC rate decision / statement (meeting {month} {day1}-{day2}, {year})'
                    ident=hashlib.sha256((title+url).encode()).hexdigest()
                    events.append({'id':ident,'title':title,'event_time':ts,'source':'Federal Reserve official FOMC calendar','url':url,'importance':10})
                except Exception: pass
        return events
    except Exception:
        return []

async def update_calendar(client,db):
    events=await fetch_bls_calendar(client)
    events+=await fetch_fomc_calendar(client)
    events+=await fetch_ics(client,C.ICS_URL)
    for ev in events: db.upsert_schedule(ev)
    if C.FF_CALENDAR_URL:
        source='Forex Factory economic calendar'
        try:
            ff_events=await fetch_forex_factory_calendar(client,C.FF_CALENDAR_URL)
            for ev in ff_events: db.upsert_schedule(ev)
            db.health(source)
            events+=ff_events
        except Exception as exc:
            db.health(source,exc)
            log.warning('Forex Factory calendar sync failed: %s',exc)
    return len(events)
