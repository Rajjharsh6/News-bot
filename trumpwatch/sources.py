import calendar, hashlib, re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import httpx
import feedparser
from bs4 import BeautifulSoup

FEEDS=[
 ('White House Briefings & Statements','https://www.whitehouse.gov/briefings-statements/feed/','trump'),
 ('White House News','https://www.whitehouse.gov/news/feed/','trump'),
 ('White House Presidential Actions','https://www.whitehouse.gov/presidential-actions/feed/','trump'),
 ('Federal Reserve','https://www.federalreserve.gov/feeds/press_all.xml','fed'),
 ('US Treasury','https://home.treasury.gov/news/press-releases/rss','treasury'),
 ('US State Department','https://www.state.gov/press-releases/feed/','geopolitics'),
 ('US Department of Defense','https://www.war.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945','geopolitics'),
 ('BLS Latest Economic Releases','https://www.bls.gov/feed/bls_latest.rss','macro'),
 ('BLS CPI','https://www.bls.gov/feed/cpi.rss','macro'),
 ('BLS Employment Situation','https://www.bls.gov/feed/empsit.rss','macro'),
 ('BLS PPI','https://www.bls.gov/feed/ppi.rss','macro'),
 ('BLS JOLTS','https://www.bls.gov/feed/jolts.rss','macro'),
 ('SEC Press Releases','https://www.sec.gov/news/pressreleases.rss','finance'),
 ('EIA','https://www.eia.gov/rss/press_rss.xml','energy'),
 ('Google News US macro','https://news.google.com/rss/search?q=US+economy+CPI+PCE+NFP+Federal+Reserve&hl=en-US&gl=US&ceid=US:en','macro'),
 ('Google News US geopolitics','https://news.google.com/rss/search?q=US+war+military+Iran+Israel+Ukraine+Russia+China+sanctions&hl=en-US&gl=US&ceid=US:en','geopolitics'),
 ('Google News US finance','https://news.google.com/rss/search?q=US+markets+Treasury+banking+tariffs+financial+crisis&hl=en-US&gl=US&ceid=US:en','finance'),
 ('Google News energy','https://news.google.com/rss/search?q=US+oil+energy+EIA+Strait+of+Hormuz&hl=en-US&gl=US&ceid=US:en','energy'),
]
IMPORTANT=['military action','attack','strike','war','emergency','tariff','sanction','fomc','rate decision','cpi','core pce','nonfarm payroll','nfp','executive order','ceasefire','debt ceiling','shutdown','invasion']
CATEGORY_TERMS={
 'trump':['trump','white house','president','truth social','executive order','tariff'],
 'fed':['federal reserve','fomc','powell','interest rate','monetary policy'],
 'macro':['cpi','pce','inflation','nonfarm','payroll','unemployment','gdp','retail sales','jobless claims','ism','pmi'],
 'geopolitics':['war','military','attack','strike','iran','israel','ukraine','russia','china','taiwan','nato','sanction','ceasefire','missile'],
 'finance':['market','bank','treasury','debt ceiling','shutdown','tariff','stock','bond','yield','financial'],
 'energy':['oil','energy','crude','gas','inventory','opec','hormuz']}
def clean(s):
    return re.sub(r'\\s+',' ',BeautifulSoup(str(s or ''),'html.parser').get_text(' ',strip=True)).strip()
def parsed_epoch(entry):
    for key in ('published_parsed','updated_parsed','created_parsed'):
        value=entry.get(key)
        if value:
            try: return calendar.timegm(value)
            except Exception: pass
    return None
def classify(title,content,default):
    text=(title+' '+content).lower()
    for cat,terms in CATEGORY_TERMS.items():
        if any(term in text for term in terms): return cat
    return default
def importance(title,content,category):
    text=(title+' '+content).lower(); score=7 if category in ('trump','fed') else 5
    for term in IMPORTANT:
        if term in text: score=max(score,9 if term in ('military action','attack','war','fomc','rate decision','cpi','nonfarm payroll','nfp','executive order') else 8)
    if 'breaking' in text or 'urgent' in text: score=max(score,9)
    return min(10,score)
def make_event(source,title,url,published,content,default,published_epoch=None):
    title=clean(title)[:450] or 'Untitled source item'; content=clean(content)[:10000]; url=(url or '').strip()
    key=url or source+title+str(published)+content
    ident=hashlib.sha256(key.encode('utf-8','ignore')).hexdigest()
    cat=classify(title,content,default)
    return {'id':ident,'source':source,'title':title,'url':url,'published':published or '', 'published_epoch':published_epoch,'content':content,'category':cat,'score':importance(title,content,cat)}
async def read_feed(client,name,url,category):
    resp=await client.get(url); resp.raise_for_status()
    parsed=feedparser.parse(resp.text)
    if parsed.bozo and not parsed.entries: raise RuntimeError('RSS parsing failed: '+str(parsed.bozo_exception))
    events=[]
    for ent in parsed.entries[:35]:
        events.append(make_event(name,ent.get('title',''),ent.get('link',''),ent.get('published',ent.get('updated','')),ent.get('summary',''),category,parsed_epoch(ent)))
    return events
async def read_truthsocial(client,profile_url,rss_url=''):
    if rss_url: return await read_feed(client,'Trump Truth Social',rss_url,'trump')
    profile=urlparse(profile_url)
    if profile.scheme!='https' or profile.hostname!='truthsocial.com':
        raise ValueError('Truth Social profile URL must use https://truthsocial.com.')
    account_name=profile.path.strip('/').removeprefix('@')
    if not account_name:
        raise ValueError('Truth Social profile URL must include an account name.')

    api_error=''
    try:
        account_response=await client.get(
            'https://truthsocial.com/api/v1/accounts/lookup',
            params={'acct':account_name},
            headers={'Accept':'application/json'},
        )
        account_response.raise_for_status()
        account=account_response.json()
        account_id=account.get('id') if isinstance(account,dict) else None
        if not account_id:
            raise RuntimeError('Public account lookup returned no account ID.')
        statuses_response=await client.get(
            f'https://truthsocial.com/api/v1/accounts/{account_id}/statuses',
            params={'limit':30,'exclude_reblogs':'true'},
            headers={'Accept':'application/json'},
        )
        statuses_response.raise_for_status()
        statuses=statuses_response.json()
        if not isinstance(statuses,list):
            raise RuntimeError('Public statuses endpoint returned an unexpected response.')
        events=[]
        for status in statuses:
            if not isinstance(status,dict):
                continue
            content=clean(status.get('content',''))
            if not content:
                continue
            published=status.get('created_at','')
            published_epoch=None
            if published:
                try:
                    published_datetime=datetime.fromisoformat(published.replace('Z','+00:00'))
                    if published_datetime.tzinfo is None:
                        published=''
                    else:
                        published_epoch=published_datetime.timestamp()
                except ValueError:
                    published=''
            title=clean(status.get('spoiler_text','')) or content
            status_url=status.get('url') or status.get('uri') or ''
            events.append(make_event(
                'Trump Truth Social',title,status_url,published,content,'trump',published_epoch
            ))
        return events[:30]
    except (httpx.HTTPStatusError,httpx.RequestError,ValueError,RuntimeError) as exc:
        api_error=f'Public Truth Social API unavailable: {type(exc).__name__}'
        if isinstance(exc,httpx.HTTPStatusError):
            api_error=f'Public Truth Social API returned HTTP {exc.response.status_code}'

    # Public-page HTML fallback only; never bypass login or access restrictions.
    try:
        resp=await client.get(profile_url,headers={'Accept':'text/html'})
        resp.raise_for_status()
    except (httpx.HTTPStatusError,httpx.RequestError) as exc:
        status=f'HTTP {exc.response.status_code}' if isinstance(exc,httpx.HTTPStatusError) else type(exc).__name__
        raise RuntimeError(
            f'Truth Social API/profile unavailable ({api_error}; {status}). '
            'Set TRUTHSOCIAL_RSS_URL to an authorized timestamped feed.'
        ) from exc
    soup=BeautifulSoup(resp.text,'html.parser'); events=[]
    for a in soup.find_all('a',href=True):
        href=a['href']
        if '/posts/' not in href: continue
        txt=clean(a.get_text(' ',strip=True))
        if not txt: continue
        events.append(make_event('Trump Truth Social',txt,urljoin(profile_url,href),'',txt,'trump',None))
    if not events:
        raise RuntimeError(
            f'{api_error}; no public post links found. '
            'Set TRUTHSOCIAL_RSS_URL to an authorized timestamped feed.'
        )
    return events[:30]
