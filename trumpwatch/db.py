import sqlite3, time
import hashlib
import re
import unicodedata
from contextlib import contextmanager
from pathlib import Path

class DB:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.path=path
        with self.conn() as c:
            c.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT, published TEXT, content TEXT, category TEXT, score INTEGER, created REAL, published_epoch REAL)')
            # Migrate existing DBs created by v1/v2.
            cols={row[1] for row in c.execute('PRAGMA table_info(events)').fetchall()}
            if 'published_epoch' not in cols:
                c.execute('ALTER TABLE events ADD COLUMN published_epoch REAL')
            c.execute('CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 1, joined REAL)')
            c.execute('CREATE TABLE IF NOT EXISTS source_health (source TEXT PRIMARY KEY, last_ok REAL, last_error TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS scheduled_events (id TEXT PRIMARY KEY, title TEXT, event_time REAL, source TEXT, url TEXT, importance INTEGER, reminder4 INTEGER DEFAULT 0, reminder1 INTEGER DEFAULT 0, event_alert INTEGER DEFAULT 0, content TEXT NOT NULL DEFAULT \'\')')
            schedule_cols={row[1] for row in c.execute('PRAGMA table_info(scheduled_events)').fetchall()}
            if 'content' not in schedule_cols:
                c.execute("ALTER TABLE scheduled_events ADD COLUMN content TEXT NOT NULL DEFAULT ''")
            c.execute('CREATE TABLE IF NOT EXISTS alerted_titles (title_key TEXT PRIMARY KEY, last_alerted REAL NOT NULL)')
    @contextmanager
    def conn(self):
        connection=sqlite3.connect(self.path,timeout=30)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    def seen(self,event_id):
        with self.conn() as c: return c.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone() is not None
    def add(self,e):
        with self.conn() as c:
            c.execute('INSERT OR IGNORE INTO events(id,source,title,url,published,content,category,score,created,published_epoch) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (e['id'],e['source'],e['title'],e['url'],e['published'],e['content'],e['category'],e['score'],time.time(),e.get('published_epoch')))
            return c.execute('SELECT changes()').fetchone()[0]==1
    def claim_news_alert(self,title,cooldown_seconds=86400):
        normalized=unicodedata.normalize('NFKC',title).casefold()
        normalized=re.sub(r'[\W_]+',' ',normalized,flags=re.UNICODE).strip()
        if not normalized:
            return False
        title_key=hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        now=time.time()
        with self.conn() as c:
            c.execute('DELETE FROM alerted_titles WHERE last_alerted <= ?',(now-cooldown_seconds,))
            cursor=c.execute(
                'INSERT INTO alerted_titles(title_key,last_alerted) VALUES(?,?) '
                'ON CONFLICT(title_key) DO UPDATE SET last_alerted=excluded.last_alerted '
                'WHERE alerted_titles.last_alerted <= ?',
                (title_key,now,now-cooldown_seconds),
            )
            return cursor.rowcount==1
    def latest(self,n=10,since_epoch=None,category=None):
        q='SELECT source,title,url,published,category,score,created FROM events'
        where=[]; args=[]
        if since_epoch is not None:
            # Filter by source publication time, never ingestion time. Undated posts are
            # excluded from "fresh" lists to prevent historic backfill masquerading as new.
            where.append('published_epoch>=?'); args.append(since_epoch)
        if category:
            where.append('category=?'); args.append(category)
        if where: q+=' WHERE '+' AND '.join(where)
        q+=' ORDER BY published_epoch DESC LIMIT ?'; args.append(n)
        with self.conn() as c: return c.execute(q,args).fetchall()
    def latest_event(self):
        with self.conn() as c:
            return c.execute(
                'SELECT source,title,url,published,content,category,score,published_epoch '
                'FROM events WHERE published_epoch IS NOT NULL '
                'ORDER BY published_epoch DESC LIMIT 1'
            ).fetchone()
    def add_user(self,chat):
        with self.conn() as c: c.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',(chat,1,time.time()))
    def users(self):
        with self.conn() as c: return [x[0] for x in c.execute('SELECT chat_id FROM users WHERE enabled=1')]
    def pause(self,chat):
        with self.conn() as c: c.execute('UPDATE users SET enabled=0 WHERE chat_id=?',(chat,))
    def resume(self,chat):
        with self.conn() as c: c.execute('INSERT INTO users(chat_id,enabled,joined) VALUES(?,?,?) ON CONFLICT(chat_id) DO UPDATE SET enabled=1',(chat,1,time.time()))
    def health(self,source,error=None):
        with self.conn() as c: c.execute('INSERT OR REPLACE INTO source_health VALUES(?,?,?)',(source,time.time() if not error else None,str(error)[:400] if error else None))
    def health_rows(self):
        with self.conn() as c: return c.execute('SELECT source,last_ok,last_error FROM source_health ORDER BY source').fetchall()
    def initialized(self,name):
        with self.conn() as c: return c.execute('SELECT value FROM kv WHERE key=?',('init:'+name,)).fetchone() is not None
    def mark_initialized(self,name):
        with self.conn() as c: c.execute('INSERT OR IGNORE INTO kv VALUES(?,?)',('init:'+name,'1'))
    def upsert_schedule(self,ev):
        with self.conn() as c:
            c.execute('INSERT INTO scheduled_events(id,title,event_time,source,url,importance,content) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,event_time=excluded.event_time,source=excluded.source,url=excluded.url,importance=excluded.importance,content=excluded.content',
            (ev['id'],ev['title'],ev['event_time'],ev['source'],ev['url'],ev['importance'],ev.get('content','')))
    def upcoming(self,now,limit=15):
        with self.conn() as c:
            return c.execute(
                "SELECT id,title,event_time,source,url,importance FROM scheduled_events "
                "WHERE event_time>? AND (substr(upper(title),1,4)='USD:' "
                "OR source IN ('BLS official schedule','Federal Reserve official FOMC calendar')) "
                "ORDER BY event_time LIMIT ?",
                (now,limit),
            ).fetchall()
    def next_scheduled_event(self,now):
        with self.conn() as c:
            return c.execute(
                'SELECT title,event_time,source,url,importance,content '
                "FROM scheduled_events WHERE event_time>? AND (substr(upper(title),1,4)='USD:' "
                "OR source IN ('BLS official schedule','Federal Reserve official FOMC calendar')) "
                'ORDER BY event_time LIMIT 1',
                (now,),
            ).fetchone()
    def reminder_candidates(self,now):
        with self.conn() as c:
            return c.execute(
                "SELECT id,title,event_time,source,url,importance,reminder4,reminder1,event_alert "
                "FROM scheduled_events WHERE event_time>? AND event_time<? "
                "AND (substr(upper(title),1,4)='USD:' "
                "OR source IN ('BLS official schedule','Federal Reserve official FOMC calendar')) "
                "ORDER BY event_time",
                (now-60,now+4*3600+60),
            ).fetchall()
    def mark_reminder(self,event_id,kind):
        field={'4':'reminder4','1':'reminder1','event':'event_alert'}[kind]
        with self.conn() as c: c.execute(f'UPDATE scheduled_events SET {field}=1 WHERE id=?',(event_id,))
